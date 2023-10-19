import statistics
import argparse
import logging
import sqlite3
import re
import collections
import pickle
import pytesseract
import glob
import csv
import math
import numpy as np
import pandas as pd
from termcolor import colored
from pathlib import Path
from hashlib import md5
from pytesseract import Output
from pprint import pprint
from word_list_match import WordListMatch

class SeedlistImageParser:

    name_abbr=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
               'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
               'var.', 'convar.', ]

    def __init__(self, 
                 name_database,
                 force_ocr=False,
                 pickle_folder="./pickles",
                 **kwargs
                 ) -> None:

        self.files=[]
        self.include_pages=None
        self.output_file=None

        self.pickle_folder=Path(pickle_folder)
        self.pickle_folder.mkdir(exist_ok=True)
        self.force_ocr=force_ocr
        self.block_counter=0
        self.word_list_matcher=None

        """
        The IPEN number consists of four elements:

        - Country of origin (two positions, abbreviation according to ISO 3166-1-alpha-2, “XX” for unknown origin)
        - Restrictions of transfer (one position, “1” if there exists a restriction; “0” if none).
        - The unique Garden code of the institution offering the plant material for exchange, (to be found on the BGCI Website under “GardenSearch”).
        - Identification Number (the specific accession number of the plant material in the recording system of the garden)

        https://www.bgci.org/our-work/inspiring-and-leading-people/policy-and-advocacy/access-and-benefit-sharing/the-international-plant-exchange-network/#ipen-documentation-system

        IPEN regex has to deal with common OCR errors: I might have become |l, O might have become 0 etc.
        Note that extract_ipen() first takes out all spaces (which OCR might have introduced) before matching the regex.
        """

        self.config={
            'species_match_threshold': 0.5,
            'concatenate_lists': True,
            're_evaluate_metadata': True,
            'use_word_list': False,
            'regex_ipen':r'([A-Z|l0]{2})([—\-\.]{1})([0O1lI|]{1})([—\-\.]{1})([A-Za-z|l0]{1,5})([—\-\.]{1})([A-Za-z0-9/—\-|]*)',
            'debug_print_ocr_data': False,
            'debug_print_name_resolvement': False,
            'debug_print_annotated_data': False,
            'debug_print_annotated_data_length': 20,
            'debug_colored_stdout': False
            }

        if 'config' in kwargs:
            self.set_config(kwargs['config'])

        db = Path(name_database)
        if not db.exists():
            raise ValueError("database %s does not exist" % name_database)

        self.conn=self.connect_db(name_database)
        logging.debug("connected to '%s'" % name_database)


    def set_word_list_matcher(self, path):
        if not self.config['use_word_list']:
            return

        word_list_path=path / Path('wordlist.txt')
        if not word_list_path.exists():
            return
        self.word_list_matcher=WordListMatch(
            db_conn=self.conn, 
            word_list_path=word_list_path)

    def get_word_list_match(self, word):
        if self.word_list_matcher:
            self.word_list_matcher.get_matches(word=word, top=3)

    def set_include_pages(self, pages):
        if pages:
            if pages.isnumeric():
                self.include_pages=[int(pages)]
            elif len(pages.split('-'))==2:
                self.include_pages=list(range(int(pages.split('-')[0]), int(pages.split('-')[1])+1))    
            elif len(pages.split(','))>1:
                self.include_pages=list(map(int, pages.split(','))) 
            else:
                raise ValueError('Wrong pages format')
            
            if len(self.include_pages)==0:
                logging.warn("pages setting '%s' results in 0 pages" % pages)
            else:
                logging.info("only processing pages %s" % pages)

    def set_output_file(self, output_file):
        if output_file:
            self.output_file=Path(output_file).resolve()
            self.output_file.parent.mkdir(parents=True, exist_ok=True)

    def set_config(self, config):
        self.config = self.config | config


    @staticmethod
    def get_files(path, image_extension='png'):
        files=[]
        p = Path(path)
        if p.is_dir():
            files=list(p.glob(f"**/*.{image_extension}"))
        elif p.is_file():
            files.append(p)

        files.sort()
        return files


    @staticmethod
    def connect_db(db_file):
        conn=None
        try:
            conn=sqlite3.connect(db_file)
            conn.row_factory=sqlite3.Row
        except Exception as e:
            print(e)

        return conn


    def load_pickle(self, file, label):
        try:
            f_hash=md5(str(file).encode('utf-8')).hexdigest()
            p = Path(self.pickle_folder / f"{f_hash}-{label}")
            with open(p, 'rb') as file:
                data=pickle.load(file)
            return data
        except:
            pass

    def save_pickle(self, file, label, data):
        f_hash=md5(str(file).encode('utf-8')).hexdigest()
        p = Path(self.pickle_folder / f"{f_hash}-{label}")
        with open(p, 'wb') as file:
            pickle.dump(data, file)


    def get_ocr_data(self):
        pages=[]
        for key, file in enumerate(self.files):

            if self.include_pages and key not in self.include_pages:
                continue

            ocr_data=None
            if not self.force_ocr:
                ocr_data=self.load_pickle(file, "ocr")
            
            if ocr_data is None:

                # better single digit numbers by resizing, but overall drop in recognition
                # image=cv2.imread(str(file))
                # resize_factor=2
                # height, width, _=image.shape
                # image=cv2.resize(image, (height*resize_factor, width*resize_factor), interpolation=cv2.INTER_CUBIC)

                ocr_data=pytesseract.image_to_data(
                        str(file),
                        output_type=Output.DATAFRAME,
                        config=r'--psm 12')

                logging.debug("OCR'd '%s'" % str(file))
                self.save_pickle(file, "ocr", ocr_data)

            pages.append({
                'key': key,
                'page': file.name,
                'page_nr': int(''.join([x for x in file.name if x.isnumeric()])),
                'data': ocr_data})

        return pages

    def preprocess_ocr_data(self, ocr_data):
        # remove rows with empty text cells
        ocr_data=ocr_data[~ocr_data.text.isna()]

        if len(ocr_data)==0:
            return pd.DataFrame()

        # group by block, concat grouped text, take mean of OCR confidence
        ocr_data=(ocr_data
            .groupby('block_num')
            .apply(
                lambda group: pd.Series(
                    [
                        group["left"].min(),
                        group["top"].min(),
                        group["width"].max(),
                        group["height"].max(),
                        group["conf"].mean(),
                        group["text"].astype(str).str.cat(sep=" "),
                    ]
                )
            )
            .reset_index(drop=True)
            .reset_index()
            .rename(
                columns={
                    0: "x_1",
                    1: "y_1",
                    2: "width",
                    3: "height",
                    4: "mean_conf",
                    5: "text",
                    "index": "id",
                }
            )
            .assign(
                x_2=lambda x: x.x_1 + x.width,
                y_2=lambda x: x.y_1 + x.height,
                page_nr=None,
                list_index=None,
                species_match=None,
                epithet_match=None,
                genus_match=None,
                family_match=None,
                ipen=None,
            ))

        ocr_data.insert(0, 'gid', range(self.block_counter, self.block_counter+len(ocr_data)))
        self.block_counter+=len(ocr_data)

        if self.config['debug_print_ocr_data']:
            print(ocr_data)
            # exit()

        return ocr_data

    def get_record(self, gid):
        for x in self.page_frames:
            if len(x['data'])==0:
                continue

            q=x['data'][x['data']['gid']==gid]
            if len(q)>0:
                return q.iloc[0]            

        return

    def clean_up_name(self,
                           text, 
                           remove_abbreviations=False, 
                           relics=[],
                           return_tokens=False,
                           return_removed=False):
        clean=text
        if isinstance(clean, list):
            clean=" ".join(clean)

        # remove entire substrings (matched index, IPEN) that might
        # be in the same cell as the name
        for relic in relics:
            clean=clean.replace(str(relic), '')

        test=clean

        # That *really* aren't plants.
        clean=re.sub('Index Seminum', '', clean, re.IGNORECASE)
        clean=re.sub('Desiderata', '', clean, re.IGNORECASE)
        # OCR will often see × as x
        clean=re.sub(' x ', ' ', clean)
        # Remove brackets containing one character at the start of text, like '(*)'
        clean=re.sub(r'^\([^\)]{1}\) ', '', clean)
        # Keep only letters, brackets and some characters
        clean=re.sub(r'[^A-Za-z().&,\- ]', '', clean)
        # Remove 'empty' pairs of brackets 
        clean=re.sub(r'\(\)', '', clean)
        # Remove any non letter(s) at the start
        clean=re.sub(r'^[^A-Za-z]*', '', clean)

        # Remove abbreviated taxonomic codes, like 'ssp.' 
        if remove_abbreviations:
            self.name_abbr.sort(key=lambda x: -len(x))
            for abbr in self.name_abbr:
                clean=clean.replace(abbr, '')

        # Multiple spaces to single space
        clean=re.sub(r'\s{1,}', ' ', clean)

        # print(f"{text} --> {clean.strip()}")

        for token in clean.strip():
            test=test.replace(token, '')

        # Optionally split the result into tokens
        if return_tokens:
            result=re.findall(r'\b([A-Za-z]+)\b', clean.strip(), flags=0)
        else:
            result=clean.strip()

        if return_removed:
            return result, test.strip()
        
        return result
            
        

    def get_genera_by_epithet(self, text, remove_abbreviations=False):
        alpha_tokens=self.clean_up_name(text=text, return_tokens=True, remove_abbreviations=remove_abbreviations)
        if len(alpha_tokens)==0 or not alpha_tokens[0].islower():
            return []

        cur=self.conn.cursor()
        query=(f"select genus from name_lookup where epithet match 'epithet:{alpha_tokens[0]}'")
        cur.execute(query)
        names=[]
        for row in cur.fetchall():
            names.append(row['genus'])

        return list(set(names))
  
    def get_species_match(self, text):

        # note that this only matches species names at the start of the text block!

        alpha_tokens=self.clean_up_name(text=text, remove_abbreviations=True, return_tokens=True)
        alpha_tokens=[x.lower() for x in alpha_tokens if len(x)>2]

        if len(alpha_tokens)==0:
            return 0

        base_query = """select count(*) as total from name_lookup
                    where scientificName match '\"{match_condition}\"'
                    or full_scientific_name  match '\"{match_condition}\"'
                    and taxonrank in ('variety', 'species', 'subspecies', 'subvariety', 'subform', 'prole')
                    limit 1"""

        cur=self.conn.cursor()

        for i in range(min(4, len(alpha_tokens)), 1, -1):
            match_condition=' '.join(alpha_tokens[:i])
            query=base_query.format(match_condition=match_condition)
            cur.execute(query)
            row=cur.fetchone()
            if row['total']>0:
                penalty=(len(alpha_tokens)-i)*0.01
                if self.config['debug_print_name_resolvement']:
                    print(f"{1-penalty:>5}: {' '.join(alpha_tokens)} <-- {match_condition}")
                return 1-penalty

        if self.config['debug_print_name_resolvement']:
            print(f"{0:>5}: {' '.join(alpha_tokens)}")
    
        return 0
            
    def get_ht_match(self, column, ranks, text, max_tokens=None):
        alpha_tokens=self.clean_up_name(text=text, return_tokens=True)

        if len(alpha_tokens)==0:
            return 0

        if max_tokens and len(alpha_tokens)>max_tokens:
            return 0

        cur=self.conn.cursor()
        ranks="','".join(ranks)
        query=f"select count(*) as total from name_lookup where {column} match '\"{alpha_tokens[0].lower()}\"' \
                and taxonrank in ('{ranks}') \
                limit 1"
        cur.execute(query)
        row=cur.fetchone()
        return 1 if row['total']>0 else 0

    def get_genus_match(self, text, max_tokens=None):
        return self.get_ht_match(column='genus', ranks=['genus', 'subgenus'], text=text, max_tokens=max_tokens)

    def get_family_match(self, text, max_tokens=None):
        return self.get_ht_match(column='family', ranks=['family', 'subfamily'], text=text, max_tokens=max_tokens)

    def get_repeated_epithet_match(self, text):
        epithet=None
        candidate_genera=[]

        tokens=self.clean_up_name(text=text, remove_abbreviations=True, return_tokens=True)

        if len(tokens)==0:
            return 0
        
        if tokens[0].islower():
            epithet=tokens[0]
        elif tokens[0] in ['-', '—'] and len(tokens)>1:
            epithet=tokens[1]

        if epithet:
            candidate_genera=self.get_genera_by_epithet(epithet)

        return 1 if len(candidate_genera)>0 else 0


    def annotate_page(self, page):
        page_nr=int(''.join([x for x in page['page'] if x.isnumeric()]))
        for index, row in page['data'].iterrows():
            page['data'].at[index, 'page_nr']=page_nr
            page['data'].at[index, 'species_match']=self.get_species_match(row['text'])
            # genus_match only matches texts that isolated genera
            page['data'].at[index, 'genus_match']=self.get_genus_match(row['text'], max_tokens=1)
            page['data'].at[index, 'family_match']=self.get_family_match(row['text'])
            # epithet_match matches isolated epithets preceded by a -
            page['data'].at[index, 'epithet_match']=self.get_repeated_epithet_match(row['text'])
            page['data'].at[index, 'list_index']=self.extract_list_index(row['text'])
            page['data'].at[index, 'ipen']=self.extract_ipen(row['text'])

            # p=page['data'].iloc[index]
            # if all(v is None for v in [p['list_index'], p['ipen']]) \
            #     and sum([p['species_match'], p['epithet_match'], p['genus_match'], p['family_match']])==0 \
            #     and len(row['text'].split())==1:
            #     candidates=self.get_word_list_match(row['text'])
            #     if candidates and [0][1]>0.75:
            #         print(row['text'], candidates)

        if self.config['debug_print_annotated_data']:
            print(page['page'])
            print(page['data'][:self.config['debug_print_annotated_data_length']])
            # exit()


    @staticmethod
    def extract_list_index(text):
        match=re.findall(r'([0-9]{1,5})[.)°\s]?', text.strip())
        if match and len(match)==1:
            return int(match[0])

    def extract_ipen(self, text):
        match=re.search(self.config['regex_ipen'], text.strip().replace(' ',''), re.UNICODE)
        if match:
            return match.group(0).strip()

    @staticmethod
    def get_neighbour(distance_function, block, df, allow_zero_distance=False):
        dist=math.inf
        nearest=None

        for row in df.itertuples():
            d=distance_function(block, row)
            if (d<dist and d!=0) or (d==0 and allow_zero_distance):
                dist=d
                nearest=row

        return nearest, dist

    def get_nearest_horizontal_neighbour(self, block, df, allow_zero_distance=False):
        def get_dist(a,b):
            return math.sqrt((getattr(a,'x_1')-getattr(b,'x_1'))**2 + ((getattr(a, 'y_2')*10)-(getattr(b,'y_2')*10))**2)
        return self.get_neighbour(get_dist, block, df, allow_zero_distance)

    def get_nearest_vertical_neighbour(self, block, df, allow_zero_distance=False):
        def get_dist(a,b):
            return math.sqrt((getattr(a,'x_1')*10-getattr(b,'x_1')*10)**2 + (getattr(a,'y_2')-getattr(b,'y_2'))**2)
        return self.get_neighbour(get_dist, block, df, allow_zero_distance)

    def get_nearest_neighbour(self, block, df, allow_zero_distance=False):
        def get_dist(a,b):
            return math.sqrt((getattr(a,'x_1')-getattr(b,'x_1'))**2 + (getattr(a,'y_2')-getattr(b,'y_2'))**2)
        return self.get_neighbour(get_dist, block, df, allow_zero_distance)

    def collect_species_list(self, page):

        def get_y2_list(data):
            return sorted(collections.Counter([round(getattr(x,'y_2')/20)*20 for x in data]).items(), key=lambda x: x[0])

        def link_nearest_record(names, attributes, attribute_name, self_check_column=None):
            if len(attributes)==0:
                return names

            # names also contains rows that are family names, which won't get attributes, so we want to leave them out here
            names_y2s=get_y2_list([x for x in names if x['species_match']>0 or x['epithet_match']>0])
            attrib_y2s=get_y2_list([row for row in attributes.itertuples()])

            # y2s_match is fraction of all the rows with the attribute under consideration that are on the
            # same line as rows that contain the names we're annotating. It is used to decide if the nearest
            # neighbour function should look (more) horizontally or vertically for the nearest attribute.
            matches=0
            for item in attrib_y2s:
                matches+=1 if len([x for x in names_y2s if x[0]==item[0]])>0 else 0

            y2s_match=matches/len(attrib_y2s)

            if self_check_column is not None:
                # blocks that have both name and IPEN: assuming name and IPEN belong together
                for name in [x for x in names if x[self_check_column] is not None]:
                    # skip families (if any)
                    if name['species_match']>0 or name['epithet_match']>0:
                        name[attribute_name]=(name['gid'], 0)
                        attributes=attributes.drop(name['id'])

            if len(attributes)==0:
                return names

            for name in names:
                # these already have the attribute added (via 'self_check_column')
                if attribute_name in name:
                    continue
                
                # families
                if name['species_match']==0 and name['epithet_match']==0:
                    continue

                if y2s_match>0.66:
                    nearest, dist=self.get_nearest_horizontal_neighbour(block=name, df=attributes)
                elif y2s_match<0.33:
                    nearest, dist=self.get_nearest_vertical_neighbour(block=name, df=attributes)
                else:
                    nearest, dist=self.get_nearest_neighbour(block=name, df=attributes)

                name[attribute_name]=(getattr(nearest,'gid'), dist)

            remove_duplicates=True

            # remove duplicates (keep closest one)
            if remove_duplicates:
                for name in names:
                    if attribute_name in name:
                        p=[x for x in names if attribute_name in x and x[attribute_name][0]==name[attribute_name][0]]
                        if len(p)>1:
                            for item in sorted(p, key=lambda d: d[attribute_name][1])[1:]:
                                del item[attribute_name]
            
            return names

        if len(page['data'])==0:
            return []

        names=[]
        df=page['data'][(page['data'].species_match>=self.config['species_match_threshold']) |
                        (page['data'].genus_match>0) | 
                        (page['data'].epithet_match>0) | 
                        (page['data'].family_match>0)].sort_values(by=['y_1', 'x_1'], ascending=True)
        names=[row for _, row in df.iterrows()]

        # records with IPEN
        df=page['data'][~page['data'].ipen.isna()]
        names=link_nearest_record(names=names, attributes=df, attribute_name='ipen_record', self_check_column='ipen')

        # records with list index
        df=page['data'][~page['data'].list_index.isna()]
        names=link_nearest_record(names=names, attributes=df, attribute_name='list_index_record', self_check_column='list_index')

        return names


    @staticmethod
    def concatenate_lists(names_lists):
        results=[]
        joined_list=[]
        prev_page=-1
        for names_list in names_lists:
            page_n=int(''.join([x for x in names_list['page'] if x.isnumeric()]))
            if prev_page>-1 and page_n-prev_page>1:
                joined_list=sorted(joined_list, key=lambda x: (x['page_nr'], x['y_2']))
                results.append(joined_list)
                joined_list=[]
            joined_list+=names_list['list']
            prev_page=page_n

        if len(joined_list)>0:
            results.append(joined_list)

        return results

    def fix_list_numbers(self, names_list):

        def get_outliers(data):
            # Tukey’s Fences
            data=np.array(data)

            if len(data)==0:
                return []

            q1=np.percentile(data, 25)
            q3=np.percentile(data, 75)
            iqr=q3-q1
            lower_fence=q1-1.5*iqr
            upper_fence=q3+1.5*iqr
            outliers=np.where((data<lower_fence) | (data>upper_fence))

            return set(list(data[outliers]))

        if len(names_list)==0:
            return names_list

        # make a list of all index numbers
        indexes=[]      
        for name in [x for x in names_list if 'list_index_record' in x]:
            p=self.get_record(gid=name['list_index_record'][0])
            indexes.append(p['list_index'])

        # determine the outliers
        outliers=get_outliers(indexes)

        # copy referenced list indexes that are not outliers to name
        for name in [x for x in names_list if 'list_index_record' in x]:
            p=self.get_record(gid=name['list_index_record'][0])
            if p['list_index'] not in outliers:
                name['corrected_list_index']=p['list_index']

        # get all duplicate list index numbers
        for duplicate_index in [x[0] for x in collections.Counter(indexes).most_common() if x[1]>1]:
            diffs=[]

            # find all items with current duplicate number
            for duplicate_record in [x for x in names_list if 'corrected_list_index' in x and x['corrected_list_index']==duplicate_index]:
                d=[]

                # get items directly preceding the duplicate
                prev=sorted([x for x in names_list 
                    if x['y_2']<duplicate_record['y_2'] 
                    and x['page_nr']<=duplicate_record['page_nr']
                    and 'corrected_list_index' in x], key=lambda x: (-x['page_nr'], -x['y_2'], x['x_1']))
                
                # if it has a index list number, store the difference with the current one
                # if it's in sequence, the difference should be 1 (or small - possibly some
                # list index numbers have been not or wrongly OCR'd)
                if len(prev)>0:
                    d.append(abs(prev[0]['corrected_list_index']-duplicate_record['corrected_list_index']))

                # same for the following item
                foll=sorted([x for x in names_list 
                    if x['y_2']>duplicate_record['y_2'] 
                    and x['page_nr']>=duplicate_record['page_nr']
                    and 'corrected_list_index' in x], key=lambda x: (x['page_nr'], x['y_2'], x['x_1']))

                if len(foll)>0:
                    d.append(abs(foll[0]['corrected_list_index']-duplicate_record['corrected_list_index']))

                diffs.append((duplicate_record['gid'], math.inf if len(d)==0 else statistics.mean(d)))

            # remove duplicate index numbers from the records with the biggest difference
            for i in sorted(diffs, key=lambda x: x[1])[1:]:
                name=[x for x in names_list if x['gid']==i[0]][0]
                del name['corrected_list_index']

        # if only 10% of the lines actually has an index number, we assume they're not actually list indexes
        if len([x for x in names_list if 'corrected_list_index' in x])/len(names_list)<0.1:
            for name in [x for x in names_list if 'corrected_list_index' in x]:
                del name['corrected_list_index']

        return names_list

    def fix_ipen(self, names_list):
        if len(names_list)==0:
            return names_list

        # copy referenced IPEN
        for name in [x for x in names_list if 'ipen_record' in x]:
            p=self.get_record(gid=name['ipen_record'][0])
            name['corrected_ipen']=p['ipen']
    
        return names_list

    
    def remove_starting_non_list_lines(self, names_list):
        has_families=len([x for x in names_list if x['family_match']>0 and len(x['text'].split())==1])>0
        has_indexes=len([x for x in names_list if 'corrected_list_index' in x])>0

        rec=False
        cleaned_list=[]
        for key, name in enumerate(names_list):
            if not rec:
                if has_families and name['family_match']>0 and len(name['text'].split())==1:
                    rec=True
                elif name['genus_match']==1:
                    rec=(len(names_list)>=key+2) and (names_list[key+1]['epithet_match'])
                elif has_indexes and 'corrected_list_index' in name:
                    rec=True
                else:
                    # we assume a list doesn't start wth just an epithet
                    rec=name['species_match']==1

            if rec:
                cleaned_list.append(name)

        return cleaned_list

    def clean_up_names(self, names_list):
        for name in [x for x in names_list]:
            name['corrected_plantname'], name['plantname_removed']=self.clean_up_name(
                name['text'], 
                relics=[name['list_index'], name['ipen']],
                return_removed=True)

        return names_list

    def complement_repeated_epithets(self, names_list):
        genus=()
        for _, name in enumerate([x for x in names_list]):
            if name['genus_match']==1:
                genus=(name['text'], name['corrected_plantname'])

            elif name['epithet_match'] and len(genus)>0:
                matching_genera=self.get_genera_by_epithet(name['corrected_plantname'], remove_abbreviations=True)

                if genus[0].lower() in matching_genera:
                    name['corrected_plantname']=self.clean_up_name(f"{genus[0]} {name['corrected_plantname']}")

                elif genus[1].lower() in matching_genera:
                    name['corrected_plantname']=self.clean_up_name(f"{genus[1]} {name['corrected_plantname']}")

        return names_list

    def get_next_lines(self, record, next_record):

        # TODO: where to stop, if we're at the last item (and next_record is none)?
        # currently, on the bottom of the same page as the curent item

        data=[]
        last_page=record['page_nr'] if next_record is None else next_record['page_nr']

        for i in range(0, (last_page-record['page_nr']+1)):
            
            y_top=record['y_2'] if i==0 else 0

            if next_record is not None and next_record['page_nr']==(record['page_nr']+i):
                y_bottom=next_record['y_1']
            else:
                y_bottom=math.inf

            df=[x['data'] for x in self.page_frames if x['page_nr']==(record['page_nr']+i)][0]
            df=df[((df.y_1<y_bottom) & (df.y_1>y_top)) | ((df.y_2==y_bottom) & (df.x_1>record['x_2']))]
            df=df[(df.ipen.isna() & (df.species_match<self.config['species_match_threshold']) & (df.epithet_match==False) & (df.genus_match==0) & (df.family_match==False))]
            data.append(df)

        return pd.concat(data)

    def set_family(self, names_list):
        if len(names_list)==0:
            return names_list

        has_families=len([x for x in names_list if x['family_match']>0 and len(x['text'].split())==1])>0

        names=[]
        current_family=None
        for name in names_list:
            if has_families and name['family_match']>0 and len(name['text'].split())==1:
                current_family=name
            elif name['species_match']>=self.config['species_match_threshold'] or name['epithet_match']==True:
                current_name={'name': name}
                if current_family is not None:
                    current_name.update({'family': current_family})
                names.append(current_name)

        return names

    def set_metadata(self, names_list, linked_records):
        if len(names_list)==0:
            return names_list

        for key, item in enumerate(names_list):
            meta=self.get_next_lines(item['name'], names_list[key+1]['name'] if len(names_list)>key+1 else None)
            meta=meta[~meta['id'].isin(linked_records)]
            names_list[key].update({'meta': meta})

        return names_list

    def re_evaluate_metadata(self, finished_list):
        result=[]
        for item in finished_list:
            name = item['name']['corrected_plantname']
            if not item['meta'].empty:
                for index, meta in item['meta'].iterrows():
                    if meta['text'].split()[0] in self.name_abbr and meta['species_match']>0:
                        item['name']['corrected_plantname']=f"{name} {meta['text']}"
                        item['meta'].drop(index, inplace=True)

            result.append(item)
        return result


    def write_output(self, finished_lists):
        if not self.output_file:
            return

        n=0
        with open(self.output_file, 'w') as file:
            csv_writer=csv.writer(file)
            for key, list in enumerate(finished_lists):
                csv_writer.writerow([f"list #{key+1}"])
                csv_writer.writerow(["index", "name", "family", "ipen", "meta"])
                for name in list:
                    row=[]

                    if 'corrected_list_index' in name['name']:
                        row.append(name['name']['corrected_list_index'])
                    else:
                        row.append(None)

                    row.append(name['name']['corrected_plantname'])

                    if 'family' in name:
                        row.append(name['family']['corrected_plantname'])
                    else:
                        row.append(None)

                    if 'corrected_ipen' in name['name']:
                        row.append(name['name']['corrected_ipen'])
                    else:
                        row.append(None)

                    if 'meta' in name:
                        for item in name['meta'].itertuples():
                            row.append(getattr(item,'text'))
                            n+=1

                    csv_writer.writerow(row)
                csv_writer.writerow([])

        logging.info("wrote %s names to to '%s'" % (n, self.output_file))

    def display_output(self, finished_lists):
        for key, list in enumerate(finished_lists):
            rows=[["index", "family", "name", "ipen", "meta"]]
            for name in list:
                row=[]

                if 'corrected_list_index' in name['name']:
                    row.append(name['name']['corrected_list_index'])
                else:
                    row.append(None)

                if 'family' in name:
                    row.append(name['family']['corrected_plantname'])
                else:
                    row.append(None)

                row.append(name['name']['corrected_plantname'])

                if 'corrected_ipen' in name['name']:
                    row.append(name['name']['corrected_ipen'])
                else:
                    row.append(None)

                if 'meta' in name:
                    row.append("; ".join([getattr(x,'text') for x in name['meta'].itertuples()]))
                else:
                    row.append(None)

                rows.append(row)

            max_col_width=50
            max_lens={}
            max_col=max([len(row) for row in rows])
            for i in range(0, max_col):
                if i not in max_lens:
                    max_lens[i]=0

                for row in rows:
                    try:
                        max_lens[i]=len(str(row[i])) if len(str(row[i])) > max_lens[i] else max_lens[i]
                        max_lens[i]=max_col_width if max_lens[i]>max_col_width else max_lens[i]
                    except:
                        pass

            pos_colors={'color': 'white', 'on_color': 'on_black'}
            neg_colors={'color': 'black', 'on_color': 'on_light_grey'} if self.config['debug_colored_stdout'] else pos_colors
            col_buffer=4

            print(f"list #{key+1}")
            for rkey, row in enumerate(rows):         
                if rkey==1:
                    for key in max_lens:
                        print('-' * max_lens[key], end="")
                        print(' ' * col_buffer, end="")
                    print()

                for ckey, cell in enumerate(row):
                    mcell=str(cell if cell else '')
                    mcell=mcell if len(mcell)<max_col_width else mcell[:max_col_width-1]+'…'
                    
                    print(
                        colored(
                            text=f"{mcell:<{max_lens[ckey]+col_buffer}}",
                            **(pos_colors if rkey%2==0 else neg_colors)
                            ), end="")
                print()
            print()


    def process_files(self,
                      path, 
                      image_extension='png',
                      pages=None,
                      output_file=None
                      ):

        self.files=self.get_files(path=path, image_extension=image_extension)
        self.set_word_list_matcher(path=path)
        
        logging.info("got %s file(s) from '%s'" % (len(self.files), path))

        self.set_include_pages(pages=pages)
        self.set_output_file(output_file=output_file)

        if len(self.files)==0:
            return

        self.page_frames=self.get_ocr_data()
        logging.debug("acquired OCR data")

        for page in self.page_frames:
            if self.include_pages and page['key'] not in self.include_pages:
                continue
            # clean up, group by block, add annotation columns
            page.update({'data': self.preprocess_ocr_data(page['data'])})
        logging.debug("preprocessed OCR data")

        for page in self.page_frames:
            if self.include_pages and page['key'] not in self.include_pages:
                continue
            # add annotations: species/genus/family match, index, ipen
            self.annotate_page(page)
        logging.debug("annotated OCR data")

        page_lists=[]
        for page in self.page_frames:
            if self.include_pages and page['key'] not in self.include_pages:
                continue
            # create lists of species
            slist=self.collect_species_list(page)
            slist=self.remove_starting_non_list_lines(slist)
            if len(slist)>0:
                page_lists.append({'page': page['page'], 'list': slist})                
        logging.debug("extracted %s lists" % len(page_lists))

        # optionally concatenate lists (which are still divided by page at this point)
        if self.config['concatenate_lists']:
            concat_lists=self.concatenate_lists(page_lists)
            logging.debug("concatenated %s lists to %s" % (len(page_lists), len(concat_lists)))
        else:
            concat_lists=[x['list'] for x in page_lists]

        for slist in concat_lists:
            slist=self.fix_list_numbers(slist)
            slist=self.fix_ipen(slist)
            slist=self.clean_up_names(slist)
            slist=self.complement_repeated_epithets(slist)
        logging.debug("cleaned up lists")

        # collecting metadata
        linked_records=[]
        for slist in concat_lists:
            for attribute in ['list_index_record', 'ipen_record']:
                linked_records.extend([x[attribute][0] for x in slist if attribute in x])

        finished_lists=[]
        for slist in concat_lists:
            slist=self.set_family(slist)
            slist=self.set_metadata(slist, linked_records)
            if self.config['re_evaluate_metadata']:
                slist=self.re_evaluate_metadata(slist)
            finished_lists.append(slist)
        logging.debug("added metadata")

        if self.output_file:
            self.write_output(finished_lists)
        else:
            self.display_output(finished_lists)

if __name__=="__main__":

    logging.basicConfig(level=logging.DEBUG)

    parser=argparse.ArgumentParser()
    parser.add_argument('-p','--path', required=True)
    parser.add_argument('-o','--output-folder')
    parser.add_argument('-r','--recursive', action='store_true', default=False)
    parser.add_argument('-d','--name-database', default='/data/seedlists/WFO_backbone.db3')
    parser.add_argument('-i','--image-extension', default='png')
    parser.add_argument('--force-ocr', action='store_true', default=False)
    parser.add_argument('--skip-existing', action='store_true', default=False)
    parser.add_argument('--pages', help='Pages to read. Can be single integer, range (0-5), or list (1,3,5). First page is 0. Leave blank for all.')
    args=parser.parse_args()

    config={
        'debug_print_ocr_data': False,
        'debug_print_annotated_data': True,
        'debug_print_annotated_data_length': 20,
        'debug_print_name_resolvement': False,
        'debug_colored_stdout': True
        }

    parser=SeedlistImageParser(
        name_database=args.name_database,
        image_extension=args.image_extension,
        force_ocr=args.force_ocr,
        config=config)

    if args.recursive:
        for item in glob.glob(args.path):
            
            output_file=None
            if args.output_folder:
                output_file=Path(args.output_folder) / Path((Path(item).parts[-1])).with_suffix(".csv")

                if output_file.exists() and args.skip_existing:
                    logging.info("skipping '%s'" % item)
                    continue

            parser.process_files(path=item, output_file=output_file, pages=args.pages)

    else:
        output_file=None
        if args.output_folder:
            output_file=Path(args.output_folder) / Path((Path(args.path).parts[-2])).with_suffix(".csv")

        if output_file and output_file.exists and args.skip_existing:
            logging.info("skipping '%s'" % output_file)
        else:
            parser.process_files(path=args.path, output_file=output_file, pages=args.pages)

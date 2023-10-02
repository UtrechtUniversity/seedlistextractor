import math
import statistics
import argparse
import logging
import sqlite3
import re
import collections
import pickle
import pytesseract
import pandas as pd
import glob
from pathlib import Path
from hashlib import md5
from pprint import pprint
from pytesseract import Output
import numpy as np


"""
    monochrome the images
        convert page_012.jpg -monochrome page_012--monochrome.jpg
        imagemagick for python?

    extra info:
        get lines between (below) list items
        get columns to the right of list items (but not overlapping next item)
    
    index numbers  --> 
        they should be in sequence
        they should be present in most
        remove outliers
        fix missing/partial
"""

class SeedlistImageParser:

    name_abbr=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
               'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
               'var.', 'convar.', ]

    def __init__(self, 
                 path, 
                 name_database,
                 force_ocr=False,
                 pickle_folder="./pickles") -> None:
        self.files=[]
        p = Path(path)
  
        if p.is_dir():
            self.files=list(p.glob('**/*.jpg'))
        elif p.is_file():
            self.files.append(p)

        self.files.sort()
        logging.info("got %s file(s) from '%s'" % (len(self.files), p))

        self.pickle_folder=Path(pickle_folder)
        self.pickle_folder.mkdir(exist_ok=True)
        self.force_ocr=force_ocr

        db = Path(name_database)
        if not db.exists():
            raise ValueError("database %s does not exist" % name_database)

        self.conn=self.connect_db(name_database)
        logging.debug("connected to '%s'" % name_database)

        self.block_counter=0
        self.query_count=0
        self.config={'concatenate_lists': False}

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
        for file in self.files:
            ocr_data=None
            if not self.force_ocr:
                ocr_data=self.load_pickle(file, "ocr")
            
            if ocr_data is None:
                ocr_data=pytesseract.image_to_data(
                        str(file), 
                        output_type=Output.DATAFRAME,
                        config=r'--psm 12')
                        # config=r'-c tessedit_char_blacklist=| --psm 12')
                self.save_pickle(file, "ocr", ocr_data)

            pages.append({
                'page': file.name,
                'key': len(pages),
                'data': ocr_data})

        return pages

    def preprocess_ocr_data(self, ocr_data):
        # remove rows with empty text cells
        ocr_data=ocr_data[~ocr_data.text.isna()]

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
                        group["text"].str.cat(sep=" "),
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

        # for k,v in ocr_data.iterrows():
        #     print(v['text'])
        # print(ocr_data)
        # exit()

        return ocr_data

    def get_record(self, gid):
        for x in self.page_frames:
            p=[row for index, row in x['data'].iterrows() if row['gid']==gid]
            
            if len(p)==1:
                return p[0]



    def clean_up_plantname(self,
                           text, 
                           remove_abbreviations=False, 
                           relics=[],
                           return_tokens=False):
        if isinstance(text, list):
            text=" ".join(text)

        for relic in relics:
            text=text.replace(str(relic), '')

        text=re.sub('Index Seminum', '', text, re.IGNORECASE)
        
        text=re.sub(r'^\([^\)]{1}\) ', '', text)
        text=re.sub(r'[^A-Za-z().&,\- ]', '', text)
        text=re.sub(r'\(\)', '', text)
        text=re.sub(r'^[^A-Za-z]*', '', text)

        if remove_abbreviations:
            self.name_abbr.sort(key=lambda x: -len(x))
            for abbr in self.name_abbr:
                text=text.replace(abbr, '')

        text=re.sub(r'\s{1,}', ' ', text)

        if return_tokens:
            return re.findall(r'\b([A-Za-z]+)\b', text.strip(), flags=0)

        return text.strip()

    def get_genera_by_epithet(self, text, remove_abbreviations=False):
        alpha_tokens=self.clean_up_plantname(text=text, return_tokens=True, remove_abbreviations=remove_abbreviations)
        if not alpha_tokens[0].islower():
            return

        cur=self.conn.cursor()
        query=(f"select genus from name_lookup where epithet match 'epithet:{alpha_tokens[0]}'")
        cur.execute(query)
        names=[]
        for row in cur.fetchall():
            names.append(row['genus'])

        return list(set(names))
  
    def get_species_match(self, text):
        alpha_tokens=self.clean_up_plantname(text=text, return_tokens=True)
        if len(alpha_tokens)==0:
            return 0

        alpha_tokens=[x.lower() for x in alpha_tokens]
        cur=self.conn.cursor()
        match=False
        
        for i in range(0,len(alpha_tokens)-1):
            query = (f"select count(*) as total from name_lookup \
                     where scientificName match '\"{' '.join(alpha_tokens[i:i+2])}\"' \
                     and taxonrank in ('variety', 'species', 'subspecies', 'subvariety', 'subform', 'prole') \
                     limit 1")
            cur.execute(query)

            self.query_count+=1

            row=cur.fetchone()
            match=row['total']>0
            if match:
                break
        
        if match:
            return 1

        matches=0
        for token in alpha_tokens:
            query = (f"select count(*) as total from name_lookup \
                        where scientificName match '\"{token}\"' \
                        and taxonrank in ('variety', 'species', 'subspecies', 'subvariety', 'subform', 'prole') \
                        limit 1")
            cur.execute(query)
            row=cur.fetchone()
            matches+=1 if row['total']>0 else 0

        if matches/len(alpha_tokens)>1:
            raise ValueError("this shouldn't happen: get_species_match / %s" % alpha_tokens)

        return (matches/len(alpha_tokens)) * 0.5

    def get_ht_match(self, column, ranks, text, max_tokens=None):
        alpha_tokens=self.clean_up_plantname(text=text, return_tokens=True)

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

    def get_genera_for_repeated_epithets(self, text):
        if len(text)==0:
            return []

        tokens=text.split()
        if tokens[0] in ['-', '—'] and len(tokens)>1:
            candidate_genera=self.get_genera_by_epithet(
                self.clean_up_plantname(tokens[1],
                                        return_tokens=True, 
                                        remove_abbreviations=True))
            return candidate_genera
        
        return []



    @staticmethod
    def extract_list_index(text):
        match=re.findall(r'([0-9]{1,5})[.)°\s]?', text.strip())
        if match and len(match)==1:
            return int(match[0])

    @staticmethod
    def extract_ipen(text):
        # [A-Z|0]
        # [0O1l] --> OCR migt misinterpret 0 and 1 as O and l,|
        match=re.search(r'[A-Z|0]{2}([-.]{1})([0O1l|]{1})(-)([A-Z]{1,5}(-))?[A-Z0-9/-]*([A-Z]{1}){0,2}', 
            text.strip().replace(' ',''),
            re.UNICODE)
        if match:
            return match.group(0).strip()

    def annotate_page(self, page):
        page_nr=int(''.join([x for x in page['page'] if x.isnumeric()]))
        for index, row in page['data'].iterrows():
            page['data'].at[index, 'page_nr']=page_nr
            page['data'].at[index, 'species_match']=self.get_species_match(row['text'])
            # genus_match only matches texts that isolated genera
            page['data'].at[index, 'genus_match']=self.get_genus_match(row['text'], max_tokens=1)
            page['data'].at[index, 'family_match']=True if self.get_family_match(row['text']) else False
            # epithet_match matches isolated epithets preceded by a -
            page['data'].at[index, 'epithet_match']=len(self.get_genera_for_repeated_epithets(row['text']))>0
            page['data'].at[index, 'list_index']=self.extract_list_index(row['text'])
            page['data'].at[index, 'ipen']=self.extract_ipen(row['text'])
            
        # print(page['page'])
        # print(page['data'])
        # exit()

    @staticmethod
    def get_neighbour(distance_function, block, df, allow_zero_distance=False):
        dist=math.inf
        nearest=None

        for _, row in df.iterrows():
            d=distance_function(block, row)
            if (d<dist and d!=0) or (d==0 and allow_zero_distance):
                dist=d
                nearest=row

        return nearest, dist

    def get_nearest_horizontal_neighbour(self, block, df, allow_zero_distance=False):
        def get_dist(a,b):
            return math.sqrt((a['x_1']-b['x_1'])**2 + ((a['y_2']*10)-(b['y_2']*10))**2)
        return self.get_neighbour(get_dist, block, df, allow_zero_distance)

    def get_nearest_vertical_neighbour(self, block, df, allow_zero_distance=False):
        def get_dist(a,b):
            return math.sqrt((a['x_1']*10-b['x_1']*10)**2 + (a['y_2']-b['y_2'])**2)
        return self.get_neighbour(get_dist, block, df, allow_zero_distance)

    def get_nearest_neighbour(self, block, df, allow_zero_distance=False):
        def get_dist(a,b):
            return math.sqrt((a['x_1']-b['x_1'])**2 + (a['y_2']-b['y_2'])**2)
        return self.get_neighbour(get_dist, block, df, allow_zero_distance)

    def collect_species_list(self, page):

        def get_y2_list(data):
            return sorted(collections.Counter([round(x['y_2']/20)*20 for x in data]).items(), key=lambda x: x[0])

        def link_nearest_record(names, df, attribute_name, self_check_column=None):
            if len(df)==0:
                return names

            names_y2s=get_y2_list(names)
            attrib_y2s=get_y2_list([row for index, row in df.iterrows()])

            matches=0
            for item in attrib_y2s:
                matches+=1 if len([x for x in names_y2s if x[0]==item[0]])>0 else 0

            y2s_match=matches/len(attrib_y2s)

            if self_check_column is not None:
                # blocks that have both name and IPEN: assuming name and IPEN belong together
                for name in [x for x in names if x[self_check_column] is not None]:
                    name[attribute_name]=(name['gid'], 0)
                    df=df.drop(name['id'])

            if len(df)==0:
                return names

            for name in names:
                if attribute_name in name:
                    continue

                if y2s_match>0.66:
                    nearest, dist=self.get_nearest_horizontal_neighbour(block=name, df=df)
                elif y2s_match<0.33:
                    nearest, dist=self.get_nearest_vertical_neighbour(block=name, df=df)
                else:
                    nearest, dist=self.get_nearest_neighbour(block=name, df=df)

                name[attribute_name]=(nearest['gid'], dist)


            remove_duplicates=True
            # remove_duplicates=False

            # remove duplicates (keep closest one)
            if remove_duplicates:
                for name in names:
                    if attribute_name in name:
                        p=[x for x in names if attribute_name in x and x[attribute_name][0]==name[attribute_name][0]]
                        if len(p)>1:
                            for item in sorted(p, key=lambda d: d[attribute_name][1])[1:]:
                                del item[attribute_name]
            
            return names

        # print(page['page'])
        # print(page['data'])
        # collect list of all blocks identified as species names

        names=[]
        df=page['data'][(page['data'].species_match>0) | (page['data'].epithet_match>0)].sort_values(by=['y_1', 'x_1'], ascending=True)
        names=[row for index, row in df.iterrows()]

        # records with IPEN
        df=page['data'][~page['data'].ipen.isna()]
        names=link_nearest_record(names=names, df=df, attribute_name='ipen_record', self_check_column='ipen')

        # records with list index
        df=page['data'][~page['data'].list_index.isna()]
        names=link_nearest_record(names=names, df=df, attribute_name='list_index_record', self_check_column='list_index')

        return names

    def concatenate_lists(self, names_lists):
        results=[]
        joined_list=[]
        prev_page=-1
        for names_list in names_lists:
            page_n=int(''.join([x for x in names_list['page'] if x.isnumeric()]))
            if prev_page>-1 and page_n-prev_page>1:
                joined_list=sorted(joined_list, key=lambda x: (x['page'], x['y_2']))
                results.append(joined_list)
                    # pprint(joined_list)
                    # exit()
                joined_list=[]
            joined_list+=names_list['list']
            prev_page=page_n

        if len(joined_list)>0:
            results.append(joined_list)

        return results

    @staticmethod 
    def get_outliers(data):
        # Tukey’s Fences
        data=np.array(data)

        q1=np.percentile(data, 25)
        q3=np.percentile(data, 75)
        iqr=q3-q1
        lower_fence=q1-1.5*iqr
        upper_fence=q3+1.5*iqr
        outliers=np.where((data<lower_fence) | (data>upper_fence))

        return list(data[outliers])

    def fix_list_numbers(self, names_list):
        # make a list of all index numbers
        indexes=[]      
        for name in [x for x in names_list if 'list_index_record' in x]:
            p=self.get_record(gid=name['list_index_record'][0])
            indexes.append(p['list_index'])

        # determine the outliers
        outliers=self.get_outliers(indexes)

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
            for name in [x for x in names_list if 'list_index_record' in x]:
                del name['corrected_list_index']

        # for name in names_list:
        #     index=''
        #     if 'corrected_list_index' in name:
        #         index=name['corrected_list_index']
        #     print(index, name['text'])
        
        return names_list

    def clean_up_plantnames(self, names_list):
        for name in [x for x in names_list]:
            name['corrected_plantname']=self.clean_up_plantname(name['text'], relics=[name['list_index'], name['ipen']])

        return names_list

    def complement_repeated_eipthets(self, names_list):
        genus=()
        for name in [x for x in names_list]:
            if name['genus_match']:
                genus=(name['text'], name['corrected_plantname'])

            elif name['epithet_match'] and len(genus)>0:
                matching_genera=self.get_genera_by_epithet(name['corrected_plantname'], remove_abbreviations=True)
                if genus[0].lower() in matching_genera:
                    name['corrected_plantname']=self.clean_up_plantname(f"{genus[0]} {name['corrected_plantname']}")
                elif genus[1].lower() in matching_genera:
                    name['corrected_plantname']=self.clean_up_plantname(f"{genus[1]} {name['corrected_plantname']}")

        return names_list

    def read_between_the_lines(self, names_list):

        have_index=len([x for x in names_list if 'corrected_list_index' in x])>0
        print(have_index)

        # for name in [x for x in names_list]:
        #     print(name['text'])
        #     print(name['corrected_plantname'])
        #     print(name['corrected_list_index'] if 'corrected_list_index' in name else '-')
        #     print('-' * 50)





    def remove_non_list_lines(self, names_list):
        # print(len(names_list))
        # for name in names_list:
        #     print(name)
        # exit()


        return names_list



    def process_files(self):

        if len(self.files)==0:
            return

        self.page_frames=self.get_ocr_data()

        for page in self.page_frames:
            # clean up, group by block, add annotation columns
            page.update({'data': self.preprocess_ocr_data(page['data'])})

        for page in self.page_frames:
            self.annotate_page(page)

        names_lists=[]

        for page in self.page_frames:
            list=self.collect_species_list(page)
            if len(list)>0:
                names_lists.append({'page': page['page'], 'list': list})

        if self.config['concatenate_lists']:
            concat_lists=self.concatenate_lists(names_lists)
        else:
            concat_lists=[x['list'] for x in names_lists]

        for concat_list in concat_lists:
            concat_list=self.remove_non_list_lines(concat_list)
            concat_list=self.fix_list_numbers(concat_list)
            concat_list=self.clean_up_plantnames(concat_list)
            concat_list=self.complement_repeated_eipthets(concat_list)
            concat_list=self.read_between_the_lines(concat_list)

        # for list in concat_list:
        #     for key, item in list.items():
        #         if key=='corrected_plantname':
        #             print(item)

        # print(self.query_count)


if __name__=="__main__":

    logging.basicConfig(level=logging.DEBUG)

    parser=argparse.ArgumentParser()
    parser.add_argument('-p','--path', required=True)
    parser.add_argument('-r','--recursive', action='store_true', default=False)
    parser.add_argument('-d','--name-database', default='/data/seedlists/WFO_backbone.db3')
    parser.add_argument('-f','--force-ocr', action='store_true', default=False)
    args=parser.parse_args()

    if args.recursive:
        for item in glob.glob(args.path):
            parser=SeedlistImageParser(
                path=item, 
                name_database=args.name_database,
                force_ocr=args.force_ocr)
            parser.process_files()

    else:
        parser=SeedlistImageParser(
            path=args.path, 
            name_database=args.name_database,
            force_ocr=args.force_ocr)       
        parser.process_files()

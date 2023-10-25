import argparse
import logging
import sqlite3
import re
import collections
import glob
import math
import numpy as np
import pandas as pd
from pathlib import Path
from name_matching import NameMatching
from ocr import OCR
from output import Output
# from word_list_match import WordListMatch

class SeedlistImageParser:

    def __init__(self, 
                 name_database,
                 **kwargs
                 ) -> None:

        """
        The IPEN number consists of four elements:

        - Country of origin (two positions, abbreviation according to ISO 3166-1-alpha-2, “XX” for unknown origin)
        - Restrictions of transfer (one position, “1” if there exists a restriction; “0” if none).
        - The unique Garden code of the institution offering the plant material for exchange, (to be found on the BGCI Website under “GardenSearch”).
        - Identification Number (the specific accession number of the plant material in the recording system of the garden)

        https://www.bgci.org/our-work/inspiring-and-leading-people/policy-and-advocacy/access-and-benefit-sharing/the-international-plant-exchange-network/#ipen-documentation-system

        IPEN regex has to deal with common OCR errors: I --> | or l, O --> 0 etc.
        """

        self.config={
            'pickle_folder': "./pickles",
            'species_match_threshold': 0.75,
            'concatenate_lists': True,
            'use_word_list': False,
            'regex_ipen':r'([A-Z|l0]{2})([—\-\. ]{1})([0O1lI|]{1})([—\-\. ]{1})([A-Za-z|l0]{1,5})([—\-\. ]{1})([^\s]*)',
            'debug_print_ocr_data': False,
            'debug_print_name_resolvement': False,
            'debug_print_annotated_data': False,
            'debug_print_annotated_data_length': 20,
            'debug_colored_stdout': False
            }

        if 'config' in kwargs:
            self.config=self.config | kwargs['config']

        db = Path(name_database)
        if not db.exists():
            raise ValueError("database %s does not exist" % name_database)

        self.conn=self.connect_db(name_database)
        self.name_matching=NameMatching(config=self.config, db_conn=self.conn)
        self.ocr=OCR(config=self.config)
        self.output=Output(config=self.config)

    # def set_word_list_matcher(self, path):
    #     if not self.config['use_word_list']:
    #         return

    #     word_list_path=path / Path('wordlist.txt')
    #     if not word_list_path.exists():
    #         return
    #     self.word_list_matcher=WordListMatch(
    #         db_conn=self.conn, 
    #         word_list_path=word_list_path)

    # def get_word_list_match(self, word):
    #     if self.word_list_matcher:
    #         self.word_list_matcher.get_matches(word=word, top=3)

    @staticmethod
    def get_include_pages(pages):
        include_pages=None
        if pages:
            if pages.isnumeric():
                include_pages=[int(pages)]
            elif len(pages.split('-'))==2:
                include_pages=list(range(int(pages.split('-')[0]), int(pages.split('-')[1])+1))    
            elif len(pages.split(','))>1:
                include_pages=list(map(int, pages.split(','))) 
            else:
                raise ValueError('Wrong pages format')
            
            if len(include_pages)==0:
                logging.warn("pages setting '%s' results in 0 pages" % pages)
            else:
                logging.info("only processing page(s) %s" % pages)

        return include_pages

    @staticmethod
    def get_output_path(output_file):
        if output_file:
            output_path=Path(output_file).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            return output_path

    @staticmethod
    def connect_db(db_file):
        conn=None
        try:
            conn=sqlite3.connect(db_file)
            conn.row_factory=sqlite3.Row
        except Exception as e:
            print(e)

        return conn

    @staticmethod
    def get_file_list(path, image_extension='png'):
        files=[]
        p = Path(path)
        if p.is_dir():
            files=list(p.glob(f"**/*.{image_extension}"))
        elif p.is_file():
            files.append(p)

        files.sort()
        return files

    def get_record(self, gid):
        for x in self.page_frames:
            if len(x['data'])==0:
                continue

            q=x['data'][x['data']['gid']==gid]
            if len(q)>0:
                return q.iloc[0]            

        return

    def annotate_page(self, page):
        page_nr=int(''.join([x for x in page['page'] if x.isnumeric()]))
        for index, row in page['data'].iterrows():
            page['data'].at[index, 'page_nr']=page_nr
            page['data'].at[index, 'species_match']=self.name_matching.get_species_match(row['text'])
            # genus_match only matches texts that isolated genera
            page['data'].at[index, 'genus_match']=self.name_matching.get_genus_match(row['text'], max_tokens=1)
            page['data'].at[index, 'family_match']=self.name_matching.get_family_match(row['text'])
            # epithet_match matches isolated epithets preceded by a -
            page['data'].at[index, 'epithet_match']=self.name_matching.get_epithet_match(row['text'])
            page['data'].at[index, 'list_index']=self.extract_list_index(row['text'])
            page['data'].at[index, 'ipen']=self.extract_ipen(row['text'])

        if self.config['debug_print_annotated_data']:
            print(page['page'])
            print(page['data'][:self.config['debug_print_annotated_data_length']])
            # exit()

        # self.fix_list_numbers(page['data'])

    @staticmethod
    def extract_list_index(text):
        match=re.findall(r'^([0-9]{1,5})[.\)°\s]?', text.strip())
        if match and len(match)==1:
            return int(match[0])

    def extract_ipen(self, text):
        match=re.search(self.config['regex_ipen'], text.strip(), re.UNICODE)
        if match:
            return match.group(0).strip()
        
    @staticmethod
    def get_neighbour(distance_function, block, df, allow_zero_distance=False, restrict_direction=None):
        dist=math.inf
        nearest=None
        restrict_direction=restrict_direction if isinstance(restrict_direction, list) else [restrict_direction]

        for item in df.itertuples():

            if 'up' in restrict_direction and getattr(item, 'y_2')>=block['y_2']:
                continue
            if 'down' in restrict_direction and getattr(item, 'y_2')<=block['y_2']:
                continue
            if 'left' in restrict_direction and getattr(item, 'x_1')>=block['x_1']:
                continue
            if 'right' in restrict_direction and getattr(item, 'x_1')<=block['x_1']:
                continue

            d=distance_function(block, item)
            if (d<dist and d!=0) or (d==0 and allow_zero_distance):
                dist=d
                nearest=item

        return nearest, dist

    def get_nearest_horizontal_neighbour(self, block, df, allow_zero_distance=False, restrict_direction=None):
        def get_dist(a,b):
            return math.sqrt((getattr(a,'x_1')-getattr(b,'x_1'))**2 + ((getattr(a, 'y_2')*10)-(getattr(b,'y_2')*10))**2)
        return self.get_neighbour(get_dist, block, df, allow_zero_distance, restrict_direction)

    def get_nearest_vertical_neighbour(self, block, df, allow_zero_distance=False, restrict_direction=None):
        def get_dist(a,b):
            return math.sqrt((getattr(a,'x_1')*10-getattr(b,'x_1')*10)**2 + (getattr(a,'y_2')-getattr(b,'y_2'))**2)
        return self.get_neighbour(get_dist, block, df, allow_zero_distance, restrict_direction)

    def get_nearest_neighbour(self, block, df, allow_zero_distance=False, restrict_direction=None):
        def get_dist(a,b):
            return math.sqrt((getattr(a,'x_1')-getattr(b,'x_1'))**2 + (getattr(a,'y_2')-getattr(b,'y_2'))**2)
        return self.get_neighbour(get_dist, block, df, allow_zero_distance, restrict_direction)

    def collect_species_list(self, page):
        if len(page['data'])==0:
            return []

        names=[]
        df=page['data'][(page['data'].species_match>=self.config['species_match_threshold']) |
                        (page['data'].genus_match>=self.config['species_match_threshold']) | 
                        (page['data'].epithet_match>=self.config['species_match_threshold'])].sort_values(by=['y_1', 'x_1'], ascending=True)
        
        names=[row for _, row in df.iterrows()]

        # for name in names:
        #     print(f"{name['species_match']:>5} {name['genus_match']:>5} {name['epithet_match']:>5} {name['text']}")

        return names

    def link_records(self, 
                     names, 
                     attr, 
                     attr_name, 
                     self_check_attr=None, 
                     col_count=1, 
                     restrict_direction=None,
                     remove_duplicates=True,
                     remove_outliers=True):

        def get_y2_list(data):
            return sorted(collections.Counter([round(getattr(x,'y_2')/20)*20 for x in data]).items(), key=lambda x: x[0])

        def link_nearest_record(names, 
                                attr, 
                                attr_name, 
                                self_check_attr=None, 
                                restrict_direction=None,
                                remove_duplicates=True,
                                remove_outliers=True):

            def do_remove_duplicates(names, attr_name):
                # remove duplicates (keep closest one)
                for name in names:
                    if attr_name in name:
                        p=[x for x in names if attr_name in x and x[attr_name][0]==name[attr_name][0]]
                        if len(p)>1:
                            for item in sorted(p, key=lambda d: d[attr_name][1])[1:]:
                                del item[attr_name]
                return names

            def do_remove_outliers(names, attr_name):
                distances=[x[attr_name][1] for x in names if attr_name in x]

                if len(distances)==0:
                    return names

                q1, q3= np.percentile(distances,[25,75])
                iqr=q3-q1 # interquartile range
                lower_bound=q1-(1.5*iqr)
                upper_bound=q3+(1.5*iqr)

                for name in names:
                    if attr_name in name:
                        if name[attr_name][1]>upper_bound and name[attr_name][1]<lower_bound:
                            del name[attr_name]
               
                return names

            if len(attr)==0:
                return names

            # names also contains rows that are family names, which don't get attributes, so we want to leave them out here
            names_y2s=get_y2_list([x for x in names if x['species_match']>0 or x['epithet_match']>0])
            attrib_y2s=get_y2_list([row for row in attr.itertuples()])

            # y2s_match is fraction of all the rows with the attribute under consideration that are on the
            # same line as rows that contain the names we're annotating. It is used to decide if the nearest
            # neighbour function should look (more) horizontally or vertically for the nearest attribute.
            matches=0
            for item in attrib_y2s:
                matches+=1 if len([x for x in names_y2s if x[0]==item[0]])>0 else 0

            y2s_match=matches/len(attrib_y2s)

            if self_check_attr is not None:
                # blocks that have both name and IPEN: assuming name and IPEN belong together
                for name in [x for x in names if x[self_check_attr] is not None]:
                    # skip families (if any)
                    if name['species_match']>0 or name['epithet_match']>0:
                        # 'self-assign' (with distance 0) and delete from set of available attribute records
                        name[attr_name]=(name['gid'], 0)
                        attr=attr.drop(name['id'])

            if len(attr)==0:
                return names

            for name in names:
                # these already have the attribute added (via 'self_check_attr')
                if attr_name in name:
                    continue
                
                # skip families
                if name['species_match']==0 and name['epithet_match']==0:
                    continue

                if y2s_match>0.66:
                    nearest, dist=self.get_nearest_horizontal_neighbour(block=name, df=attr, restrict_direction=restrict_direction)
                elif y2s_match<=0.33:
                    nearest, dist=self.get_nearest_vertical_neighbour(block=name, df=attr, restrict_direction=restrict_direction)
                else:
                    nearest, dist=self.get_nearest_neighbour(block=name, df=attr, restrict_direction=restrict_direction)

                if nearest:
                    name[attr_name]=(getattr(nearest,'gid'), dist)

            if remove_duplicates:
                names=do_remove_duplicates(names=names, attr_name=attr_name)
            if remove_outliers:
                names=do_remove_outliers(names=names, attr_name=attr_name)

            return names

        if col_count==2:
            mid=(max([x['x_2'] for x in names])-min([x['x_1'] for x in names]))/2

            left=link_nearest_record(names=[x for x in names if x['x_1']<mid],
                                     attr=attr[attr.x_1<mid],
                                     attr_name=attr_name,
                                     self_check_attr=self_check_attr,
                                     restrict_direction=restrict_direction,
                                     remove_duplicates=remove_duplicates,
                                     remove_outliers=remove_outliers)
            
            right=link_nearest_record(names=[x for x in names if x['x_1']>=mid],
                                      attr=attr[attr.x_1>=mid],
                                      attr_name=attr_name,
                                      self_check_attr=self_check_attr,
                                      restrict_direction=restrict_direction,
                                      remove_duplicates=remove_duplicates,
                                      remove_outliers=remove_outliers)
            left.extend(right)
            return left
        else:
            return link_nearest_record(names=names, 
                                       attr=attr, 
                                       attr_name=attr_name, 
                                       self_check_attr=self_check_attr,
                                       restrict_direction=restrict_direction,
                                       remove_duplicates=remove_duplicates,
                                       remove_outliers=remove_outliers)

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

    def copy_referenced_value(self, names_list, ref_attr, source_col, target_col):
        if len(names_list)==0:
            return names_list

        for name in [x for x in names_list if ref_attr in x]:
            p=self.get_record(gid=name[ref_attr][0])
            name[target_col]=p[source_col]

        return names_list

    def remove_starting_non_list_lines(self, names_list):
        has_families=len([x for x in names_list if x['family_match']>0 and len(x['text'].split())==1])>0
        has_indexes=len([x for x in names_list if 'corrected_index' in x])>0

        rec=False
        cleaned_list=[]
        for key, name in enumerate(names_list):
            if not rec:
                if has_families and name['family_match']>0 and len(name['text'].split())==1:
                    rec=True
                elif name['genus_match']==1:
                    rec=(len(names_list)>=key+2) and (names_list[key+1]['epithet_match'])
                elif has_indexes and 'corrected_index' in name:
                    rec=True
                else:
                    # we assume a list doesn't start wth just an epithet
                    rec=name['species_match']>=self.config['species_match_threshold']

            if rec:
                cleaned_list.append(name)

        return cleaned_list

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
            df=df[(df.ipen.isna() & (df.species_match<self.config['species_match_threshold']) & (df.epithet_match==0) & (df.genus_match==0) & (df.family_match==0))]
            data.append(df)

        return pd.concat(data)

    def set_metadata(self, names_list, linked_records):
        if len(names_list)==0:
            return names_list

        for key, item in enumerate(names_list):
            meta=self.get_next_lines(item, names_list[key+1] if len(names_list)>key+1 else None)
            meta=meta[~meta['gid'].isin(linked_records)]
            linked_records.extend(meta['gid'].tolist())
            names_list[key]['meta']=meta

        return names_list, linked_records

    def clean_metadatas(self, names_list):

        def filter_meta(meta):
            return not re.match(r'^[\)]{1,}$', meta.strip(), re.IGNORECASE)

        if len(names_list)==0:
            return names_list

        for key, item in enumerate(names_list):
            if 'name_removed' in item['name']:
                names_list[key]['name'].update({'name_removed': filter(filter_meta, item['name']['name_removed'])})

            if 'meta' in item:
                names_list[key].update({'meta': item['meta'][item['meta'].text.apply(filter_meta)]})

        return names_list

    def get_col_count(self, sp_list):
        if len(sp_list)==0:
            return 1

        n=10
        data=[(round(x['x_1']/n,0)*n) for x in sp_list if x['species_match']>self.config['species_match_threshold']]
        data.sort()
        c=collections.Counter(data)
        mid=(max([x['x_2'] for x in sp_list])-min([x['x_1'] for x in sp_list]))/2
        mc=c.most_common(2)

        if len(mc)<2:
            return 1

        if abs(mc[0][1]/mc[1][1]) > 4:
            return 1

        return 2 if ((mid-mc[0][0])*(mid-mc[1][0]))<0 else 1

    def process_files(self, path,  image_extension='png', pages=None, output_file=None, force_ocr=False):
       
        # self.set_word_list_matcher(path=path)
        include_pages=self.get_include_pages(pages=pages)
        output_path=self.get_output_path(output_file=output_file)
        files=self.get_file_list(path=path, image_extension=image_extension)

        logging.info("got %s file(s) from '%s'" % (len(files), path))

        if len(files)==0:
            return

        self.page_frames=self.ocr.get_ocr_data(
            files=files,
            include_pages=include_pages,
            force_ocr=force_ocr)
        logging.debug("acquired OCR data")

        for page in self.page_frames:
            if include_pages and page['key'] not in include_pages:
                continue
            # clean up, group by block, add annotation columns
            page.update({'data': self.ocr.preprocess_ocr_data(page['data'])})
        logging.debug("preprocessed OCR data")

        for page in self.page_frames:
            if include_pages and page['key'] not in include_pages:
                continue
            # add annotations: species/genus/family match, index, ipen
            self.annotate_page(page)
        logging.debug("annotated OCR data")

        # self.page_frames
        # list of dict: {'key': int, 'page': str (filename), 'page_nr': int, 'data': dataframe

        page_lists=[]
        for page in self.page_frames:
            if include_pages and page['key'] not in include_pages:
                continue

            sp_list=self.collect_species_list(page)
            col_count=self.get_col_count(sp_list)

            # sp_list: list of dict

            if not page['data'].empty:

                logging.debug("page %s: %s columns" % (page['page_nr'], col_count))
                
                sp_list=self.link_records(names=sp_list,
                    attr=page['data'][~page['data'].ipen.isna()], 
                    attr_name='ipen_record', 
                    self_check_attr='ipen',
                    col_count=col_count)

                sp_list=self.link_records(names=sp_list, 
                    attr=page['data'][~page['data'].list_index.isna()], 
                    attr_name='list_index_record', 
                    self_check_attr='list_index',
                    col_count=col_count)

                sp_list=self.link_records(names=sp_list, 
                    attr=page['data'][page['data'].family_match>0], 
                    attr_name='family_record', 
                    col_count=col_count,
                    restrict_direction='up',
                    remove_duplicates=False,
                    remove_outliers=False)

            sp_list=self.remove_starting_non_list_lines(sp_list)

            if len(sp_list)>0:
                page_lists.append({'page': page['page'], 'list': sp_list})                
        logging.debug("extracted %s lists" % len(page_lists))

        # optionally concatenate lists (which are still divided by page at this point)
        if self.config['concatenate_lists']:
            concat_lists=self.concatenate_lists(page_lists)
            logging.debug("concatenated %s lists to %s" % (len(page_lists), len(concat_lists)))
        else:
            concat_lists=[x['list'] for x in page_lists]

        # do some cleaning and complementing names
        cleaned_lists=[]
        for concat_list in concat_lists:
            sp_list=self.copy_referenced_value(
                names_list=concat_list,
                ref_attr='ipen_record',
                source_col='ipen',
                target_col='ipen_text')

            sp_list=self.copy_referenced_value(
                names_list=sp_list,
                ref_attr='family_record',
                source_col='text',
                target_col='family_text')

            sp_list=self.copy_referenced_value(
                names_list=sp_list,
                ref_attr='list_index_record',
                source_col='list_index',
                target_col='list_index_text')

            sp_list=self.name_matching.clean_up_names(sp_list)
            sp_list=self.name_matching.complement_repeated_epithets(sp_list)
            sp_list=self.name_matching.merge_isolated_epithets(sp_list)

            if len(sp_list)>0:
                cleaned_lists.append(sp_list)
        logging.debug("cleaned up lists")

        ## collecting metadata
        linked_records=[]
        for sp_list in concat_lists:
            for attribute in ['list_index_record', 'ipen_record', 'family_record']:
                linked_records.extend([x[attribute][0] for x in sp_list if attribute in x])

        finished_lists=[]
        for cleaned_list in cleaned_lists:
            sp_list, linked_records=self.set_metadata(cleaned_list, linked_records)
            sp_list=self.clean_metadatas(sp_list)
            if len(sp_list)>0:
                finished_lists.append(sp_list)
        logging.debug("added metadata")

        if output_path:
            self.output.csv(output_path=output_path, lists=finished_lists)
        else:
            self.output.stdout(lists=finished_lists)


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
        'debug_print_annotated_data': False,
        'debug_print_annotated_data_length': 30,
        'debug_print_name_resolvement': False,
        'debug_colored_stdout': True
        }

    parser=SeedlistImageParser(
        name_database=args.name_database,
        image_extension=args.image_extension,
        config=config)

    if args.recursive:
        for item in glob.glob(args.path):
            
            output_file=None
            if args.output_folder:
                output_file=Path(args.output_folder) / Path((Path(item).parts[-1])).with_suffix(".csv")

                if output_file.exists() and args.skip_existing:
                    logging.info("skipping '%s'" % item)
                    continue

            parser.process_files(path=item, output_file=output_file, pages=args.pages, force_ocr=args.force_ocr)

    else:
        output_file=None
        if args.output_folder:
            output_file=Path(args.output_folder) / Path((Path(args.path).parts[-2])).with_suffix(".csv")

        if output_file and output_file.exists and args.skip_existing:
            logging.info("skipping '%s'" % output_file)
        else:
            parser.process_files(path=args.path, output_file=output_file, pages=args.pages, force_ocr=args.force_ocr)

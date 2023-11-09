import argparse
import logging
import json
import re
import sqlite3
import statistics
import pickle
from pathlib import Path
from pprint import pprint

class ColumnGuesser:

    all_names_query="select * from name_lookup"

    name_abbr=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
               'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
               'var.', 'convar.', ]

    def __init__(self, 
                 input_path, 
                 output_path,
                 name_database,) -> None:

        self.config={
            'cache_names': True
        }

        self.files=[]

        if input_path:
            p = Path(input_path)
        
            if p.is_dir():
                self.files=list(p.glob('**/*.json'))
            elif p.is_file():
                self.files.append(p)
            
            self.files=sorted(self.files)

        if output_path:
            self.output_path=Path(output_path)
            self.output_path.mkdir(parents=True, exist_ok=True)

        db = Path(name_database)
        if not db.exists():
            raise ValueError("database %s does not exist" % name_database)

        self.pickle_file=Path("./pickles/names_pickle")
        self.conn=self.connect_db(name_database)
        self.load_names()

    @staticmethod
    def connect_db(db_file):
        conn=None
        try:
            conn=sqlite3.connect(db_file)
            conn.row_factory=sqlite3.Row
        except Exception as e:
            logging.error(str(e))
            raise(e)

        return conn

    def load_names_pickle(self):
        try:
            with open(self.pickle_file, 'rb') as file:
                data=pickle.load(file)
            return data
        except:
            pass

    def save_names_pickle(self, data):
        with open(self.pickle_file, 'wb') as file:
            pickle.dump(data, file)

    def load_names(self):
        if self.config['cache_names']:
            names=self.load_names_pickle()
            if names:
                self.families=names['families']
                self.genera=names['genera']
                self.species=names['species']
                self.epithets=names['epithets']
                logging.info("unpickled %s family names" % format(len(self.families), ','))
                logging.info("unpickled %s genus names" % format(len(self.genera), ','))
                logging.info("unpickled %s species names" % format(len(self.species), ','))
                logging.info("unpickled %s epithets" % format(len(self.epithets), ','))
                return

        self.families=[]
        self.genera=[]
        self.species=[]
        self.epithets=[]

        cur=self.conn.cursor()
        cur.execute(self.all_names_query)
        for row in cur.fetchall():
            # scientificName, scientificNameAuthorship, genus, epithet, family, subfamily, tribe, subtribe, full_scientific_name, taxonrank
            if row['taxonrank'] in ['family', 'subfamily'] and len(row['family'])>0:
                self.families.append(row['family'])

            if row['taxonrank'] in ['genus'] and len(row['genus'])>0:
                self.genera.append(row['genus'])

            if row['taxonrank'] in ['variety', 'species', 'subspecies', 'subvariety', 'subform', 'prole']:
                if len(row['scientificName'])>0:
                    self.species.append(row['scientificName'])
                if len(row['full_scientific_name'])>0:
                    self.species.append(row['full_scientific_name'])
                if len(row['epithet'])>0:
                    self.epithets.append(row['epithet'])

        self.families=set(sorted(self.families, key=len, reverse=True))
        logging.info("loaded %s family names" % format(len(self.families), ','))
        self.genera=set(sorted(self.genera, key=len, reverse=True))
        logging.info("loaded %s genus names" % format(len(self.genera), ','))
        self.species=set(sorted(self.species, key=len, reverse=True))
        logging.info("loaded %s species names" % format(len(self.species), ','))
        self.epithets=set(sorted(self.epithets, key=len, reverse=True))
        logging.info("loaded %s epithets" % format(len(self.epithets), ','))

        self.save_names_pickle({
            'families': self.families,
            'genera': self.genera,
            'species': self.species,
            'epithets': self.epithets,
        })

    def extract_names(self, text, rank):

        def remove_outer_non_alpha(text):
            regex=r'(^[^a-zA-Z]{1,}|[^a-zA-Z\.\)]{1,}$)'
            cleaned=re.sub(regex, '', text.strip(), re.UNICODE)
            if cleaned != text:
                return cleaned, text.split(cleaned)
            return text, ['','']

        def remove_abbreviations(name):
            return ' '.join([x for x in name.split() if x not in self.name_abbr])

        def extract_name(tokens, rank):
            min_name_length=1
            if rank=='species':
                min_name_length=2

            candidates=[]

            for i in range(0, len(tokens)):
                for j in range(len(tokens), 0, -1):
                    if j-i<min_name_length:
                        break

                    lookup=self.clean_up_name(remove_abbreviations(' '.join(tokens[i:j])))

                    if (rank=='families' and lookup in self.families) \
                    or (rank=='genera' and lookup in self.genera) \
                    or (rank=='species' and lookup in self.species) \
                    or (rank=='epithets' and lookup in self.epithets):
                        candidates.append((i, j, lookup))

            if len(candidates)>0:
                # cleanup() takes out non-alpha chars, which will re-appear in the slicing
                # of the (uncleaned) tokens, so we take the longest of the (cleaned) candidates
                # that uses the smallest amount of tokens
                best=sorted(candidates, key=lambda x: (-len(x[2]), abs(x[1]-x[0]) ))[0]
                return tokens[best[0]:best[1]], (tokens[:best[0]], tokens[best[1]:])

            return None, (tokens, )
        
        tokens=text.strip().split()
        if len(tokens)==0:
            return []

        names=[]
        while True:
            name, rest=extract_name(tokens=tokens, rank=rank)
            if name is None:
                break
            cleaned, c_rest=remove_outer_non_alpha(' '.join(name))
            names.append(cleaned)
            tokens=[x for x in rest[0]+c_rest+rest[1] if len(x)>0]

        return names

    def clean_up_name(self, name):
        return re.sub(r'(\s){1,}', ' ', re.sub(r'[^a-z ]', '', name.lower())).strip()




    def main(self):
        for file in self.files:
            # logging.info("processing '%s'" % (file))
            with open(file, "r") as f:
                doc=json.load(f)

            # pprint(doc['filename'])
            meta=doc['document']['metadata']
            # doc['document']['content']doc['document']['content']
            
            meta['pdf:charsPerPage']=list(map(int,meta['pdf:charsPerPage']))

            # print(meta['pdf:charsPerPage'])
            # print(len(meta['pdf:charsPerPage']))
            # print(meta['xmpTPg:NPages'])

            content=doc['document']['content']
            content=content.replace('\t', ' ')

            # namespaces = {'owl': 'http://www.w3.org/2002/07/owl#'} # add more as needed
            # root.findall('owl:Class', namespaces)                

            import xml.etree.ElementTree as ET
            root = ET.fromstring(content)
            ns='{http://www.w3.org/1999/xhtml}'
            pages=[]

            for child in root:
                if child.tag==ns+'body':
                    for childchild in child:
                        if 'class' in childchild.attrib and childchild.attrib['class']=='page':
                            lines=[]
                            for page in childchild:
                                if page.text:
                                    lines.extend(list(map(lambda x: x.strip(),page.text.split('\n'))))
                            pages.append({'lines': lines})

            # pprint(pages[3]['lines'])
            # pprint(len(pages))
            # print(doc['filename'])
            tralala=list(map(int, meta['pdf:charsPerPage']))
            counts=[]
            pagechars=[]
            for key, page in enumerate(pages):
                namecount=0
                for line in page['lines']:
                    # nf=len(self.extract_names(line, rank='families'))
                    ns=len(self.extract_names(line, rank='species'))
                    # if ns==0:
                    #     ng=len(self.extract_names(line, rank='genera'))
                    #     ne=len(self.extract_names(line, rank='epithets'))
                    # else:
                    #     ng=0
                    #     ne=0

                    namecount += ns

                if namecount>20:
                    counts.append(namecount)
                    pagechars.append(tralala[key])
                    # print(f"{key:>4} {namecount:>4}")

            mean_pp=1 if len(pagechars)<2 else statistics.mean(pagechars)
            bla=1 if len(counts)<2 else statistics.mean(counts)

            print(f"{round(bla):>5} {round(mean_pp):>5} {round(bla*100/mean_pp):>5} {doc['filename']}")
            # print('-'*100)

            # pprint(pages[3]['lines'])
            


if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('-i','--input-path', required=True)
    parser.add_argument('-o','--output-path')
    parser.add_argument('-d','--name-database', default='/data/seedlists/WFO_backbone.db3')
    parser.add_argument('--debug', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    sp=ColumnGuesser(
        input_path=args.input_path, 
        output_path=args.output_path,
        name_database=args.name_database,)

    sp.main()

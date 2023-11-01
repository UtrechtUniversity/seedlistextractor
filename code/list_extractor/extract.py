import argparse
import logging
import json
import re
import sqlite3
from pathlib import Path
import pickle
from pprint import pprint
import statistics

class SeedlistExtractor:

    all_names_query="select * from name_lookup"

    name_abbr=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
               'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
               'var.', 'convar.', ]

    line_template={
        'line_nr': None,
        'families': [],
        'genera': [],
        'species': [],
        'epithets': [],
        'list_indexes': [],
        'ipens': [],
        'rest_texts': [],
        'next_lines': [] }


    def __init__(self, 
                 path, 
                 output,
                 name_database) -> None:

        self.files=[]
        self.pickle_file=Path("./pickles/names_pickle")

        if path:
            p = Path(path)
        
            if p.is_dir():
                self.files=list(p.glob('**/*.json'))
            elif p.is_file():
                self.files.append(p)

        if output:
            self.output=Path(output)
            self.output.mkdir(parents=True, exist_ok=True)

        logging.info("got %s file(s) from '%s'" % (len(self.files), p))

        db = Path(name_database)
        if not db.exists():
            raise ValueError("database %s does not exist" % name_database)
        
        self.conn=self.connect_db(name_database)
        self.load_names()

    @staticmethod
    def connect_db(db_file):
        conn=None
        try:
            conn=sqlite3.connect(db_file)
            conn.row_factory=sqlite3.Row
        except Exception as e:
            print(e)

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
        # TODO: take out again once done developing
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

        self.families=set(self.families)
        logging.info("loaded %s family names" % format(len(self.families), ','))
        self.genera=set(self.genera)
        logging.info("loaded %s genus names" % format(len(self.genera), ','))
        self.species=set(self.species)
        logging.info("loaded %s species names" % format(len(self.species), ','))
        self.epithets=set(self.epithets)
        logging.info("loaded %s epithets" % format(len(self.epithets), ','))

        self.save_names_pickle({
            'families': self.families,
            'genera': self.genera,
            'species': self.species,
            'epithets': self.epithets,
        })

    def numbered_lines_from_doc(self, doc):
        lines=doc['document']['content'].splitlines()
        lines=list(map(lambda x: x.replace('\t',' ').strip(), lines))
        return [(v, k) for k, v in enumerate(lines)]

    def extract_lines(self, all_lines):
        lines=[]
        for key, doc_line in enumerate(all_lines):

            a_line=doc_line[0]

            if len(a_line)>0:

                line=self.line_template.copy()
                line.update({'line_nr': key})

                # for rank in ['families', 'genera', 'species', 'epithets']:
                for rank in ['families', 'genera', 'species' ]:
                    names=self.extract_names(text=a_line, rank=rank)
                    if len(names)>0:
                        line.update({rank: names})

                ipens=self.extract_ipens(text=a_line)
                if len(ipens)>0:
                    line.update({'ipens': ipens})

                list_indexes=self.extract_list_indexes(text=a_line)
                if len(list_indexes)>0:
                    line.update({'list_indexes': list_indexes})

                lines.append(line)

        return [x for x in lines if 
                len(x['families'])>0 or 
                len(x['genera'])>0 or 
                len(x['species'])>0 or 
                len(x['epithets'])>0 or 
                len(x['list_indexes'])>0 or 
                len(x['ipens'])>0]

    def clean_up_name(self, name):
        return re.sub(r'(\s){1,}', ' ', re.sub(r'[^a-z ]', '', name.lower())).strip()

    def extract_names(self, text, rank):

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
            names.append(' '.join(name))
            tokens=rest[0]+rest[1]
        return names

    @staticmethod
    def extract_ipens(text):
        """
        The IPEN number consists of four elements:

        - Country of origin (two positions, abbreviation according to ISO 3166-1-alpha-2, “XX” for unknown origin)
        - Restrictions of transfer (one position, “1” if there exists a restriction; “0” if none).
        - The unique Garden code of the institution offering the plant material for exchange, (to be found on the BGCI Website under “GardenSearch”).
        - Identification Number (the specific accession number of the plant material in the recording system of the garden)

        https://www.bgci.org/our-work/inspiring-and-leading-people/policy-and-advocacy/access-and-benefit-sharing/the-international-plant-exchange-network/#ipen-documentation-system
        """
        regex=r'(([A-Z]{2})([—\-\. ]{1})([01]{1})([—\-\. ]{1})([A-Za-z]{1,5})([—\-\./ ]{1})([^\s]*))'
        matches=re.findall(regex, text.strip(), re.UNICODE)
        if matches:
            return [x[0] for x in matches]
        return []

    @staticmethod
    def extract_list_indexes(text):
        matches=re.findall(r'(([0-9]{1,5})[.\)°\s])', text.strip())
        if matches:
            return [x[0].strip() for x in matches]
        return []

    def genus_header_look_ahead(self, lines, all_lines):
        updates=[]

        for line in [x for x in lines if len(x['genera'])>0 and len(x['species'])==0]:

            next_items=[x for x in lines 
                        if x['line_nr']>line['line_nr'] 
                        and (len(x['families'])>0 or len(x['genera'])>0 or len(x['species']))>0]

            start=line['line_nr']+1
            if len(next_items)>0:
                end=next_items[0]['line_nr']
            else:
                end=line['line_nr']+5
            
            for genus in line['genera']: 
                candidates=[]

                for key, line in enumerate(all_lines[start:end]):
                    tokens=line[0].split()
                    if len(tokens)==0:
                        continue

                    while len(tokens)>0:
                        ele=tokens.pop(0)
                        if len(self.clean_up_name(ele))>0:
                            break
                    tokens.insert(0, ele)
                    joined=' '.join(tokens).strip()
                    candidates.extend([(x, start+key, x.replace(genus, '').strip()) for x 
                                       in self.extract_names(text=f"{genus} {joined}", 
                                                             rank='species')])

                if candidates:
                    updates.append(sorted(candidates, key=lambda x: -len(x[0]))[0])

        for update in updates:
            existing=[x for x in lines if  x['line_nr']==update[1]]
            if existing:
                species=existing[0]['species'].copy()
                species.append(update[0])
                existing[0].update({'species': species, '_remove': [update[2]]})
            else:
                new=self.line_template.copy()
                new.update({'line_nr': update[1], 'species': [update[0]]})
                lines.append(new)

        return lines

    def extract_rest_texts(self, lines, all_lines):

        def remove_item(elements, item):
            remains=[]
            for element in elements:
                remains.extend(element.split(item))
            return remains

        for key, line in enumerate(lines):
            rest_texts=list(map(lambda x: re.sub(r'\s{1,}', ' ', x), [x[0] for x in all_lines if x[1]==line['line_nr']]))
            for attr in ['families', 'genera', 'species', 'epithets', 'list_indexes', 'ipens', '_remove']:
                if attr in line:
                    for item in line[attr]:
                        rest_texts=remove_item(elements=rest_texts, item=item)

            lines[key]['rest_texts']=list(map(lambda x: x.strip(),filter(lambda x: len(x.strip())>0, rest_texts)))
            if '_remove' in lines[key]:
                del lines[key]['_remove']

        return lines

    def add_unannotated_lines(self, lines, all_lines, max_look_ahead=5):
        next_lines=[]

        for key, line in enumerate(lines):

            start=line['line_nr']+1

            if key>=len(lines)-1:
                end=line['line_nr']+max_look_ahead
            else:
                end=min(lines[key+1]['line_nr'], line['line_nr']+max_look_ahead)
    
            n_lines=[x[0] for x in all_lines[start:end] if len(x[0])>0]
            if lines:
                next_lines.append((n_lines, line['line_nr']))

        for next_line in next_lines:
            existing=[x for x in lines if x['line_nr']==next_line[1]]
            existing[0].update({'next_lines': next_line[0]})

        return lines

    def filter_useful(self, lines):
        lines=[x for x in lines if (len(x['families'])>0 or len(x['genera'])>0 or len(x['species']))>0]
        lines=sorted(lines, key=lambda x: x['line_nr'])
        return lines

    def main(self):
        for file in self.files:
            logging.info("processing '%s'" % (file))
            with open(file, "r") as f:
                doc=json.load(f)

            all_lines=self.numbered_lines_from_doc(doc)
            lines=self.extract_lines(all_lines=all_lines)
            lines=self.genus_header_look_ahead(lines=lines, all_lines=all_lines)
            lines=self.extract_rest_texts(lines=lines, all_lines=all_lines)
            lines=self.add_unannotated_lines(lines=lines, all_lines=all_lines)
            lines=self.filter_useful(lines=lines)

            pprint(lines)
            
            

if __name__=="__main__":

    logging.basicConfig(level=logging.INFO)

    parser=argparse.ArgumentParser()
    parser.add_argument('-p','--path', required=True)
    parser.add_argument('-o','--output')
    parser.add_argument('-d','--name-database', default='/data/seedlists/WFO_backbone.db3')
    args=parser.parse_args()
    
    sp=SeedlistExtractor(
        path=args.path, 
        output=args.output,
        name_database=args.name_database,)

    sp.main()


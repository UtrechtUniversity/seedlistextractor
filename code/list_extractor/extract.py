import argparse
import logging
import json
import re
import sqlite3
import statistics
import pickle
import shutil
from pathlib import Path
from pprint import pprint
from output import Output

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
        'list_idx': [],
        'ipens': [],
        'syns': [],
        'rest_texts': [],
        'next_lines': [],
        '_remove': [], }

    def __init__(self, 
                 input_path, 
                 output_path,
                 name_database,
                 skip_existing=False,
                 exceptions_path=None) -> None:

        self.files=[]
        self.pickle_file=Path("./pickles/names_pickle")
        self.output_path=None
        self.exceptions_path=None

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

        if exceptions_path:
            self.exceptions_path=Path(exceptions_path)
            self.exceptions_path.mkdir(parents=True, exist_ok=True)

        self.output=Output(skip_existing=skip_existing)

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

    @staticmethod
    def list_elements_strip(a_list):
        return list(map(lambda x: x.strip(), a_list))

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

        #TODO: take out!
        self.families.append("adoxaceae")
        self.species.append("abelia umbellate")
        self.species.append("cephalaria gigantean")

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


    def get_output_path(self, file):
        if self.output_path:
            output_path=self.output_path / Path((Path(file).parts[-1])).with_suffix(".csv")
            output_path=Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            return output_path

    def numbered_lines_from_doc(self, doc, remove_empty_lines=True):
        lines=doc['document']['content'].splitlines()
        lines=list(map(lambda x: x.replace('\t',' ').strip(), lines))
        if remove_empty_lines:
            lines=filter(lambda x: len(x.strip())>0, lines)
        return [(v, k) for k, v in enumerate(lines)]


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

    @staticmethod
    def extract_syns(text):
        regex=r'(\[(sin|syn)\.? ([^\]]*)\])'
        matches=re.findall(regex, text.strip(), re.UNICODE)
        if matches:
            # [('M. recutita L.', '[syn. M. recutita L.]')]
            return [(x[2], x[0]) for x in matches]
        return []

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
        regex=r'(([A-Z]{2})([—\-\. ]{1})([01]{1})([—\-\. ]{1})([A-Za-z]{1,5})([—\-\./ ]{1})([^\s\]]*))'
        matches=re.findall(regex, text.strip(), re.UNICODE)
        if matches:
            return [x[0] for x in matches]
        return []

    @staticmethod
    def extract_list_idx(text):
        matches=re.findall(r'((^|\s)([0-9]{1,5})[.\)°]?\s)', text.strip())
        if matches:
            return [x[0] for x in matches]
        return []

    def clean_up_name(self, name):
        return re.sub(r'(\s){1,}', ' ', re.sub(r'[^a-z ]', '', name.lower())).strip()

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
                _remove=existing[0]['_remove'].copy()
                _remove.append(update[2])
                existing[0].update({'species': species, '_remove': _remove})
            else:
                new=self.line_template.copy()
                new.update({'line_nr': update[1], 'species': [update[0]]})
                lines.append(new)

        return lines

    def synonyms_look_ahead(self, lines):
        updates=[]

        for line in [x for x in lines if (len(x['species'])>0 or len(x['epithets'])>0)]:
            for next_line in [x for x in lines if x['line_nr']>line['line_nr'] ]:
                if len(next_line['species'])>0 or len(next_line['epithets'])>0:
                    break
                if len(next_line['syns'])>0:
                    updates.append((next_line['syns'], line['line_nr']))
                    break

        for update in updates:
            existing=[x for x in lines if  x['line_nr']==update[1]]
            existing[0].update({'syns': update[0]})

        return lines

    def clean_up_list_indexes(self, lines):
        # see if there's multiple possible indexes per row,
        # collect the values for each, and sort them
        columns={}
        for key, line in enumerate(lines):
            lines[key].update({'list_idx_clean': list(map(lambda x: int(''.join([y for y in x if y.isnumeric()])), line['list_idx']))})
            for lkey, idx in enumerate(lines[key]['list_idx_clean']):
                if lkey not in columns:
                    columns[lkey]=[]
                columns[lkey].append(idx)
                columns[lkey].sort()

        if len(columns)>0:
            # calculate the average step size for subsequent index numbers, total number of indexes
            # and the amount of steps with size zero (i.e. subsequent identical numbers)
            stats=[]
            for key, column in columns.items():
                avg=[]
                prev=0
                for ele in column:
                    avg.append(ele-prev)
                    prev=ele
                stats.append((key, len(avg), statistics.mean(avg), len([x for x in avg if x==0])))

            # sorty by:
            #   most elements
            #   least zeroes (= least subsequent identical numbers)
            #   smallest average diff of subseq numbers
            # and assume the first column contains the indexes
            stats=sorted(stats, key=lambda x: (-x[1], x[3], x[2]))
            best_idx_key=stats[0][0]
            apply=(stats[0][1]/len([x for x in lines if len(x['epithets'])>0 or len(x['species'])>0]))>0.75
            for key, line in enumerate(lines):
                # even the best option we only apply if at least 75% of all list items
                # have an index number in that column
                if apply:
                    if len(line['list_idx_clean'])>best_idx_key+1:
                        lines[key].update({'list_idx_clean': [line['list_idx_clean'][best_idx_key]]})
                        lines[key].update({'list_idx': [line['list_idx'][best_idx_key]]})
                else:
                    lines[key].update({'list_idx_clean': []})
                    lines[key].update({'list_idx': []})

        return lines

    def extract_rest_texts(self, lines, all_lines):

        def remove_item(elements, item):
            remains=[]
            for element in elements:
                remains.extend(element.split(item))
            return remains

        for key, line in enumerate(lines):
            
            rest_texts=list(map(lambda x: re.sub(r'\s{1,}', ' ', x), [x[0] for x in all_lines if x[1]==line['line_nr']]))
            # order matters (species before generea and epithets; IPENS before list_idx)
            # syns (literals, including '[syn.' and ']') are in _remove

            for attr in ['species', 'families', 'genera', 'epithets', 'ipens', 'list_idx', '_remove']:
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

            if len(n_lines)>0:
                next_lines.append((n_lines, line['line_nr']))

        for next_line in next_lines:
            existing=[x for x in lines if x['line_nr']==next_line[1]]
            existing[0].update({'next_lines': next_line[0]})
            
        return lines

    def extract_lines(self, all_lines):
        lines=[]
        for key, doc_line in enumerate(all_lines):

            a_line=doc_line[0]

            if len(a_line)>0:

                line=self.line_template.copy()
                line.update({'line_nr': key})

                syns_plus_literals=self.extract_syns(text=a_line)
                syns=[x[0] for x in syns_plus_literals]
                if len(syns)>0:
                    line.update({'syns': syns})
                    line.update({'_remove': [x[1] for x in syns_plus_literals]})

                # for rank in ['families', 'genera', 'species', 'epithets']:
                for rank in ['families', 'genera', 'species' ]:
                    names=self.extract_names(text=a_line, rank=rank)
                    if len(names)>0:
                        if len(syns)>0:
                            names=[x for x in names if x not in syns]
                        line.update({rank: names})

                ipens=self.extract_ipens(text=a_line)
                if len(ipens)>0:
                    line.update({'ipens': ipens})

                list_idx=self.extract_list_idx(text=a_line)
                if len(list_idx)>0:
                    line.update({'list_idx': list_idx})

                lines.append(line)

        return [x for x in lines if 
                len(x['families'])>0 or 
                len(x['genera'])>0 or 
                len(x['species'])>0 or 
                len(x['epithets'])>0 or 
                len(x['syns'])>0 or 
                len(x['list_idx'])>0 or 
                len(x['ipens'])>0]

    def filter_useful_lines(self, lines):
        lines=[x for x in lines if (len(x['families'])+len(x['genera'])+len(x['species']))>0]
        lines=sorted(lines, key=lambda x: x['line_nr'])
        return lines

    def compile_output(self, lines):

        def set_assoc_values(val_list, line, key):
            if len(line[key])>0:
                val_list.clear()
                val_list.extend(line[key])

        def get_assoc_value(values, key):
            if values:
                return values[key] if key in values else '; '.join(list(map(lambda x: str(x), values)))
            return ''

        def get_line_space_distr(lines):
            line_spaces=[]
            p_line_nr=0
            for line in lines:
                line_spaces.append(line['line_nr']-p_line_nr)
                p_line_nr=line['line_nr']
            if len(line_spaces)<2:
                return 0, 0

            mean=statistics.mean(line_spaces)
            stdev=statistics.stdev(line_spaces, xbar=mean)
            return mean, stdev

        mean, stdev=get_line_space_distr(lines)

        logging.debug("line space mean: %s; stdev: %s" % (mean, stdev))

        out_lists=[]
        out_list=[]

        row=[]
        p_line_nr=0

        families=[]
        genera=[]

        for line in lines:
            list_idx=[]
            ipens=[]
            syns=[]
            rest_texts=[]
            next_lines=[]

            if ((line['line_nr']-p_line_nr)>(mean+(stdev*2)) and len(out_list)>0):
                out_lists.append(out_list)
                logging.debug("extracted list #%s with %s row(s)" % (len(out_lists), len(out_list)))
                out_list=[]

            set_assoc_values(val_list=list_idx, line=line, key='list_idx_clean')
            set_assoc_values(val_list=families, line=line, key='families')
            set_assoc_values(val_list=genera, line=line, key='genera')
            set_assoc_values(val_list=ipens, line=line, key='ipens')
            set_assoc_values(val_list=syns, line=line, key='syns')
            set_assoc_values(val_list=rest_texts, line=line, key='rest_texts')
            set_assoc_values(val_list=next_lines, line=line, key='next_lines')

            # list_idx=list(map(lambda x: int(re.sub(r'[^0-9]', '', x)), list_idx))

            if len(line['species'])==0:
                for key, item in enumerate(line['genera']):
                    if logging.root.level==logging.DEBUG:
                        row.append(line['line_nr'])
                    row.extend([get_assoc_value(list_idx, key), get_assoc_value(families, key)])
                    row.append(item)
                    row.extend(['', '', ''])
                    row.extend([get_assoc_value(rest_texts, key), get_assoc_value(next_lines, key)])
                    out_list.append(row)
                    row=[]

            for key, item in enumerate(line['species']):
                if logging.root.level==logging.DEBUG:
                    row.append(line['line_nr'])
                row.append(get_assoc_value(list_idx, key))
                row.append(get_assoc_value(families, key))
                row.append('')
                row.append(item)
                row.append(get_assoc_value(syns, key))
                row.append(get_assoc_value(ipens, key))
                row.append(get_assoc_value(rest_texts, key))
                row.append(get_assoc_value(next_lines, key))
                out_list.append(row)
                row=[]
            p_line_nr=line['line_nr']

        if len(out_list)>0:
            out_lists.append(out_list)

        header=[ 'index', 'family', 'genus', 'species', 'synonyms', 'IPEN', 'rest_texts', 'next_lines']
        if logging.root.level==logging.DEBUG:
            header.insert(0, '_line')

        return out_lists, header

    def main(self):
        for file in self.files:
            logging.info("processing '%s'" % (file))
            with open(file, "r") as f:
                doc=json.load(f)

            # num_pages=int(doc['document']['metadata']['xmpTPg:NPages'])

            all_lines=self.numbered_lines_from_doc(doc)

            lines=self.extract_lines(all_lines=all_lines)
            lines=self.genus_header_look_ahead(lines=lines, all_lines=all_lines)
            
            lines=self.synonyms_look_ahead(lines=lines)
            lines=self.extract_rest_texts(lines=lines, all_lines=all_lines)
            lines=self.add_unannotated_lines(lines=lines, all_lines=all_lines)
            lines=self.filter_useful_lines(lines=lines)
            
            lines=self.clean_up_list_indexes(lines=lines)
            

            output, header=self.compile_output(lines=lines)

            if len(output)==0 and self.exceptions_path:
                shutil.copy(file, self.exceptions_path)

            if self.output_path:
                self.output.csv(lists=output, header=header, output_path=self.get_output_path(file))

            if not self.output_path or logging.root.level==logging.DEBUG:
                self.output.stdout(lists=output, header=header)


if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('-i','--input-path', required=True)
    parser.add_argument('-o','--output-path')
    parser.add_argument('-d','--name-database', default='/data/seedlists/WFO_backbone.db3')
    parser.add_argument('--skip-existing', action='store_true', default=False)
    parser.add_argument('--exceptions-path')
    parser.add_argument('--debug', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    sp=SeedlistExtractor(
        input_path=args.input_path, 
        output_path=args.output_path,
        name_database=args.name_database,
        exceptions_path=args.exceptions_path,
        skip_existing=args.skip_existing,)

    sp.main()

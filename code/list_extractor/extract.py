import argparse
import logging
import json
import re
import sqlite3
import statistics
import pickle
import pprint
import xml.etree.ElementTree as ET
from pathlib import Path
from itertools import groupby
from output import Output
from checks import Checks

def pp(this):
    prp=pprint.PrettyPrinter(indent=4, width=100)
    prp.pprint(this)


class SeedlistExtractor:

    all_names_query="select * from name_lookup"

    name_abbr=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
               'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
               'var.', 'convar.', ]

    line_template={
        'line_nr': None,
        'page': 0,
        'raw': None, 
        'families': [],
        'genera': [],
        'species': [],
        'epithets': [],
        'index_raw': [],
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
                 exceptions_path=None,
                 suppress_stdout=False) -> None:

        self.config={
            'cache_names': True
        }

        self.files=[]
        self.pickle_file=Path("./pickles/names_pickle")
        self.output_path=None
        self.exceptions_path=None
        self.suppress_stdout=suppress_stdout

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
        self.families_seen=[]

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

    def get_lines(self, doc):

        def clean_line(text):
            if text:
                return text.replace('\t','    ').strip()
            else:
                return ''

        lines=[]
        
        try:
            root=ET.fromstring(doc['document']['content'])
            ns=re.sub('}html','}', root.tag)
            
            page=0
            line_nr=0
            for elem in root.iter():
                if elem.tag==f"{ns}div":
                    page+=1
                if elem.tag==f"{ns}p" and elem.text:
                    for line in elem.text.splitlines():
                        line=clean_line(line)
                        # print(line)
                        # print('-'*50)
                        if len(line.strip())>0:
                            new_line=self.line_template.copy()
                            new_line.update({'line_nr': line_nr, 'page': page, 'raw': line})
                            lines.append(new_line)
                            line_nr+=1

        except Exception as e:

            doc_lines=map(clean_line, doc['document']['content'].splitlines())
            for line_nr, line in enumerate(doc_lines):
                new_line=self.line_template.copy()
                new_line.update({'line_nr': line_nr, 'raw': line})
                lines.append(new_line)

        return lines

    def get_output_path(self, file):
        if self.output_path:
            output_path=self.output_path / Path((Path(file).parts[-1])).with_suffix(".csv")
            output_path=Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            return output_path

    def clean_up_name(self, name):
        return re.sub(r'(\s){1,}', ' ', re.sub(r'[^a-zA-Z ]', '', name)).strip()

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
                    start_cap=False if len(lookup)==0 else lookup[0].isupper()
                    lookup=lookup.lower()

                    if (rank=='families' and start_cap and lookup in self.families) \
                    or (rank=='genera' and start_cap and lookup in self.genera) \
                    or (rank=='species' and start_cap and lookup in self.species) \
                    or (rank=='epithets' and not start_cap and lookup in self.epithets):
                        candidates.append((i, j, lookup))

            if len(candidates)>0:
                # cleanup() takes out non-alpha chars, which will re-appear in the slicing
                # of the (uncleaned) tokens, so we take the longest of the (cleaned) candidates
                # that uses the smallest amount of tokens
                best=sorted(candidates, key=lambda x: (-len(x[2]), abs(x[1]-x[0]) ))[0]
                return tokens[best[0]:best[1]], (tokens[:best[0]], tokens[best[1]:])

            return None, (tokens, )
        
        tokens=text.strip().split()
        if len(tokens)==0 or len(tokens)>20:
            return []
        
        names=[]
        while True:
            name, rest=extract_name(tokens=tokens, rank=rank)
            if name is None:
                break
            cleaned, c_rest=remove_outer_non_alpha(' '.join(name))
            names.append(cleaned)
            tokens=[x for x in rest[0]+c_rest+rest[1] if len(x)>0]

        if rank=='families':
            self.families_seen.extend(names)

        return names

    def extract_syns(self, text):
        # regex=r'((\[|\()(sin|syn)\.?\:? ([^\]\)]*)(\]|\)))'
        regex=r'((\[|\()(sin|syn)\.?\:? (.*))'
        matches=re.findall(regex, text.strip(), re.UNICODE|re.IGNORECASE)
        results=[]
        if matches:
            for match in matches:
                names=self.extract_names(match[0], rank='species')
                if len(names)>0:
                    results.append((names[0], match[0]))
        return results

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
        regex=r'(([A-Za-z]{2})([—\-\. ]{1})([01]{1})([—\-\. ]{1})([A-Za-z]{1,5})([—\-\./ ]{1})([^\s\]]*))'
        matches=re.findall(regex, text.strip(), re.UNICODE)
        if matches:
            return [x[0] for x in matches]
        return []

    @staticmethod
    def extract_index_raw(text):
        matches=re.findall(r'((^|\s)([0-9]{1,5})[.\)°]?\s?)', text)
        if matches:
            return [x[0].strip() for x in matches]
        return []

    def extract_data(self, lines):
        for line in lines:
            if len(line['raw'])==0:
                continue

            syns_plus_noise=self.extract_syns(text=line['raw'])
            syns=[x[0] for x in syns_plus_noise]
            if len(syns)>0:
                line.update({'syns': syns})
                line.update({'_remove': [x[1] for x in syns_plus_noise]})

            for rank in ['families', 'genera', 'species', 'epithets']:
                names=self.extract_names(text=line['raw'], rank=rank)
                if len(names)>0:
                    if len(syns)>0:
                        names=[x for x in names if x not in syns]
                    line.update({rank: names})

            ipens=self.extract_ipens(text=line['raw'])
            if len(ipens)>0:
                line.update({'ipens': ipens})

            index_raw=self.extract_index_raw(text=line['raw'])
            if len(index_raw)>0:
                line.update({'index_raw': index_raw})

        return lines

    def genus_header_look_ahead(self, lines, all_lines):
        """
        Looks for genera are listed as 'header', with entries following only listed as epithet,
        and reassembles genus and epithet as full name.
        """

        updates=[]
        # look for isolated genera 
        for line in [x for x in lines if len(x['genera'])>0 and len(x['species'])==0]:

            # find the next item as the point where to stop looking ahead
            next_items=[x for x in lines 
                        if x['line_nr']>line['line_nr'] 
                        and (len(x['families'])>0 or len(x['genera'])>0 or len(x['species']))>0]

            start=line['line_nr']+1
            if len(next_items)>0:
                end=next_items[0]['line_nr']+1
            else:
                #TODO: magic number
                end=line['line_nr']+5

            # for all genera on ths line (in case of multiple columns, 
            # multiple genera might appear on one line), look for full names.
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
                    # longest candidate becomes the new name
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
        """
        Function looks for listed synonyms (syn. or sin.) and adds them to the preceding
        species name.
        """
        updates=[]
        for line in [x for x in lines if (len(x['species'])>0 or len(x['epithets'])>0)]:
            for next_line in [x for x in lines if x['line_nr']>line['line_nr'] ]:
                if len(next_line['species'])>0:
                    break
                if len(next_line['syns'])>0:
                    updates.append((next_line['syns'], line['line_nr']))
                    updates.append(([], next_line['line_nr']))
                    break

        for update in updates:
            existing=[x for x in lines if  x['line_nr']==update[1]]
            if len(existing)>0:
                if update[0]==[] and len(existing[0]['species'])==0:
                    # assume genera came from the synonyms, not remaining half species
                    existing[0].update({'genera': []})
                else:
                    existing[0].update({'syns': update[0]})

        return lines

    def fix_isolated_epithets(self, lines):
        updates=[]
        # look for isolated epithets 
        for line in [x for x in lines if len(x['epithets'])>0 and len(x['species'])==0]:

            # find the previous items with a genus
            prev_items=[x for x in lines 
                        if x['line_nr']<line['line_nr']  and (len(x['genera'])>0) ][::-1]

            if len(prev_items)==0:
                # nothing useful before the current item
                continue

            # for all epithets on ths line (in case of multiple columns, 
            # multiple epithets might appear on one line), look for full names.
            for key, epithet in enumerate(line['epithets']):
                if len(prev_items[0]['genera'])>=key+1:
                    genus=prev_items[0]['genera'][key]
                else:
                    genus=prev_items[0]['genera'][0]

                candidates=[(x, line['line_nr'], epithet) for x
                            in self.extract_names(text=f'{genus} {epithet}', 
                                                  rank='species')]

                if len(candidates)==0:
                    continue

                # longest candidate becomes a new name
                updates.append(sorted(candidates, key=lambda x: -len(x[0]))[0])

        for update in updates:
            existing=[x for x in lines if  x['line_nr']==update[1]]
            species=existing[0]['species'].copy()
            species.append(update[0])
            _remove=existing[0]['_remove'].copy()
            _remove.append(update[2])
            existing[0].update({'species': species, '_remove': _remove})

        return lines


    def ipens_look_ahead(self, lines):
        updates=[]

        for line in [x for x in lines if (len(x['species'])>0 or len(x['epithets'])>0) and len(x['ipens'])==0]:
            for next_line in [x for x in lines if x['line_nr']>line['line_nr'] ]:
                if len(next_line['species'])>0 or len(next_line['epithets'])>0:
                    break
                if len(next_line['ipens'])>0 and (next_line['line_nr']-line['line_nr'])<5:
                    updates.append((next_line['ipens'], line['line_nr']))
                    break

        for update in updates:
            existing=[x for x in lines if  x['line_nr']==update[1]]
            existing[0].update({'ipens': update[0]})

        return lines

    def clean_up_list_indexes(self, lines):
        # see if there's multiple possible indexes per row,
        # collect the values for each, and sort them
        columns={}
        for key, line in enumerate(lines):
            lines[key].update({'index': list(map(lambda x: int(''.join([y for y in x if y.isnumeric()])), line['index_raw']))})
            for lkey, idx in enumerate(lines[key]['index']):
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
                    if len(line['index'])>best_idx_key+1:
                        lines[key].update({'index': [line['index'][best_idx_key]]})
                        lines[key].update({'index_raw': [line['index_raw'][best_idx_key]]})
                else:
                    lines[key].update({'index': []})
                    lines[key].update({'index_raw': []})

        return lines

    def extract_rest_texts(self, lines):

        def remove_item(elements, item):
            remains=[]
            for element in elements:
                remains.extend(element.split(item))
            return remains

        for key, line in enumerate(lines):

            rest_texts=list(map(lambda x: re.sub(r'\s{1,}', ' ', x), [line['raw']]))

            # order matters (species before generea and epithets; IPENS before index_raw)
            # syns (literals, including '[syn.' and ']') are in _remove
            for attr in ['species', 'families', 'genera', 'epithets', 'ipens', 'index_raw', '_remove']:
                if attr in line:
                    for item in line[attr]:
                        rest_texts=remove_item(elements=rest_texts, item=item)

            lines[key]['rest_texts']=list(map(lambda x: x.strip(),filter(lambda x: len(x.strip())>0, rest_texts)))
            if '_remove' in lines[key]:
                del lines[key]['_remove']

        return lines

    def add_unannotated_lines(self, lines, all_lines, max_look_ahead=5):
        next_lines=[]
        # for all 'main entries' (w/ species or genus), look for following lines
        for line in [x for x in lines if len(x['genera'])>0 or len(x['species'])>0]:

            next_items=[x for x in lines 
                        if x['line_nr']>line['line_nr'] 
                        and (len(x['families'])+len(x['genera'])+len(x['species'])+len(x['syns']))>0]

            start=line['line_nr']+1
            if len(next_items)>0:
                end=next_items[0]['line_nr']
            else:
                end=line['line_nr']+max_look_ahead

            # select the appropriate lines from the original raw lines (returns list of (line, line_nr)).
            candidate_lines=[x for x in all_lines[start:end] if len(x[0])>0]

            if len(candidate_lines)>0:
                n_lines=[]
                # if one of these candidate lines was a;lready annotated, use the rest texts 
                # of that line (which has IPENs etc removed); otherwise, use the raw original line.
                for candidate_line in candidate_lines:
                    existing=[x for x in lines if x['line_nr']==candidate_line[1]]
                    if len(existing)==1:
                        n_lines.append(" ".join(existing[0]['rest_texts']))
                    else:
                        n_lines.append(candidate_line[0])
                next_lines.append((n_lines, line['line_nr']))

        for next_line in next_lines:
            existing=[x for x in lines if x['line_nr']==next_line[1]]
            existing[0].update({'next_lines': next_line[0]})

        return lines

    def filter_useful_lines(self, lines):
        lines=[x for x in lines if (len(x['families'])+len(x['genera'])+len(x['species']))>0]
        lines=sorted(lines, key=lambda x: x['line_nr'])
        return lines

    # def compile_output(self, lines):

    #     def set_assoc_values(val_list, line, key):
    #         if len(line[key])>0:
    #             val_list.clear()
    #             val_list.extend(line[key])

    #     def get_assoc_value(values, key):
    #         if values:
    #             return values[key] if key in values else '; '.join(list(map(lambda x: str(x), values)))
    #         return ''

    #     def get_line_space_distr(lines):
    #         line_spaces=[]
    #         p_line_nr=0
    #         for line in lines:
    #             line_spaces.append(line['line_nr']-p_line_nr)
    #             p_line_nr=line['line_nr']
    #         if len(line_spaces)<2:
    #             return 0, 0

    #         mean=statistics.mean(line_spaces)
    #         stdev=statistics.stdev(line_spaces, xbar=mean)
    #         return mean, stdev

    #     mean, stdev=get_line_space_distr(lines)

    #     logging.debug("line space mean: %s; stdev: %s" % (mean, stdev))

    #     out_lists=[]
    #     out_list=[]

    #     row=[]
    #     p_line_nr=0

    #     families=[]
    #     genera=[]

    #     for line in lines:
    #         index_raw=[]
    #         ipens=[]
    #         syns=[]
    #         rest_texts=[]
    #         next_lines=[]

    #         if ((line['line_nr']-p_line_nr)>(mean+(stdev*2)) and len(out_list)>0):
    #             out_lists.append(out_list)
    #             logging.debug("extracted list #%s with %s row(s)" % (len(out_lists), len(out_list)))
    #             out_list=[]

    #         set_assoc_values(val_list=index_raw, line=line, key='index')
    #         set_assoc_values(val_list=families, line=line, key='families')
    #         set_assoc_values(val_list=genera, line=line, key='genera')
    #         set_assoc_values(val_list=ipens, line=line, key='ipens')
    #         set_assoc_values(val_list=syns, line=line, key='syns')
    #         set_assoc_values(val_list=rest_texts, line=line, key='rest_texts')
    #         set_assoc_values(val_list=next_lines, line=line, key='next_lines')

    #         # index_raw=list(map(lambda x: int(re.sub(r'[^0-9]', '', x)), index_raw))

    #         if len(line['species'])==0:
    #             for key, item in enumerate(line['genera']):
    #                 if logging.root.level==logging.DEBUG:
    #                     row.append(line['line_nr'])
    #                 row.extend([get_assoc_value(index_raw, key), get_assoc_value(families, key)])
    #                 row.append(item)
    #                 row.extend(['', ''])
    #                 row.append(get_assoc_value(ipens, key))
    #                 row.append(get_assoc_value(rest_texts, key))
    #                 row.append(get_assoc_value(next_lines, key))
    #                 out_list.append(row)
    #                 row=[]

    #         for key, item in enumerate(line['species']):
    #             if logging.root.level==logging.DEBUG:
    #                 row.append(line['line_nr'])
    #             row.append(get_assoc_value(index_raw, key))
    #             row.append(get_assoc_value(families, key))
    #             row.append('')
    #             row.append(item)
    #             row.append(get_assoc_value(syns, key))
    #             row.append(get_assoc_value(ipens, key))
    #             row.append(get_assoc_value(rest_texts, key))
    #             row.append(get_assoc_value(next_lines, key))
    #             out_list.append(row)
    #             row=[]
    #         p_line_nr=line['line_nr']

    #     if len(out_list)>0:
    #         out_lists.append(out_list)

    #     header=[ 'index', 'family', 'genus', 'species', 'synonyms', 'IPEN', 'rest_texts', 'next_lines']
    #     if logging.root.level==logging.DEBUG:
    #         header.insert(0, '_line')

    #     return out_lists, header

    def main(self):
        for file in self.files:
            logging.info("processing '%s'" % (file))
            with open(file, "r") as f:
                doc=json.load(f)

            lines=self.get_lines(doc)
            lines=self.extract_data(lines=lines)

            # lines=self.genus_header_look_ahead(lines=lines, all_lines=all_lines)
            # lines=self.synonyms_look_ahead(lines=lines)
            # lines=self.ipens_look_ahead(lines=lines)
            # lines=self.fix_isolated_epithets(lines=lines)
            # lines=self.clean_up_list_indexes(lines=lines)
            # lines=self.extract_rest_texts(lines=lines)

            pages=self.collect_lists(lines=lines)
            lists=self.compile_records(lines=lines, pages=pages)

            output=self.compile_output(lists=lists)
            header=['list', 'name', 'ipen', 'metadata']

            # pp(output)
            # exit()

            # lines=self.add_unannotated_lines(lines=lines, all_lines=all_lines)
            # lines=self.filter_useful_lines(lines=lines)

            # output, header=self.compile_output(lines=lines)

            # self.checks=Checks(file=file, output=output, header=header)
            # self.checks.check_families(families_seen=self.families_seen)
            # self.checks.copy_erroneous(target_path=self.exceptions_path)

            if self.output_path:
                # self.output.csv(lists=output, header=header, output_path=self.get_output_path(file))
                self.output.csv(lines=output, header=header, output_path=self.get_output_path(file))

            # if (not self.output_path or logging.root.level==logging.DEBUG) and not self.suppress_stdout:
            #     self.output.stdout(lists=output, header=header)

    def collect_lists(self, lines):

        def get_item_order(families, names, ipens):
            item_order=['species', 'ipen']

            if len(ipens)==0:
                item_order.remove('ipen')
            else:
                item_order.remove(first)
                item_order.insert(0, first)

            if len(families)>0:
                item_order.insert(0, 'family')

            if len(names)==0:
                item_order=[]

            return item_order

        pages=[]
        groups=[]

        for page, group in groupby(lines, key=lambda x: x['page']):
            groups.append((page, list(group)))

        families=[]
        names=[]
        ipens=[]
        first=None
        start_page=None

        for page, group in groups:
            start_page=page if start_page is None else start_page
            empty=0
            empty_sections=[]
            for line in group:
                if len(line['species'])>0 or len(line['ipens'])>0:
                    empty_sections.append(empty)
                    empty=0
                else:
                    empty+=1

                families.append((line['families'], line['line_nr']))
                names.append((line['species'], line['line_nr']))
                ipens.append((line['ipens'], line['line_nr']))

                families=[x for x in families if len(x[0])>0]
                names=[x for x in names if len(x[0])>0]
                ipens=[x for x in ipens if len(x[0])>0]

                if len(line['species'])>0 and first is None:
                    first='species'

                if len(line['ipens'])>0 and first is None:
                    first='ipen'

            empty_sections.append(empty)

            if len(set([x for x in empty_sections if x>0]))>1:
                mean=statistics.mean([x for x in empty_sections if x>0])
                stddev=statistics.stdev([x for x in empty_sections if x>0], xbar=mean)
                list_ends=empty>(mean+stddev)
            else:
                list_ends=False

            if list_ends:
                pages.append({
                    'page': start_page,
                    'families': families,
                    'names': names,
                    'ipens': ipens,
                    'item_order': get_item_order(families, names, ipens),
                    'list_ends': list_ends,
                    'records': []
                    })

                names=[]
                ipens=[]
                start_page=None

        if len(names)>0:
            pages.append({
                'page': start_page,
                'families': families,
                'names': names,
                'ipens': ipens,
                'item_order': get_item_order(families, names, ipens),
                'list_ends': list_ends,
                'records': []
                })

        return pages

    def compile_records(self, lines, pages):

        def get_assoc_attribute_value(attribute, attribute_values, item_order, current_name):
            result=None
            if attribute in item_order:
                if item_order.index(attribute) < item_order.index('species'):
                    candidates=[x for x in attribute_values if x[1]<=current_name[1]]
                    candidates=sorted(candidates, key=lambda x: -x[1])
                else:
                    candidates=[x for x in ipens if x[1]>=current_name[1]]
                    candidates=sorted(candidates, key=lambda x: x[1])
            
                if len(candidates)>0:
                    result=candidates[0]

            return result

        def get_metadata(name, next_name):
            if (next_name is None) or (next_name[1]>name[1]+5):
                next_lines=[x for x in lines if x['line_nr']>name[1] and len(x['raw'])>0]
                if len(next_lines)==0:
                    end=name[1]+1
                elif len(next_lines)>5:
                    end=name[1]+5
                else:
                    end=next_lines[-1]['line_nr']
            else:
                end=next_name[1]
                 
            items=[x for x in lines if x['line_nr'] in range(name[1], end)]
            meta=[]

            for item in items:
                if len(item['families'])>0:
                    continue
                raw=item['raw']
                raw=re.sub(r'\s+', ' ', raw)
                for element in [name, ipen]:
                    if element is None:
                        continue
                    if item['line_nr']==element[1]:
                        for this in element[0]:
                            raw=raw.replace(this, '')

                meta.append(re.sub(r'\s+', ' ', raw).strip())

            return meta

        records=[]
        for page in pages:
            if len(page['item_order'])==0:
                continue

            families=page['families'].copy()
            names=page['names'].copy()
            ipens=page['ipens'].copy()

            while len(names)>0:
                current_name=names.pop(0)
                ipen=get_assoc_attribute_value(
                    attribute='ipen',
                    item_order=page['item_order'],
                    attribute_values=ipens,
                    current_name=current_name
                )
                if ipen:
                    ipens.remove(ipen)

                family=get_assoc_attribute_value(
                    attribute='family',
                    item_order=page['item_order'],
                    attribute_values=families,
                    current_name=current_name
                )
                # if family:
                #     families.remove(family)

                meta=get_metadata(current_name, names[0] if len(names)>0 else None)
                records.append({
                    'name': current_name,
                    'ipen': ipen,
                    'family': family,
                    'meta': meta
                    })
            
            page.update({'records': records})

        return pages

    @staticmethod
    def compile_output(lists):
        lines=[]
        for key, page in enumerate(lists):
            for record in page['records']:
                family=record['family'][0][0] if isinstance(record['family'], tuple) else ''
                ipen=record['ipen'][0][0] if isinstance(record['ipen'], tuple) else ''
                name=record['name'][0][0]
                # lines.append((page['page'], record['name'][0], ipen, record['meta']))
                lines.append((key, family, name, ipen, " ".join(record['meta'])))
        return lines





if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('-i','--input-path', required=True)
    parser.add_argument('-o','--output-path')
    parser.add_argument('-d','--name-database', default='/data/seedlists/WFO_backbone.db3')
    parser.add_argument('--skip-existing', action='store_true', default=False)
    parser.add_argument('--exceptions-path')
    parser.add_argument('--debug', action='store_true', default=False)
    parser.add_argument('--suppress-stdout', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    sp=SeedlistExtractor(
        input_path=args.input_path, 
        output_path=args.output_path,
        name_database=args.name_database,
        exceptions_path=args.exceptions_path,
        skip_existing=args.skip_existing,
        suppress_stdout=args.suppress_stdout,)

    sp.main()

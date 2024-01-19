import argparse
import logging
import json
import re
import statistics
import pprint
import xml.etree.ElementTree as ET
from math import ceil
from pathlib import Path
from itertools import groupby
from output import Output
from name_resolver import NameResolver

def pp(this):
    prp=pprint.PrettyPrinter(indent=4, width=100, sort_dicts=False)
    prp.pprint(this)

class SeedlistExtractor:

    name_abbr=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
               'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
               'var.', 'convar.', ]

    line_template={
        'line_nr': None,
        'page': 0,
        'raw': None, 
        'family': [],
        'genus': [],
        'species': [],
        'epithet': [],
        'cultivar': [],
        'index_raw': [],
        'ipen': [],
        'syn': [],
        'rest_texts': [],
        'next_lines': [],
        '_remove': [], }

    def __init__(self, 
                 input_path, 
                 output_path,
                 name_resolver,
                 fuzzy_name_match=True,
                 lines=None,
                 skip_existing=False,
                 exceptions_path=None,
                 suppress_stdout=False) -> None:

        self.files=[]
        self.output_path=None
        self.exceptions_path=None
        self.suppress_stdout=suppress_stdout
        self.name_resolver=name_resolver
        self.fuzzy_name_match=fuzzy_name_match
        self.lines=lines

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

    def get_lines(self, doc):

        """
        Reads raw data from either XML or JSON, exported from Apache Tika.
        Tika's XML includes page numbers, which are absent from the JSON output.
        """

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
                        # if len(line.strip())>0:
                        new_line=self.line_template.copy()
                        new_line.update({'line_nr': line_nr, 'page': page, 'raw': line})
                        lines.append(new_line)
                        line_nr+=1

            logging.debug(f"read {len(lines)} lines from XML")

        except Exception as e:

            doc_lines=map(clean_line, doc['document']['content'].splitlines())
            for line_nr, line in enumerate(doc_lines):
                new_line=self.line_template.copy()
                new_line.update({'line_nr': line_nr, 'raw': line})
                lines.append(new_line)

            logging.debug(f"read {len(lines)} lines from JSON")

        return lines

    def get_output_path(self, file):
        if self.output_path:
            output_path=self.output_path / Path((Path(file).parts[-1])).with_suffix(".csv")
            output_path=Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            return output_path

    def clean_up_name(self, name):
        return re.sub(r'(\s){1,}', ' ', re.sub(r'[^a-zA-Z ]', '', name)).strip()

    def remove_abbreviations(self, name, abbreviations=None):
        if abbreviations is None:
            abbreviations=self.name_abbr 
        return ' '.join([x for x in name.split() if x not in abbreviations])

    @staticmethod
    def remove_outer_non_alpha(text):
        regex=r'(^[^a-zA-Z]{1,}|[^a-zA-Z\.\)]{1,}$)'
        cleaned=re.sub(regex, '', text.strip(), re.UNICODE)
        if cleaned != text:
            return cleaned, text.split(cleaned)
        return text, ['','']

    def extract_names(self, text, rank):

        def extract_name(tokens, rank, epithet_starts_lower=True, genus_starts_upper=True):
            min_token_len=1

            if rank=='species':
                min_token_len=2

            candidates=[]

            for i in range(0, len(tokens)):
                for j in range(len(tokens), 0, -1):
                    if j-i<min_token_len:
                        break

                    lookup=self.clean_up_name(self.remove_abbreviations(name=' '.join(tokens[i:j])))

                    if len(lookup)==0:
                        continue

                    if rank=='genus' and genus_starts_upper and lookup[0].islower():
                        continue

                    if rank=='epithet' and epithet_starts_lower and lookup[0].isupper():
                        continue

                    match, score=self.name_resolver.match_exact(lookup=lookup, rank=rank)

                    if match:
                        # candidates.append((i, j, lookup, match, score))
                        candidates.append((i, j, match, score))

            if len(candidates)>0:
                # cleanup() takes out non-alpha chars, which will re-appear in the slicing
                # of the (uncleaned) tokens, so we take the longest of the (cleaned) candidates
                # that uses the smallest amount of tokens
                i, j, match, score=sorted(candidates, key=lambda x: (-len(x[2]), abs(x[1]-x[0]) ))[0]

                return tokens[i:j], (tokens[:i], tokens[j:]), match, score

            return None, (tokens, ), None, 0
        
        def extraction_loop(tokens, rank, names):
            while True:
                name, rest, match, score=extract_name(tokens=tokens, rank=rank)
                if name is None:
                    break
                cleaned, c_rest=self.remove_outer_non_alpha(' '.join(name))
                names.append((cleaned, match, score))
                tokens=[x for x in rest[0]+c_rest+rest[1] if len(x)>0]
            return names, tokens

        tokens=text.strip().split()
        if len(tokens)==0 or len(tokens)>50:
            return []
        
        names=[]
        names, remaining_tokens=extraction_loop(tokens=tokens, rank=rank, names=names)

        return names, remaining_tokens

    #TODO: DOES THIS STILL WORK?
    def extract_syns(self, text):
        # regex=r'((\[|\()(sin|syn)\.?\:? ([^\]\)]*)(\]|\)))'
        regex=r'((\[|\()(sin|syn)\.?\:? (.*))'
        matches=re.findall(regex, text.strip(), re.UNICODE|re.IGNORECASE)
        results=[]
        if matches:
            for match in matches:
                names, _=self.extract_names(match[0], rank='species')
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

    @staticmethod
    def extract_cultivars(text):
        #TODO: could be more elegant
        regex=r'(‘[A-Za-z ]+’|´[A-Za-z ]+´|\'[A-Za-z ]+\'|"[A-Za-z ]+"|\([A-Za-z ]+form\))'
        matches=re.findall(regex, text.strip(), re.UNICODE|re.IGNORECASE)
        return matches

    def extract_data(self, lines):

        def remove_from_rest_tokens(values, rest_tokens):
            tokens=[]
            [tokens.extend(item.split()) for item in values]
            return [x for x in rest_tokens if x not in tokens]

        names_start=-1
        names_end=int(1e6)
        
        for line in lines:

            if self.lines is not None and line['line_nr'] not in self.lines:
                # logging.debug("skipping line %s" % line['line_nr'])
                continue

            if len(line['raw'])==0:
                # logging.debug("empty line %s" % line['line_nr'])
                continue

            # logging.debug("line %s" % line['line_nr'])

            #TODO DOES THIS STILL WORK?
            syns=self.extract_syns(text=line['raw'])
            line.update({'syn': syns})
            line.update({'_remove': [syn for syn, _ in syns]})

            names, rest_tokens=self.extract_names(text=line['raw'], rank='species')
            names=[x for x in names if x not in syns]
            line.update({'species': names})

            names, rest_too=self.extract_names(text=line['raw'], rank='family')
            line.update({'family': names})
            rest_tokens=list(set(rest_tokens) & set(rest_too))

            if len(line['species'])==0:
                for rank in ['genus', 'epithet']:
                    names, rest_too=self.extract_names(text=line['raw'], rank=rank)
                    line.update({rank: names})
                    rest_tokens=list(set(rest_tokens) & set(rest_too))

            if len(line['species']+line['epithet'])>0:
                cultivars=self.extract_cultivars(text=line['raw'])
                line.update({'cultivar': cultivars})
                rest_tokens=remove_from_rest_tokens(values=line['cultivar'], rest_tokens=rest_tokens)
                names_start=names_start if names_start>-1 else line['line_nr']
                names_end=line['line_nr']

            ipens=self.extract_ipens(text=line['raw'])
            line.update({'ipen': ipens})
            rest_tokens=remove_from_rest_tokens(values=line['ipen'], rest_tokens=rest_tokens)

            index_raw=self.extract_index_raw(text=line['raw'])
            line.update({'index_raw': index_raw})
            rest_tokens=remove_from_rest_tokens(values=line['index_raw'], rest_tokens=rest_tokens)

            line.update({'_rest_tokens':rest_tokens})


        if False and self.fuzzy_name_match:

            buffer=10
            buffer=2

            for rank in ['species', 'epithet']:

                string_list=[]
                for i in range(names_start-buffer, names_end+buffer):
                    line=[x for x in lines if x['line_nr']==i]
                    if not line or len(line[0]['raw'])==0:
                        continue

                    if len(line[0][rank])>0:
                        continue
                    
                    # print(line)
                    string_list.append((i, line[0]['raw'], []))


                names=self.extract_names_fuzzy(string_list=string_list, rank=rank)
                print(names)
                exit()
                # if species names, skip the epithet


            """
            python extract.py -i '/data/seedlists/2020_sample_seedlists/json/ABD-2020-x-x-x-1-x.json' --debug  --suppress-stdout

            Nexts steps:
            - fuzzy lookup still also returns perfect matches (score 1), which
                should have been found earlier? --> take out unnecessary lookups for performance
            - the token numbers (i, j) that are included in the return no longer have meaning
            - extract_names_fuzzy() currently doesn't return anything
            - add the fuzzy matches to the line
            - remove them from the rest tokens
            - can the rest tokens replace the rest_texts attribute?
            - code beyond this point still thinks names=[name, ] rather than [(name, match, score),  ]
            - check #TODO's
            """

                # print(rank)
                # group_list = [(k, list(g)) for k, g in names]                
                # print(group_list)
                # for k, groups in names:
                #     # group candidate matches by line
                #     for line_nr, group in groups:
                #         print(list(group))
                #         # sort: longest name using the smallest number of tokens
                #         i, j, match, score, _=sorted(group, key=lambda x: (-len(x[2]), abs(x[1]-x[0]) ))[0]
                #         print(rank, line_nr, i, j, match, score)
                # break







                # return tokens[i:j], (tokens[:i], tokens[j:]), match, score

        return lines

    def extract_names_fuzzy(self, string_list, rank):

        def generate_candidates(tokens, rank, exclude):
            max_token_length=8
            min_token_len=1
            if rank=='species':
                min_token_len=2

            candidates=[]
            
            exclude=[self.clean_up_name(self.remove_abbreviations(name)) for name, _, _ in exclude]
            
            for i in range(0, len(tokens)):
                for j in range(len(tokens), 0, -1):
                    if j-i<min_token_len:
                        break
                    if j-i>max_token_length:
                        break

                    lookup=self.clean_up_name(self.remove_abbreviations(name=' '.join(tokens[i:j])))

                    if len(lookup)>0 and lookup not in exclude:
                        candidates.append((i, j, lookup))

            return candidates

        lookups=[]
        for line_nr, string, exclude in string_list:
            
            tokens=string.strip().split()

            # generate candidate sets of tokens to check for names
            # but exclude canidates that already have been extracted as name
            candidates=generate_candidates(tokens, rank, exclude)
            if len(candidates)>0:
                lookups.extend([(lookup, (line_nr, i, j)) for i, j, lookup in candidates])


        lookups=[('Viburnum opulus', (83, 0, 4))]
        print(rank)
        print(lookups)
        matches=self.name_resolver.diff_lib_matcher(lookup=lookups, rank=rank)
        exit()

        # lookup matches for all candidates        
        matches=self.name_resolver.match_fuzzy(lookup=lookups, rank=rank, assume_correct_start=1)
        candidate_matches=[]
        for lookup, ((match, score), meta) in matches.items():
            if score>0:
                logging.debug(f'fuzzy lookup: {lookup:<25} --> {match:<25} ({score:<18}) {meta} [{rank}]')
                line_nr, i, j = meta
                # repackage for easier processing
                candidate_matches.append((i, j, match, score, line_nr))

        # print(candidate_matches)
        # return groupby(candidate_matches, key=lambda x: x[4])
        group_list = [(k, list(g)) for k, g in groupby(candidate_matches, key=lambda x: x[4])]
        # print(group_list)

    def connect_synonyms(self, lines):
        """
        Function looks for listed synonyms (syn. or sin.) and adds them to the preceding
        species name.
        """
        updates=[]
        for line in [x for x in lines if (len(x['species'])>0 or len(x['epithet'])>0)]:
            for next_line in [x for x in lines if x['line_nr']>line['line_nr'] ]:
                if len(next_line['species'])>0:
                    break
                if len(next_line['syn'])>0:
                    updates.append((next_line['syn'], line['line_nr']))
                    updates.append(([], next_line['line_nr']))
                    break

        for update in updates:
            existing=[x for x in lines if  x['line_nr']==update[1]]
            if len(existing)>0:
                if update[0]==[] and len(existing[0]['species'])==0:
                    # assume genera came from the synonyms, not remaining half species
                    existing[0].update({'genus': []})
                else:
                    existing[0].update({'syn': update[0]})

        return lines

    def fix_isolated_epithets(self, lines):
        updates=[]
        # look for isolated epithets 
        for line in [x for x in lines if len(x['epithet'])>0 and len(x['species'])==0]:

            # find the previous items with a genus
            prev_items=[x for x in lines 
                        if x['line_nr']<line['line_nr']  and (len(x['genus'])>0) ][::-1]

            if len(prev_items)==0:
                # nothing useful before the current item
                continue

            # for all epithets on ths line (in case of multiple columns, 
            # multiple epithets might appear on one line), look for full names.
            for key, epithet in enumerate(line['epithet']):
                if len(prev_items[0]['genus'])>=key+1:
                    genus=prev_items[0]['genus'][key]
                else:
                    genus=prev_items[0]['genus'][0]

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
            apply=(stats[0][1]/len([x for x in lines if len(x['epithet'])>0 or len(x['species'])>0]))>0.75
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

    def add_unannotated_lines(self, lines, max_look_ahead=5):

        next_lines=[]
        # for all 'main entries' (w/ species or genus), look for following lines
        # TODO: why genus?
        for line in [x for x in lines if len(x['genus'])>0 or len(x['species'])>0]:

            next_items=[x for x in lines 
                        if x['line_nr']>line['line_nr'] 
                        and (len(x['family'])+len(x['genus'])+len(x['species'])+len(x['syn']))>0]

            start=line['line_nr']+1
            if len(next_items)>0:
                end=next_items[0]['line_nr']
            else:
                end=line['line_nr']+max_look_ahead

            # select the appropriate lines from the original raw lines (returns list of (line, line_nr)).
            # candidate_lines=[(x['raw'], x['line_nr']) for x in lines[start:end] if len(x['raw'])>0]
            candidate_lines=[(x['raw'], x['line_nr']) for x in lines[start:end]]

            if len(candidate_lines)>0:
                n_lines=[]
                # if one of these candidate lines was already annotated, use the rest texts 
                # of that line (which has IPENs etc removed); otherwise, use the raw original line.
                for candidate_line in candidate_lines:

                    if len(candidate_line[0].strip())==0:
                        break

                    existing=[x for x in lines if x['line_nr']==candidate_line[1]]

                    if len(existing)==1:
                        n_lines.append(" ".join(existing[0]['rest_texts']))
                    else:
                        n_lines.append(candidate_line[0])

                next_lines.append((n_lines, line['line_nr']))

        #TODO: check if useful, or find another way of removing extra lines
        # if True:
        #     # dropping the next lines that are too long
        #     lengths=[]
        #     for next_line in next_lines:
        #         lengths.extend([len(x) for x in next_line[0]])

        #     mean=statistics.mean(lengths)
        #     stddev=statistics.stdev(lengths, xbar=mean)

        #     new=[]
        #     for next_line in next_lines:
        #         shorter=[x for x in next_line[0] if len(x)<(mean+stddev)]
        #         if len(shorter)>0:
        #             new.append((shorter, next_line[1]))

        #     next_lines=new
            

        for next_line in next_lines:
            existing=[x for x in lines if x['line_nr']==next_line[1]]
            existing[0].update({'next_lines': next_line[0]})

        return lines

    def main(self):
        for file in self.files:
            logging.info("processing '%s'" % (file))
            with open(file, "r") as f:
                doc=json.load(f)

            lines=self.get_lines(doc)
            lines=self.extract_data(lines=lines)
            lines=self.connect_synonyms(lines=lines)
            lines=self.fix_isolated_epithets(lines=lines)
            lines=self.clean_up_list_indexes(lines=lines)
            lines=self.add_unannotated_lines(lines=lines)

            print(lines)
            exit()            

            pages=self.output.collect_lists(lines=lines)
            lists=self.output.compile_records(lines=lines, pages=pages)
            output=self.output.compile_output(lists=lists)

            #TODO
            # self.checks=Checks(file=file, output=output)
            # self.checks.check_families(families_seen=self.families_seen, family_key=self.output.header.index('family'))
            # self.checks.copy_erroneous(target_path=self.exceptions_path)

            if self.output_path:
                self.output.csv(lines=output, output_path=self.get_output_path(file))

            if (not self.output_path or logging.root.level==logging.DEBUG) and not self.suppress_stdout:
                self.output.stdout(lines=output)

        logging.debug("finished '%s'" % (file))

if __name__=="__main__":

    def lines_range(c):
        c=c.split('-')
        return range(int(c[0]), int(c[1]))

    parser=argparse.ArgumentParser()
    parser.add_argument('-i','--input-path', required=True)
    parser.add_argument('-o','--output-path')
    parser.add_argument('-d','--names-database')
    parser.add_argument('--force-names-reload', action='store_true', default=False)
    parser.add_argument('--no-fuzzy-name-match', action='store_true', default=False)
    parser.add_argument('--skip-existing', action='store_true', default=False)
    parser.add_argument('--exceptions-path')
    parser.add_argument('--debug', action='store_true', default=False)
    parser.add_argument('--suppress-stdout', action='store_true', default=False)
    parser.add_argument('--lines', type=lines_range, help='lines to process (start-end)')
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    nres=NameResolver(
        names_database=args.names_database,
        force_names_reload=args.force_names_reload,)

    spe=SeedlistExtractor(
        input_path=args.input_path, 
        output_path=args.output_path,
        name_resolver=nres,
        exceptions_path=args.exceptions_path,
        skip_existing=args.skip_existing,
        suppress_stdout=args.suppress_stdout,
        lines=args.lines,
        fuzzy_name_match=not args.no_fuzzy_name_match,)

    spe.main()

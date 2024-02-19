import argparse
import logging
import json
import statistics
import pprint
from pathlib import Path
from output import Output
from extract_data import ExtractData
from utils import get_lines

def pp(this):
    prp=pprint.PrettyPrinter(indent=4, width=100, sort_dicts=False)
    prp.pprint(this)

class SeedlistExtractor:

    def __init__(self, 
                 input_path, 
                 output_path,
                 names_database,
                 logger,
                 force_names_reload=False,
                 fuzzy_name_match=True,
                 include_lines=None,
                 skip_existing=False,
                 exceptions_path=None,
                 suppress_stdout=False) -> None:

        self.files=[]
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

        if exceptions_path:
            self.exceptions_path=Path(exceptions_path)
            self.exceptions_path.mkdir(parents=True, exist_ok=True)

        self.data_extractor=ExtractData(
            include_lines=include_lines,
            fuzzy_name_match=fuzzy_name_match,
            names_database=names_database,
            force_names_reload=force_names_reload,
            logger=logger)

        self.output=Output(
            output_path=output_path,
            skip_existing=skip_existing,
            logger=logger)

        self.logger=logger
        self.logger.info("got %s file(s) from '%s'" % (len(self.files), p))

    @staticmethod
    def add_following_synonyms(lines):
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
                            in self.data_extractor.extract_names(text=f'{genus} {epithet}', 
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

    @staticmethod
    def clean_up_list_indexes(lines):
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
                        # lines[key].update({'index_raw': [line['index_raw'][best_idx_key]]})
                else:
                    lines[key].update({'index': []})
                    # lines[key].update({'index_raw': []})
                del lines[key]['index_raw']

        return lines

    @staticmethod
    def add_meta_data(lines, max_look_ahead=5):

        next_lines=[]
        # all 'main entries' w/ species
        for line in [x for x in lines if len(x['species'])>0]:

            # promote remaining tokens from the same line to meta data
            if '_rest_tokens' in line:
                line.update({'meta_rest': line['_rest_tokens']})
                del line['_rest_tokens']

            # look for the next line with some name; everything between current line
            # and that line is considered meta data
            next_items=[x for x in lines 
                        if x['line_nr']>line['line_nr'] 
                        and (len(x['family'])+len(x['genus'])+len(x['species'])+len(x['syn']))>0]

            start=line['line_nr']+1
            if len(next_items)>0:
                end=next_items[0]['line_nr']
            else:
                end=line['line_nr']+max_look_ahead

            # select the original raw lines (returns list of (line, line_nr)).
            candidate_lines=[(x['raw'], x['line_nr']) for x in lines[start:end]]

            if len(candidate_lines)>0:
                n_lines=[]
                # if one of these candidate lines was already annotated, use the rest texts 
                # of that line (which has IPENs etc removed); otherwise, use the raw original line.
                for candidate_line in candidate_lines:

                    if len(candidate_line[0].strip())==0:
                        break

                    existing=[x for x in lines if x['line_nr']==candidate_line[1]]

                    if len(existing)==1 and '_rest_tokens' in existing[0]:
                        n_lines.append(" ".join(existing[0]['_rest_tokens']))
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
            existing[0].update({'meta_next': next_line[0]})

        return lines

    def main(self):
        for file in self.files:
            self.logger.info("processing '%s'" % (file))
            with open(file, "r") as f:
                doc=json.load(f)

            lines=get_lines(doc)
            lines=self.data_extractor.extract(lines=lines)
            lines=self.add_following_synonyms(lines=lines)
            lines=self.fix_isolated_epithets(lines=lines)
            lines=self.clean_up_list_indexes(lines=lines)
            lines=self.add_meta_data(lines=lines)

            pages=self.output.collect_lists(lines=lines)
            lists=self.output.compile_records(lines=lines, pages=pages)
            output=self.output.compile_output(lists=lists)

            #TODO
            # self.checks=Checks(file=file, output=output)
            # self.checks.check_families(families_seen=self.families_seen, family_key=self.output.header.index('family'))
            # self.checks.copy_erroneous(target_path=self.exceptions_path)

            if self.output.output_path:
                self.output.csv(lines=output, source_file=file)

            if (not self.output.output_path or logging.root.level==logging.DEBUG) and not self.suppress_stdout:
                self.output.stdout(lines=output)

        self.logger.debug("finished '%s'" % (file))

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

    logger=logging.getLogger()
    logger.setLevel(logging.DEBUG if args.debug else logging.INFO)

    spe=SeedlistExtractor(
        input_path=args.input_path, 
        output_path=args.output_path,
        names_database=args.names_database,
        force_names_reload=args.force_names_reload,
        exceptions_path=args.exceptions_path,
        skip_existing=args.skip_existing,
        suppress_stdout=args.suppress_stdout,
        include_lines=args.lines,
        fuzzy_name_match=not args.no_fuzzy_name_match,
        logger=logger)

    spe.main()

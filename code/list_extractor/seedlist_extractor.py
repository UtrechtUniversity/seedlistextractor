import logging
import pprint

def pp(this):
    prp=pprint.PrettyPrinter(indent=4, width=100, sort_dicts=False)
    prp.pprint(this)

class SeedlistExtractor:

    def __init__(self, 
                 document, 
                 data_extractor,
                 output,
                 logger,
                 no_stdout=False) -> None:
        self.document=document
        self.no_stdout=no_stdout
        self.logger=logger
        self.data_extractor=data_extractor
        self.output=output
        self.main()

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

                text=f'{genus.match} {epithet.match}'
                names, _=self.data_extractor.extract_names(text=text, rank='species', line_nr=line['line_nr'])
                candidates=[(x, line['line_nr'], epithet) for x in names]

                if len(candidates)==0:
                    continue

                # longest candidate becomes a new name
                updates.append(sorted(candidates, key=lambda x: -len(x[0].match))[0])

        for update in updates:
            existing=[x for x in lines if  x['line_nr']==update[1]]
            species=existing[0]['species'].copy()
            species.append(update[0])
            existing[0].update({'species': species})

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
        lines=self.data_extractor.extract(lines=self.document)
        lines=self.add_following_synonyms(lines=lines)
        lines=self.fix_isolated_epithets(lines=lines)
        lines=self.add_meta_data(lines=lines)

        pages=self.output.collect_lists(lines=lines)

        """
        See if it is 
            family, name, ipen
        or (much rarer?)
            family, family, family,
            name, name, name
            ipen, ipen, ipen
        and act accordingly
        """

        for line in lines:
            print(line)
            break
        exit()

        lists=self.output.compile_records(lines=lines, pages=pages)
        output=self.output.compile_output(lists=lists)

        #TODO save this as separate index (optional?)
        # self.data_extractor.species_index

        #TODO
        # self.checks=Checks(file=file, output=output)
        # self.checks.check_families(families_seen=self.families_seen, family_key=self.output.header.index('family'))

        if self.output.output_path:
            #TODO: make this append rather than overwrite (optional?)
            self.output.csv(lines=output, source_file=file)

        if (not self.output.output_path or logging.root.level==logging.DEBUG) and not self.no_stdout:
            self.output.stdout(lines=output)

        self.logger.debug("Finished '%s'", file)

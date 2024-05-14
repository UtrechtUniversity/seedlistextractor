import re
from math import ceil
from statistics import mean 
from utils import LegendItem, extract_filename_vars

class SeedlistExtractor:

    def __init__(self,
                 document, 
                 data_extractor,
                 logger,
                 output,
                 filename=None,
                 print_stdout=False) -> None:
        self.filename=filename
        self.document=document
        self.print_stdout=print_stdout
        self.logger=logger
        self.output=output
        self.data_extractor=data_extractor
        self.main()

    @staticmethod
    def collect_meta_data(lines, max_look_ahead=5):
        for line in [x for x in lines if x.species or x.genus]:
            # promote remaining tokens from the same line to meta data
            if line._rest:
                setattr(line, 'meta_rest', line._rest.strip())
                setattr(line, '_rest', None)

            # look for next lines w/o anything 
            next_items=[]
            for next in [x for x in lines if x.line_nr>line.line_nr]:
                if next.genus \
                    or next.species \
                    or next.epithet \
                    or next.cultivar \
                    or len(next.synonyms)>0:
                    break
                if len(next_items)>=max_look_ahead:
                    break
                if len(next.raw.strip())>0:
                    next_items.append(next.raw.strip())
            
            if len(next_items)>0:
                setattr(line, 'meta_next', next_items)

        # setting the length of the list of lines of the final element
        # to the average of the preceding lines
        l_meta_next = [len(x.meta_next) for x in lines if x.species or x.genus]
        if len(l_meta_next)>3:
            last = [x for x in lines if x.species or x.genus][-1]
            setattr(line, 'meta_next', last.meta_next[:ceil(mean(l_meta_next[1:-1]))])

        return lines

    def parse_legend(self, lines):

        symbols=[
            '*A*', '*F*', '*G*', '*P*',
            '(**)', '(*)', '**', '*',
            '(++)', '(+)', '++', '+',
            '^', '%', '#', 'º', '!',
            'CW', 'IAS', '(W)', 'Ø',
            'A', 'G', 'P', 'W', 'U', 'Z', 
            '☉', '⚇', '♃', '🌲', '🌳', '🌿', '🏠',
            ]
        
        legend=[]

        # find & count presence of symbols in lines with names' their metadata
        for line in lines:
            if not line.species and not line.genus and not line.epithet and not line.ipen:
                continue
            if not line.meta_rest and not line.meta_next:
                continue
            tmp = line.meta_rest if line.meta_rest else "" + " ".join(line.meta_next) if line.meta_next else ""
            for symbol in symbols:
                if re.search(f'(^| ){re.escape(symbol)}( |$)', tmp):
                    p = [x for x in legend if x.symbol==symbol]
                    if len(p)==0:
                        legend.append(LegendItem(symbol=symbol))
                    else:
                        p[0].increase_count()

        # we assume the ones that are letters and have a relative low count
        # are remnants, not reference symbols
        total = sum([x.count for x in legend])
        legend = [x for x in legend if not x.symbol.isalpha() or (x.symbol.isalpha() and x.count/total>0.01)]


        # go through all doc lines that have no names data to look for possible
        # legends for each symbol
        for line in lines:
            if line.species or line.genus or line.epithet or line.ipen:
                continue
            # if not line._rest or len(line._rest.strip())==0:
            #     continue
            if len(line.raw.strip())==0:
                continue
            for item in legend:
                if (
                        re.search(f'^(\s*){re.escape(item.symbol)}(:| |,|-|=)(.*)', line.raw, re.MULTILINE) \
                        or re.search(f'^[^„\"“]*(„|\"|“)\s+{re.escape(item.symbol)}\s+(\"|”|“)(.*)$', line.raw)
                    ) and re.search(r'[a-zA-Z]+', line.raw):
                        item.add_descriptor(descriptor=line.raw)


        # for any symbol that doesn't have a descriptor yet, search more generally
        # for the symbol, and use the matching line that has the least capital letters
        # to avoid using a line that has a unmatched bit of species name.
        for item in [x for x in legend if not x.descriptor]:
            candidates=[]
            for line in lines:
                if line.species or line.genus or line.epithet or line.ipen:
                    continue
                smbl = re.escape(item.symbol)
                if re.search(r'([: ,-=\n]{1}'+smbl+'[\b ]{1}|[\b ]{1}'+smbl+'[: ,-=\n]{1})', line.raw):
                    if sum(1 for c in line.raw if c.isalpha())>0:
                        candidates.append(line.raw)
            if len(candidates)>0:
                item.add_descriptor(descriptor=sorted(candidates, key=lambda x: sum(1 for c in x if c.isupper()))[0])

        # get rid of the ones that still have no descriptor
        legend=[x for x in legend if x.descriptor]

        # add the relevant descriptors to species
        for line in lines:
            if not line.species:
                continue
            if not line.meta_rest and not line.meta_next:
                continue
            tmp=line.meta_rest if line.meta_rest else "" + " ".join(line.meta_next) if line.meta_next else ""
            refs=[]
            for item in legend:    
                smbl=re.escape(item.symbol)
                if re.search(f'[^A-Za-z]{smbl}[^A-Za-z]', tmp):
                    refs.append(item.descriptor)
            setattr(line, 'ref', refs)
        
        return lines

    def main(self):
        self.logger.info("Reading %s", self.filename)

        lines = self.data_extractor.extract(lines=self.document)
        lines = self.collect_meta_data(lines=lines)
        lines = self.parse_legend(lines=lines)

        basename, garden_code, year = extract_filename_vars(self.filename)

        rows = self.output.get_rows(lines=lines, 
                                    static_cols=[('filename', basename), ('garden code', garden_code), ('year', year)])

        if len(rows)==0:
            self.logger.info("Extracted no data; writing no output.")
        else:
            output_file = self.output.get_output_path(source=self.filename)
            self.output.write_csv(rows=rows, output_file=output_file)

        if self.print_stdout:
            self.output.stdout(rows=rows)
 

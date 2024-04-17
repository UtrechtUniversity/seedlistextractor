import re
from statistics import mean 
from math import ceil
from utils import LegendItem

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
                if next.has_values():
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

    def main(self):
        self.logger.info("Reading %s", self.filename)

        lines=self.data_extractor.extract(lines=self.document)
        lines=self.collect_meta_data(lines=lines)
        lines=self.parse_legend(lines=lines)

        rows=self.output.get_rows(lines=lines)
        if len(rows)==0:
            self.logger.info("Extracted no data; writing no output.")
        else:
            output_file=self.output.get_output_path(source=self.filename)
            self.output.write_csv(rows=rows, output_file=output_file)
        if self.print_stdout:
            self.output.stdout(rows=rows)
 
    def parse_legend(self, lines):
        symbols=[
            '*A*', '*F*', '*G*', '*P*',
            '(**)', '(*)', '**', '*',
            '(++)', '(+)', '++', '+',
            '^', '%', '#', 'º', '!',
            'CW', 'IAS', '(W)', 'Ø',
            'A', 'Z', 'W', 'P', 'G',
            '☉', '⚇', '♃', '🌲', '🌳', '🌿', '🏠',
            ]
        
        legend=[]

        for line in lines:
            if not line.species and not line.genus:
                continue
            if not line.meta_rest:
                continue
            tmp=line.meta_rest
            for symbol in symbols:
                if re.search(f'(^| ){re.escape(symbol)}( |$)', tmp):
                    p=[x for x in legend if x.symbol==symbol]
                    if len(p)==0:
                        legend.append(LegendItem(symbol=symbol))
                    else:
                        p[0].increase_count()

        # MAGIC NUMBER
        total=sum([x.count for x in legend])
        legend=[x for x in legend if x.count/total>0.05]

        for line in lines:
            if not line._rest or len(line._rest.strip())==0:
                continue
            if not line.species and not line.genus and not line.ipen:
                for item in legend:
                    if (
                            re.search(f'^(\s*){re.escape(item.symbol)}(:| |,|-|=)(.*)', line.raw, re.MULTILINE) \
                            or re.search(f'^[^„\"“]*(„|\"|“)\s+{re.escape(item.symbol)}\s+(\"|”|“)(.*)$', line.raw)
                        ) \
                        and re.search(r'[a-zA-Z]+', line.raw):
                            item.add_descriptor(descriptor=line.raw)


        for item in [x for x in legend if not x.descriptor]:
            candidates=[]
            for line in lines:
                # if item.symbol in line.raw and not line.species and not line.epithet:
                smbl=re.escape(item.symbol)
                if not line.species and not line.epithet and re.search(f'((:| |=){smbl}\b|\b{smbl}(:| |,|-|=))', line.raw):
                    if sum(1 for c in line.raw if c.isalpha())>0:
                        candidates.append(line.raw)
            if len(candidates)>0:
                item.add_descriptor(descriptor=sorted(candidates, key=lambda x: sum(1 for c in x if c.isupper()))[0])
        
        legend=[x for x in legend if x.descriptor]

        for line in lines:
            if (not line.species and line.genus) or not line.meta_rest:
                continue
            refs=[]
            for item in legend:
                if item.symbol in line.meta_rest:
                    refs.append(item.descriptor)
                setattr(line, 'ref', refs)
        
        return lines


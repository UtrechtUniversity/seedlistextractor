import re
from math import ceil
from statistics import mean
from objects import LegendItem
from utils import single_spaces
from extraction_utils import extract_filename_vars

class SeedlistExtractor:

    def __init__(self,   # pylint: disable=too-many-arguments
                 document,
                 data_extractor,
                 logger,
                 source,
                 output=None,
                 output_file=None,
                 stdout=False) -> None:
        self.document = document
        self.print_stdout = stdout
        self.logger = logger
        self.source = source
        self.output = output
        self.output_file = output_file
        self.data_extractor = data_extractor
        self.main()

    @staticmethod
    def collect_meta_data(lines, max_look_ahead=5):
        for line in [x for x in lines if x.name]:
            # promote remaining tokens from the same line to meta data
            if line._rest:  # pylint: disable=protected-access
                setattr(line, 'meta_rest', line._rest.strip())  # pylint: disable=protected-access
                setattr(line, '_rest', None)

            # look for next lines w/o anything
            next_items=[]
            for l_next in [x for x in lines if x.line_nr>line.line_nr]:
                if l_next.name \
                    or l_next.epithet \
                    or l_next.cultivar \
                    or len(l_next.synonyms)>0:
                    break
                if len(next_items)>=max_look_ahead:
                    break
                if len(l_next.raw.strip())>0:
                    next_items.append(l_next.raw.strip())

            if len(next_items)>0:
                setattr(line, 'meta_next', next_items)

        # setting the length of the list of lines of the final element
        # to the average of the preceding lines
        l_meta_next = [len(x.meta_next) for x in lines if x.name]
        if len(l_meta_next)>3:
            last = [x for x in lines if x.name][-1]
            setattr(last, 'meta_next', last.meta_next[:ceil(mean(l_meta_next[1:-1]))])

        return lines

    def parse_legend(self, lines):  # pylint: disable=too-many-branches

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
            if not line.has_names():
                continue
            if not line.meta_rest and not line.meta_next:
                continue
            tmp = line.meta_rest if line.meta_rest else "" + \
                  " ".join(line.meta_next) if line.meta_next else ""
            for symbol in symbols:
                if not re.search(f'(^| ){re.escape(symbol)}( |$)', tmp):
                    continue
                p = [x for x in legend if x.symbol==symbol]
                if len(p)==0:
                    legend.append(LegendItem(symbol=symbol))
                else:
                    p[0].increase_count()

        # we assume the ones that are letters and have a relative low count
        # are remnants, not reference symbols
        total = sum(x.count for x in legend)
        legend = [x for x in legend if not x.symbol.isalpha()
                                       or (x.symbol.isalpha() and x.count/total>0.01)]

        # go through all doc lines that have no names data to look for possible
        # legends for each symbol
        for line in lines:
            if line.has_names():
                continue

            if len(line.raw.strip())==0:
                continue
            for item in legend:
                if (  # pylint: disable=line-too-long
                    re.search(rf'^(\s*){re.escape(item.symbol)}(:| |,|-|=)(.*)', line.raw, re.MULTILINE) \
                    or re.search(rf'^[^„\"“]*(„|\"|“)\s+{re.escape(item.symbol)}\s+(\"|”|“)(.*)$', line.raw)
                    ) and re.search(r'[a-zA-Z]+', line.raw):
                    item.add_descriptor(descriptor=single_spaces(line.raw))

        # for any symbol that doesn't have a descriptor yet, search more generally
        # for the symbol, and use the matching line that has the least capital letters
        # to avoid using a line that has a unmatched bit of species name.
        for item in [x for x in legend if not x.descriptor]:
            candidates=[]
            for line in lines:
                if line.has_names():
                    continue
                smbl = re.escape(item.symbol)
                if re.search(r'([: ,-=\n]{1}'+smbl+'[\b ]{1}|[\b ]{1}'+smbl+'[: ,-=\n]{1})', line.raw):  # pylint: disable=line-too-long
                    if sum(1 for c in line.raw if c.isalpha())>0:
                        candidates.append(line.raw)
            if len(candidates)>0:
                item.add_descriptor(descriptor=sorted(candidates,
                                    key=lambda x: sum(1 for c in x if c.isupper()))[0])

        # get rid of the ones that still have no descriptor
        legend=[x for x in legend if x.descriptor]

        # add the relevant descriptors to species
        for line in lines:
            if not line.name:
                continue
            if not line.meta_rest and not line.meta_next:
                continue

            tmp=line.meta_rest if line.meta_rest else "" + \
                " ".join(line.meta_next) if line.meta_next else ""
            refs=[]

            for item in legend:
                smbl=re.escape(item.symbol)
                if re.search(rf'[\W^]?{smbl}[\W$]?', tmp):
                    refs.append(item.descriptor)

            setattr(line, 'ref', refs)

        return lines

    def main(self):
        self.logger.info("Reading %s", str(self.source))

        lines = self.data_extractor.extract(lines=self.document)
        lines = self.collect_meta_data(lines=lines)
        lines = self.parse_legend(lines=lines)

        basename, garden_code, year = extract_filename_vars(str(self.source))

        rows = self.output.get_rows(lines=lines,
                                    static_cols=[('filename', basename),
                                                 ('garden code', garden_code),
                                                 ('year', year)])

        if len(rows)==0:
            self.logger.info("Extracted no data; writing no output.")
        else:
            self.output.write(rows=rows, output_file=self.output_file)
            self.logger.info("Wrote to '%s'.", self.output_file)

        if self.print_stdout:
            self.output.stdout(rows=rows)
 
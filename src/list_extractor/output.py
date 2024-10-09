import csv
import re
from pathlib import Path
from statistics import mean

class Output:

    out_formats = {
        'tsv' : {
            'extension': '.tsv',
            'delimiter': '\t',
            'encoding': 'utf-8'
        },
        'csv' : {
            'extension': '.csv',
            'delimiter': ',',
            'encoding': 'utf-8'
        }
    }

    stdout_col_limit = 10

    def __init__(self,
                 output_directory,
                 output_in_situ,
                 skip_existing,
                 print_stdout,
                 logger,
                 out_format='tsv',
                 include_line_nr=False) -> None:
        self.output_directory = output_directory
        self.output_in_situ = output_in_situ
        self.skip_existing = skip_existing

        if self.output_directory and self.output_in_situ:
            raise ValueError("Cannot have both output_directory and output_in_situ")

        self.out_format = out_format
        self.include_line_nr = include_line_nr
        self.print_stdout = print_stdout
        self.logger = logger
        self.input_file = None
        self.output_file = None

    def set_output_file(self, input_file):
        self.input_file = Path(input_file)
        self.output_file = None

        if self.output_directory and self.input_file.is_file():
            self.output_file = self.output_directory / Path(str(self.input_file.name))
        elif self.output_in_situ:
            self.output_file = Path(self.input_file)

        if not self.output_file:
            return

        self.output_file = Path(self.output_file).with_suffix(self.out_formats[self.out_format]['extension'])

        # if self.output_file.suffix.lstrip(".") not in self.out_formats:
        #     raise ValueError(f'Extension {self.output_file.suffix!r} not recognized.')

        if self.input_file==self.output_file:
            raise ValueError('Input and output files are the same.')

    def can_output(self):
        return not (self.skip_existing and self.output_file and self.output_file.is_file())

    def get_rows(self, lines, static_cols=None):

        def get_field_order(lines):
            if len([x for x in lines if x.ipen])==0:
                return ('name',)

            if len([x for x in lines if x.ipen and x.name])==0:
                if [x for x in lines if x.ipen][0].line_nr<[x for x in lines if x.name][0].line_nr:
                    return ('ipen', 'name')

                return ('name', 'ipen')

            if mean([x.name.index-x.ipen.index for x in lines if x.ipen and x.name])>0:
                return ('ipen', 'name')

            return ('name', 'ipen')

        def get_ipen(line, lines, field_order):
            if 'ipen' not in field_order:
                return ''

            if line.ipen:
                return line.ipen.text

            if field_order.index('ipen') < field_order.index('name'):
                candidates=list(reversed([x for x in lines if x.line_nr<line.line_nr]))
            else:
                candidates=[x for x in lines if x.line_nr>line.line_nr]

            for candidate in candidates:
                if candidate.name:
                    return ''
                if candidate.ipen:
                    return candidate.ipen.text

            return ''

        def get_next_synonyms(line, lines):
            r_val = None
            if hasattr(line, 'synonyms') and len(getattr(line, 'synonyms'))>0:
                r_val = getattr(line, 'synonyms')
            else:
                # always after the main name, but not more than 2 lines
                for candidate in [x for x in lines if 0<(x.line_nr-line.line_nr)<3 and not x.name]:
                    if hasattr(candidate, 'synonyms') and len(getattr(candidate, 'synonyms'))>0:
                        r_val = getattr(candidate, 'synonyms')
                        break

            if r_val:
                return [f"{x.match.canonical_name} ({x.text})" for x in r_val]
            return ''

        def get_next_cultivar(line, lines):
            r_val = None
            if hasattr(line, 'cultivar') and getattr(line, 'cultivar') is not None:
                r_val = getattr(line, 'cultivar')
            else:
                # always after the main name, but not more than 2 lines
                for candidate in [x for x in lines if 0<(x.line_nr-line.line_nr)<3 and not x.name]:
                    if hasattr(candidate, 'cultivar') \
                    and getattr(candidate, 'cultivar') is not None:
                        r_val = getattr(candidate, 'cultivar')
                        break

            if r_val:
                return r_val.text
            return ''

        field_order=get_field_order(lines=lines)

        rows=[]
        for line in lines:
            # if not line.name:
            #     continue
            if not line.name and not line.epithet:
                continue

            ipen = get_ipen(line=line, lines=lines, field_order=field_order)
            meta_next = list(filter(None, [x.replace(ipen, '').strip() for x in line.meta_next]))

            if line.name:

                row = {
                    'extracted_name': line.name.text,
                    'match_name': line.name.match.canonical_name,
                    'match_score': line.name.score,
                    'match_possibly_partial': line.name.match.possibly_partial,
                    'match_rank': line.name.match.taxon_rank,
                    'match_genus': line.name.match.genus,
                    'match_epithet': line.name.match.epithet,
                    'match_infraspecific_epithet': line.name.match.infraspecific_epithet,
                    'match_authorship': line.name.match.authorship,
                    'match_is_hybrid': line.name.match.is_hybrid,
                    'match_source': line.name.match.source,
                    'match_identical_canonical': "; ".join([f"{x.full_name} [{x.source}]" 
                                                            for x in line.name.identical_canonicals]),
                }

            else:

                row = {
                    'extracted_name': line.epithet.text,
                    'match_name': '',
                    'match_score': line.epithet.score,
                    'match_possibly_partial': False,
                    'match_rank': line.epithet.match.taxon_rank,
                    'match_genus': '',
                    'match_epithet': line.epithet.match.epithet,
                    'match_infraspecific_epithet': line.epithet.match.infraspecific_epithet,
                    'match_authorship': '',
                    'match_is_hybrid': '',
                    'match_source': line.epithet.match.source,
                    'match_identical_canonical': '',
                }

            row['extracted_synonyms'] = get_next_synonyms(line=line, lines=lines)
            row['extracted_cultivar_form'] = get_next_cultivar(line=line, lines=lines)
            row['extracted_ipen'] = ipen
            row['extracted_metadata_remnant'] = line.meta_rest
            row['extracted_metadata_next_lines'] = meta_next if len(meta_next)>0 else None
            row['extracted_notes'] = list(line.ref) if len(line.ref)>0 else None
            row['raw_line'] = line.raw

            if static_cols:
                for static_col in static_cols:
                    row[static_col[0]] = static_col[1]

            if self.include_line_nr:
                new = { 'line': line.line_nr }
                new.update(row)
                row = new

            rows.append(row)

        return rows

    def output(self, lines):
        basename, garden_code, year = self.extract_filename_vars(str(self.input_file))

        rows = self.get_rows(lines=lines,
                             static_cols=[('filename', basename),
                                          ('garden code', garden_code),
                                          ('year', year)])

        if len(rows)==0:
            self.logger.info("Extracted no data; writing no output.")
            return

        if self.output_file:
            self.to_file(rows=rows)
            self.logger.info("Wrote to '%s'", self.output_file)

        if self.print_stdout:
            self.to_stdout(rows=rows)

    def to_file(self, rows):
        if self.output_file.is_file():
            Path.unlink(self.output_file)

        out_format = self.out_formats[self.out_format]

        with open(self.output_file, 'w', encoding=out_format['encoding']) as file:
            dict_writer=csv.DictWriter(file, rows[0].keys(), delimiter=out_format['delimiter'])
            dict_writer.writeheader()
            dict_writer.writerows(rows)

    def to_stdout(self, rows):
        print(list(rows[0].keys())[:self.stdout_col_limit])
        for row in rows:
            print([row[x] for key, x in enumerate(row.keys()) if key < self.stdout_col_limit])
        print(list(rows[0].keys())[:self.stdout_col_limit])

    @staticmethod
    def extract_filename_vars(filename):
        garden_code = None
        year = None
        bits = Path(filename).stem.split('-')
        if len(bits)>3 and re.match(r'^[A-Z]+$', bits[0]) and re.match(r'^\d{4}$', bits[1]):
            garden_code = bits[0]
            year = int(bits[1])
        else:
            bits = Path(filename).stem.split('_')
            if len(bits)>1 and re.match(r'^[A-Z]+$', bits[0]) and re.match(r'^\d{4}', bits[1]):
                garden_code = bits[0]
                year = int(re.split(r'(^\d{4})', bits[1])[1])
        
        if year is None:
            match = re.search(r'(1(8|9)\d{2})', Path(filename).name)
            if match:
                year = int(Path(filename).name[match.span()[0]:match.span()[1]])

        return Path(filename).name, garden_code, year


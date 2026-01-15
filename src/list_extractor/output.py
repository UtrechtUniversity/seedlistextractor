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

    field_orders = [('name', 'ipen'), ('ipen', 'name')]

    def __init__(self,
                 output_directory,
                 logger,
                 field_order_in_input,
                 out_format = 'tsv',
                 skip_existing = False,
                 output_in_situ = False,
                 print_stdout = False) -> None:
        if output_directory and output_in_situ:
            raise ValueError("Cannot have both output_directory and output_in_situ")
        if field_order_in_input not in self.field_orders:
            raise ValueError("Invalid value for field_order_in_input: %s" % str(field_order_in_input))
        self.output_directory = output_directory
        self.output_in_situ = output_in_situ
        self.skip_existing = skip_existing
        self.out_format = out_format
        self.field_order_in_input = field_order_in_input
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

        if self.input_file==self.output_file:
            raise ValueError('Input and output files are the same.')

    def can_output(self):
        return not (self.skip_existing and self.output_file and self.output_file.is_file())

    def get_rows(self, lines, static_cols=[]):

        value_sep = '; '

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
                # return value_sep.join([f'{x.match.canonical_name} ({x.text})' for x in r_val])
                return value_sep.join([f'{x.match.full_name} [{x.text}]' for x in r_val])
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

        def get_authorships(name):
            # only first source for each identical author
            # assuming source sorting during name loading stays in tact
            buffer = []
            for item in name.authorships:
                if item[0] not in [x[0] for x in buffer]:
                    buffer.append(item)

            return value_sep.join([f"{x[0]} [{x[1]}]" for x in buffer])

        rows = []

        for line in lines:

            if not line.name and not line.epithet and not line.genus:
                continue

            ipen = get_ipen(line=line, lines=lines, field_order=self.field_order_in_input)
            meta_next = list(filter(None, [x.replace(ipen, '').strip() for x in line.meta_next]))

            if line.name:
                item = line.name
            elif line.epithet:
                item = line.epithet
            elif line.genus:
                item = line.genus

            row = {
                'line': line.line_nr,
                'extracted_name': item.text,
                'match_name': None,
                'match_score': item.score,
                'match_rank': item.match.taxon_rank,
                'match_genus': None,
                'match_epithet': None,
                'match_infraspecific_epithet': item.match.infraspecific_epithet,
                'match_authorship': get_authorships(item),
                'match_is_hybrid': False,
                'match_source': item.match.source,
                'genus_extracted_name': None,
                'genus_match_genus': None,
                'genus_match_score': None,
                'genus_match_genus': None,
                'genus_match_source': None,
                'genera_match_score': line.genus_match_score,
                'extracted_synonyms': get_next_synonyms(line=line, lines=lines),
                'extracted_cultivar_form': get_next_cultivar(line=line, lines=lines),
                'extracted_ipen': ipen,
                'extracted_metadata_remnant': line.meta_rest,
                'extracted_metadata_next_lines': value_sep.join(meta_next) if len(meta_next)>0 else None,
                'extracted_notes': value_sep.join(list(line.ref)) if len(line.ref)>0 else None,
                'raw_line': line.raw,
            }

            if line.name:

                row['match_name'] = line.name.match.canonical_name
                row['match_genus'] = line.name.match.genus
                row['match_epithet'] = line.name.match.epithet
                row['match_is_hybrid'] = line.name.match.is_hybrid
                
            elif line.epithet:

                row['match_epithet'] = line.epithet.match.epithet
                row['genus_match_score'] = None
            
            elif line.genus:
                
                row['match_genus'] = line.genus.match.genus
                row['match_epithet'] = None
                row['match_infraspecific_epithet'] = None

            if line.genus and line.name \
                and line.genus.match.genus != line.name.match.genus \
                and line.genus.score==1:

                row['genus_extracted_name'] = line.genus.text
                row['genus_match_genus'] = line.genus.match.genus
                row['genus_match_score'] = line.genus.score
                row['genus_match_genus'] = line.genus.match.genus
                row['genus_match_source'] = line.genus.match.source

            for static_col in static_cols:
                row[static_col[0]] = static_col[1]

            rows.append(row)

        return rows

    def output(self, lines):
        basename, garden_code, year = self.extract_filename_vars(str(self.input_file))

        rows = self.get_rows(lines=lines,
                             static_cols=[('filename', basename),
                                          ('garden_code', garden_code),
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

        # None to '' for empty CSV-cells
        rows = [{k:'' if v is None else v for k,v in row.items()} for row in rows]

        with open(self.output_file, 'w', encoding=out_format['encoding']) as file:
            dict_writer = csv.DictWriter(file, rows[0].keys(), delimiter=out_format['delimiter'])
            dict_writer.writeheader()
            dict_writer.writerows(rows)

    def to_stdout(self, rows):
        for row in rows:
            print(row)

    @staticmethod
    def extract_filename_vars(filename):
        garden_code = None
        year = None
        filename = Path(filename).name

        # four digit number, starting with 1 or 2, not preceded by a number
        regex = re.compile(r'(?<!\d)((1|2)\d{3})')
        if regex.search(filename):
            year = int(regex.search(filename).group())

        # letter-only string of 1 character minimum at the start of string
        regex = re.compile(r'^[A-Za-z]{1,}(?![A-Za-z])')
        if regex.search(filename):
            garden_code = regex.search(filename).group()

        return filename, garden_code, year

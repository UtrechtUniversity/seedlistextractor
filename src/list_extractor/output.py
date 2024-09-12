import csv
from statistics import mean
from pathlib import Path

class Output:

    def __init__(self, include_line_nr=False) -> None:
        self.include_line_nr = include_line_nr

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
                    # 'extracted_synonyms': get_next_synonyms(line=line, lines=lines),
                    # 'extracted_cultivar_form': get_next_cultivar(line=line, lines=lines),
                    # 'extracted_ipen': ipen,
                    # 'extracted_metadata_remnant': line.meta_rest,
                    # 'extracted_metadata_next_lines': meta_next if len(meta_next)>0 else None,
                    # 'extracted_notes': list(line.ref) if len(line.ref)>0 else None,
                    # 'raw_line': line.raw
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
                    # 'extracted_synonyms': get_next_synonyms(line=line, lines=lines),
                    # 'extracted_cultivar_form': get_next_cultivar(line=line, lines=lines),
                    # 'extracted_ipen': ipen,
                    # 'extracted_metadata_remnant': line.meta_rest,
                    # 'extracted_metadata_next_lines': meta_next if len(meta_next)>0 else None,
                    # 'extracted_notes': list(line.ref) if len(line.ref)>0 else None,
                    # 'raw_line': line.raw
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

    @staticmethod
    def stdout(rows):
        print(list(rows[0].keys()))
        for row in rows:
            print([row[x] for x in row.keys()])
        print(list(rows[0].keys()))

    def write_tsv(self, rows, output_file):
        if not output_file or len(rows)==0:
            return

        if output_file.is_file():
            Path.unlink(output_file)

        with open(output_file, 'w', encoding=self.out_format['encoding']) as file:
            dict_writer=csv.DictWriter(file, rows[0].keys(), delimiter=self.out_format['delimiter'])
            dict_writer.writeheader()
            dict_writer.writerows(rows)

def get_output_path(source,
                    output_path,
                    output_in_situ,
                    out_format='tsv'):

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

    if not output_path and not output_in_situ:
        return None

    if output_path:
        output_path = output_path / Path(str(source.parent).replace(str(source), '').lstrip("/")) / Path(str(source.name))
    elif output_in_situ:
        output_path = Path(source)

    output_path = Path(output_path).with_suffix(out_formats[out_format]['extension'])

    if Path(source)==output_path:
        raise ValueError('Input and output files have the same path.')

    return output_path


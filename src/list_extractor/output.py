import csv
from statistics import mean
from pathlib import Path

class Output:

    def __init__(self, output_root=None, include_line_nr=False) -> None:
        self.output_root = None
        self.include_line_nr = include_line_nr
        if output_root:
            self.output_root = Path(output_root)
            self.output_root.mkdir(parents=True, exist_ok=True)

    def get_output_path(self, source):
        if self.output_root:
            output_path = Path(self.output_root) / Path(source.lstrip("/")).with_suffix(".csv")
            output_path = Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            return output_path

    def get_rows(self, lines, static_cols=[]):

        def get_field_order(lines):
            if len([x for x in lines if x.ipen])==0:
                return ('name',)
            
            if len([x for x in lines if x.ipen and x.name])==0:
                if [x for x in lines if x.ipen][0].line_nr<[x for x in lines if x.name][0].line_nr:
                    return ('ipen', 'name')
                else:
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
                    if hasattr(candidate, 'cultivar') and getattr(candidate, 'cultivar') is not None:
                        r_val = getattr(candidate, 'cultivar')
                        break

            if r_val:
                return r_val.text
            return ''

        field_order=get_field_order(lines=lines)

        rows=[]
        for line in lines:
            if not line.name:
                continue

            ipen = get_ipen(line=line, lines=lines, field_order=field_order)
            meta_next = list(filter(None, [x.replace(ipen, '').strip() for x in line.meta_next]))

            row = {
                'extracted_name': line.name.text,
                'match_name': line.name.match.canonical_name,
                'match_score': line.name.score,
                'match_rank': line.name.match.taxon_rank,
                'match_genus': line.name.match.genus,
                'match_epithet': line.name.match.epithet,
                'match_infraspecific_epithet': line.name.match.infraspecific_epithet,
                'match_authorship': line.name.match.authorship,
                'match_source': line.name.match.source,
                'match_identical_canonical': "; ".join([f"{x.full_name} [{x.source}]" for x in line.name.identical_canonicals]),
                'extracted_synonyms': get_next_synonyms(line=line, lines=lines),
                'extracted_cultivar_form': get_next_cultivar(line=line, lines=lines),
                'extracted_ipen': ipen,
                'extracted_metadata_remnant': line.meta_rest,
                'extracted_metadata_next_lines': meta_next if len(meta_next)>0 else None,
                'extracted_notes': [x for x in line.ref] if len(line.ref)>0 else None,
                'raw_line': line.raw
            }

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

    def write_csv(self, rows, output_file):
        if not output_file or len(rows)==0:
            return
        
        if output_file.is_file():
            Path.unlink(output_file)

        with open(output_file, 'w', encoding='utf-8') as file:
            dict_writer=csv.DictWriter(file, rows[0].keys())
            dict_writer.writeheader()
            dict_writer.writerows(rows)
        
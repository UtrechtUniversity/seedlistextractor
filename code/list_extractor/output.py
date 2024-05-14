import csv
from statistics import mean
from pathlib import Path

class Output:

    def __init__(self, output_root=None) -> None:
        self.output_root=None
        if output_root:
            self.output_root=Path(output_root)
            self.output_root.mkdir(parents=True, exist_ok=True)

    def get_output_path(self, source):
        if self.output_root:
            output_path=Path(self.output_root) / Path(source.lstrip("/")).with_suffix(".csv")
            output_path=Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            return output_path

    @staticmethod
    def get_rows(lines):

        def get_field_order(lines):
            if len([x for x in lines if x.ipen])==0:
                return ('species',)
            
            if len([x for x in lines if x.ipen and x.species])==0:
                if [x for x in lines if x.ipen][0].line_nr<[x for x in lines if x.species][0].line_nr:
                    return ('ipen', 'species')
                else:
                    return ('species', 'ipen')

            if mean([x.species.index-x.ipen.index for x in lines if x.ipen and x.species])>0:
                return ('ipen', 'species')

            return ('species', 'ipen')

        def get_ipen(line, lines, field_order):
            if 'ipen' not in field_order:
                return ''

            if line.ipen:
                return line.ipen.text

            if field_order.index('ipen') < field_order.index('species'):
                candidates=list(reversed([x for x in lines if x.line_nr<line.line_nr]))
            else:
                candidates=[x for x in lines if x.line_nr>line.line_nr]
            
            for candidate in candidates:
                if candidate.species:
                    return ''
                if candidate.ipen:
                    return candidate.ipen.text
            
            return ''

        def get_next_val(line, lines, field):
            r_val=None

            if hasattr(line, field) and getattr(line, field) is not None:
                r_val=getattr(line, field)
            else:
                # always after the main name, but not more than 2 lines
                # print(line.line_nr, line.species.text, field)
                for candidate in [x for x in lines if 0<(x.line_nr-line.line_nr)<3 and not x.species]:
                    if getattr(candidate, field) \
                        and getattr(candidate, field) is not None \
                        and len(getattr(candidate, field))>0:
                        r_val=getattr(candidate, field)

            if r_val:
                if field=='synonyms':
                    return [f"{x.match.full_name} ({x.text})" for x in r_val]
                return r_val.text
            return ''

        field_order=get_field_order(lines=lines)

        rows=[]
        for line in lines:
            if line.species:
                matched_level = 'species'
                matched = line.species
            elif line.genus:
                matched_level = 'genus'
                matched = line.genus
            else:
                continue

            ipen = get_ipen(line=line, lines=lines, field_order=field_order)
            meta_next = list(filter(None, [x.replace(ipen, '').strip() for x in line.meta_next]))

            rows.append({
                # 'line': line.line_nr,
                'extracted_name': matched.text,
                'matched_name': matched.match.full_name,
                'matched_score': matched.score,
                'matched_level': matched_level,
                'matched_genus': matched.match.genus,
                'matched_epithet': matched.match.epithet,
                'matched_infraspecific_epithet': matched.match.infraspecific_epithet,
                'matched_authorship': matched.match.authorship,
                'extracted_synonyms': get_next_val(line=line, lines=lines, field='synonyms'),
                'extracted_cultivar_form': get_next_val(line=line, lines=lines, field='cultivar'),
                'extracted_ipen': ipen,
                'extracted_metadata_remnant': line.meta_rest,
                'extracted_metadata_next_lines': meta_next if len(meta_next)>0 else None,
                'extracted_notes': [x for x in line.ref] if len(line.ref)>0 else None,
                'raw_line': line.raw
            })

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

        with open(output_file, 'w') as file:
            dict_writer=csv.DictWriter(file, rows[0].keys())
            dict_writer.writeheader()
            dict_writer.writerows(rows)
        
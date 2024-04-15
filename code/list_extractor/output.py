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
            output_path=self.output_root / Path((Path(source).parts[-1])).with_suffix(".csv")
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
                candidates=list(reversed([x for x in lines if x.line_nr<line.line_nr and line.ipen]))
            else:
                candidates=[x for x in lines if x.line_nr>line.line_nr and line.ipen]
            
            if len(candidates)>0:
                return getattr(candidates[0], 'ipen').text
            
            return ''

        def get_other(line, lines, field):
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
                    return [x.match for x in r_val]
                    # return "; ".join([f"{x.match} ({x.score})" for x in r_val])
                return r_val.text
            return ''

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

            rows.append({
                'name (text)': matched.text,
                'match level': matched_level,
                'match name': matched.match.full_name,
                'match score': matched.score,
                'match genus': matched.match.genus,
                'match epithet': matched.match.epithet,
                'match infraspecific_epithet': matched.match.infraspecific_epithet,
                'match authorship': matched.match.authorship,
                'synonym(s)': get_other(line=line, lines=lines, field='synonyms'),
                'cultivar/form': get_other(line=line, lines=lines, field='cultivar'),
                'ipen': get_ipen(line=line, lines=lines, field_order=get_field_order(lines=lines)),
                'metadata (line rest)': line.meta_rest,
                'metadata (next lines)': [x for x in line.meta_next],
                'raw line': line.raw
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

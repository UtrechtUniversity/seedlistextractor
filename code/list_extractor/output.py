import csv
from statistics import mean
from pathlib import Path

class Output:

    def __init__(self,
                 logger,
                 output_root=None) -> None:
        self.output_root=None
        if output_root:
            self.output_root=Path(output_root)
            self.output_root.mkdir(parents=True, exist_ok=True)
        self.logger=logger

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
                candidates=reversed([x for x in lines if x.line_nr<line.line_nr and line.ipen])
            else:
                candidates=[x for x in lines if x.line_nr>line.line_nr and line.ipen]
            
            if len(candidates)>0:
                return getattr(candidates[0], 'ipen').text
            
            return ''

        def get_other(line, lines, field):
            for candidate in [x for x in lines if x.line_nr>=line.line_nr]:
                if getattr(candidate, field) \
                    and getattr(candidate, field) is not None \
                    and len(getattr(candidate, field))>0:
                    return getattr(candidate, field)
            return ''

        rows=[]
        for line in lines:
            if not line.species:
                continue

            rows.append({
                'name': line.species.match if line.species else '',
                'match': line.species.score if line.species else '',
                'synonym(s)': get_other(line=line, lines=lines, field='synonyms'),
                'cultivar': get_other(line=line, lines=lines, field='cultivar'),
                'ipen': get_ipen(line=line, lines=lines, field_order=get_field_order(lines=lines)),
                'metadata (line rest)': line.meta_rest,
                'metadata (next lines)': line.meta_next,
                'raw': line.raw
            })

        return rows

    @staticmethod
    def stdout(rows):
        print(rows[0].keys())
        for row in rows:
            print([row[x] for x in row.keys()])
        print(rows[0].keys())

    def write_csv(self, rows, output_file):
        if output_file is None:
            self.logger.info("Didn't write CSV (no output path specified).")
            return

        if output_file.is_file():
            Path.unlink(output_file)

        with open(output_file, 'w') as file:
            dict_writer=csv.DictWriter(file, rows[0].keys())
            dict_writer.writeheader()
            dict_writer.writerows(rows)

        self.logger.info("Wrote %s name(s) to '%s'" % (len(rows), output_file))

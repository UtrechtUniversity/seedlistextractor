import csv
from pathlib import Path

class Output:

    def __init__(self,
                 logger,
                 output_path=None,
                 skip_existing=False) -> None:
        self.output_path=None
        if output_path:
            self.output_path=Path(output_path)
            self.output_path.mkdir(parents=True, exist_ok=True)
        self.skip_existing=skip_existing
        self.logger=logger

    def get_output_path(self, file):
        if self.output_path:
            output_path=self.output_path / Path((Path(file).parts[-1])).with_suffix(".csv")
            output_path=Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            return output_path

    @staticmethod
    def get_rows(lines, field_order):

        def get_ipen(line, lines, field_order):
            if 'ipen' not in field_order:
                return ''

            if line['ipen']:
                return line['ipen'].text

            if field_order.index('ipen') < field_order.index('species'):
                candidates=reversed([x for x in lines if x['line_nr']<line['line_nr'] and line['ipen']])
            else:
                candidates=[x for x in lines if x['line_nr']>line['line_nr'] and line['ipen']]
            
            if len(candidates)>0:
                return candidates[0]['ipen'].text
            
            return ''

        def get_other(line, lines, field):
            candidates=[x for x in lines if x['line_nr']>=line['line_nr'] and line[field] and len(line[field])>0]
            if len(candidates)>0:
                return candidates[0][field]
            return ''

        header=['name', 'match', 'synonym(s)', 'cultivar', 'ipen', 'metadata (rest tokens)' , 'metadata (next lines)', 'raw']
        rows=[]
        for line in lines:
            if not line['species']:
                continue

            rows.append([
                line['species'].match if line['species'] else '',
                line['species'].score if line['species'] else '',
                get_other(line=line, lines=lines, field='synonyms'),
                get_other(line=line, lines=lines, field='cultivar'),
                get_ipen(line=line, lines=lines, field_order=field_order),
                line['meta_rest'],
                line['meta_next'],
                line['raw']
            ])

        return header, rows

    @staticmethod
    def stdout(rows, header):
        print(header)
        for row in rows:
            print(row)
        print(header)

    # def csv(self, lines, source_file):
    #     output_file=self.get_output_path(source_file)

    #     if output_file.is_file() and self.skip_existing:
    #         self.logger.info("Skipped existing file '%s'" % output_file)
    #         return

    #     with open(output_file, 'w') as file:
    #         csv_writer=csv.writer(file)
    #         csv_writer.writerow(self.header)
    #         for record in lines:
    #             csv_writer.writerow(record)

    #     self.logger.info("Wrote %s name(s) to '%s'" % (len(lines), output_file))

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
        for line in [x for x in lines if x.species]:
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

        return lines

    def main(self):
        self.logger.info("Reading %s", self.filename)
        lines=self.data_extractor.extract(lines=self.document)
        lines=self.collect_meta_data(lines=lines)
        rows=self.output.get_rows(lines=lines)
        if len(rows)==0:
            self.logger.info("Extracted no data; writing no output.")
        else:
            output_file=self.output.get_output_path(source=self.filename)
            self.output.write_csv(rows=rows, output_file=output_file)
        if self.print_stdout:
            self.output.stdout(rows=rows)
 
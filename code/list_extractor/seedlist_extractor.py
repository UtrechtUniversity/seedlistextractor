import pprint

def pp(this):
    prp=pprint.PrettyPrinter(indent=4, width=100, sort_dicts=False)
    prp.pprint(this)

class SeedlistExtractor:

    def __init__(self,
                 document, 
                 data_extractor,
                 output,
                 logger,
                 filename=None,
                 no_stdout=False) -> None:
        self.filename=filename
        self.document=document
        self.no_stdout=no_stdout
        self.logger=logger
        self.data_extractor=data_extractor
        self.output=output
        self.main()

    @staticmethod
    def collect_meta_data(lines, max_look_ahead=5):
        for line in [x for x in lines if x.species]:
            # promote remaining tokens from the same line to meta data
            if line._rest:
                setattr(line, 'meta_rest', line._rest)
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
        self.output.stdout(rows=rows)

        # # print(header)
        # # print(rows)

        # if self.output.output_path:
        #     #TODO: make this append rather than overwrite (optional?)
        #     self.output.csv(lines=output, source_file=file)

        # if (not self.output.output_path or logging.root.level==logging.DEBUG) and not self.no_stdout:
        #     self.output.stdout(lines=output)

        # self.logger.debug("Finished '%s'", file)

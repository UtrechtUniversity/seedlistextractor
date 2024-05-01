import argparse
import logging
import re
from name_resolver import NameResolver
from pathlib import Path
from utils import InputDocs

class ScanPreprocessor:

    def __init__(self,
                 file_path,
                 document,
                 logger,
                 name_resolver,
                 filename_addon=None,
                 output_path=None) -> None:
        self.logger = logger
        self.name_resolver = name_resolver
        self.document = document
        self.output_file = Path(output_path) / Path(file_path.lstrip("/"))
        if self.output_file.is_file():
            raise FileExistsError(f"'{self.output_file}' already exists")
        self.main()

    def preprocess(self, line):
        return re.sub(r'\s+', ' ', re.sub(r'\t', ' ', line))

    def split_on_genera(self, text):
        tokens = text.split()
        genera = []
        for i in range(0, len(tokens)):
            match = self.name_resolver.match_exact(lookup=tokens[i], rank='genus')
            if match.match:
                genera.append(tokens[i])

        if len(genera)==0:
            return  []

        sections = []
        for genus in reversed(genera):
            idx = text.rfind(genus)
            sections.append(text[idx:])
            text = text[:idx]
        
        sections[len(sections)-1] = text + sections[len(sections)-1]

        return list(reversed(sections))

    def main(self):
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        wrote = 0
        with open(self.output_file, 'w') as file:
            for line in self.document:
                sections = self.split_on_genera(text=self.preprocess(line))
                if len(sections)<2:
                    file.write(line + "\n")
                    wrote += 1
                else:
                    for section in sections:
                        file.write(section + "\n")
                        wrote += 1
        
        self.logger.info("Wrote %s (was %s) lines to %s" % (wrote, len(self.document), self.output_file))

if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('-i','--input-path', type=str, required=True)
    parser.add_argument('-o','--output-path', type=str, required=True)  
    parser.add_argument('-d','--names-database', type=str)
    parser.add_argument('--force-names-reload', action='store_true', default=False)
    parser.add_argument('--debug', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    logger=logging.getLogger()

    name_resolver=NameResolver(
        names_database=args.names_database,
        force_names_reload=args.force_names_reload,
        logger=logger)

    for rel_filepath, document in InputDocs(input_path=args.input_path, raw_lines=True, logger=logger):
        ScanPreprocessor(
            file_path=rel_filepath,
            output_path=args.output_path,
            document=document,
            name_resolver=name_resolver,
            logger=logger)

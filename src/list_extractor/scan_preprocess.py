import argparse
import logging
from pathlib import Path
from name_resolver import NameResolver
from objects import InputDocs
from utils import raw_line_preprocess

class ScanPreprocessor:

    def __init__(self,
                 output_file,
                 document,
                 logger,
                 name_resolver
                 ) -> None:
        self.logger = logger
        self.name_resolver = name_resolver
        self.document = document
        self.output_file = output_file
        self.main()

    def split_on_genera(self, text):
        tokens = text.split()
        genera = []
        for _, token in enumerate(tokens):
            match = self.name_resolver.match_exact(lookup=token, rank='genus')
            if match.match:
                genera.append(token)

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
        wrote = 0
        with open(self.output_file, 'w', encoding='utf-8') as file:
            for line in self.document:
                sections = self.split_on_genera(text=raw_line_preprocess(line))
                if len(sections)<2:
                    file.write(line + "\n")
                    wrote += 1
                else:
                    for section in sections:
                        file.write(section + "\n")
                        wrote += 1

                    self.logger.debug(f"{line} --> {len(sections)}")

        self.logger.info(f"Wrote {wrote} (was {len(self.document)}) lines to {self.output_file}")

if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('-i','--input-path', type=str, required=True)
    parser.add_argument('-o','--output-path', type=str, required=True)
    parser.add_argument('-d','--names-database', type=str)
    parser.add_argument('--force-names-reload', action='store_true', default=False)
    parser.add_argument('--skip-existing', action='store_true', default=False,
                        help="Skip extraction if the output file already exists.")
    parser.add_argument('--debug', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    p_logger=logging.getLogger()

    p_name_resolver=NameResolver(
        names_database=args.names_database,
        force_names_reload=args.force_names_reload,
        separate_genera=True,
        logger=p_logger)

    for file_path, p_document in InputDocs(input_path=args.input_path,
                                           raw_lines=True, logger=p_logger):

        p_output_file = Path(args.output_path) / Path(file_path.lstrip("/"))
        p_output_file = Path(str(p_output_file).replace(p_output_file.suffix,
                                                    f'--preprocessed{p_output_file.suffix}'))

        if args.skip_existing and p_output_file and p_output_file.is_file():
            p_logger.info("Skipping '%s' (output already exists)", str(p_output_file))
            continue

        p_output_file.parent.mkdir(parents=True, exist_ok=True)

        ScanPreprocessor(
            output_file=p_output_file,
            document=p_document,
            name_resolver=p_name_resolver,
            logger=p_logger)

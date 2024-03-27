import argparse
import logging
from data_extractor import DataExtractor
from name_resolver import NameResolver
from output import Output
from seedlist_extractor import SeedlistExtractor
from utils import InputDocs

parser=argparse.ArgumentParser()
parser.add_argument('-i','--input-path', type=str, required=True)
parser.add_argument('-o','--output-path', type=str)
parser.add_argument('-d','--names-database', type=str)
parser.add_argument('--ext','--extension', type=str, default=".json")
parser.add_argument('--force-names-reload', action='store_true', default=False)
parser.add_argument('--fuzzy-match-threshold', type=float, help='Value of 0<1; None for no fuzzy matching')
parser.add_argument('--skip-existing', action='store_true', default=False)
parser.add_argument('--debug', action='store_true', default=False)
args=parser.parse_args()

logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
logger=logging.getLogger()

name_resolver=NameResolver(
    names_database=args.names_database,
    force_names_reload=args.force_names_reload,
    logger=logger)

data_extractor=DataExtractor(
    fuzzy_match_threshold=args.fuzzy_match_threshold,
    name_resolver=name_resolver,
    logger=logger)

output=Output(output_root=args.output_path)

for filename, document in InputDocs(input_path=args.input_path, extension=args.ext, logger=logger):   

    out=output.get_output_path(filename)
    if args.skip_existing and out and out.is_file():
        logger.info("Skipping '%s' (output already exists)", filename)
        continue

    SeedlistExtractor(
        filename=filename,
        document=document,
        data_extractor=data_extractor,
        print_stdout=args.debug,
        output=output,
        logger=logger)

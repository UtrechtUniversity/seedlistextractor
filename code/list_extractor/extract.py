import argparse
import logging
from data_extractor import DataExtractor
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
parser.add_argument('--debug', action='store_true', default=False)
args=parser.parse_args()

logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
logger=logging.getLogger()

data_extractor=DataExtractor(
    fuzzy_match_threshold=args.fuzzy_match_threshold,
    names_database=args.names_database,
    force_names_reload=args.force_names_reload,
    logger=logger)

output=Output(
    output_root=args.output_path,
    logger=logger)

for filename, document in InputDocs(input_path=args.input_path, extension=args.ext, logger=logger):   
    SeedlistExtractor(
        filename=filename,
        document=document,
        data_extractor=data_extractor,
        print_stdout=args.debug,
        output=output,
        logger=logger)

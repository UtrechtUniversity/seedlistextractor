import argparse
import logging
from seedlist_extractor import SeedlistExtractor
from utils import InputDocs

def lines_range(c):
    c=c.split('-')
    return range(int(c[0]), int(c[1]) if len(c)==2 else int(c[0])+1)

parser=argparse.ArgumentParser()
parser.add_argument('-i','--input-path', type=str, required=True)
parser.add_argument('-o','--output-path', type=str)
parser.add_argument('-d','--names-database', type=str)
parser.add_argument('--force-names-reload', action='store_true', default=False)
parser.add_argument('--fuzzy-match-threshold', type=float, help='Value of 0<1; None for no fuzzy matching')
parser.add_argument('--skip-existing', action='store_true', default=False)
parser.add_argument('--exceptions-path')
parser.add_argument('--debug', action='store_true', default=False)
parser.add_argument('--no-stdout', action='store_true', default=False)
parser.add_argument('--lines', type=lines_range, help='Lines to process (start-end)')
args=parser.parse_args()

logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
logger=logging.getLogger()

for document in InputDocs(input_path=args.input_path,
                            extension="json",
                            logger=logger):
    SeedlistExtractor(
        document=document,
        output_path=args.output_path,
        names_database=args.names_database,
        force_names_reload=args.force_names_reload,
        skip_existing=args.skip_existing,
        no_stdout=args.no_stdout,
        line_selection=args.lines,
        fuzzy_match_threshold=args.fuzzy_match_threshold,
        logger=logger)


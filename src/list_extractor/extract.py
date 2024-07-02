import argparse
import logging
from data_extractor import DataExtractor
from name_resolver import NameResolver
from output import Output
from seedlist_extractor import SeedlistExtractor
from utils import InputDocs, JobLog

parser=argparse.ArgumentParser()
parser.add_argument("-i", "--input-path", type=str, required=True, 
                    help="""Path to file or directory (program will also go through 
subdirectories).""")
parser.add_argument("-o", "--output-path", type=str, 
                    help="""Path to directory to write CSV\'s to. If input is a 
directory with subdirectories, structure will be maintained in the output.""")
parser.add_argument("--names-database", type=str, help="""Path to SQLite database with taxonomical
                    names. See 'tools/fill_names_table.py' and 'doc/namelists.md' for details.""")
parser.add_argument("--extract-ipen", action="store_true", default=False, 
                    help="Make program look for IPEN-codes.")
parser.add_argument("--force-names-reload", action="store_true", default=False,
                    help="""During the first run, names are cached in a pickle-file; use this flag
to force reloading names from the database""")
parser.add_argument("--fuzzy-match-threshold", type=float,
                    help="""Fuzzy matching confidence threshold. Value between 0 and 1; skip for no
fuzzy matching.""")
parser.add_argument("--fuzzy-match-strategy", default="best_score",
                    choices=["best_score", "longest_name"], help="""Select the longest, or the
highest scoring of all fuzzy matches for a single line (default: 'best_score').""")
parser.add_argument("--skip-existing", action="store_true", default=False,
                    help="Skip extraction if the output file already exists.")
parser.add_argument("--debug", action="store_true", default=False,
                    help="Print debugging info. Also adds line numbers to the output files.")
parser.add_argument("--stdout", action="store_true", default=False, help="Print output to screen.")
args=parser.parse_args()

logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
logger = logging.getLogger()

name_resolver = NameResolver(
    names_database=args.names_database,
    force_names_reload=args.force_names_reload,
    logger=logger)

data_extractor = DataExtractor(
    extract_ipen=args.extract_ipen,
    fuzzy_match_threshold=args.fuzzy_match_threshold,
    fuzzy_match_strategy = args.fuzzy_match_strategy,
    name_resolver=name_resolver,
    logger=logger)

output = Output(
    output_root=args.output_path,
    include_line_nr=args.debug)

joblog = JobLog(
    input_path=args.input_path,
    output_root=args.output_path,
    skip_existing=args.skip_existing,
    names_database=args.names_database,
    names_count=(
        len(name_resolver.canonical_lookup),
        len(name_resolver.full_name_lookup),
        len(name_resolver.epithet_lookup),
    ),
    extract_ipen=args.extract_ipen,
    fuzzy_match_threshold=args.fuzzy_match_threshold,
    fuzzy_match_strategy=args.fuzzy_match_strategy)

for rel_filepath, document in InputDocs(input_path=args.input_path, logger=logger):   
    output_path = output.get_output_path(rel_filepath)
    if args.skip_existing and output_path and output_path.is_file():
        logger.info("Skipping '%s' (output already exists)", str(output_path))
        joblog.add_skipped(str(output_path))
        continue

    SeedlistExtractor(
        filename=rel_filepath,
        document=document,
        data_extractor=data_extractor,
        stdout=args.stdout,
        output=output,
        logger=logger)

    joblog.add_processed(str(output_path))

joblog.done()

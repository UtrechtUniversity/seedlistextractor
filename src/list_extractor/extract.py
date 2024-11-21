import argparse
import logging
from name_resolver import NameResolver
from objects import (InputDocs, JobLog, FuzzySettings, FuzzyMatchStrategy)
from output import Output
from pathlib import Path
from seedlist_extractor import SeedlistExtractor

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--input_path", type=Path, required=True, 
                    help="""Path to file or directory (program will also go through 
subdirectories).""")
parser.add_argument("-o", "--output_directory", type=Path, 
                    help="""Path to directory to write TSV\'s to. If input is a 
directory with subdirectories, structure will be maintained in the output.
Cannot be combined with --output_in_situ""")
parser.add_argument("--skip_existing", action="store_true", default=False,
                    help="Skip extraction if the output file already exists (default False).")
parser.add_argument("--output_in_situ", action="store_true", default=False,
                    help="""Write output to corresponding input file\'s folder (default False).
Cannot be combined with --output_path""")
parser.add_argument("--fuzzy_threshold", type=float,
                    help="""Fuzzy matching confidence threshold. Value must be
between 0 and 1; omit for no fuzzy matching.""")
parser.add_argument("--fuzzy_strategy", default="best_score",
                    choices=["best_score", "longest_name"], help="""Select the longest, or the
highest scoring of all fuzzy matches for a single line (default: 'best_score').""")
parser.add_argument("--fuzzy_near_blocks", action="store_true", default=False,
                    help=f"""Only look for for fuzzy matches near blocks of exactly matched names,
rather than the entire document. Increases performance at risk of missing names (default False).
Documents of {FuzzySettings.line_block_limit} lines or less are always processed 
in its entirety.""")
parser.add_argument("--extract_ipen", action="store_true", default=False, 
                    help="Extract IPEN-codes (default False).")
parser.add_argument("--names_database", type=str, help="""Path to SQLite database with taxonomic
names. See documentation for details. Mandatory during first run; after that, names are read from cache.""")
parser.add_argument("--force_names_reload", action="store_true", default=False,
                    help="""Force reloading names from the database (recreates names cache).""")
parser.add_argument("--lines", nargs="+", help="""If two values, line numbers of start and end (inclusive) of 
section to process; otherwise, specific lines to process. Separate values by spaces.""")
parser.add_argument("--debug", action="store_true", default=False,
                    help="Print debugging info.")
parser.add_argument("--stdout", action="store_true", default=False, 
                    help=f"""Print output to screen (default False).""")
parser.add_argument("--logfile", type=Path,
                    help="""Logfile path. Leave empty for logging to screen only.""")

args=parser.parse_args()

if args.lines:
    section = sorted([int(x) for x in args.lines])
    if len(section)==2:
        section = range(section[0], section[1]+1)
else:
    section = None

# input_encoding = 'utf-8'
input_encoding = None   # None is auto
names_pickle_file = './pickles/names_pickle'
names_sources_sort_order = {'WCVP': 0, 'WFO': 1, 'CoL': 2, 'GBIF': 3, 'PlantList': 4}
# field_order_in_input = ('ipen', 'name')
field_order_in_input = ('name', 'ipen')

logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(asctime)s::%(levelname)s::%(message)s",)
logger = logging.getLogger()

if args.logfile:
    fh = logging.FileHandler(filename=args.logfile, mode='a')
    fh.setLevel(logging.DEBUG if args.debug else logging.INFO)
    fh.setFormatter(logging.getLogger().handlers[0].formatter)
    logger.addHandler(fh)

fuzzy_options = FuzzySettings(
    match_threshold=args.fuzzy_threshold,
    match_strategy=FuzzyMatchStrategy.LONGEST_NAME if args.fuzzy_strategy=='longest_name' else FuzzyMatchStrategy.BEST_SCORE,
    near_blocks=args.fuzzy_near_blocks)

name_resolver = NameResolver(
    names_database=args.names_database,
    force_names_reload=args.force_names_reload,
    pickle_file=names_pickle_file,
    sources_sort_order=names_sources_sort_order,
    logger=logger)

output = Output(
    output_directory=args.output_directory,
    output_in_situ=args.output_in_situ,
    skip_existing=args.skip_existing,
    field_order_in_input=field_order_in_input,
    print_stdout=args.stdout,
    logger=logger)

joblog = JobLog(
    input_path=args.input_path,
    output_directory=args.output_directory,
    output_in_situ=args.output_in_situ,
    skip_existing=args.skip_existing,
    input_encoding=input_encoding if input_encoding else '(auto-detect)',
    names_pickle_file=names_pickle_file,
    names_database=args.names_database,
    names_sources_sort_order=names_sources_sort_order,
    names_count={
        'canonical': len(name_resolver.canonical_lookup),
        'epithet': len(name_resolver.epithet_lookup),
    },
    extract_ipen=args.extract_ipen,
    field_order_in_input=field_order_in_input,
    fuzzy_options={
        'threshold': fuzzy_options.match_threshold,
        'strategy': fuzzy_options.match_strategy,
        'near_blocks': fuzzy_options.near_blocks,
        'min_tokens': fuzzy_options.min_tokens,
        'min_token_length': fuzzy_options.min_token_length,
        'large_token_length': fuzzy_options.large_token_length,
    }
)

logger.info("Job log: %s", f"{str(joblog.joblog_file)!r}")

for input_file, lines in InputDocs(input_path=args.input_path,
                                   encoding=input_encoding,
                                   logger=logger):

    output.set_output_file(input_file=input_file)

    if not output.can_output():
        logger.info(f'Skipping {str(input_file)!r} (output file {str(output.output_file)!r} already exists)')
        joblog.add_skipped(str(input_file))
        continue

    extract = SeedlistExtractor(
        input_file=input_file,
        lines=lines,
        name_resolver=name_resolver,
        extract_ipen=args.extract_ipen,
        fuzzy_options=fuzzy_options,
        section=section,
        logger=logger)

    lines = extract.run()      
    output.output(lines=lines)

    joblog.add_processed(str(input_file))
    joblog.add_output(str(output.output_file))

joblog.done()

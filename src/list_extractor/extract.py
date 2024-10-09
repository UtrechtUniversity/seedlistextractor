import argparse
import logging
# from data_extractor import DataExtractor
from name_resolver import NameResolver
from objects import (InputDocs, JobLog)
from output import Output
from pathlib import Path
from name_list_checks import NameListChecks
from seedlist_extractor import SeedlistExtractor

parser=argparse.ArgumentParser()
parser.add_argument("-i", "--input_path", type=Path, required=True, 
                    help="""Path to file or directory (program will also go through 
subdirectories).""")
parser.add_argument("-o", "--output_directory", type=Path, 
                    help="""Path to directory to write TSV\'s to. If input is a 
directory with subdirectories, structure will be maintained in the output.
Cannot be combined with --output_in_situ""")
parser.add_argument("--output_in_situ", action="store_true", default=False,
                    help="""Write output to corresponding input file\'s folder.
Cannot be combined with --output_path""")
parser.add_argument("--fuzzy_threshold", type=float,
                    help="""Fuzzy matching confidence threshold. Value must be
between 0 and 1; omit for no fuzzy matching.""")
parser.add_argument("--fuzzy_strategy", default="best_score",
                    choices=["best_score", "longest_name"], help="""Select the longest, or the
highest scoring of all fuzzy matches for a single line (default: 'best_score').""")
parser.add_argument("--fuzzy_near_blocks", action="store_true", default=False,
                    help=f"""Only look for for fuzzy matches near blocks of exactly matched names,
rather than the entire document. Increases performance at risk of missing names. Documents of
{SeedlistExtractor.fuzzy_line_block_limit} lines or less are always processed in its entirety.""")
parser.add_argument("--extract_ipen", action="store_true", default=False, 
                    help="Make program look for IPEN-codes.")
parser.add_argument("--names_database", type=str, help="""Path to SQLite database with taxonomical
names. See documentation for details. Mandatory during first run; subsequently, names are cached.""")
parser.add_argument("--force_names_reload", action="store_true", default=False,
                    help="""Force reloading names from the database.""")
parser.add_argument("--lines", nargs="+", help="""If two values, line numbers of start and end (inclusive) of 
section to process; otherwise, specific lines to process. Separate values by spaces.""")
parser.add_argument("--skip_existing", action="store_true", default=False,
                    help="Skip extraction if the output file already exists.")
parser.add_argument("--debug", action="store_true", default=False,
                    help="Print debugging info.")
parser.add_argument("--stdout", action="store_true", default=False, help=f"""Print output to screen
(first {Output.stdout_col_limit} columns only).
""")
args=parser.parse_args()

if args.lines:
    section = sorted([int(x) for x in args.lines])
    if len(section)==2:
        section = range(section[0], section[1]+1)
else:
    section = None

fuzzy_min_tokens = 2
fuzzy_min_token_length = 3
include_line_nr = True
input_encoding = 'utf-8'

logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
logger = logging.getLogger()

name_resolver = NameResolver(
    names_database=args.names_database,
    force_names_reload=args.force_names_reload,
    logger=logger)

output = Output(
    include_line_nr=include_line_nr,
    output_directory=args.output_directory,
    output_in_situ=args.output_in_situ,
    skip_existing=args.skip_existing,
    print_stdout=args.stdout,
    logger=logger)

joblog = JobLog(
    input_path=args.input_path,
    output_directory=args.output_directory,
    output_in_situ=args.output_in_situ,
    skip_existing=args.skip_existing,
    names_database=args.names_database,
    names_count={
        'canonical': len(name_resolver.canonical_lookup),
        'full': len(name_resolver.full_name_lookup),
        'epithet': len(name_resolver.epithet_lookup),
    },
    extract_ipen=args.extract_ipen,
    fuzzy_threshold=args.fuzzy_threshold,
    fuzzy_strategy=args.fuzzy_strategy,
    fuzzy_near_blocks=args.fuzzy_near_blocks,
    fuzzy_min_tokens=fuzzy_min_tokens,
    fuzzy_min_token_length=fuzzy_min_token_length,
    )

logger.info("Job log: '%s'", str(joblog.joblog_file))

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
        fuzzy_match_threshold=args.fuzzy_threshold,
        fuzzy_match_strategy = args.fuzzy_strategy,
        fuzzy_near_blocks = args.fuzzy_near_blocks,
        section=section,
        logger=logger)

    lines = extract.run()

    # checks = NameListChecks(lines=lines)
    # lines = checks.run()
        
    output.output(lines=lines)

    joblog.add_processed(str(input_file))
    joblog.add_output(str(output.output_file))

joblog.done()

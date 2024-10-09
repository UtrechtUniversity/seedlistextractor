import argparse
import logging
from name_resolver import NameResolver

parser = argparse.ArgumentParser()
parser.add_argument('-l','--lookup', type=str, nargs='+')
parser.add_argument('--epithet', action='store_true', default=False)
parser.add_argument('--genus', action='store_true', default=False)
parser.add_argument('--fuzzy', action='store_true', default=False)
parser.add_argument('-d','--names-database', type=str)
parser.add_argument('--force-names-reload', action='store_true', default=False)
parser.add_argument('-i','--interactive', action='store_true', default=False)

args = parser.parse_args()

if not args.lookup and not args.interactive:
    print("Need either a string to lookup (-l) or be in interactive mode (-i)")
    exit()

logger = logging.getLogger()
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
logger.addHandler(ch)

res = NameResolver(logger=logger,
                    names_database=args.names_database,
                    force_names_reload=args.force_names_reload)

def print_fuzzy_matches(matches):
    for match in matches:
        print(match)

def print_match(match):
    print(match)
    for identical_canonical in match.identical_canonicals:
        print(f"- {identical_canonical.full_name} ({identical_canonical.source})")

if not args.interactive:

    if args.fuzzy:
        print_fuzzy_matches(res.match_fuzzy(lookups=args.lookup))
    else:
        rank = 'epithet' if args.epithet else ('genus' if args.genus else None)
        print_match(res.match_exact(lookup=args.lookup[0], rank=rank))

else:

    print("\nInteractive mode")
    print("(start with 'e+' for epithet, 'g+' for genus; start with 'f+' for fuzzy (species only); 'q' to quit)\n")

    prev = None

    while True:
        lookup = input(f"Lookup (press enter for {prev!r}): " if prev else "Lookup: ").strip()

        if lookup.lower()=='q':
            break

        if prev and len(lookup)==0:
            lookup, prev = prev, None

        if len(lookup)==0:
            continue

        flag = lookup.lower()[:2]
        if flag in ['f+', 'e+', 'g+']:
            lookup = lookup[2:].strip()
        else:
            flag = None
        
        if flag=='f+':
            print(f"Looking up '{lookup}' (fuzzy)")
            print_fuzzy_matches(res.match_fuzzy(lookups=lookup))
        else:
            rank = 'epithet' if flag=='e+' else ('genus' if flag=='g+' else None)
            print(f"Looking up {f'{rank} ' if rank else ''}'{lookup}' (exact)")
            result = res.match_exact(lookup=lookup, rank=rank)
            print_match(result)
            if not result.match and not rank:
                prev = f"f+ {lookup}"
        print("")

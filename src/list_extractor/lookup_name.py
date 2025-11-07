import argparse
from pathlib import Path
from name_resolver import NameResolver

parser = argparse.ArgumentParser()
parser.add_argument('-l','--lookup', type=str, nargs='+')
parser.add_argument('-i','--interactive', action='store_true', default=False)
parser.add_argument('--epithet', action='store_true', default=False)
parser.add_argument('--genus', action='store_true', default=False)
parser.add_argument('--fuzzy', action='store_true', default=False)
parser.add_argument('--pickle-file', type=str, default='./pickles/names_pickle')

args = parser.parse_args()

if not args.lookup and not args.interactive:
    print("Need either a string to lookup (-l) or be run in interactive mode (-i)")
    exit()

names_pickle_file = args.pickle_file

print("Loading", end="\r")

try:
    if not Path(names_pickle_file).exists():
        raise ValueError(f"Pickle file '{names_pickle_file}' does not exist.")
    res = NameResolver(pickle_file=names_pickle_file)
except Exception as e:
    print(f"error: {e}")
    exit()

def print_fuzzy_matches(matches):
    for match in matches:
        print(match)

def print_match(match):
    print(match)
    for x in match.authorships:
        print(f"- {x[0]} ({x[1]})")

if not args.interactive:

    if args.fuzzy:
        print_fuzzy_matches(res.match_fuzzy(lookups=args.lookup))
    else:
        rank = 'epithet' if args.epithet else ('genus' if args.genus else None)
        print_match(res.match_exact(lookup=args.lookup[0], rank=rank))

else:

    print("Interactive mode")
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

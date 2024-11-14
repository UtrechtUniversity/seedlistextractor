import re
from collections import namedtuple
from itertools import groupby
from math import ceil
from statistics import mean
from objects import (
    CandidateObject,
    MatchedNameObject,
    CultivarObject,
    IpenObject,
    LegendItem,
    FuzzySettings,
    FuzzyMatchStrategy)
from utils import (
    remove_outer_non_alpha,
    clean_up_name,
    remove_abbreviations,
    fully_clean,
    raw_line_preprocess,
    single_spaces)
from extraction_utils import (
    extract_synonym_strings,
    extract_cultivar_string,
    extract_ipen,
    extract_split_ipen,
    extract_repeat_symbols)

class SeedlistExtractor:

    def __init__(self,   # pylint: disable=too-many-arguments
                 lines,
                 input_file,
                 name_resolver,
                 logger,
                 extract_ipen = False,
                 fuzzy_options = None,
                 section = None,
                 output_generator = None,
                 output_file = None,
                 stdout = False):

        self.lines = lines
        self.input_file = input_file
        self.name_resolver = name_resolver
        self.logger = logger
        self.extract_ipen = extract_ipen
        self.fuzzy_options = fuzzy_options
        self.section = section
        self.output_generator = output_generator
        self.output_file = output_file
        self.print_stdout = stdout

    def run(self):
        self.logger.info("Processing '%s'", str(self.input_file))

        proc_lines = self.lines

        self.extract_data(lines=proc_lines)
        self.extract_names_fuzzy(lines=proc_lines)
        self.resolve_isolated_epithets(lines=proc_lines)
        self.collect_meta_data(lines=proc_lines)
        self.parse_legend(lines=proc_lines)
        self.compare_genera(lines=proc_lines)

        return proc_lines

    def extract_data(self, lines):
        """Extract mtehod contains main loop, extracting
        various bits of information frome ach line.
        """

        self.logger.info("Processing %s lines", len(lines))

        names = 0

        for line in lines:

            raw_line = raw_line_preprocess(line.raw)

            if len(raw_line)==0:
                continue

            if self.section and line.line_nr not in self.section:
                self.logger.debug('Skipping line %s', line.line_nr)
                continue

            # print(line.line_nr, raw_line)

            # Symbols are extracted but not removed from raw_line, to avoid interfering with extracting legends
            setattr(line, 'repeat_symbols', extract_repeat_symbols(text=raw_line))

            # Synonyms: "[syn. ....]" etc
            # Extracted from string, then resolved as name
            synonyms = []
            for syn_string in extract_synonym_strings(text=raw_line):
                name, _ = self.extract_name(text=syn_string, line_nr=line.line_nr)
                if name:
                    synonyms.append(name)
                    raw_line = raw_line.replace(syn_string, '')
            setattr(line, 'synonyms', synonyms)

            # Extract genus
            name, _ = self.extract_name(text=raw_line, line_nr=line.line_nr, rank='genus')
            if name:
                setattr(line, 'genus', name)

            # Extract isolated epithets (get resolved to full name later)
            name, _ = self.extract_name(text=raw_line, line_nr=line.line_nr, rank='epithet')
            if name:
                setattr(line, 'epithet', name)

            # Extract name from line (species, subspecies, form, variety)
            name, rest_tokens = self.extract_name(text=raw_line, line_nr=line.line_nr)
            if name and name not in line.synonyms:
                setattr(line, 'name', name)
                raw_line = ' '.join(rest_tokens)
                names += 1

            # Cultivars follow a species name between quotes; plain string matches (no database lookup)
            if line.name or line.epithet:
                cultivar = extract_cultivar_string(text=raw_line)
                if cultivar:
                    setattr(line, 'cultivar', CultivarObject(text=cultivar, line_nr=line.line_nr))
                    raw_line = raw_line.replace(cultivar, '')

            if self.extract_ipen:
                # Extract IPEN-code
                ipen, index = extract_ipen(text=raw_line)
                if ipen:
                    raw_line = raw_line.replace(ipen, '')
                else:
                    # Looking for IPENs that have been split over two lines
                    next_lines = [x for x in lines if x.line_nr > line.line_nr and len(raw_line_preprocess(x.raw))>0]
                    if len(next_lines)>0:
                        next_line = next_lines[0]
                        next_raw_line = raw_line_preprocess(next_line.raw)
                        ipen = extract_split_ipen(line_text=raw_line, next_line_text=next_raw_line)
                        if ipen:
                            # We have re-assembled a split IPEN! Now comes the tricky part of removing 
                            # the two "halves"  from the raw line (we don't know exactly where the line
                            # split in the IPEN occurred).
                            self.logger.debug("Lines %s+%s: resolved broken IPEN '%s'", line.line_nr, next_line.line_nr, ipen)
                            first_half = ''
                            for char in reversed(raw_line):
                                first_half = char + first_half
                                if not first_half in ipen:
                                    first_half = first_half[1:]
                                    break
                            raw_line = raw_line.replace(first_half, '')
                            second_half = ''
                            for char in next_raw_line:
                                second_half += char
                                if not second_half in ipen:
                                    second_half = second_half[:-1]
                                    break

                            lines[next_line.line_nr].raw = next_line.raw.replace(second_half, '')

                if ipen:
                    setattr(line, 'ipen', IpenObject(text=ipen, line_nr=line.line_nr, index=index))

            setattr(line, '_rest', raw_line)

        self.logger.info("Found %s names by exact matching", names)

        return lines

    def extract_name(self, text, line_nr, rank=None):
        tokens = text.strip().split()

        if len(tokens)==0:
            return [], tokens

        candidate = None

        for i in range(0, len(tokens)):
            for j in range(len(tokens), 0, -1):
                if j-i < 1:
                    break

                match = self.name_resolver.match_exact(lookup=' '.join(tokens[i:j]), rank=rank)

                if match.match:
                    candidate=(i, j, match)
                    break

            if candidate:
                break

        if candidate:
            # cleanup() takes out non-alpha chars, which will re-appear in the slicing
            # of the (uncleaned) tokens, so we take the longest of the (cleaned) candidates
            # that uses the smallest amount of tokens
            i, j, name_matched = candidate
            name_text, rest = remove_outer_non_alpha(' '.join(tokens[i:j]))
            remaining_tokens = [x for x in tokens[:i]+rest+tokens[j:] if len(x)>0]
            return MatchedNameObject(text=name_text,
                                     match=name_matched.match,
                                     authorships=name_matched.authorships,
                                     score=name_matched.score,
                                     line_nr=line_nr,
                                     index=text.find(name_text)), remaining_tokens

        return None, tokens

    def extract_names_fuzzy(self, lines):
        """Extract names by fuzzy matching

        Function tries to extract names by fuzzy matching from lines that
        do not yet have an exactly matched (sub)species.
        """
        if self.fuzzy_options is None or self.fuzzy_options.match_threshold is None:
            return lines

        def select_lines(lines):
            if not self.fuzzy_options.near_blocks:
                return lines

            if len(lines)<=self.fuzzy_options.line_block_limit:
                return lines

            # First, we select lines to do fuzzy name matching on. As fuzzy matching is expensive,
            # we don't to analyze more lines than we think is necessary, so we look for blocks of
            # line that already have a sizeable amount of identified names, and assume these are
            # the actual lists that are in each seedlist document. Next, we will only fuzzily look
            # within these blocks of lines to find names we've missed (due to typo's, spelling
            # errors, etc.)

            lines_to_check = []
            maxgap = 10
            # Get line numbers of all lines that already have extracted names.
            data = [x.line_nr for x in lines if x.name]

            if len(data)==0:
                return lines

            def cluster(data, maxgap):
                '''
                Arrange data into groups where successive elements
                differ by no more than *maxgap*
                '''
                data.sort()
                groups = [[data[0]]]
                for x in data[1:]:
                    if abs(x - groups[-1][-1]) <= maxgap:
                        groups[-1].append(x)
                    else:
                        groups.append([x])
                return groups

            # We are looking for blocks of names, so we cluster the line numbers, and also weed out
            # lines within these clusters that are empty, have too many tokens (= have lots of
            # text, probably meta data, or even page headers or footers), or already have a name,
            # or just have a genus.
            for clst in cluster(data=data, maxgap=maxgap):
                lines_to_check.extend([x for x in lines
                            if x.line_nr>=min(clst)
                            and x.line_nr<=max(clst)
                            and len(raw_line_preprocess(x.raw))>0
                            and len(raw_line_preprocess(x.raw).split())<10])

            return lines_to_check

        def generate_candidates(tokens, min_tokens=2, max_tokens=8):
            candidates = []
            for i in range(0, len(tokens)):
                for j in range(len(tokens), 0, -1):
                    if j-i < min_tokens:
                        break
                    if j-i > max_tokens:
                        break

                    lookup = ' '.join(tokens[i:j])

                    if len(lookup)>0 and lookup.count(' ')+1>=min_tokens:
                        candidates.append((lookup, j-i))

            return candidates

        # First, we select the lines we're actually going to look in
        lines_to_check = select_lines(lines)
        lines_to_check = [x for x in lines_to_check if (not x.name or (x.name and x.name.match.taxon_rank in ['genus']))]

        # Next we make sure there's no duplicates, and sort the result by line number.
        lines_to_check = sorted(list(set(lines_to_check)), key=lambda x: x.line_nr)

        # For each line, we generate a set of strings to look up. This is a unique list of
        # all possible cleaned up concatenated subsequent tokens.
        candidates = []
        for line in lines_to_check:
            tokens = line.raw.split()
            tokens = [fully_clean(name=x) for x in tokens]
            tokens = list(filter(None, [x for x in tokens if len(x)>=self.fuzzy_options.min_token_length]))

            for option, num_tokens in generate_candidates(tokens=tokens, 
                                                          min_tokens=self.fuzzy_options.min_tokens):
                candidates.append(CandidateObject(
                    line_nr=line.line_nr, 
                    num_tokens=num_tokens,
                    index=line.raw.lower().find(option.lower()),
                    option=option))

            if len(tokens)<self.fuzzy_options.min_tokens:
                for long_token in [x for x in tokens if len(x)>=self.fuzzy_options.large_token_length]:
                    candidates.append(CandidateObject(
                        line_nr=line.line_nr, 
                        num_tokens=1,
                        index=line.raw.lower().find(long_token.lower()),
                        option=long_token))

        uniq = sorted(list(set({x.option for x in candidates})))

        if len(uniq)==0:
            return lines

        self.logger.info("Trying fuzzy matching for %s lines (%s candidates) with confidence threshold %s, using %s", 
                         len(set({x.line_nr for x in candidates if x.option in uniq})), 
                         len(uniq), 
                         self.fuzzy_options.match_threshold, self.fuzzy_options.match_strategy)

        # Next, we feed all unique candidates to the fuzzy matcher.
        matches = self.name_resolver.match_fuzzy(lookups=uniq, include_epithets=False, 
                                                 score_cutoff=self.fuzzy_options.match_threshold)

        for match in matches:
            # We keep the matches that clear the match threshold and match them with the candidates.
            if match.score>=self.fuzzy_options.match_threshold:
                for candidate in [x for x in candidates if x.option.lower()==match.lookup.lower()]:
                    candidate.match=match

        # We lose all candidates that didn't get a match.
        candidates = [x for x in candidates if x.match is not None]
        updated = 0

        #TODO: complete inline documentation
        for line_nr, group in groupby(candidates, lambda x: x.line_nr):

            l_group = list(group)

            if self.fuzzy_options.match_strategy==FuzzyMatchStrategy.BEST_SCORE:
                # match with best score > longest string > shortest number of tokens
                best = sorted(l_group, key=lambda x: (-x.match.score, -len(x.option), x.num_tokens))[0]
            else:
                # match with longest string > best score > shortest number of tokens
                best = sorted(l_group, key=lambda x: (-len(x.option), -x.match.score, x.num_tokens))[0]

            line = [x for x in lines if x.line_nr==line_nr][0]

            if line.name:
                self.logger.debug("Replaced '%s' (%s) [%s] with '%s' (%s) [%s] from \"%s\"",
                                 line.name.match.canonical_name,
                                 line.name.match.taxon_rank,
                                 line.name.score,
                                 best.match.match.canonical_name,
                                 best.match.match.taxon_rank,
                                 best.match.score,
                                 line.raw)
            else:
                self.logger.debug("Extracted '%s' (%s) [%s] from \"%s\"",
                                 best.match.match.canonical_name,
                                 best.match.match.taxon_rank,
                                 best.match.score,
                                 line.raw)

            setattr(line, 'name', MatchedNameObject(text=best.option,
                                                    match=best.match.match,
                                                    score=best.match.score,
                                                    authorships=best.match.authorships,
                                                    index=best.index,
                                                    line_nr=line_nr))

            for bit in best.option.split():
                line._rest = line._rest.replace(bit, '').strip()

            updated += 1

        self.logger.info("Found %s names by fuzzy matching", updated)

        return lines

    def resolve_isolated_epithets(self, lines):
        """Resolve isolated epithets into full names

        Function tries to combines epithets of lines containing just that
        with the genus of the preceding line into a complete name.
        """

        def match_candidate(tokens, prev, line):
            name, _ = self.extract_name(text=" ".join(tokens), line_nr=line.line_nr)
            if name and name.match.canonical_name != prev.name:

                # if prev was resolved fuzzily, we use its original string for score calculation
                if prev.original:
                    name.text = f"{prev.original if prev.original else prev.name} {' '.join(tokens[1:])}"

                name.score = self.name_resolver.levenshtein_ratio_normalized(
                    str1=fully_clean(name.text),
                    str2=fully_clean(name.match.canonical_name),
                    score_cutoff=0)

                setattr(line, 'name', name)

                p_line = [x for x in lines if x.line_nr == prev.line_nr][0]
                p_line.name_repeated += 1

                return True

            return False

        PrevName = namedtuple('PrevName', ['name', 'original', 'line_nr'])
        p_genus = PrevName(name=None, original=None, line_nr=-1)
        p_genus_alt = PrevName(name=None, original=None, line_nr=-1)
        p_species = PrevName(name=None, original=None, line_nr=-1)

        names = 0

        for line in lines:

            matched = False

            if (bool(line.epithet) and line.epithet.score==1) and (not line.name or line.name.match.taxon_rank=='genus'):

                # looking for possible subspecies (etc)
                # 0 symbols = lists that don't use repeater symbols, 2 for ones that do
                if p_species.name and (len(line.repeat_symbols) in [0,2]):
                    matched = match_candidate(
                        tokens=[p_species.name, line.epithet.match.epithet],
                        prev=p_species,
                        line=line)

                # if nothing found, looking for possible species
                # 0 symbols = lists that don't use repeater symbols, 1 for ones that do
                if not matched and p_genus.name and (len(line.repeat_symbols)<=1):
                    matched = match_candidate(
                    tokens=[p_genus.name, line.epithet.match.epithet],
                    prev=p_genus,
                    line=line)

                if not matched and p_genus_alt.name and (len(line.repeat_symbols)<=1):
                    matched = match_candidate(
                        tokens=[p_genus_alt.name, line.epithet.match.epithet],
                        prev=p_genus_alt,
                        line=line)
                    if matched:
                        self.logger.debug(f"Fuzzy genus match: {p_genus_alt.name} {line.epithet.match.epithet}")

                names += 1 if matched else 0

            # repeater symbols trump identified genus (epithets are occasionally identified as genera as well)
            if line.genus and len(line.repeat_symbols)==0:
                p_genus = PrevName(name=line.genus.match.genus, original=None, line_nr=line.line_nr)
                p_species = PrevName(name=None, original=None, line_nr=-1)
                p_genus_alt = PrevName(name=None, original=None, line_nr=-1)

                if line.name and line.name.score < 1:
                    parts = line.name.match.canonical_name.split()
                    if parts[0] != p_genus.name:
                        p_genus_alt = PrevName(name=parts[0], original=p_genus.name, line_nr=line.line_nr)

            elif line.name and line.name.score < 1 and len(line.repeat_symbols)==0:
                # this can happen if the species name was identified fuzzily; we don't also do fuzzy matching for
                # genus, so that will most likely be empty
                parts = line.name.match.canonical_name.split()
                p_genus = PrevName(name=parts[0], original=None, line_nr=line.line_nr)
                p_genus_alt = PrevName(name=None, original=None, line_nr=-1)
                p_species = PrevName(name=None, original=None, line_nr=-1)

            if line.name:
                parts = line.name.match.canonical_name.split()
                p_species = PrevName(name=" ".join(parts[:2]), original=line.name.text, line_nr=line.line_nr)

        self.logger.info("Found %s names by resolving isolated epithets", names)

        return lines

    def compare_genera(self, lines):
        for line in lines:
            if not line.name:
                continue

            score = 1

            if line.genus:
                g_genus = line.genus.match.genus.lower()
            else:
                g_genus = line.name.text.split()[0].lower()

            g_species = line.name.match.genus.lower()
            
            if not g_genus==g_species:
                score = self.name_resolver.levenshtein_ratio_normalized(
                    str1=g_genus,
                    str2=g_species,
                    score_cutoff=0)

            setattr(line, 'genus_match_score', score)

    @staticmethod
    def collect_meta_data(lines, max_look_ahead=5):
        for line in [x for x in lines if x.name or x.epithet]:
            # promote remaining tokens from the same line to meta data
            if line._rest:  # pylint: disable=protected-access
                setattr(line, 'meta_rest', line._rest.strip())  # pylint: disable=protected-access
                setattr(line, '_rest', None)

            # look for next lines w/o anything
            next_items=[]
            for l_next in [x for x in lines if x.line_nr>line.line_nr]:
                if l_next.name \
                    or l_next.epithet \
                    or l_next.cultivar \
                    or len(l_next.synonyms)>0:
                    break
                if len(next_items)>=max_look_ahead:
                    break
                if len(l_next.raw.strip())>0:
                    next_items.append(l_next.raw.strip())

            if len(next_items)>0:
                setattr(line, 'meta_next', next_items)

        # setting the length of the list of lines of the final element
        # to the average of the preceding lines
        l_meta_next = [len(x.meta_next) for x in lines if x.name]
        if len(l_meta_next)>3:
            last = [x for x in lines if x.name][-1]
            setattr(last, 'meta_next', last.meta_next[:ceil(mean(l_meta_next[1:-1]))])

        return lines

    @staticmethod
    def parse_legend(lines):  # pylint: disable=too-many-branches

        symbols=[
            '*A*', '*F*', '*G*', '*P*',
            '(**)', '(*)', '**', '*',
            '(++)', '(+)', '++', '+',
            '^', '%', '#', 'º', '!',
            'CW', 'IAS', '(W)', 'Ø',
            'A', 'G', 'P', 'W', 'U', 'Z', 
            '☉', '⚇', '♃', '🌲', '🌳', '🌿', '🏠',
            ]

        legend=[]

        # find & count presence of symbols in lines with names' their metadata
        for line in lines:
            if not line.has_names_or_code():
                continue
            if not line.meta_rest and not line.meta_next:
                continue
            tmp = line.meta_rest if line.meta_rest else "" + \
                  " ".join(line.meta_next) if line.meta_next else ""
            for symbol in symbols:
                if not re.search(f'(^| ){re.escape(symbol)}( |$)', tmp):
                    continue
                p = [x for x in legend if x.symbol==symbol]
                if len(p)==0:
                    legend.append(LegendItem(symbol=symbol))
                else:
                    p[0].increase_count()

        # we assume the ones that are letters and have a relative low count
        # are remnants, not reference symbols
        total = sum(x.count for x in legend)
        legend = [x for x in legend if not x.symbol.isalpha()
                                       or (x.symbol.isalpha() and x.count/total>0.01)]

        # go through all doc lines that have no names data to look for possible
        # legends for each symbol
        for line in lines:
            if line.has_names_or_code():
                continue

            if len(line.raw.strip())==0:
                continue
            for item in legend:
                if (  # pylint: disable=line-too-long
                    re.search(rf'^(\s*){re.escape(item.symbol)}(:| |,|-|=)(.*)', line.raw, re.MULTILINE) \
                    or re.search(rf'^[^„\"“]*(„|\"|“)\s+{re.escape(item.symbol)}\s+(\"|”|“)(.*)$', line.raw)
                    ) and re.search(r'[a-zA-Z]+', line.raw):
                    item.add_descriptor(descriptor=single_spaces(line.raw))

        # for any symbol that doesn't have a descriptor yet, search more generally
        # for the symbol, and use the matching line that has the least capital letters
        # to avoid using a line that has a unmatched bit of species name.
        for item in [x for x in legend if not x.descriptor]:
            candidates=[]
            for line in lines:
                if line.has_names_or_code():
                    continue
                smbl = re.escape(item.symbol)
                if re.search(r'([: ,-=\n]{1}'+smbl+'[\b ]{1}|[\b ]{1}'+smbl+'[: ,-=\n]{1})', line.raw):  # pylint: disable=line-too-long
                    if sum(1 for c in line.raw if c.isalpha())>0:
                        candidates.append(line.raw)
            if len(candidates)>0:
                item.add_descriptor(descriptor=sorted(candidates,
                                    key=lambda x: sum(1 for c in x if c.isupper()))[0])

        # get rid of the ones that still have no descriptor
        legend=[x for x in legend if x.descriptor]

        # add the relevant descriptors to species
        for line in lines:
            if not line.name:
                continue
            if not line.meta_rest and not line.meta_next:
                continue

            tmp=line.meta_rest if line.meta_rest else "" + \
                " ".join(line.meta_next) if line.meta_next else ""
            refs=[]

            for item in legend:
                smbl=re.escape(item.symbol)
                if re.search(rf'[\W^]?{smbl}[\W$]?', tmp):
                    refs.append(item.descriptor)

            setattr(line, 'ref', refs)

        return lines


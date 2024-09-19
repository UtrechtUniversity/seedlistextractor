from collections import namedtuple
from itertools import groupby
from utils import (remove_outer_non_alpha, clean_up_name, remove_abbreviations, raw_line_preprocess)
from extraction_utils import (extract_synonym_strings,  extract_cultivar_string, extract_ipen, extract_split_ipen, extract_repeat_symbols)
from objects import (CandidateObject, MatchedNameObject, CultivarObject, IpenObject)

class DataExtractor:

    fuzzy_min_tokens = 2
    fuzzy_min_token_length = 3

    def __init__(self,
                 logger,
                 name_resolver,
                 extract_ipen = False,
                 fuzzy_match_threshold = None,
                 fuzzy_match_strategy = 'best_score',
                 fuzzy_match_whole_doc = False,
                 section = None
                 ) -> None:

        self.logger = logger
        self.name_resolver = name_resolver
        self.extract_ipen = extract_ipen
        self.fuzzy_match_threshold = None
        self.fuzzy_match_whole_doc = fuzzy_match_whole_doc
        if fuzzy_match_threshold is not None:
            if isinstance(fuzzy_match_threshold, float) and 0 < fuzzy_match_threshold < 1:
                self.fuzzy_match_threshold=fuzzy_match_threshold
            else:
                raise ValueError("fuzzy_match_threshold should be a float between 0 and 1")

        strats = ['longest_name', 'best_score']
        if fuzzy_match_strategy in strats:
            self.fuzzy_match_strategy = fuzzy_match_strategy
        else:
            raise ValueError(f"fuzzy_match_strategy can be: {strats}")

        self.section = section

    def extract(self, lines):
        """Extract mtehod contains main loop, extracting
        various bits of information frome ach line.
        """

        self.logger.info("Processing %s lines", len(lines))

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

            # Extract name from line (genus, species, subspecies, form, variety)
            name, rest_tokens = self.extract_name(text=raw_line, line_nr=line.line_nr)
            if name and name not in line.synonyms:
                setattr(line, 'name', name)

                # We have run into names that are recognized as both genus and epithet
                if line.name.match.taxon_rank=='genus':
                    name, _ = self.extract_name(text=raw_line, line_nr=line.line_nr, rank='epithet')
                    if name:
                        setattr(line, 'epithet', name)

                raw_line = ' '.join(rest_tokens)

            # Extract isolated epithets (get resolved to full name later)
            if line.name is None and line.epithet is None:
                name, _ = self.extract_name(text=raw_line, line_nr=line.line_nr, rank='epithet')
                if name:
                    setattr(line, 'epithet', name)
                    raw_line = raw_line.replace(name.text, '')

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

        # Fuzzy matching is outside the main loop because it benefits from
        # processing batches of lines
        if self.fuzzy_match_threshold is not None:
            lines = self.extract_names_fuzzy(lines=lines)

        self.resolve_isolated_epithets(lines=lines)

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
                                     identical_canonicals=name_matched.identical_canonicals,
                                     score=name_matched.score,
                                     line_nr=line_nr,
                                     index=text.find(name_text)), remaining_tokens

        return None, tokens

    def extract_names_fuzzy(self, lines):
        """Extract names by fuzzy matching

        Function tries to extract names by fuzzy matching from lines that
        do not yet have an exactly matched (sub)species.
        """

        def select_lines(lines):
            if self.fuzzy_match_whole_doc:
                return lines

            # First we select lines to do fuzzy name matching on. As fuzzy matching is expensive,
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

        def generate_candidates(tokens, min_tokens, min_token_length, max_tokens=8):
            tokens = [clean_up_name(remove_abbreviations(name=x)) for x in tokens]
            tokens = list(filter(None, [x for x in tokens if len(x)>=min_token_length]))

            candidates = []
            for i in range(0, len(tokens)):
                for j in range(len(tokens), 0, -1):
                    if j-i < min_tokens:
                        break
                    if j-i > max_tokens:
                        break

                    # lookup = clean_up_name(remove_abbreviations(name=' '.join(tokens[i:j])))
                    lookup = ' '.join(tokens[i:j])

                    if len(lookup)>0 and lookup.count(' ')+1>=min_tokens:
                        candidates.append((i, j, lookup))

            return candidates

        # First, we select the lines we're actually going to look in
        lines_to_check = select_lines(lines)
        lines_to_check = [x for x in lines_to_check if (not x.name or (x.name and x.name.match.taxon_rank in ['genus']))]

        # Next we make sure there's no duplicates, and sort the result by line number.
        lines_to_check = sorted(list(set(lines_to_check)), key=lambda x: x.line_nr)

        # For each line, we generate a set of strings to look up. This is a unique list of
        # all possible cleaned up concatenated subsequent tokens (minimum length of 2 tokens).
        candidates = []
        for line in lines_to_check:
            tokens = line.raw.split()
            for start, end, option in generate_candidates(tokens=tokens, 
                                                          min_tokens=self.fuzzy_min_tokens,
                                                          min_token_length=self.fuzzy_min_token_length):
                candidates.append(CandidateObject(
                    line_nr=line.line_nr, start=start, end=end,
                    index=line.raw.lower().find(option.lower()),
                    option=option))

        uniq = sorted(list(set({x.option for x in candidates})))

        if len(uniq)==0:
            return lines

        self.logger.info("Trying fuzzy matching for %s lines (%s candidates) with confidence threshold %s, using %s", 
                         len(set({x.line_nr for x in candidates if x.option in uniq})), 
                         len(uniq), 
                         self.fuzzy_match_threshold, self.fuzzy_match_strategy)

        # Next, we feed all unique candidates to the fuzzy matcher.
        matches = self.name_resolver.match_fuzzy(lookups=uniq, include_epithets=False, score_cutoff=self.fuzzy_match_threshold)

        for match in matches:
            # We keep the matches that clear the match threshold and match them with the candidates.
            if match.score>=self.fuzzy_match_threshold:
                for candidate in [x for x in candidates if x.option.lower()==match.lookup.lower()]:
                    candidate.match=match

        # We lose all candidates that didn't get a match.
        candidates = [x for x in candidates if x.match is not None]
        updated = 0

        #TODO: complete inline documentation
        for line_nr, group in groupby(candidates, lambda x: x.line_nr):

            l_group = list(group)

            # # match with best score > longest string > shortest number of tokens
            # best_score = sorted(l_group, key=lambda x: (-x.match.score, -len(x.option), (x.end-x.start)))[0]

            # # match with longest string > best score > shortest number of tokens
            # best_longest = sorted(l_group, key=lambda x: (-len(x.option), -x.match.score, (x.end-x.start)))[0]

            if self.fuzzy_match_strategy=='best_score':
                # match with best score > longest string > shortest number of tokens
                best = sorted(l_group, key=lambda x: (-x.match.score, -len(x.option), (x.end-x.start)))[0]
            else:
                # match with longest string > best score > shortest number of tokens
                best = sorted(l_group, key=lambda x: (-len(x.option), -x.match.score, (x.end-x.start)))[0]

            line = [x for x in lines if x.line_nr==line_nr][0]

            # if best_score.match.match.canonical_name != best_longest.match.match.canonical_name:
            #     self.logger.debug("highest: %s --> %s (%s); longest: %s --> %s (%s) - [%s]",
            #                         best_score.option,
            #                         best_score.match.match.canonical_name,
            #                         best_score.match.score,
            #                         best_longest.option,
            #                         best_longest.match.match.canonical_name,
            #                         best_longest.match.score,
            #                         line.raw)

            if line.name:
                self.logger.debug("replaced '%s' (%s) [%s] with '%s' (%s) [%s] from \"%s\"",
                                 line.name.match.canonical_name,
                                 line.name.match.taxon_rank,
                                 line.name.score,
                                 best.match.match.canonical_name,
                                 best.match.match.taxon_rank,
                                 best.match.score,
                                 line.raw)
            else:
                self.logger.debug("extracted '%s' (%s) [%s] from \"%s\"",
                                 best.match.match.canonical_name,
                                 best.match.match.taxon_rank,
                                 best.match.score,
                                 line.raw)

            setattr(line, 'name', MatchedNameObject(text=best.option,
                                                    match=best.match.match,
                                                    score=best.match.score,
                                                    identical_canonicals=best.match.identical_canonicals,
                                                    index=best.index,
                                                    line_nr=line_nr))

            for bit in best.option.split():
                line._rest = line._rest.replace(bit, '').strip()

            updated+=1

        self.logger.info("Found %s names by fuzzy matching", updated)

        return lines
 
    def resolve_isolated_epithets(self, lines):
        """Resolve isolated epithets into full names

        Function tries to combines epithets of lines containing just that
        with the genus of the preceding line into a complete name.
        """

        PrevName = namedtuple('PrevName', ['name', 'score', 'line_nr'])
        p_genus = PrevName(name=None, score=0, line_nr=-1)
        p_species = PrevName(name=None, score=0, line_nr=-1)

        for line in lines:

            name = None

            if (bool(line.epithet) and line.epithet.score==1) and (not line.name or line.name.match.taxon_rank=='genus'):

                if p_species.name and (len(line.repeat_symbols) in [0,2]):
                    
                    name, _ = self.extract_name(text=f"{p_species.name} {line.epithet.match.epithet}", line_nr=line.line_nr)
                    if name and name.match.canonical_name != p_species.name:
                        name.score *= p_species.score
                        setattr(line, 'name', name)
                        p_line = [x for x in lines if x.line_nr == p_species.line_nr][0]
                        p_line.name_repeated += 1
                        p_line.name.match.possibly_partial = len(line.repeat_symbols)==0
                    else:
                        name = None

                if not name and p_genus.name and (len(line.repeat_symbols)<=1):

                    name, _ = self.extract_name(text=f"{p_genus.name} {line.epithet.match.epithet}", line_nr=line.line_nr)
                    if name and name.match.canonical_name != p_genus.name:
                        name.score *= p_genus.score
                        setattr(line, 'name', name)
                        p_line = [x for x in lines if x.line_nr == p_genus.line_nr][0]
                        p_line.name_repeated += 1

            if line.name:
                parts = line.name.match.canonical_name.split()
                p_genus = PrevName(name=parts[0], score=line.name.score, line_nr=line.line_nr)
                if line.name.match.taxon_rank=='genus':
                    p_species = PrevName(name=None, score=0, line_nr=-1)
                else:
                    p_species = PrevName(name=" ".join(parts[:2]), score=line.name.score, line_nr=line.line_nr)

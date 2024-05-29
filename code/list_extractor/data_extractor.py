from itertools import groupby
from utils import (remove_outer_non_alpha, clean_up_name, remove_abbreviations, raw_line_preprocess)
from extraction_utils import (extract_synonym_strings, extract_cultivar_string, extract_ipen, extract_repeater)
from objects import (CandidateObject, MatchedNameObject, CultivarObject, IpenObject)

class DataExtractor:
    
    def __init__(self,
                 logger,
                 name_resolver,
                 fuzzy_match_threshold = None,
                 fuzzy_match_strategy = 'longest_name',
                 ) -> None:

        self.logger = logger
        self.name_resolver = name_resolver
        self.fuzzy_match_threshold = None
        if fuzzy_match_threshold is not None:
            if isinstance(fuzzy_match_threshold, float) and 0 < fuzzy_match_threshold < 1:
                self.fuzzy_match_threshold=fuzzy_match_threshold
            else:
                raise ValueError("fuzzy_match_threshold should be a float between 0 and 1")

        strats = ['longest_name', 'best_score']
        if fuzzy_match_strategy in strats:
            self.fuzzy_strategy = fuzzy_match_strategy
        else:
            raise ValueError(f"fuzzy_strategy can be: {strats}")

    def extract(self, lines):

        def get_next_non_empty_line(key):
            i = 1
            while True:
                next_raw = raw_line_preprocess(lines[key+i].raw)
                i += 1
                if len(next_raw)>0 or key+i>=len(lines):
                    break
            return next_raw

        self.logger.info("Processing %s lines", len(lines))

        for key, line in enumerate(lines):
            raw_line = raw_line_preprocess(line.raw)

            if len(raw_line)==0:
                continue

            # print(line.line_nr, raw_line)

            setattr(line, 'repeater', extract_repeater(text=raw_line))
            # not removing symbols from raw_line, can interfere with extracting legends

            # synonyms "[syn. ....]" etc
            # but we add them only if they resolve
            synonyms = []
            for syn_string in extract_synonym_strings(text=raw_line):
                name, _ = self.extract_name(text=syn_string, line_nr=line.line_nr)
                if name:
                    synonyms.append(name)
                    raw_line = raw_line.replace(syn_string, '')
            setattr(line, 'synonyms', synonyms)

            # name (genus, species, subspecies, form, variety)
            name, rest_tokens = self.extract_name(text=raw_line, line_nr=line.line_nr)
            if name and name not in line.synonyms:
                setattr(line, 'name', name)
                raw_line = ' '.join(rest_tokens)

            # isolated epithets (only when there's no complete species names)
            if line.name is None:
                name, _ = self.extract_name(text=raw_line, line_nr=line.line_nr, rank='epithet')
                if name:
                    setattr(line, 'epithet', name)
                    raw_line = raw_line.replace(name.text, '')

            # cultivars should follow a species name, and are plain string matches (no database lookup)
            if line.name or line.epithet:
                cultivar = extract_cultivar_string(text=raw_line)
                if cultivar:
                    setattr(line, 'cultivar', CultivarObject(text=cultivar, line_nr=line.line_nr))
                    raw_line = raw_line.replace(cultivar, '')

            ipen, index = extract_ipen(text=raw_line)

            # resolving IPENs that have been split over two lines
            if not ipen:
                next_raw = get_next_non_empty_line(key)
                # next_raw = raw_line_preprocess(lines[key+1].raw)
                next_ipen, _ = extract_ipen(text=next_raw)
                if not next_ipen:
                    ipen, index = extract_ipen(text=raw_line+next_raw)
                    if ipen:
                        first_half = ''
                        for chr in reversed(raw_line):
                            first_half = chr + first_half
                            if not first_half in ipen:
                                first_half = first_half[1:]
                                break
                        raw_line = raw_line.replace(first_half, '')
                        second_half = ''
                        for chr in next_raw:
                            second_half += chr
                            if not second_half in ipen:
                                second_half = second_half[:-1]
                                break
                        lines[key+1].raw = lines[key+1].raw.replace(second_half, '')
            else:
                raw_line = raw_line.replace(ipen, '')

            if ipen:
                setattr(line, 'ipen', IpenObject(text=ipen, line_nr=line.line_nr, index=index))

            setattr(line, '_rest', raw_line)

        self.resolve_repeaters_and_isolated_epithets(lines=lines)

        # extract_names_fuzzy is outside the main loop because it benefits from
        # processing batches of lines
        if self.fuzzy_match_threshold is not None:
            lines = self.extract_names_fuzzy(lines=lines)

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

                lookup = clean_up_name(remove_abbreviations(name=' '.join(tokens[i:j])))

                if len(lookup)==0:
                    continue

                match = self.name_resolver.match_exact(lookup=lookup, rank=rank)

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
                                     score=name_matched.score,
                                     line_nr=line_nr,
                                     index=text.find(name_text)), remaining_tokens

        return None, tokens

    def extract_names_fuzzy(self, lines):

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

        # TODO explain cluster
        # select lines to do fuzzy name matching on, fuzzy matching is expensive, so we try
        # to not analyze more lines than necessary theoretically

        lines_to_check = []
        maxgap = 10
        data = [x.line_nr for x in lines if x.name]

        for clst in cluster(data=data, maxgap=maxgap):
            lines_to_check.extend([x for x in lines
                        if x.line_nr>=min(clst)
                        and x.line_nr<=max(clst)
                        and len(raw_line_preprocess(x.raw))>0
                        and len(raw_line_preprocess(x.raw).split())<10
                        and (not x.name or (x.name and x.name.match.taxon_rank=='genus'))])

        lines_to_check = sorted(list(set(lines_to_check)), key=lambda x: x.line_nr)

        def generate_candidates(tokens, min_token_len=1, max_token_length=8):
            candidates=[]
            for i in range(0, len(tokens)):
                for j in range(len(tokens), 0, -1):
                    if j-i<min_token_len:
                        break
                    if j-i>max_token_length:
                        break

                    lookup=clean_up_name(remove_abbreviations(name=' '.join(tokens[i:j])))

                    if len(lookup)>0 and lookup.count(' ')+1>=min_token_len:
                        candidates.append((i, j, lookup))

            return candidates

        candidates=[]

        for line in lines_to_check:
            tokens=line.raw.split()
            for i, j, option in generate_candidates(tokens=tokens, min_token_len=2):
                candidates.append(CandidateObject(
                    line_nr=line.line_nr, i=i, j=j,
                    index=line.raw.lower().find(option.lower()),
                    option=option))

        uniq=sorted(list(set({x.option for x in candidates})))
    
        if len(uniq)==0:
            return lines

        self.logger.info("Trying fuzzy matching for %s lines with confidence threshold %s, using %s", 
                         len(set({x.line_nr for x in candidates if x.option in uniq})), 
                         self.fuzzy_match_threshold, self.fuzzy_strategy)

        matches=self.name_resolver.match_fuzzy(lookups=uniq)

        for match in matches:
            if match.score>=self.fuzzy_match_threshold:
                for candidate in [x for x in candidates if x.option==match.lookup]:
                    candidate.match=match

        candidates=[x for x in candidates if x.match is not None]
        updated=0
        for line_nr, group in groupby(candidates, lambda x: x.line_nr):

            l_group = list(group)

            # match with best score > longest string > shortest number of tokens
            best_score = sorted(l_group, key=lambda x: (-x.match.score, -len(x.option), (x.j-x.i)))[0]

            # match with longest string > best score > shortest number of tokens
            best_longest = sorted(l_group, key=lambda x: (-len(x.option), -x.match.score, (x.j-x.i)))[0]

            if self.fuzzy_strategy=='best_score':
                best = best_score
            else:
                best = best_longest


            line = [x for x in lines if x.line_nr==line_nr][0]

            # if best_score.match.match.canonical_name != best_longest.match.match.canonical_name:
            #     self.logger.debug("highest: %s --> %s (%s); longest: %s --> %s (%s) - [%s]",
            #                       best_score.option,
            #                       best_score.match.match.canonical_name,
            #                       best_score.match.score,
            #                       best_longest.option,
            #                       best_longest.match.match.canonical_name,
            #                       best_longest.match.score,
            #                       line.raw)

            if line.name:
                self.logger.debug("replaced  '%s' (%s) [%s] with '%s' (%s) [%s] from \"%s\"",
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
                                                    index=best.index,
                                                    line_nr=line_nr))

            for bit in best.option.split():
                line._rest = line._rest.replace(bit, '').strip()

            updated+=1

        self.logger.info("Found %s names by fuzzy matching", updated)

        return lines
 
    def resolve_repeaters_and_isolated_epithets(self, lines):
        # resolving epithets with "repeater symbols" & isolated epitheps to full names
        p_genus = None

        for line in lines:
            # if p_genus and (line._rest is None or len(line._rest.strip())<=5):
            if p_genus:
                if line.repeater:
                    candidate = f"{p_genus} {line.raw[line.raw.find(line.repeater):]}"
                elif (bool(line.epithet) and line.epithet.score==1) and not line.name:
                    candidate = f"{p_genus} {line.epithet.text}"
                else:
                    candidate = None

                if candidate:
                    name, _ = self.extract_name(text=candidate, line_nr=line.line_nr)
                    if name and name.text != p_genus:
                        setattr(line, 'name', name)

            if line.name and line.name.match.taxon_rank=='genus':
                p_genus = line.name.text
            elif line.name:
                p_genus = line.name.text.split()[0]

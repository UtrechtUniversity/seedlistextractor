from itertools import groupby
from utils import (remove_outer_non_alpha, clean_up_name, remove_abbreviations, raw_line_preprocess)
from extraction_utils import (MatchedNameObject, CultivarObject, IpenObject, 
                              extract_synonym_strings, extract_cultivar_string, extract_ipen, extract_repeater)

class DataExtractor:
    
    def __init__(self,
                 logger,
                 name_resolver,
                 fuzzy_match_threshold,
                 strict_exact_matching=False
                 ) -> None:

        self.logger = logger
        self.name_resolver = name_resolver
        self.fuzzy_match_threshold = None
        if fuzzy_match_threshold is not None:
            if isinstance(fuzzy_match_threshold, float) and 0 < fuzzy_match_threshold < 1:
                self.fuzzy_match_threshold=fuzzy_match_threshold
            else:
                raise ValueError("fuzzy_match_threshold should be a float between 0 and 1")
        self.strict_exact_matching=strict_exact_matching

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
            raw_no_ipen = raw_line
            if len(raw_line)==0:
                continue

            setattr(line, 'repeater', extract_repeater(text=raw_line))
            # removing some symbols interferes with extracting legends
            # raw_line=raw_line.replace(str(line.repeater), '', 1)

            """
            extract_name() / extract_species_fuzzy() return:
                name, remaining_tokens
            'name' contains:
                ('name (in text)', 'matched name (from database)', score)
            """

            # synonyms "[syn. ....]" etc
            # but we add them only if they resolve
            synonyms = []
            for syn_string in extract_synonym_strings(text=raw_line):
                name, _ = self.extract_name(text=syn_string, rank='species', line_nr=line.line_nr)
                if name:
                    synonyms.append(name)
                    raw_line = raw_line.replace(syn_string, '')
            setattr(line, 'synonyms', synonyms)

            # species name
            name, rest_tokens = self.extract_name(text=raw_line, rank='species', line_nr=line.line_nr)
            if name and name not in line.synonyms:
                setattr(line, 'species', name)
                raw_line = ' '.join(rest_tokens)

            # species names that have been split over two lines
            # (doing the same thing for IPEN further down)
            if not name:
                next_raw = get_next_non_empty_line(key)
                next_name, _ = self.extract_name(text=next_raw, rank='species', line_nr=line.line_nr)
                if not next_name:
                    name, rest_tokens = self.extract_name(text=raw_line+' '+next_raw, rank='species', line_nr=line.line_nr)
                    if name and name not in line.synonyms:
                        setattr(line, 'species', name)
                        for bit in clean_up_name(name.text).split():
                            raw_line = raw_line.replace(bit, '')
                            next_raw = next_raw.replace(bit, '')

                        lines[key+1].raw = next_raw

            # genus and isolated epithets (only when there's no complete species names)
            if line.species is None:
                rest_tokens = []
                for rank in ['genus', 'epithet']:
                    name, _ = self.extract_name(text=raw_line, rank=rank, line_nr=line.line_nr)
                    if name:
                        setattr(line, rank, name)
                        raw_line = raw_line.replace(name.text, '')

            # cultivars should follow a species name, and are plain string matches (no database lookup)
            if line.species or line.epithet:
                cultivar = extract_cultivar_string(text=raw_line)
                if cultivar:
                    setattr(line, 'cultivar', CultivarObject(text=cultivar, line_nr=line.line_nr))
                    raw_line = raw_line.replace(cultivar, '')

            ipen, index = extract_ipen(text=raw_line)

            # resolving IPENs that have been split over two lines
            # if not ipen and len(lines)>=key+1:
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

            if ipen:
                setattr(line, 'ipen', IpenObject(text=ipen, line_nr=line.line_nr, index=index))
                raw_line = raw_line.replace(ipen, '')
                raw_no_ipen = raw_no_ipen.replace(ipen, '')

            setattr(line, '_rest', raw_line)
            setattr(line, '_raw_no_ipen', raw_no_ipen)

        self.resolve_repeaters(lines=lines)
        self.resolve_isolated_epithets(lines=lines)

        # extract_names_fuzzy is outside the main loop because it benefits from
        # processing batches of lines
        if self.fuzzy_match_threshold is not None:
            lines = self.extract_species_fuzzy(lines=lines)

        return lines

    def extract_name(self, text, rank, line_nr):
        tokens = text.strip().split()

        if len(tokens)==0 or len(tokens)>30:
            return [], tokens

        candidates=[]
        cache=[]

        for i in range(0, len(tokens)):
            for j in range(len(tokens), 0, -1):
                if j-i < (2 if rank=='species' else 1):
                    break

                lookup = clean_up_name(remove_abbreviations(name=' '.join(tokens[i:j])))

                if len(lookup)==0:
                    continue

                if rank=='genus' and lookup[0].islower():
                    continue

                cached=[x for x in cache if x.lookup==lookup]
                if len(cached)==0:
                    match = self.name_resolver.match_exact(lookup=lookup, rank=rank, strict=self.strict_exact_matching)
                    cache.append(match)
                else:
                    match = cached[0]

                if match.match:
                    candidates.append((i, j, match))

        if len(candidates)>0:
            # cleanup() takes out non-alpha chars, which will re-appear in the slicing
            # of the (uncleaned) tokens, so we take the longest of the (cleaned) candidates
            # that uses the smallest amount of tokens
            i, j, name_matched = sorted(candidates, key=lambda x: (-x[2].score, -len(x[2].match.full_name), abs(x[1]-x[0]) ))[0]
            name_text, rest = remove_outer_non_alpha(' '.join(tokens[i:j]))
            remaining_tokens = [x for x in tokens[:i]+rest+tokens[j:] if len(x)>0]
            return MatchedNameObject(text=name_text,
                                     match=name_matched.match,
                                     score=name_matched.score,
                                     line_nr=line_nr,
                                     index=text.find(name_text)), remaining_tokens

        return None, tokens
    
    def extract_species_fuzzy(self, lines):

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
        # to not analyze more lines than necessary theoretically, the very first and last
        # names might be misspelled, hence the -1/+1 buffer

        lines_to_check = []
        maxgap = 10
        buffer = 1
        data = [x.line_nr for x in lines if x.species]

        for clst in cluster(data=data, maxgap=maxgap):
            lines_to_check.extend([x for x in lines
                          if x.line_nr>=min(clst)-buffer and x.line_nr<=max(clst)+buffer
                          and len(raw_line_preprocess(x.raw))>0
                          and not x.genus
                          and not x.species])

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
                candidates.append({
                    'line_nr': line.line_nr,
                    'index': line.raw.lower().find(option.lower()),
                    'i': i, 'j': j,
                    'option': option,
                    'matched_name': None})

        uniq=sorted(list(set({x['option'] for x in candidates if x['option'].count(' ')>0})))

        if len(uniq)==0:
            return lines

        self.logger.info("Trying fuzzy matching for %s candidates with confidence threshold %s", len(uniq), self.fuzzy_match_threshold)

        matches=self.name_resolver.match_fuzzy(lookups=uniq, rank='species')
        for match in matches:
            if match.score>=self.fuzzy_match_threshold:
                for candidate in [x for x in candidates if x['option']==match.lookup]:
                    candidate.update({'matched_name': (match.match, match.score)})

        candidates=[x for x in candidates if x['matched_name'] is not None]

        updated=0
        for line_nr, group in groupby(candidates, lambda x: x['line_nr']):
            # match with longest name > best score > shortest number of tokens
            best = sorted(list(group), key=lambda x: ( len(x['matched_name'][0].full_name), -x['matched_name'][1], (x['j']-x['i'])))[0]
            line = [x for x in lines if x.line_nr==line_nr][0]
            setattr(line, 'species', MatchedNameObject(text=best['option'],
                                                       match=best['matched_name'][0],
                                                       score=best['matched_name'][1],
                                                       index=best['index'],
                                                       line_nr=line_nr))
            updated+=1

        self.logger.info("Found %s names by fuzzy matching", updated)

        return lines
 
    def resolve_repeaters(self, lines):
        # resolving epithets with "repeater symbols" to full names
        p_genus=None

        for line in lines:

            clean_epithet=(bool(line.epithet) and line.epithet.score==1) \
                and not line.species \
                and (line._rest is None or len(line._rest.strip())<=5)

            if line.genus:
                p_genus=line.genus.text
            elif line.species:
                p_genus=line.species.text.split()[0]

            if (line.repeater or clean_epithet) and p_genus:
                if line.repeater:
                    candidate=f"{p_genus} {line.raw[line.raw.find(line.repeater):]}"
                else:
                    candidate=f"{p_genus} {line.epithet.text}"

                name, _=self.extract_name(text=candidate, rank='species', line_nr=line.line_nr)

                if name:
                    setattr(line, 'species', name)

    def resolve_isolated_epithets(self, lines):
        p_genus=None

        for line in lines:
            if line.genus:
                p_genus=line.genus.text
            elif line.species:
                p_genus=line.species.text.split()[0]

            if line.species and len(line.species)>0:
                continue

            if not line.epithet or len(line.epithet)==0:
                continue

            if line.epithet and p_genus:
                candidate = f"{p_genus} {line._raw_no_ipen}"
                name, _ = self.extract_name(text=candidate, rank='species', line_nr=line.line_nr)
                if name:
                    setattr(line, 'species', name)

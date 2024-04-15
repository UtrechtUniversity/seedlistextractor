import re
from itertools import groupby
from utils import (remove_outer_non_alpha, clean_up_name, remove_abbreviations, MatchedNameObject, CultivarObject, IpenObject)

class DataExtractor:
    
    def __init__(self,
                 logger,
                 name_resolver,
                 fuzzy_match_threshold,
                 strict_exact_matching=False
                 ) -> None:

        self.logger=logger
        self.name_resolver=name_resolver
        self.fuzzy_match_threshold=None
        if fuzzy_match_threshold is not None:
            if isinstance(fuzzy_match_threshold, float) and 0 < fuzzy_match_threshold < 1:
                self.fuzzy_match_threshold=fuzzy_match_threshold
            else:
                raise ValueError("fuzzy_match_threshold should be a float between 0 and 1")
        self.strict_exact_matching=strict_exact_matching

    @staticmethod
    def preprocess(text):
        text=re.sub(r'\t', ' ', text)
        text=re.sub(r'Index[\s]{1,}seminum', '', text, flags=re.IGNORECASE).strip()
        return text

    def extract(self, lines):
        self.logger.info("Processing %s lines", len(lines))

        for line in lines:
            raw_line=self.preprocess(line.raw)
            if len(raw_line)==0:
                continue

            setattr(line, 'repeater', self.extract_repeater(text=raw_line))
            raw_line=raw_line.replace(str(line.repeater), '', 1)

            """
            extract_name() / extract_species_fuzzy() return:
                name, remaining_tokens
            'name' contains:
                ('name (in text)', 'matched name (from database)', score)
            """

            # synonyms "[syn. ....]" etc
            # but we add them only if they resolve
            synonyms=[]
            for syn_string in self.extract_synonym_strings(text=raw_line):
                name, _=self.extract_name(text=syn_string, rank='species', line_nr=line.line_nr)
                if name:
                    synonyms.append(name)
                    raw_line=raw_line.replace(syn_string, '')
            setattr(line, 'synonyms', synonyms)

            # species name
            name, rest_tokens=self.extract_name(text=raw_line, rank='species', line_nr=line.line_nr)
            if name and name not in line.synonyms:
                setattr(line, 'species', name)
                raw_line=" ".join(rest_tokens)


            # genus and isolated epithets (only when there's no complete species names)
            if line.species is None:
                rest_tokens=[]
                for rank in ['genus', 'epithet']:
                    name, _=self.extract_name(text=raw_line, rank=rank, line_nr=line.line_nr)
                    if name:
                        setattr(line, rank, name)
                        raw_line=raw_line.replace(name.text, '')

            # cultivars should follow a species name, and are plain string matches (no database lookup)
            if line.species or line.epithet:
                cultivar=self.extract_cultivar_string(text=raw_line)
                if cultivar:
                    setattr(line, 'cultivar', CultivarObject(text=cultivar, line_nr=line.line_nr))
                    raw_line=raw_line.replace(cultivar, '')

            ipen, index=self.extract_ipen(text=raw_line)
            if ipen:
                setattr(line, 'ipen', IpenObject(text=ipen, line_nr=line.line_nr, index=index))
                raw_line=raw_line.replace(ipen, '')

            setattr(line, '_rest', raw_line)

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
            # elif not line.repeater:
            #     p_genus=None

            # if line.repeater and p_genus and line.epithet and not line.species:
            if (line.repeater or clean_epithet) and p_genus:
                # candidate=f"{p_genus} {line.raw[line.raw.find(line.repeater):]}"
                if line.repeater:
                    candidate=f"{p_genus} {line.raw[line.raw.find(line.repeater):]}"
                else:
                    candidate=f"{p_genus} {line.epithet.text}"

                name, _=self.extract_name(text=candidate, rank='species', line_nr=line.line_nr)
                if name:
                    setattr(line, 'species', name)
                    setattr(line, 'epithet', None)

        # extract_names_fuzzy is outside the main loop because it benefits from
        # processing batches of lines
        if self.fuzzy_match_threshold is not None:
            lines=self.extract_species_fuzzy(lines=lines)

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
        # select lines to do fuzzy name matching on, fuzzy matching is expensive, so we try
        # to not analyze more lines than necessary theoretically, the very first and last
        # names might be misspelled, hence the -5/+5 buffer
        sp_lines=[x.line_nr for x in lines if x.species]
        if len(sp_lines)==0:
            return lines

        for n in range(min(sp_lines)-5, max(sp_lines)+5):
            # select only lines the not already have a (normally matched) full name
            line=[x for x in lines
                    if x.line_nr==n 
                    and len(self.preprocess(x.raw))>0 
                    and not x.genus
                    and not x.species]

            if not line:
                continue

            line=line[0]
            tokens=line.raw.split()
            for i, j, option in generate_candidates(tokens=tokens, min_token_len=2):
                candidates.append({
                    'line_nr': line.line_nr,
                    'index': line.raw.lower().find(option.lower()),
                    'i': i,
                    'j': j,
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
            # clean_up_name() takes out non-alpha chars, which will
            # re-appear in the slicing of the (uncleaned) tokens, so we take the longest of the
            # (cleaned) candidates that uses the smallest amount of tokens
            # sort by score (desc), len(matched name) (desc),  len(num of tokens) (asc)
            best=sorted(list(group), key=lambda x: (-x['matched_name'][1], -len(x['matched_name'][0].full_name), (x['j']-x['i'])))[0]
            line=[x for x in lines if x.line_nr==line_nr][0]
            setattr(line, 'species', MatchedNameObject(text=best['option'],
                                                       match=best['matched_name'][0],
                                                       score=best['matched_name'][1],
                                                       index=best['index'],
                                                       line_nr=line_nr))
            updated+=1

        self.logger.info("Found %s names by fuzzy matching", updated)

        return lines

    @staticmethod
    def extract_synonym_strings(text):
        regex=r'((\[|\()(sin|syn)\.?\:? ([^\]\)]*)(\]|\)))'
        matches=re.findall(regex, text.strip(), re.UNICODE|re.IGNORECASE)
        return [x[0] for x in matches]

    @staticmethod
    def extract_cultivar_string(text):
        #TODO: could be more elegant
        regex=r'(‘[A-Za-z ]+’|´[A-Za-z ]+´|\'[A-Za-z ]+\'|"[A-Za-z ]+"|\([A-Za-z ]+form\))'
        match=re.search(regex, text.strip(), re.UNICODE|re.IGNORECASE)
        if match:
            return match.group(0)

    @staticmethod
    def extract_ipen(text):
        """
        The IPEN number consists of four elements:

        - Country of origin (two positions, abbreviation according to ISO 3166-1-alpha-2, “XX” for unknown origin)
        - Restrictions of transfer (one position, “1” if there exists a restriction; “0” if none).
        - The unique Garden code of the institution offering the plant material for exchange, (to be found on the BGCI Website under “GardenSearch”).
        - Identification Number (the specific accession number of the plant material in the recording system of the garden)

        https://www.bgci.org/our-work/inspiring-and-leading-people/policy-and-advocacy/access-and-benefit-sharing/the-international-plant-exchange-network/#ipen-documentation-system
        """
        regex=r'(([A-Z]{2}|[a-z]{2})([—\-\.]{1})([01]{1})([—\-\.]{1})([A-Z]{1,5}|[a-z]{1,5})([—\-\./_]{1})([^\s\]]*))'
        match=re.search(regex, text.strip(), re.UNICODE)
        if match:
            return match.group(0), match.span(0)[0]
        return None, -1

    @staticmethod
    def extract_repeater(text):
        # "repeater" symbols
        r_single=set(list('"\'„”"«»*_>'))
        r_double=set(list('’\'.,−—--"'))

        t_text=re.sub(r'^[\dIiogS\^]+\.?\s+', '', text).strip()
        chars=r_single.union(r_double).union(set([f"{x}{x}" for x in r_double])).union([f"{x} {x}" for x in r_double])
        for char in chars:
            if t_text[:len(char)]==char:
                return char

    # def extract_species_fuzzy_ORIGINAL(self, lines):

    #     def generate_candidates(tokens, min_token_len=1, max_token_length=8):
    #         candidates=[]
    #         for i in range(0, len(tokens)):
    #             for j in range(len(tokens), 0, -1):
    #                 if j-i<min_token_len:
    #                     break
    #                 if j-i>max_token_length:
    #                     break

    #                 lookup=clean_up_name(remove_abbreviations(name=' '.join(tokens[i:j])))

    #                 if len(lookup)>0 and lookup.count(' ')+1>=min_token_len:
    #                     candidates.append((i, j, lookup))

    #         return candidates

    #     candidates=[]
    #     # select lines to do fuzzy name matching on, fuzzy matching is expensive, so we try
    #     # to not analyze more lines than necessary theoretically, the very first and last
    #     # names might be misspelled, hence the -5/+5 buffer
    #     sp_lines=[x.line_nr for x in lines if x.species]
    #     if len(sp_lines)==0:
    #         return lines

    #     for n in range(min(sp_lines)-5, max(sp_lines)+5):
    #         # select only lines the not already have a (normally matched) full name
    #         line=[x for x in lines
    #                 if x.line_nr==n 
    #                 and len(self.preprocess(x.raw))>0 
    #                 and not x.genus
    #                 and not x.species]

    #         if not line:
    #             continue

    #         line=line[0]
    #         tokens=line.raw.split()
    #         for i, j, option in generate_candidates(tokens=tokens, min_token_len=2):
    #             candidates.append({
    #                 'line_nr': line.line_nr,
    #                 'index': line.raw.lower().find(option.lower()),
    #                 'i': i,
    #                 'j': j,
    #                 'option': option,
    #                 'matched_name': None})

    #     uniq=sorted(list(set({x['option'] for x in candidates if x['option'].count(' ')>0})))
    #     if len(uniq)==0:
    #         return lines

    #     self.logger.info("Trying fuzzy matching for %s candidates with confidence threshold %s", len(uniq), self.fuzzy_match_threshold)

    #     matches=self.name_resolver.match_fuzzy(lookups=uniq, rank='species')
    #     for _, match in matches.iterrows():
    #         if match['Lookup 1 Confidence']>self.fuzzy_match_threshold:
    #             for candidate in [x for x in candidates if x['option']==match['Original Name']]:
    #                 orignal=self.name_resolver.get_original_name(lookup=match['Lookup 1'], rank='species')
    #                 candidate.update({'matched_name': (orignal if orignal else match['Lookup 1'], match['Lookup 1 Confidence'])})

    #     candidates=[x for x in candidates if x['matched_name'] is not None]

    #     updated=0
    #     for line_nr, group in groupby(candidates, lambda x: x['line_nr']):
    #         # clean_up_name() takes out non-alpha chars, which will
    #         # re-appear in the slicing of the (uncleaned) tokens, so we take the longest of the
    #         # (cleaned) candidates that uses the smallest amount of tokens
    #         best=sorted(list(group), key=lambda x: (-len(x['matched_name'][0]), (x['j']-x['i'])))[0]
    #         line=[x for x in lines if x.line_nr==line_nr][0]
    #         setattr(line, 'species', NameObject(text=best['option'],
    #                                              match=best['matched_name'][0],
    #                                              score=best['matched_name'][1],
    #                                              index=best['index'],
    #                                              line_nr=line_nr))
    #         updated+=1

    #     self.logger.info("Found %s names by fuzzy matching", updated)

    #     return lines

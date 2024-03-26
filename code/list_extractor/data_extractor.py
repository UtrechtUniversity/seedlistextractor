import re
from itertools import groupby
from name_resolver import NameResolver
from utils import (remove_outer_non_alpha, clean_up_name, remove_abbreviations, NameObject, CultivarObject, IpenObject)

class DataExtractor:
    
    # "repeater" symbols
    r_single=set(list('"\'„”"«»*_>'))
    r_double=set(list('’\'.,−—--"'))

    def __init__(self,
                 names_database,
                 logger,
                 fuzzy_match_threshold,
                 force_names_reload=False,
                 ) -> None:

        self.logger=logger
        self.name_resolver=NameResolver(
            names_database=names_database,
            force_names_reload=force_names_reload,
            logger=logger)

        self.fuzzy_match_threshold=None
        if fuzzy_match_threshold is not None:
            if isinstance(fuzzy_match_threshold, float) and 0 < fuzzy_match_threshold < 1:
                self.fuzzy_match_threshold=fuzzy_match_threshold
            else:
                raise ValueError("fuzzy_match_threshold should be a float between 0 and 1")

    @staticmethod
    def preprocess(line):
        line=re.sub(r'\t', ' ', line)
        line=re.sub(r'Index[\s]{1,}seminum', '', line, flags=re.IGNORECASE).strip()
        return line

    def extract(self, lines):
        self.logger.info("Processing %s lines", len(lines))

        for line in lines:
            raw_line=self.preprocess(line['raw'])
            if len(raw_line)==0:
                continue

            repeater=self.extract_repeater(text=raw_line)
            if repeater:
                line.update({'repeater': repeater})
                raw_line=raw_line.replace(repeater, '', 1)

            """
            extract_name() / extract_species_fuzzy() return:
                name, remaining_tokens
            'name' contains:
                ('name (in text)', 'matched name (from database)', score)
            """

            # synonyms "[syn. ....]" etc
            synonyms=[]
            for syn_string in self.extract_synonym_strings(text=raw_line):
                name, _=self.extract_name(text=syn_string, rank='species', line_nr=line['line_nr'])
                if name:
                    synonyms.extend(name)
                    raw_line=raw_line.replace(syn_string, '')
            line.update({'synonyms': synonyms})

            # species name
            name, rest_tokens=self.extract_name(text=raw_line, rank='species', line_nr=line['line_nr'])
            if name and name not in line['synonyms']:
                line.update({'species': name})
                raw_line=" ".join(rest_tokens)

            # genus and isolated epithets (only when there's no complete species names)
            if line['species'] is None:
                rest_tokens=[]
                for rank in ['genus', 'epithet']:
                    name, _=self.extract_name(text=raw_line, rank=rank, line_nr=line['line_nr'])
                    if name:
                        line.update({rank: name})
                        raw_line=raw_line.replace(name.text, '')

            # cultivars should follow a species name, and are plain string matches (no database lookup)
            if line['species'] or line['epithet']:
                cultivar=self.extract_cultivar_string(text=raw_line)
                if cultivar:
                    line.update({'cultivar': CultivarObject(text=cultivar, line_nr=line['line_nr'])})
                    raw_line=raw_line.replace(cultivar, '')

            ipen=self.extract_ipen(text=raw_line)
            if ipen:
                line.update({'ipen': IpenObject(text=ipen, line_nr=line['line_nr'])})
                raw_line=raw_line.replace(ipen, '')

            line.update({'_rest': raw_line})

        # resolving epithets with "repeater symbols" to full names
        p_genus=None
        for line in lines:

            if line['genus']:
                p_genus=line['genus'].text
            elif line['species']:
                p_genus=line['species'].text.split()[0]
            elif not line['repeater']:
                p_genus=None

            if line['repeater'] and p_genus and line['epithet'] and not line['species']:
                candidate=f"{p_genus} {line['raw'][line['raw'].find(line['repeater']):]}"
                name,_=self.extract_name(text=candidate, rank='species', line_nr=line['line_nr'])
                if name:
                    line.update({'species': name, 'epithet': None})

        # extract_names_fuzzy is outside the main loop because it benefits from
        # processing batches of lines
        if self.fuzzy_match_threshold is not None:
            lines=self.extract_species_fuzzy(lines=lines)

        return lines

    def extract_name(self, text, rank, line_nr):
        tokens=text.strip().split()

        if len(tokens)==0 or len(tokens)>30:
            return [], tokens

        candidates=[]
        cache=[]

        for i in range(0, len(tokens)):
            for j in range(len(tokens), 0, -1):
                if j-i < (2 if rank=='species' else 1):
                    break

                lookup=clean_up_name(remove_abbreviations(name=' '.join(tokens[i:j])))

                if len(lookup)==0:
                    continue

                if rank=='genus' and lookup[0].islower():
                    continue

                cached=[x for x in cache if x[0]==lookup]
                if len(cached)==0:
                    match, score=self.name_resolver.match_exact(lookup=lookup, rank=rank)
                    cache.append((lookup, match, score))
                else:
                    _, match, score=cached[0]

                if match:
                    candidates.append((i, j, match, score))

        if len(candidates)>0:
            # cleanup() takes out non-alpha chars, which will re-appear in the slicing
            # of the (uncleaned) tokens, so we take the longest of the (cleaned) candidates
            # that uses the smallest amount of tokens
            i, j, name_matched, score=sorted(candidates, key=lambda x: (-len(x[2]), abs(x[1]-x[0]) ))[0]
            name_text, rest=remove_outer_non_alpha(' '.join(tokens[i:j]))
            remaining_tokens=[x for x in tokens[:i]+rest+tokens[j:] if len(x)>0]
            return NameObject(text=name_text, match=name_matched, score=score, line_nr=line_nr), remaining_tokens

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
        sp_lines=[x['line_nr'] for x in lines if x['species']]
        for n in range(min(sp_lines)-5, max(sp_lines)+5):
            # select only lines the not already have a (normally matched) full name
            line=[x for x in lines
                    if x['line_nr']==n 
                    and len(self.preprocess(x['raw']))>0 
                    and not x['genus']
                    and not x['species']]

            if not line:
                continue

            line=line[0]
            tokens=line['raw'].split()
            for i, j, option in generate_candidates(tokens=tokens, min_token_len=2):
                candidates.append({'line_nr': line['line_nr'], 'i': i, 'j': j, 'option': option, 'matched_name': None})

        uniq=sorted(list(set({x['option'] for x in candidates if x['option'].count(' ')>0})))

        self.logger.info("Trying fuzzy matching for %s candidates with confidence threshold %s", len(uniq), self.fuzzy_match_threshold)

        matches=self.name_resolver.match_fuzzy(lookups=uniq, rank='species')
        for _, match in matches.iterrows():
            if match['Lookup 1 Confidence']>self.fuzzy_match_threshold:
                for option in [x for x in candidates if x['option']==match['Original Name']]:
                    option.update({'matched_name': (match['Lookup 1'], match['Lookup 1 Confidence'])})

        candidates=[x for x in candidates if x['matched_name'] is not None]

        updated=0
        for line_nr, group in groupby(candidates, lambda x: x['line_nr']):
            # clean_up_name() takes out non-alpha chars, which will
            # re-appear in the slicing of the (uncleaned) tokens, so we take the longest of the
            # (cleaned) candidates that uses the smallest amount of tokens
            best=sorted(list(group), key=lambda x: (-len(x['matched_name'][0]), (x['j']-x['i'])))[0]
            line=[x for x in lines if x['line_nr']==line_nr][0]
            line.update({'species': NameObject(text=best['option'],
                                               match=best['matched_name'][0],
                                               score=best['matched_name'][1],
                                               line_nr=line_nr)})
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
        regex=r'(([A-Z]{2}|[a-z]{2})([—\-\. ]{1})([01]{1})([—\-\. ]{1})([A-Z]{1,5}|[a-z]{1,5})([—\-\./ ]{1})([^\s\]]*))'
        match=re.search(regex, text.strip(), re.UNICODE)
        if match:
            return match.group(0)

    def extract_repeater(self, text):
        t_text=re.sub(r'^[\dIiogS\^]+\.?\s+', '', text).strip()
        chars=self.r_single.union(self.r_double).union(set([f"{x}{x}" for x in self.r_double])).union([f"{x} {x}" for x in self.r_double])
        for char in chars:
            if t_text[:len(char)]==char:
                return char

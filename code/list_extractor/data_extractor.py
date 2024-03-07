import re
from itertools import groupby
from name_resolver import NameResolver
from utils import (remove_outer_non_alpha, clean_up_name, remove_abbreviations, NameObject, CultivarObject, IpenObject)

class DataExtractor:

    def __init__(self,
                 line_selection,
                 names_database,
                 logger,
                 fuzzy_match_threshold,
                 force_names_reload=False,
                 ) -> None:

        self.line_selection=line_selection
        self.logger=logger
        self.name_resolver=NameResolver(
            names_database=names_database,
            force_names_reload=force_names_reload,
            logger=logger)
        self.species_index=[]

        self.fuzzy_match_threshold=None
        if fuzzy_match_threshold is not None:
            if isinstance(fuzzy_match_threshold, float) and 0 < fuzzy_match_threshold < 1:
                self.fuzzy_match_threshold=fuzzy_match_threshold
            else:
                raise ValueError("fuzzy_match_threshold should be a float between 0 and 1")
  
    @staticmethod
    def preprocess(line):
        return re.sub('Index[\s]{1,}seminum', '', line, flags=re.IGNORECASE).strip()

    def extract(self, lines):
        self.species_index=[]
        
        for line in lines:

            if self.line_selection is not None and line['line_nr'] not in self.line_selection:
                continue

            if len(line['raw'])==0:
                continue

            raw_line=self.preprocess(line['raw'])
            # self.logger.debug("Line %s: %s", line['line_nr'], raw_line)

            """
            extract_names returns:
                names, remaining_tokens
            names contains:
                [ ('name (in text)', 'matched name (from database)', score), ... ]
            """

            # synonyms "[syn. ....]" etc
            syns=[]
            for syn_string in self.extract_synonym_strings(text=raw_line):
                names, _=self.extract_names(text=syn_string, rank='species', line_nr=line['line_nr'])
                if len(names)>0:
                    syns.extend(names)
                    raw_line=raw_line.replace(syn_string, '')
            line.update({'syn': syns})

            # species names
            names, rest_tokens=self.extract_names(text=raw_line, rank='species', line_nr=line['line_nr'])
            names=[x for x in names if x[1] not in line['syn']]
            line.update({'species': names})
            raw_line=" ".join(rest_tokens)

            # genus and isolated epithets (only when there's no complete species names)
            if len(line['species'])==0:
                rest_tokens=[]
                for rank in ['genus', 'epithet']:
                    names, _=self.extract_names(text=raw_line, rank=rank, line_nr=line['line_nr'])
                    line.update({rank: names})
                    for item, _, _ in line[rank]:
                        raw_line=raw_line.replace(item, '')

            # cultivars are plain string matches, they are not resolved in a database
            if len(line['species']+line['epithet'])>0:
                line.update({'cultivar': [CultivarObject(text=x, line_nr=line['line_nr']) 
                                          for x in self.extract_cultivar_strings(text=raw_line)]})
                for item in line['cultivar']:
                    raw_line=raw_line.replace(item.text, '')

            # family names
            names, rest_tokens=self.extract_names(text=raw_line, rank='family', line_nr=line['line_nr'])
            line.update({'family': names})
            raw_line=" ".join(rest_tokens)

            # IPEN
            line.update({'ipen': [IpenObject(text=x, line_nr=line['line_nr'])
                                  for x in self.extract_ipens(text=raw_line)]})
            for item in line['ipen']:
                raw_line=raw_line.replace(item.text, '')

            line.update({'_rest': raw_line})
            
            if len(line['species'])>0:
                self.species_index.append((line['line_nr'], line['species']))
            elif len(line['epithet'])>0:
                self.species_index.append((line['line_nr'], line['epithet']))

        # extract_names_fuzzy is outside the main loop because it benefits from processing
        # batches of lines
        if self.fuzzy_match_threshold is not None:
            # select lines to do fuzzy name matching on, fuzzy matching is expensive, so we try
            # to not analyze more lines than necessary theoretically, the very first and last
            # names might be misspelled, hence a buffer
            lines=self.extract_names_fuzzy(
                lines=lines, 
                start=(self.line_selection[0] if self.line_selection else self.species_index[0][0])-5, 
                end=(self.line_selection[-1] if self.line_selection else self.species_index[-1][0])+5)       

        return lines

    def extract_names(self, text, rank, line_nr):

        def extract_name(tokens, rank, epithet_starts_lower=True, genus_starts_upper=True):
            min_token_len=1

            if rank=='species':
                min_token_len=2

            candidates=[]
            cache=[]

            for i in range(0, len(tokens)):
                for j in range(len(tokens), 0, -1):
                    if j-i<min_token_len:
                        break

                    lookup=clean_up_name(remove_abbreviations(name=' '.join(tokens[i:j])))

                    if len(lookup)==0:
                        continue

                    if rank=='genus' and genus_starts_upper and lookup[0].islower():
                        continue

                    if rank=='epithet' and epithet_starts_lower and lookup[0].isupper():
                        continue

                    cached=[x for x in cache if x[0]==lookup]
                    if len(cached)==0:
                        match, score=self.name_resolver.match_exact(lookup=lookup, rank=rank)
                        cache.append((lookup, match, score))
                    else:
                        _, match, score=cached[0]

                    # self.logger.debug(f"{lookup}, {i}, {j}, {match}, {score}, {'-' if len(cached)==0 else '*'}")

                    if match:
                        candidates.append((i, j, match, score))

            if len(candidates)>0:
                # cleanup() takes out non-alpha chars, which will re-appear in the slicing
                # of the (uncleaned) tokens, so we take the longest of the (cleaned) candidates
                # that uses the smallest amount of tokens
                i, j, match, score=sorted(candidates, key=lambda x: (-len(x[2]), abs(x[1]-x[0]) ))[0]

                return tokens[i:j], (tokens[:i], tokens[j:]), match, score

            return None, (tokens, ), None, 0
        
        def extraction_loop(tokens, rank, names):
            while True:
                name_tokens, rest_tokens, name_matched, score=extract_name(tokens=tokens, rank=rank)

                if name_tokens is None:
                    break

                name_text, c_rest_tokens=remove_outer_non_alpha(' '.join(name_tokens))
                names.append(NameObject(text=name_text, match=name_matched, score=score, line_nr=line_nr))
                tokens=[x for x in rest_tokens[0]+c_rest_tokens+rest_tokens[1] if len(x)>0]
            return names, tokens

        tokens=text.strip().split()
        if len(tokens)==0 or len(tokens)>50:
            return [], tokens
        
        names=[]
        names, remaining_tokens=extraction_loop(tokens=tokens, rank=rank, names=names)

        return names, remaining_tokens
    
    def extract_names_fuzzy(self, lines, start, end, rank='species'):

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
        for n in range(start, end):
            # select only lines the not already have a (normally matched) name
            line=[x for x in lines
                    if x['line_nr']==n 
                    and len(self.preprocess(x['raw']))>0 
                    and len(x['family']+x['genus']+x['species'])==0]
            if not line:
                continue
            line=line[0]
            tokens=line['raw'].split()
            min_token_len = 1 if rank=='epithet' else 2
            for i, j, option in generate_candidates(tokens=tokens, min_token_len=min_token_len):
                candidates.append({'line_nr': line['line_nr'], 'i': i, 'j': j, 'option': option, 'matched_name': None })

        uniq=list(set({x['option'] for x in candidates if x['option'].count(' ')>0}))
        matches=self.name_resolver.match_fuzzy(lookups=uniq, rank='species')
        for _, match in matches.iterrows():
            if match['Lookup 1 Confidence']>self.fuzzy_match_threshold:
                for option in [x for x in candidates if x['option']==match['Original Name']]:
                    option.update({'matched_name': (match['Lookup 1'], match['Lookup 1 Confidence'])})

        candidates=[x for x in candidates if x['matched_name'] is not None]

        for line_nr, group in groupby(candidates, lambda x: x['line_nr']):
            # clean_up_name() takes out non-alpha chars, which will
            # re-appear in the slicing of the (uncleaned) tokens, so we take the longest of the
            # (cleaned) candidates that uses the smallest amount of tokens
            best=sorted(list(group), key=lambda x: (-len(x['matched_name'][0]), (x['j']-x['i'])))[0]
            line=[x for x in lines if x['line_nr']==line_nr][0]
            vals=line[rank]
            vals.append(NameObject(text=best['option'],
                                   match=best['matched_name'][0],
                                   score=best['matched_name'][1],
                                   line_nr=line_nr))
            line.update({rank: vals })

        return lines

    @staticmethod
    def extract_synonym_strings(text):
        regex=r'((\[|\()(sin|syn)\.?\:? ([^\]\)]*)(\]|\)))'
        matches=re.findall(regex, text.strip(), re.UNICODE|re.IGNORECASE)
        return [x[0] for x in matches]

    @staticmethod
    def extract_cultivar_strings(text):
        #TODO: could be more elegant
        regex=r'(‘[A-Za-z ]+’|´[A-Za-z ]+´|\'[A-Za-z ]+\'|"[A-Za-z ]+"|\([A-Za-z ]+form\))'
        matches=re.findall(regex, text.strip(), re.UNICODE|re.IGNORECASE)
        return matches

    @staticmethod
    def extract_ipens(text):
        """
        The IPEN number consists of four elements:

        - Country of origin (two positions, abbreviation according to ISO 3166-1-alpha-2, “XX” for unknown origin)
        - Restrictions of transfer (one position, “1” if there exists a restriction; “0” if none).
        - The unique Garden code of the institution offering the plant material for exchange, (to be found on the BGCI Website under “GardenSearch”).
        - Identification Number (the specific accession number of the plant material in the recording system of the garden)

        https://www.bgci.org/our-work/inspiring-and-leading-people/policy-and-advocacy/access-and-benefit-sharing/the-international-plant-exchange-network/#ipen-documentation-system
        """
        regex=r'(([A-Za-z]{2})([—\-\. ]{1})([01]{1})([—\-\. ]{1})([A-Za-z]{1,5})([—\-\./ ]{1})([^\s\]]*))'
        matches=re.findall(regex, text.strip(), re.UNICODE)
        if matches:
            return [x[0].strip() for x in matches]
        return []

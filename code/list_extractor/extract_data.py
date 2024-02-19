import re
from itertools import groupby
from name_resolver import NameResolver
from utils import (remove_outer_non_alpha, extract_ipens, extract_index_raw, 
                   extract_cultivars, clean_up_name, remove_abbreviations)

class ExtractData:

    def __init__(self,
                 include_lines,
                 names_database,
                 logger,
                 fuzzy_name_match=True,
                 force_names_reload=False,
                 ) -> None:

        self.include_lines=include_lines
        self.fuzzy_name_match=fuzzy_name_match
        self.name_resolver=NameResolver(
            names_database=names_database,
            force_names_reload=force_names_reload)
        self.logger=logger
  
    def extract(self, lines):

        def remove_from_rest_tokens(values, rest_tokens):
            tokens=[]
            [tokens.extend(item.split()) for item in values]
            return [x for x in rest_tokens if x not in tokens]

        names_start=-1
        names_end=int(1e6)
        
        for line in lines:

            if self.include_lines is not None and line['line_nr'] not in self.include_lines:
                continue

            if len(line['raw'])==0:
                continue

            self.logger.debug("Line %s: %s" % (line['line_nr'], line['raw']))

            syns=self.extract_synonyms(text=line['raw'])
            # syns = [((cleaned, match, score), matched_string), ]
            line.update({'syn': [syn[1] for syn, _ in syns]})
            line.update({'_remove': [matched_string for _, matched_string in syns]})

            names, rest=self.extract_names(text=line['raw'], rank='species')
            # names = [(cleaned, match, score), ]
            names=[x for x in names if x[1] not in line['syn']]
            line.update({'species': names})
            rest_tokens=rest

            names, rest=self.extract_names(text=line['raw'], rank='family')
            line.update({'family': names})
            rest_tokens=list(set(rest_tokens) & set(rest))

            if len(line['species'])==0:
                for rank in ['genus', 'epithet']:
                    names, rest=self.extract_names(text=line['raw'], rank=rank)
                    line.update({rank: names})
                    rest_tokens=list(set(rest_tokens) & set(rest))

            if len(line['species']+line['epithet'])>0:
                line.update({'cultivar': extract_cultivars(text=line['raw'])})
                rest_tokens=remove_from_rest_tokens(values=line['cultivar'], rest_tokens=rest_tokens)
                names_start=names_start if names_start>-1 else line['line_nr']
                names_end=line['line_nr']

            line.update({'ipen': extract_ipens(text=line['raw'])})
            rest_tokens=remove_from_rest_tokens(values=line['ipen'], rest_tokens=rest_tokens)

            line.update({'index_raw': extract_index_raw(text=line['raw'])})
            rest_tokens=remove_from_rest_tokens(values=line['index_raw'], rest_tokens=rest_tokens)

            line.update({'_rest_tokens':rest_tokens})

        #TODO: fix fuzzy matching
        if False and self.fuzzy_name_match:

            buffer=10
            buffer=2

            for rank in ['species', 'epithet']:

                string_list=[]
                for i in range(names_start-buffer, names_end+buffer):
                    line=[x for x in lines if x['line_nr']==i]
                    if not line or len(line[0]['raw'])==0:
                        continue

                    if len(line[0][rank])>0:
                        continue
                    
                    # print(line)
                    string_list.append((i, line[0]['raw'], []))


                names=self.extract_names_fuzzy(string_list=string_list, rank=rank)
                print(names)
                exit()
                # if species names, skip the epithet
                # print(rank)
                # group_list = [(k, list(g)) for k, g in names]                
                # print(group_list)
                # for k, groups in names:
                #     # group candidate matches by line
                #     for line_nr, group in groups:
                #         print(list(group))
                #         # sort: longest name using the smallest number of tokens
                #         i, j, match, score, _=sorted(group, key=lambda x: (-len(x[2]), abs(x[1]-x[0]) ))[0]
                #         print(rank, line_nr, i, j, match, score)
                # break

                # return tokens[i:j], (tokens[:i], tokens[j:]), match, score

        return lines
    
    def extract_synonyms(self, text):
        regex=r'((\[|\()(sin|syn)\.?\:? ([^\]\)]*)(\]|\)))'
        matches=re.findall(regex, text.strip(), re.UNICODE|re.IGNORECASE)
        results=[]
        if matches:
            for match in matches:
                matched_string=match[0]
                names, _=self.extract_names(matched_string, rank='species')
                if len(names)>0:
                    # names = [(cleaned, match, score), ]
                    results.append((names[0], matched_string))

        return results

    def extract_names(self, text, rank):

        def extract_name(tokens, rank, epithet_starts_lower=True, genus_starts_upper=True):
            min_token_len=1

            if rank=='species':
                min_token_len=2

            candidates=[]

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

                    match, score=self.name_resolver.match_exact(lookup=lookup, rank=rank)

                    if match:
                        # candidates.append((i, j, lookup, match, score))
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
                name, rest, match, score=extract_name(tokens=tokens, rank=rank)
                if name is None:
                    break
                cleaned, c_rest=remove_outer_non_alpha(' '.join(name))
                names.append((cleaned, match, score))
                tokens=[x for x in rest[0]+c_rest+rest[1] if len(x)>0]
            return names, tokens

        tokens=text.strip().split()
        if len(tokens)==0 or len(tokens)>50:
            return [], tokens
        
        names=[]
        names, remaining_tokens=extraction_loop(tokens=tokens, rank=rank, names=names)

        return names, remaining_tokens
    
    def extract_names_fuzzy(self, string_list, rank):

        def generate_candidates(tokens, rank, exclude):
            max_token_length=8
            min_token_len=1
            if rank=='species':
                min_token_len=2

            candidates=[]
            
            exclude=[clean_up_name(remove_abbreviations(name)) for name, _, _ in exclude]
            
            for i in range(0, len(tokens)):
                for j in range(len(tokens), 0, -1):
                    if j-i<min_token_len:
                        break
                    if j-i>max_token_length:
                        break

                    lookup=clean_up_name(remove_abbreviations(name=' '.join(tokens[i:j])))

                    if len(lookup)>0 and lookup not in exclude:
                        candidates.append((i, j, lookup))

            return candidates

        lookups=[]
        for line_nr, string, exclude in string_list:
            
            tokens=string.strip().split()

            # generate candidate sets of tokens to check for names
            # but exclude canidates that already have been extracted as name
            candidates=generate_candidates(tokens, rank, exclude)
            if len(candidates)>0:
                lookups.extend([(lookup, (line_nr, i, j)) for i, j, lookup in candidates])

        lookups=[('Viburnum opulus', (83, 0, 4))]
        print(rank)
        print(lookups)
        matches=self.name_resolver.diff_lib_matcher(lookup=lookups, rank=rank)
        exit()

        # lookup matches for all candidates        
        matches=self.name_resolver.match_fuzzy(lookup=lookups, rank=rank, assume_correct_start=1)
        candidate_matches=[]
        for lookup, ((match, score), meta) in matches.items():
            if score>0:
                self.logger.debug(f'Fuzzy lookup: {lookup:<25} --> {match:<25} ({score:<18}) {meta} [{rank}]')
                line_nr, i, j = meta
                # repackage for easier processing
                candidate_matches.append((i, j, match, score, line_nr))

        # print(candidate_matches)
        # return groupby(candidate_matches, key=lambda x: x[4])
        group_list = [(k, list(g)) for k, g in groupby(candidate_matches, key=lambda x: x[4])]
        # print(group_list)



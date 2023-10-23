import re

class NameMatching:

    name_abbr=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
               'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
               'var.', 'convar.', ]

    species_query = """select count(*) as total from name_lookup
                where scientificName match '\"{match_condition}\"'
                or full_scientific_name  match '\"{match_condition}\"'
                and taxonrank in ('variety', 'species', 'subspecies', 'subvariety', 'subform', 'prole')
                limit 1"""

    def __init__(self, config, db_conn) -> None:
        self.conn=db_conn
        self.config=config

    def clean_up_name(self,
                      text,
                      remove_abbreviations=False, 
                      relics=[],
                      return_tokens=False,
                      return_removed=False):
        clean=text
        if isinstance(clean, list):
            clean=" ".join(clean)

        # remove entire substrings (matched index, IPEN) that might
        # be in the same cell as the name
        for relic in relics:
            clean=clean.replace(str(relic), '')

        test=clean

        # That *really* aren't plants.
        clean=re.sub('Index Seminum', '', clean, re.IGNORECASE)
        clean=re.sub('Desiderata', '', clean, re.IGNORECASE)
        # OCR will often see × as x
        clean=re.sub(' x ', ' ', clean)
        # Remove brackets containing one character at the start of text, like '(*)'
        clean=re.sub(r'^\([^\)]{1}\) ', '', clean)
        # Keep only letters, brackets and some characters
        clean=re.sub(r'[^A-Za-z().&,\- ]', '', clean)
        # Remove 'empty' pairs of brackets 
        clean=re.sub(r'\(\)', '', clean)
        # Remove any non letter(s) at the start
        clean=re.sub(r'^[^A-Za-z]*', '', clean)

        # Remove abbreviated taxonomic codes, like 'ssp.' 
        if remove_abbreviations:
            self.name_abbr.sort(key=lambda x: -len(x))
            for abbr in self.name_abbr:
                clean=clean.replace(abbr, '')

        # Multiple spaces to single space
        clean=re.sub(r'\s{1,}', ' ', clean)

        # print(f"{text} --> {clean.strip()}")

        for token in clean.strip():
            test=test.replace(token, '')

        # Optionally split the result into tokens
        if return_tokens:
            result=re.findall(r'\b([A-Za-z]+)\b', clean.strip(), flags=0)
        else:
            result=clean.strip()

        if return_removed:
            return result, test.strip()
        
        return result

    def get_genera_by_epithet(self, text, remove_abbreviations=False):
        alpha_tokens=self.clean_up_name(text=text, return_tokens=True, remove_abbreviations=remove_abbreviations)
        if len(alpha_tokens)==0 or not alpha_tokens[0].islower():
            return []

        cur=self.conn.cursor()
        query=(f"select genus from name_lookup where epithet match 'epithet:{alpha_tokens[0]}'")
        cur.execute(query)
        names=[]
        for row in cur.fetchall():
            names.append(row['genus'])

        return list(set(names))
  
    def get_species_match(self, text):

        # note that this only matches species names at the start of the text block!

        alpha_tokens=self.clean_up_name(text=text, remove_abbreviations=True, return_tokens=True)
        alpha_tokens=[x.lower() for x in alpha_tokens if len(x)>2]

        if len(alpha_tokens)==0:
            return 0

        cur=self.conn.cursor()

        for i in range(min(4, len(alpha_tokens)), 1, -1):
            match_condition=' '.join(alpha_tokens[:i])
            query=self.species_query.format(match_condition=match_condition)
            cur.execute(query)
            row=cur.fetchone()
            if row['total']>0:
                penalty=(len(alpha_tokens)-i)*0.01
                if self.config['debug_print_name_resolvement']:
                    print(f"{1-penalty:>5}: {' '.join(alpha_tokens)} <-- {match_condition}")
                return 1-penalty

        if self.config['debug_print_name_resolvement']:
            print(f"{0:>5}: {' '.join(alpha_tokens)}")
    
        return 0

    def get_ht_match(self, column, ranks, text, max_tokens=None):
        alpha_tokens=self.clean_up_name(text=text, return_tokens=True)

        if len(alpha_tokens)==0:
            return 0

        if max_tokens and len(alpha_tokens)>max_tokens:
            return 0

        cur=self.conn.cursor()
        ranks="','".join(ranks)
        query=f"select count(*) as total from name_lookup where {column} match '\"{alpha_tokens[0].lower()}\"' \
                and taxonrank in ('{ranks}') \
                limit 1"
        cur.execute(query)
        row=cur.fetchone()
        return 1 if row['total']>0 else 0

    def get_genus_match(self, text, max_tokens=None):
        return self.get_ht_match(column='genus', ranks=['genus', 'subgenus'], text=text, max_tokens=max_tokens)

    def get_family_match(self, text, max_tokens=None):
        return self.get_ht_match(column='family', ranks=['family', 'subfamily'], text=text, max_tokens=max_tokens)

    def get_repeated_epithet_match(self, text):
        epithet=None
        candidate_genera=[]

        tokens=self.clean_up_name(text=text, remove_abbreviations=True, return_tokens=True)

        if len(tokens)==0:
            return 0
        
        if tokens[0].islower():
            epithet=tokens[0]
        elif tokens[0] in ['-', '—'] and len(tokens)>1:
            epithet=tokens[1]

        if epithet:
            candidate_genera=self.get_genera_by_epithet(epithet)

        return 1 if len(candidate_genera)>0 else 0

    def extract_name(self, text):
        tokens=text.strip().split()

        if len(tokens)==0:
            return text

        regex=r'(\s|^)([^A-Za-z]{1,})(\s|$)'

        name=None
        found=False
        cur=self.conn.cursor()
        # starting anywhere in the string...
        for start in range(0, len(tokens)):
            # look for the largest matching set of subsequent tokens that match a name
            for length in range(min(6, len(tokens)), 1, -1):
                # get subset of tokens, remove abbreviations
                token_sub=[x for x in tokens[start:start+length] if x not in self.name_abbr]
                # join them, remove bits that are only non-alpha (like dashes separating names
                # and metadata), which can become part of the name, as they are ignored by 
                # SQLite's matching 
                match_condition=re.sub(regex, '', ' '.join(token_sub)).strip()
                cur.execute(self.species_query.format(match_condition=match_condition))
                row=cur.fetchone()
                if row['total']>0:
                    name=' '.join(tokens[start:start+length])
                    found=True
                    break

            if found:
                break

        if not found:
            return text, []

        name=re.sub(regex, '', name)
        return name, list(map(lambda x: x.strip(),re.split(re.escape(name), text)))


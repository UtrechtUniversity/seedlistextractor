class NameListChecks:

    def __init__(self, lines):
        self.lines = lines
    
    def run(self):
        self.genus_fuzzy_species_match()
        return self.lines

    @staticmethod
    def add_warning(line, warning):
        e_prev = line.warnings.copy()
        e_prev.append(warning)
        line.warnings = e_prev

    def genus_fuzzy_species_match(self):
        for line in self.lines:

            if not line.name or line.name.score==1:
                continue

            g_species = line.name.match.genus
            
            if line.genus and line.genus.score==1:
                g_genus = line.genus.match.genus
            else:
                g_genus = line.name.text.split()[0]
            
            if not g_genus.lower()==g_species.lower():
                self.add_warning(line, 'Fuzzy name/genus mismatch')
                


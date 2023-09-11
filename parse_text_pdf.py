import PyPDF2
import re
import pandas

def read_text_pdf(filename: str, startindex: int, endindex: int) -> list:
    reader = PyPDF2.PdfFileReader(filename)
    pages = [p.extract_text() for p in reader.pages[startindex:endindex]]
    text = ''.join(pages).split('\n')
    text[:] = [item for item in text if (item != '' and item != ' ')]
    return text

def remove_lines_containing_pattern(text: list, pattern: re.Pattern, match = False) -> list:
    if match:
        return [item for item in text if not (p.match(item) and p.match(item).group() == item)]
    return [item for item in text if not p.match(item)]
    
def get_items_containing_pattern(idx_to_text: dict, p: re.Pattern, match = False) -> dict:
    if match:
        return dict([(key, value) for key, value in idx_to_text.items() 
                     if p.match(value) and p.match(value).group() == value])
    return dict([(key, value) for key, value in idx_to_text.items() if p.match(value)])

def index_lines(text: list) -> dict:
    idx_to_text = dict(zip(range(0, len(text)), text))
    return idx_to_text

def create_table(species: dict, families: dict, 
                 p_idx: re.Pattern, p_species: re.Pattern) -> pandas.DataFrame:
    # p_idx: regex for identifier
    # p_species: regex for species

    table = []
    for spec_key in species.keys():
        family = ''
        ident = ''
        name = ''
        info = ''
        item = species[spec_key]
        ident = p_idx.match(item).group()
        info = ' '.join(item.split(ident))
        if p_species.match(info):
            name = p_species.match(info).group()
        # Find family
        fam_idx = max([idx for idx in families.keys() if idx < spec_key])
        family = families[fam_idx]
        table.append([family, ident, name, info])
    data = pandas.DataFrame(table, columns = ['fammily', 'id', 'name', 'info'])
    return data

# Example 1
text = read_text_pdf('data/BRLU-2020-x-WE-a-1-x.pdf', 7, 29)
# Remove page numbers ' [1-9] ' and empty rows
p = re.compile('\s\d*\s*')
text = remove_lines_containing_pattern(text, p, True)
idx_to_text = index_lines(text)

# Find families
p = re.compile('[A-Z]+[a-z]+\s*')
families = get_items_containing_pattern(idx_to_text, p, True)
# Find species
p = re.compile('\d+\s[A-Z, a-z, \s]+')
species = get_items_containing_pattern(idx_to_text, p)
# Create list [Family, number, species, info]
p_species = re.compile(r'\s[A-Z][a-z, A-Z, \s]+', re.UNICODE)
p_idx = re.compile('\d+\s*')
data = create_table(species, families, p_idx, p_species)


# Example 2
text = read_text_pdf('data/KL-2020-G-WI-x-1-I.pdf', 4, 34)
# Remove page numbers ' [1-9] ' and empty rows
p = re.compile('\s\d*\s*')
text = remove_lines_containing_pattern(text, p, True)
idx_to_text = index_lines(text)

# Find families
p = re.compile('[\s, A-Z]+')
families = get_items_containing_pattern(idx_to_text, p, True)
# Find species
p = re.compile('\d+\s+([A-Z, a-z, \s])+')
species = get_items_containing_pattern(idx_to_text, p)
# Create list [Family, number, species, info]
p_species = re.compile(r'\s[A-Z][a-z, A-Z, \s]+', re.UNICODE)
p_idx = re.compile('\d+\s*')
data = create_table(species, families, p_idx, p_species)

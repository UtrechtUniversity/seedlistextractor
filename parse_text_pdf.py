import PyPDF2
import re
import pandas

# Example 1

reader = PyPDF2.PdfFileReader('data/BRLU-2020-x-WE-a-1-x.pdf')
pages = [p.extract_text() for p in reader.pages[7:29]]
text = ''.join(pages).split('\n')
text[:] = [item for item in text if (item != '' and item != ' ')]

# Remove page numbers ' [1-9] '
p = re.compile('\s\d*\s')
text[:] = [item for item in text if not (p.match(item) and p.match(item).group() == item)]

idx_to_text = dict(zip(range(0, len(text)-1), text))

# Find families
p = re.compile('[A-Z][a-z]+')
families = dict([(key, value) for key, value in idx_to_text.items() if p.match(value)])
# Find species
p = re.compile('\d+\s([A-Z, a-z, \s])+')
species = dict([(key, value) for key, value in idx_to_text.items() if p.match(value)])
# Create list [Family, number, species]
table = []
for spec_key in species.keys():
    item = species[spec_key]
    ident = item.split()[0]
    name = " ".join(item.split()[1:])
    # Find family
    fam_idx = max([idx for idx in families.keys() if idx < spec_key])
    family = families[fam_idx]
    table.append([family, ident, name])
data = pandas.DataFrame(table, columns = ['fammily', 'id', 'name and info'])


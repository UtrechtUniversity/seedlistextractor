import PyPDF2
import re
import pandas

def read_text_pdf(filename: str, startindex = 0, endindex = 0) -> list:
    reader = PyPDF2.PdfFileReader(filename)
    if startindex == 0 and endindex == 0:
        pages = [p.extract_text() for p in reader.pages]
    else:
        pages = [p.extract_text() for p in reader.pages[startindex:endindex]]
    text = ''.join(pages).split('\n')
    text[:] = [item for item in text if (item != '' and item != ' ')]
    return text

def remove_lines_containing_pattern(text: list, pattern: re.Pattern, match = False) -> list:
    if match:
        return [item for item in text if not p.match(item) or not p.match(item).group() == item]
    else:
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

import os
data = {}
directory = "data"
files = [f for f in os.listdir(directory) if f.lower().endswith(".pdf")]
columns = ["file", "start", "end", "family_regex", "species_regex", "ident_regex", "speciesname_regex"]
idx = len(files)*[0]
regex = len(files)*[""]
metadata = pandas.DataFrame(list(zip(files, idx, idx, regex, regex, regex, regex)), columns = columns)

for name in files:
    print("STATUS:", name)
    f =  os.path.join(directory, name)
    try:
        text = read_text_pdf(f)
        p = re.compile('\s\d*\s*')
        text = remove_lines_containing_pattern(text, p, True)
        idx_to_text = index_lines(text)
    except Exception as e:
        data[f] = {}
        print("CAN'T READ FILE: "+ repr(e))
        data[f]["error"] = "CAN'T READ FILE: "+ repr(e)
        continue

    try:
        # Find families
        p = re.compile('[A-Z]+\s*')
        families = get_items_containing_pattern(idx_to_text, p, True)
        if families == {} or len(families) < 10:
            p = re.compile('[A-Z]+[a-z]+\s*')
            families = get_items_containing_pattern(idx_to_text, p, True)
        # Find species
        p = re.compile('\d+.\s[A-Z, a-z, \s]+')
        species = get_items_containing_pattern(idx_to_text, p)
        if species == {} or len(species) < 50:
            p = re.compile('-\s([A-Z, a-z, \s])+')
            species = get_items_containing_pattern(idx_to_text, p)
        if species == {} or len(species) < 50:
            p = re.compile('\d+\s[A-Z, a-z, \s]+')
            species = get_items_containing_pattern(idx_to_text, p)
        if species == {} or len(species) < 50:
            p = re.compile('[A-Z, a-z]+\s+[A-Z]+')
            species = get_items_containing_pattern(idx_to_text, p)
        if len(families) > 10 and len(species) > 50:
            print("CREATING dataframe")
            p_species = re.compile(r'\s[A-Z][a-z, A-Z, \s]+', re.UNICODE)
            p_idx = re.compile('\d+.\s+')
            tmp = get_items_containing_pattern(idx_to_text, p_idx)
            if len(tmp) > 50:
                data[f] = create_table(species, families, p_idx, p_species)
                continue
            p_idx = re.compile('\d+\s+')
            tmp = get_items_containing_pattern(idx_to_text, p_idx)
            if len(tmp) > 50:
                data[f] = create_table(species, families, p_idx, p_species)
                continue
            else:
                data[f] = {}
                data[f]["error"] = "INDEX NUMBER not found: check regexps for family and species"
                data[f]['text'] = idx_to_text
        else:
            data[f] = {}
            data[f]['text'] = idx_to_text
            data[f]["error"] = "NOT ENOUGH DATA FOUND: check regexps for family and species"
    except Exception as e:
        print("WRNONG FORMAT: "+ repr(e))
        data[f] = {}
        data[f]["text"] = idx_to_text
        data[f]["error"] = "WRNONG FORMAT: "+ repr(e)

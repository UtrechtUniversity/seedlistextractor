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

# Example 3 (two column PDF)
text = read_text_pdf('data/bgr02-2020-G-WI-a-2-x.pdf', 1, 6)
text = read_text_pdf('data/bgr02-2020-G-WI-a-2-x.pdf')
p = re.compile('\s\d*\s*')
text = remove_lines_containing_pattern(text, p, True)
idx_to_text = index_lines(text)
# Find families
p = re.compile('[\s, A-Z]+')
families = get_items_containing_pattern(idx_to_text, p, True)
# Find species
p = re.compile('\d+.\s[A-Z, a-z, \s]+')
species = get_items_containing_pattern(idx_to_text, p)
# Create list [Family, number, species, info]
p_species = re.compile(r'\s[A-Z][a-z, A-Z, \s]+', re.UNICODE)
p_idx = re.compile('\d+.\s*')
data = create_table(species, families, p_idx, p_species)

# Example 5
text = read_text_pdf('data/AND-2020-G-x-a-1-A.pdf', 5, 18)
text = read_text_pdf('data/AND-2020-G-x-a-1-A.pdf')
p = re.compile('\s\d*\s*')
text = remove_lines_containing_pattern(text, p, True)
idx_to_text = index_lines(text)
# Find families
p = re.compile('[\s, A-Z]+')
families = get_items_containing_pattern(idx_to_text, p, True)
# Find species
p = re.compile('\d+.\s+([A-Z, a-z, \s])+')
species = get_items_containing_pattern(idx_to_text, p)
# Create list [Family, number, species, info]
p_species = re.compile(r'\s[A-Z][a-z, A-Z, \s]+', re.UNICODE)
p_idx = re.compile('\d+*')
data = create_table(species, families, p_idx, p_species)

# Example 6
text = read_text_pdf('data/BESN-2020-x-x-a-1-x.PDF', 1, 9)
p = re.compile('\s\d*\s*')
text = remove_lines_containing_pattern(text, p, True)
idx_to_text = index_lines(text)
p = re.compile('[A-Z]+[a-z]+\s*')
families = get_items_containing_pattern(idx_to_text, p, True)
p = re.compile('-\s([A-Z, a-z, \s])+')
species = get_items_containing_pattern(idx_to_text, p)
p_idx = re.compile('-\s')
p_species = re.compile(r'\s[A-Z][a-z, A-Z, \s]+', re.UNICODE)
data = create_table(species, families, p_idx, p_species)

import re 
from pathlib import Path

def extract_synonym_strings(text):
    regex=r'((\[|\()(sin|syn)\.?\:? ([^\]\)]*)(\]|\)))'
    matches=re.findall(regex, text.strip(), re.UNICODE|re.IGNORECASE)
    return [x[0] for x in matches]

def extract_cultivar_string(text):
    c_class = '[A-Za-z ]+'
    regex = rf'\({c_class}form\)'
    for delim in ('‘','’'), '´', '"', "'", ('„', '”'):
        if not isinstance(delim, tuple):
            delim = (delim, delim)
        regex = rf'{re.escape(delim[0])}{c_class}{re.escape(delim[1])}|{regex}'

    regex=rf'({regex})'

    match=re.search(regex, text.strip(), re.UNICODE|re.IGNORECASE)
    if match:
        return match.group(0)

def extract_ipen(text):
    """
    The IPEN number consists of four elements:

    - Country of origin (two positions, abbreviation according to ISO 3166-1-alpha-2, “XX” for unknown origin)
    - Restrictions of transfer (one position, “1” if there exists a restriction; “0” if none).
    - The unique Garden code of the institution offering the plant material for exchange, (to be found on the BGCI Website under “GardenSearch”).
    - Identification Number (the specific accession number of the plant material in the recording system of the garden)

    https://www.bgci.org/our-work/inspiring-and-leading-people/policy-and-advocacy/access-and-benefit-sharing/the-international-plant-exchange-network/#ipen-documentation-system
    """
    regex = r'(([A-Z]{2}|[a-z]{2})([-\.]{1})([01]{1})([-\.]{1})([A-Z]{1,5}|[a-z]{1,5})([-\./_]{1})([^\s\]\:\)]+))'
    match = re.search(regex, text.strip())
    if match:
        return match.group(0), match.span(0)[0]
    return None, -1

def extract_split_ipen(line_text, next_line_text):
    # if the next line has a complete IPEN, don't do anything
    if extract_ipen(text=next_line_text)[0]:
        return None

    # extract IPEN from the two concated lines
    return extract_ipen(text=line_text+next_line_text)[0]

def extract_filename_vars(filename):
    garden_code = None
    year = None
    bits = Path(filename).stem.split('-')
    if len(bits)>3 and re.match(r'^[A-Z]+$', bits[0]) and re.match(r'^\d{4}$', bits[1]):
        garden_code = bits[0]
        year = int(bits[1])
    else:
        bits = Path(filename).stem.split('_')
        if len(bits)>1 and re.match(r'^[A-Z]+$', bits[0]) and re.match(r'^\d{4}', bits[1]):
            garden_code = bits[0]
            year = int(re.split(r'(^\d{4})', bits[1])[1])
    
    if year is None:
        match = re.search(r'(1(8|9)\d{2})', Path(filename).name)
        if match:
            year = int(Path(filename).name[match.span()[0]:match.span()[1]])

    return Path(filename).name, garden_code, year

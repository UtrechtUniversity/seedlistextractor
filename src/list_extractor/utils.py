import re

def raw_line_preprocess(text):
    # tabs to spaces
    text = re.sub(r'\t', ' ', text)
    # homogenise dashes
    # see https://en.wikipedia.org/wiki/Hyphen#Unicode for "dashes" (list omits \u2013, \u2014)
    text = re.sub(r'[\u2013\u2014\u002D\u00AD\u2010\u2011\u2E5D\u058A\u05BE\u1806\u1B60\u2E17\u30FB\uFE63\uFF0D\uFF65\u1400\u2027\u2043\u2E1A\u2E40\u30A0]+', '-', text)  # pylint: disable=line-too-long
    # remove standard title
    text = re.sub(r'Index[\s]{1,}seminum', '', text, flags=re.IGNORECASE)
    # replacing isolated x's with hybrid symbol ×
    text = re.sub(r'\s{1}(x|X)\s{1}', ' × ', text)
    # replace repeating (4 or more) non-alphanumeric characters with single character (dots in index)
    text = re.sub(r'([^A-Za-z0-9])\1{4,}', r'\1', text)
    # misc characters (OCR artefacts)
    text = re.sub(r'■', ' ', text)

    return text.strip()

def remove_outer_non_alpha(text):
    regex=r'(^[^a-zA-Z]{1,}|[^a-zA-Z\.\)]{1,}$)'
    cleaned=re.sub(regex, '', text.strip(), re.UNICODE)

    if cleaned[0]=='(' and ')' not in cleaned:
        cleaned=cleaned[1:]
    elif cleaned[-1]==')' and '(' not in cleaned:
        cleaned=cleaned[:-1]

    if cleaned != text:
        return cleaned, text.split(cleaned)

    return text, ['','']

def single_spaces(string):
    return re.sub(r'(\s){1,}', ' ', string)

def clean_up_name(name):
    return single_spaces(re.sub(r'[^a-zA-Z ]', ' ', name)).strip()

def remove_abbreviations(name, abbreviations=None):
    if abbreviations is None:
        abbreviations=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
                       'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
                       'var.', 'convar.', ]
    return ' '.join([x for x in name.split() if x not in abbreviations 
                     and f"{x}." not in abbreviations])

def fully_clean(name, abbreviations=None):
    return clean_up_name(remove_abbreviations(name=name, abbreviations=abbreviations))
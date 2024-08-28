import logging
import re
import xml.etree.ElementTree as ET

def raw_line_preprocess(text):
    text = re.sub(r'\t', ' ', text)
    # see https://en.wikipedia.org/wiki/Hyphen#Unicode for "dashes" (list omits \u2013)
    text = re.sub(r'[\u2013\u002D\u00AD\u2010\u2011\u2E5D\u058A\u05BE\u1806\u1B60\u2E17\u30FB\uFE63\uFF0D\uFF65\u1400\u2027\u2043\u2E1A\u2E40\u30A0]+', '-', text)
    text = re.sub(r'Index[\s]{1,}seminum', '', text, flags=re.IGNORECASE)
    # replacing isolated x's with hybrid symbol ×
    text = re.sub(r'\s{1}(x|X)\s{1}', ' × ', text)
    # replace repeating (4 or more) non-alphanumeric characters with single character
    text = re.sub(r'([^A-Za-z0-9])\1{3,}', r'\1', text)
  
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

def single_spaces(str):
    return re.sub(r'(\s){1,}', ' ', str)

def clean_up_name(name):
    return single_spaces(re.sub(r'[^a-zA-Z ]', '', name)).strip()

def remove_abbreviations(name, abbreviations=None):
    if abbreviations is None:
        abbreviations=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
                        'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
                        'var.', 'convar.', ]
    return ' '.join([x for x in name.split() if x not in abbreviations])


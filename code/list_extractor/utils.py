import logging
import re
import xml.etree.ElementTree as ET

def get_lines(doc):

    """
    Reads raw data from either XML or JSON, exported from Apache Tika.
    Tika's XML includes page numbers, which are absent from the JSON output.
    """

    line_template={
        'line_nr': None,
        'page': 0,
        'raw': None, 
        'family': [],
        'genus': [],
        'species': [],
        'epithet': [],
        'cultivar': [],
        'index': [],
        'index_raw': [],
        'ipen': [],
        'syn': [],
        'meta_rest': [],
        'meta_next': [],
        '_remove': [], }


    def clean_line(text):
        if text:
            return text.replace('\t','    ').strip()
        return ''

    lines=[]
    
    try:
        root=ET.fromstring(doc['document']['content'])
        ns=re.sub('}html','}', root.tag)
        
        page=0
        line_nr=0
        for elem in root.iter():
            if elem.tag==f"{ns}div":
                page+=1
            if elem.tag==f"{ns}p" and elem.text:
                for line in elem.text.splitlines():
                    line=clean_line(line)
                    # print(line)
                    # print('-'*50)
                    # if len(line.strip())>0:
                    new_line=line_template.copy()
                    new_line.update({'line_nr': line_nr, 'page': page, 'raw': line})
                    lines.append(new_line)
                    line_nr+=1

        logging.debug(f"read {len(lines)} lines from XML")

    except Exception as e:

        doc_lines=map(clean_line, doc['document']['content'].splitlines())
        for line_nr, line in enumerate(doc_lines):
            new_line=line_template.copy()
            new_line.update({'line_nr': line_nr, 'raw': line})
            lines.append(new_line)

        logging.debug(f"read {len(lines)} lines from JSON")

    return lines

def remove_outer_non_alpha(text):
    regex=r'(^[^a-zA-Z]{1,}|[^a-zA-Z\.\)]{1,}$)'
    cleaned=re.sub(regex, '', text.strip(), re.UNICODE)
    if cleaned != text:
        return cleaned, text.split(cleaned)
    return text, ['','']

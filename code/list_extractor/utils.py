import chardet
import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

class NameObject(NamedTuple):
    text: str
    match: str
    score: float
    line_nr: int
    index: int

class CultivarObject(NamedTuple):
    text: str
    line_nr: int

class IpenObject(NamedTuple):
    text: str
    line_nr: int
    index: int

class DocumentLine:

    line_nr=None
    raw=None
    page=0
    family=None
    genus=None
    species=None
    epithet=None
    cultivar=None
    ipen=None
    synonyms=[]
    repeater=None
    meta_rest=None
    meta_next=[]
    _rest=None 

    def __init__(self, line_nr, raw, page=0) -> None:
        self.line_nr=line_nr
        self.raw=raw
        self.page=page

    def has_values(self):
        return self.family \
            or self.genus \
            or self.species \
            or self.epithet \
            or self.cultivar \
            or self.ipen \
            or len(self.synonyms)>0

class InputDocs:

    def __init__(self,
                 input_path, 
                 extension=None,
                 logger=None):

        self.files=[]
        self.logger=logger

        p=Path(input_path)

        if p.is_dir():
            self.files=[x for x in p.glob('**/*') if x.is_file() if extension is None or x.suffix==extension]
        elif p.is_file():
            self.files.append(p)

        if len(self.files)==0:
            raise ValueError("No files found (input path should be either a file, or a folder without wildcards).")
    
        self.logger.info("Got %s file(s) from '%s'" , len(self.files), p)
        self.files=sorted(self.files)
        self.extension=extension

    def parse_doc(self, doc):
        """
        Reads raw data from either XML or JSON, exported from Apache Tika.
        Tika's XML includes page numbers, which are absent from the JSON output.
        """
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
                        new_line=DocumentLine(line_nr=line_nr, raw=line, page=page)
                        lines.append(new_line)
                        line_nr+=1

            logging.debug(f"read {len(lines)} lines from XML")

        except Exception as e:

            doc_lines=map(clean_line, doc['document']['content'].splitlines())
            for line_nr, line in enumerate(doc_lines):
                new_line=DocumentLine(line_nr=line_nr, raw=line)
                lines.append(new_line)

            logging.debug(f"Read {len(lines)} lines from JSON")

        return lines

    def __iter__(self):
        for file in self.files:
            with open(file, mode='rb') as f:
                rawdata=f.read()
                char=chardet.detect(rawdata)
                char['encoding']

            with open(file, "r", encoding=char['encoding']) as f:
                if self.extension==".json":
                    lines=self.parse_doc(json.load(f))
                else:
                    lines=[]
                    for line_nr, line in enumerate(f.read().splitlines()):
                        # new_line=self.line_template.copy()
                        # new_line.update({'line_nr': line_nr, 'raw': line})
                        new_line=DocumentLine(line_nr=line_nr, raw=line)
                        lines.append(new_line)

            yield file, lines

def remove_outer_non_alpha(text):
    regex=r'(^[^a-zA-Z]{1,}|[^a-zA-Z\.\)]{1,}$)'
    cleaned=re.sub(regex, '', text.strip(), re.UNICODE)
    if cleaned != text:
        return cleaned, text.split(cleaned)
    return text, ['','']

def clean_up_name(name):
    return re.sub(r'(\s){1,}', ' ', re.sub(r'[^a-zA-Z ]', '', name)).strip()

def remove_abbreviations(name, abbreviations=None):
    if abbreviations is None:
        abbreviations=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
                        'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
                        'var.', 'convar.', ]
    return ' '.join([x for x in name.split() if x not in abbreviations])

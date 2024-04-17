import chardet
import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

class MatchedNameObject(NamedTuple):
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
    genus=None
    species=None
    epithet=None
    cultivar=None
    ipen=None
    synonyms=[]
    repeater=None
    meta_rest=None
    meta_next=[]
    ref=[]
    _rest=None 
    _raw_no_ipen=None

    def __init__(self, line_nr, raw, page=0) -> None:
        self.line_nr=line_nr
        self.raw=raw
        self.page=page
        self._raw_no_ipen=raw

    def has_values(self):
        return self.genus \
            or self.species \
            or self.epithet \
            or self.cultivar \
            or self.ipen \
            or len(self.synonyms)>0

    def __str__(self):
        return f"{{ line_nr: {self.line_nr}, " + \
            f"page: {self.page}, " + \
            f"raw: '{self.raw}', " + \
            f"genus: {self.genus}, " + \
            f"species: {self.species}, " + \
            f"epithet: {self.epithet}, " + \
            f"cultivar: {self.cultivar}, " + \
            f"ipen: {self.ipen}, " + \
            f"synonyms: {self.synonyms}, " + \
            f"repeater: {self.repeater}, " + \
            f"meta_rest: {self.meta_rest}, " + \
            f"meta_next: {self.meta_next}, " + \
            f"ref: {self.ref}, " + \
            f"_raw_no_ipen: {self._raw_no_ipen}, " + \
            f"_rest: '{self._rest}' }}"

class InputDocs:

    def __init__(self,
                 input_path, 
                 logger=None):

        self.files=[]
        self.logger=logger

        p=Path(input_path)

        if p.is_dir():
            self.files=[x for x in p.glob('**/*') if x.is_file() if x.suffix.lower() in ['.json', '.txt']]
        elif p.is_file():
            self.files.append(p)

        if len(self.files)==0:
            raise ValueError("No files found (input path should be either a file, or a folder without wildcards).")
    
        self.logger.info("Got %s file(s) from '%s'" , len(self.files), p)
        self.files=sorted(self.files)

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

            suffix=Path(file).suffix

            with open(file, mode='rb') as f:
                rawdata=f.read()
                char=chardet.detect(rawdata)
                char['encoding']

            with open(file, "r", encoding=char['encoding']) as f:
                if suffix==".json":
                    lines=self.parse_doc(json.load(f))
                elif suffix==".txt":
                    lines=[]
                    for line_nr, line in enumerate(f.read().splitlines()):
                        new_line=DocumentLine(line_nr=line_nr, raw=line)
                        lines.append(new_line)

            yield file, lines

class LegendItem:

    def __init__(self, symbol, count=1):
        self.symbol=symbol
        self.count=count
        self.descriptor=None
        self._descriptors=[]

    def __repr__(self):
        return f"LegendItem(symbol='{self.symbol}', " + \
            f"count={self.count}, " + \
            f"descriptor='{self.descriptor}', " + \
            f"descriptors='{'; '.join(self._descriptors)}')"

    def increase_count(self, count=1):
        self.count+=count

    def add_descriptor(self, descriptor):
        self._descriptors.append(descriptor)
        self.assign_descriptor()

    def assign_descriptor(self):
        if len(self._descriptors)==1:
            self.descriptor=self._descriptors[0]
        elif len(self._descriptors)>1:
            self.descriptor=sorted(
                self._descriptors,
                key=lambda x: x.index(self.symbol))[0]

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

def clean_up_name(name):
    return re.sub(r'(\s){1,}', ' ', re.sub(r'[^a-zA-Z ]', '', name)).strip()

def remove_abbreviations(name, abbreviations=None):
    if abbreviations is None:
        abbreviations=['aff.', 'agg.', 'ambig.', 'cl.', 'f.', 'gx',
                        'sensu lato', 'ssp.', 'sp.', 'subsp.', 'subvar.',
                        'var.', 'convar.', ]
    return ' '.join([x for x in name.split() if x not in abbreviations])

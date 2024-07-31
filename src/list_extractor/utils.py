import chardet
import datetime
import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

class DocumentLine:

    line_nr = None
    raw = None
    page = 0
    name = None
    epithet = None
    ipen = None
    synonyms = []
    cultivar = None
    repeat_symbols= None 
    meta_rest = None
    meta_next = []
    ref = []
    _rest = None 

    def __init__(self, line_nr, raw, page=0) -> None:
        self.line_nr = line_nr
        self.raw = raw
        self.page = page
        self._raw_no_ipen = raw

    def __str__(self):
        return f"{{ line_nr: {self.line_nr}, " + \
            f"page: {self.page}, " + \
            f"raw: '{self.raw}', " + \
            f"name: {self.name}, " + \
            f"epithet: {self.epithet}, " + \
            f"ipen: {self.ipen}, " + \
            f"synonyms: {self.synonyms}, " + \
            f"cultivar: {self.cultivar}, " + \
            f"repeat_symbols: {self.repeat_symbols}, " + \
            f"meta_rest: {self.meta_rest}, " + \
            f"meta_next: {self.meta_next}, " + \
            f"ref: {self.ref}, " + \
            f"_rest: '{self._rest}' }}"

    def __repr__(self):
        return f"{{ line_nr: {self.line_nr}, " + \
            f"page: {self.page}, " + \
            f"raw: '{self.raw}', " + \
            f"name: {self.name}, " + \
            f"epithet: {self.epithet}, " + \
            f"ipen: {self.ipen}, " + \
            f"synonyms: {self.synonyms}, " + \
            f"cultivar: {self.cultivar}, " + \
            f"repeat_symbols: {self.repeat_symbols}, " + \
            f"meta_rest: {self.meta_rest}, " + \
            f"meta_next: {self.meta_next}, " + \
            f"ref: {self.ref}, " + \
            f"_rest: '{self._rest}' }}"

    def has_names(self):
        return self.name \
            or self.epithet \
            or self.ipen \
            or len(self.synonyms)>0 \
            or self.cultivar

class InputDocs:

    def __init__(self,
                 input_path,
                 raw_lines=False,
                 logger=None):

        self.files = []
        self.raw_lines = raw_lines
        self.logger = logger
        self.input_path = Path(input_path)

        p = Path(input_path)

        if p.is_dir():
            self.files = [x for x in p.glob('**/*') if x.is_file() if x.suffix.lower() in ['.json', '.txt']]
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

        lines = []
        
        try:
            root = ET.fromstring(doc['document']['content'])
            ns = re.sub('}html','}', root.tag)
            
            page = 0
            line_nr = 0
            for elem in root.iter():
                if elem.tag==f"{ns}div":
                    page += 1
                if elem.tag==f"{ns}p" and elem.text:
                    for line in elem.text.splitlines():
                        line = clean_line(line)
                        if self.raw_lines:
                            new_line = line
                        else:
                            new_line = DocumentLine(line_nr=line_nr, raw=line, page=page)
                        lines.append(new_line)
                        line_nr += 1

            logging.debug(f"read {len(lines)} lines from XML")

        except Exception as e:

            doc_lines = map(clean_line, doc['document']['content'].splitlines())
            for line_nr, line in enumerate(doc_lines):
                if self.raw_lines:
                    new_line = line
                else:
                    new_line = DocumentLine(line_nr=line_nr, raw=line)
                lines.append(new_line)

            logging.debug(f"Read {len(lines)} lines from JSON")

        return lines

    def __iter__(self):
        for file in self.files:

            suffix = Path(file).suffix
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
                        if self.raw_lines:
                            new_line = line
                        else:
                            new_line = DocumentLine(line_nr=line_nr, raw=line)
                        lines.append(new_line)
                else:
                    lines=[]

            folder = str(self.input_path) if self.input_path.is_dir() else str(self.input_path.parent)

            yield str(file).replace(folder, ''), lines
            
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
        self.count += count

    def add_descriptor(self, descriptor):
        descriptor = descriptor.strip()
        if len(descriptor)>10 and ' ' in descriptor:
            self._descriptors.append(descriptor)
            self.assign_descriptor()

    def assign_descriptor(self):
        if len(self._descriptors)==1:
            self.descriptor = self._descriptors[0]
        elif len(self._descriptors)>1:
            self.descriptor = sorted(
                self._descriptors,
                key=lambda x: (sum(1 for c in x if c.isupper()), x.index(self.symbol)))[0]

class JobLog:

    def __init__(self,
                 input_path,
                 skip_existing,
                 output_root,
                 names_database,
                 names_count,
                 extract_ipen,
                 fuzzy_match_threshold,
                 fuzzy_match_strategy,
                 ):
        self.joblog_file = None
        if output_root:
            self.joblog_file = Path(output_root) / "joblog.json"
            data = {
                'paths': {
                    'input_path': input_path,
                    'output_root': output_root,
                },
                'files': {
                    'processed': [],
                    'skipped': [],
                },
                'skip_existing': skip_existing,
                'names_database': {
                    'path': names_database or '(from cache)',
                    'count': {
                        'canonical': names_count[0],
                        'full': names_count[1],
                        'epithet': names_count[2],
                    }
                },
                'extract_ipen': extract_ipen,
                'fuzzy_matching': None,
                'timers': {
                    'execution_start': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'execution_end': None,
                    'updated': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            }

            data['fuzzy_matching'] =  {
                'threshold': fuzzy_match_threshold,
                'strategy': fuzzy_match_strategy,
                } if fuzzy_match_threshold else '(no fuzzy matching)'


            self.write_joblog(data)

    def add_skipped(self, path):
        if not self.joblog_file:
            return
        data = self.read_joblog()
        data['files']['skipped'].append(path)
        self.write_joblog(data)

    def add_processed(self, path):
        if not self.joblog_file:
            return
        data = self.read_joblog()
        data['files']['processed'].append(path)
        self.write_joblog(data)

    def done(self):
        if not self.joblog_file:
            return
        data = self.read_joblog()
        data['timers']['execution_end'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.write_joblog(data)

    def read_joblog(self):
        if not self.joblog_file:
            return
        with open(self.joblog_file, 'r') as f:
            data = json.load(f)
        return data

    def write_joblog(self, data):
        if not self.joblog_file:
            return
        data['timers']['updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.joblog_file, 'w+') as f:
            json.dump(data, f)

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


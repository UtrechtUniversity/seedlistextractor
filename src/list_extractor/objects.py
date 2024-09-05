import datetime
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union, Optional
import xml.etree.ElementTree as ET
import chardet

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
            self.files = [x for x in p.glob('**/*') if x.is_file()
                          and x.suffix.lower() in ['.json', '.txt']]
        elif p.is_file():
            self.files.append(p)

        if len(self.files)==0:
            raise ValueError("No files found (input path should be either a file, " + \
                             "or a folder without wildcards).")

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

        if not 'document' in doc or not 'content' in doc['document']:
            return lines

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

            self.logger.debug(f"read {len(lines)} lines from XML")

        except Exception:  # pylint: disable=broad-exception-caught

            doc_lines = map(clean_line, doc['document']['content'].splitlines())
            for line_nr, line in enumerate(doc_lines):
                if self.raw_lines:
                    new_line = line
                else:
                    new_line = DocumentLine(line_nr=line_nr, raw=line)
                lines.append(new_line)

            self.logger.debug(f"Read {len(lines)} lines from JSON")

        return lines

    def __iter__(self):
        for file in self.files:

            suffix = Path(file).suffix
            with open(file, mode='rb') as f:
                rawdata=f.read()
                char=chardet.detect(rawdata)

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

            folder = str(self.input_path) if self.input_path.is_dir() \
                     else str(self.input_path.parent)

            yield str(file).replace(folder, ''), lines

class LegendItem:

    def __init__(self, symbol, count=1):
        self.symbol = symbol
        self.count = count
        self.descriptor = None
        self._descriptors = []

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

    def __init__(self,  # pylint: disable=too-many-arguments
                 input_path,
                 skip_existing,
                 output_root,
                 names_database,
                 names_count,
                 extract_ipen,
                 fuzzy_match_threshold,
                 fuzzy_match_strategy,
                 fuzzy_match_whole_doc
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
                'whole_doc': fuzzy_match_whole_doc,
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
            return None
        with open(self.joblog_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data

    def write_joblog(self, data):
        if not self.joblog_file:
            return
        data['timers']['updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.joblog_file, 'w+', encoding='utf-8') as f:
            json.dump(data, f)

@dataclass
class CultivarObject():
    text: str
    line_nr: int

@dataclass
class IpenObject():
    text: str
    line_nr: int
    index: int

class NameObject():  # pylint: disable=too-many-instance-attributes

    def __init__(self,  # pylint: disable=too-many-arguments
                 canonical_name: str,
                 taxon_rank: str,
                 genus: Union[str|None] = None,
                 epithet: Union[str|None] = None,
                 infraspecific_epithet: Union[str|None] = None,
                 authorship: Union[str|None] = None,
                 source: Union[str|None] = None,
                 possibly_partial: bool = False) -> None:
        self.canonical_name = canonical_name
        self.taxon_rank = taxon_rank
        self.genus = genus
        self.epithet = epithet
        self.infraspecific_epithet = infraspecific_epithet
        self.authorship = authorship
        self.source = source
        self.possibly_partial = possibly_partial

    @property
    def full_name(self):
        return f"{self.canonical_name} {self.authorship if self.authorship else ''}".strip()

    @property
    def is_hybrid(self):
        return ' × ' in self.full_name

    def __repr__(self):
        def frmt(s):
            return 'None' if s is None else f"'{s}'"
        return f'{__class__.__name__}(' +\
            f"full_name={frmt(self.full_name)} " + \
            f"canonical_name={frmt(self.canonical_name)} " + \
            f"taxon_rank={frmt(self.taxon_rank)} " + \
            f"genus={frmt(self.genus)} " + \
            f"epithet={frmt(self.epithet)} " + \
            f"infraspecific_epithet={frmt(self.infraspecific_epithet)} " + \
            f"authorship={frmt(self.authorship)} " + \
            f"source={frmt(self.source)} " + \
            f"possibly_partial={self.possibly_partial})"

@dataclass
class EpithetObject():
    epithet: Union[str|None] = None
    infraspecific_epithet: Optional[str] = None

@dataclass
class MatchedNameObject():
    text: str
    match: str
    score: float
    line_nr: int
    index: int
    identical_canonicals: list[NameObject] = field(default_factory=lambda: [])

@dataclass
class MatchObject():
    lookup: str
    match: Union[NameObject|EpithetObject|None] = None
    score: float = 0
    identical_canonicals: list[NameObject] = field(default_factory=lambda: [])

@dataclass
class CandidateObject():
    line_nr: int
    index: int
    start: int
    end: int
    option: str
    match: Optional[MatchObject] = None

class DocumentLine:

    line_nr:Optional[int] = None
    raw:Optional[str] = None
    page:int = 0
    name:Optional[NameObject] = None
    epithet:Optional[EpithetObject] = None
    ipen:Optional[str] = None
    synonyms:list[NameObject] = []
    cultivar:Optional[str] = None
    repeat_symbols:list[str] = []
    meta_rest:Optional[str] = None
    meta_next:list[str] = []
    ref:list[str] = []
    name_repeated:int = 0
    _rest:Optional[str] = None

    def __init__(self, line_nr, raw, page=0) -> None:
        self.line_nr = line_nr
        self.raw = raw
        self.page = page

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
            f"name_repeated: {self.name_repeated}, " + \
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
            f"name_repeated: {self.name_repeated}, " + \
            f"_rest: '{self._rest}' }}"

    def has_names(self):
        return self.name \
            or self.epithet \
            or self.ipen \
            or len(self.synonyms)>0 \
            or self.cultivar

import chardet
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from dataclasses import dataclass, field
from subprocess import check_output
from enum import Enum
from pathlib import Path
from typing import Union, Optional

class InputDocs:

    def __init__(self,
                 input_path,
                 encoding,
                 raw_lines=False,
                 logger=None):

        self.files = []
        self.raw_lines = raw_lines
        self.logger = logger
        self.input_path = Path(input_path)
        # use 'None' for encoding guessing per file
        self.encoding = encoding

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
        self.files = sorted(self.files)

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

            page = 1
            line_nr = 1
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

            self.logger.debug(f"Read {len(lines)} lines from XML")

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
            
            if not self.encoding:
                with open(file, mode='rb') as f:
                    rawdata = f.read()
                    char = chardet.detect(rawdata)
                    encoding = char['encoding']
                    self.logger.debug(f"Detecting encoding for '{file}': {char['encoding']} (confidence: {char['confidence']})")
            else:
                encoding = self.encoding

            with open(file, "r", encoding=encoding) as f:
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

            yield file, lines

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

    def __init__(self, **kwargs):

        self.joblog_file = None

        data = {}
        data['arguments'] = kwargs

        if data['arguments']['output_directory'] or data['arguments']['output_in_situ']:
            now = datetime.now().strftime("%Y-%m-%dT%H%M")
            if data['arguments']['output_in_situ']:
                self.joblog_file = f"./joblog-{now}.json"
            else:
                self.joblog_file = Path(data['arguments']['output_directory']) / f"joblog-{now}.json"

            if not data['arguments']['names_database']:
                data['arguments']['names_database'] = '(from cache)' 

            for key, value in data['arguments'].items():
                if isinstance(data['arguments'][key], Path):
                    data['arguments'][key] = str(value)

            data['files'] = { 'processed': [], 'skipped': [], 'output': [], 'failed': [] }

            data['timers'] = {
                'execution_start': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'execution_end': None,
                'updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            data['git'] = self.get_git_details()

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

    def add_output(self, path):
        if not self.joblog_file:
            return
        data = self.read_joblog()
        data['files']['output'].append(path)
        self.write_joblog(data)

    def add_failed(self, path, cause):
        if not self.joblog_file:
            return
        data = self.read_joblog()
        data['files']['failed'].append((path, cause))
        self.write_joblog(data)

    def done(self):
        if not self.joblog_file:
            return
        data = self.read_joblog()
        data['timers']['execution_end'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        data['timers']['updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.joblog_file, 'w+', encoding='utf-8') as f:
            json.dump(data, f)

    @staticmethod
    def get_git_details():
        try:
            url = check_output(['git', 'config', '--get', 'remote.origin.url']).decode('utf-8').strip()
            tag = check_output(['git', 'tag']).decode('utf-8').strip()
            hsh = check_output(['git', 'log', '-n', '1', '--pretty=tformat:%H']).decode('utf-8').strip()
        except Exception:
            url, tag, hsh = '?', '?', '?'

        return { 'url': url, 'tag': tag, 'hash': hsh }


class FuzzyMatchStrategy(str, Enum):
    # subclass of str makes it serializable
    BEST_SCORE = 'BEST_SCORE'
    LONGEST_NAME = 'LONGEST_NAME'

@dataclass
class FuzzySettings:

    match_threshold: float = None
    match_strategy: FuzzyMatchStrategy = FuzzyMatchStrategy.BEST_SCORE
    near_blocks: bool = False
    min_tokens: int = 2
    min_token_length: int = 3
    large_token_length: int = 15
    line_block_limit: int = 1000

    def __init__(self,
                 match_threshold: float = None,
                 match_strategy: FuzzyMatchStrategy = FuzzyMatchStrategy.BEST_SCORE,
                 near_blocks: bool = False,
                 min_tokens: int = 2,
                 min_token_length: int = 3,
                 large_token_length: int = 15,
                 line_block_limit: int = 1000):

        self.match_threshold = self.set_match_threshold(match_threshold)
        self.match_strategy = match_strategy
        self.near_blocks = near_blocks
        self.min_tokens = min_tokens
        self.min_token_length = min_token_length
        self.large_token_length = large_token_length

    def set_match_threshold(self, value: float) -> None:
        if value is None:
            return
        if value<=0 or value>1:
            raise ValueError("fuzzy_threshold should be a float between 0 and 1")
        return value

@dataclass
class CultivarObject:
    text: str
    line_nr: int

@dataclass
class IpenObject:
    text: str
    line_nr: int
    index: int

class NameObject:  # pylint: disable=too-many-instance-attributes

    def __init__(self,  # pylint: disable=too-many-arguments
                 canonical_name: str,
                 taxon_rank: str,
                 genus: Union[str|None] = None,
                 epithet: Union[str|None] = None,
                 infraspecific_epithet: Union[str|None] = None,
                 authorship: Union[str|None] = None,
                 source: Union[str|None] = None) -> None:
        self.canonical_name = canonical_name
        self.genus = genus
        self.epithet = epithet
        self.infraspecific_epithet = infraspecific_epithet
        self.authorship = authorship
        self.taxon_rank = taxon_rank
        self.source = source

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
            f"source={frmt(self.source)}"

@dataclass
class EpithetObject:
    epithet: Optional[str] = None
    infraspecific_epithet: Optional[str] = None
    taxon_rank: Optional[str] = None
    source: Optional[str] = None

@dataclass
class MatchedNameObject:
    text: str
    match: str
    score: float
    line_nr: int
    index: int
    authorships: list[str] = field(default_factory=lambda: [])

@dataclass
class MatchObject:
    lookup: str
    match: Union[NameObject|EpithetObject|None] = None
    score: float = 0
    authorships: list[str] = field(default_factory=lambda: [])

@dataclass
class CandidateObject:
    line_nr: int
    index: int
    num_tokens: int
    option: str
    match: Optional[MatchObject] = None

class DocumentLine:

    line_nr:Optional[int] = None
    raw:Optional[str] = None
    page:int = 0
    genus:Optional[NameObject] = None
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
    genus_match_score:float = 0
    _rest:Optional[str] = None

    def __init__(self, line_nr, raw, page=0) -> None:
        self.line_nr = line_nr
        self.raw = raw
        self.page = page

    def __str__(self):
        return f"{{ line_nr: {self.line_nr}, " + \
            f"page: {self.page}, " + \
            f"raw: '{self.raw}', " + \
            f"genus: {self.genus}, " + \
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
            f"genus_match_score: {self.genus_match_score}, " + \
            f"_rest: '{self._rest}' }}"

    def __repr__(self):
        return f"{{ line_nr: {self.line_nr}, " + \
            f"page: {self.page}, " + \
            f"raw: '{self.raw}', " + \
            f"genus: {self.genus}, " + \
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
            f"genus_match_score: {self.genus_match_score}, " + \
            f"_rest: '{self._rest}' }}"

    def has_names(self):
        return self.genus \
            or self.name \
            or self.epithet \
            or self.cultivar \
            or len(self.synonyms)>0

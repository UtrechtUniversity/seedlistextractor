from dataclasses import dataclass
from typing import Union

@dataclass
class MatchedNameObject():
    text: str
    match: str
    score: float
    line_nr: int
    index: int

@dataclass
class CultivarObject():
    text: str
    line_nr: int

@dataclass
class IpenObject():
    text: str
    line_nr: int
    index: int

@dataclass
class NameObject():
    canonical_name: str
    taxon_rank: str
    genus: str = None
    epithet: str = None
    infraspecific_epithet: str = None
    authorship: str = None
    source: str = None

@dataclass
class EpithetObject():
    epithet: str = None
    infraspecific_epithet: str = None

@dataclass
class MatchObject():
    lookup: str
    match: Union[NameObject, EpithetObject] = None
    score: float = 0

@dataclass
class CandidateObject():
    line_nr: int
    index: int
    i: int
    j: int
    option: str
    match: MatchObject = None


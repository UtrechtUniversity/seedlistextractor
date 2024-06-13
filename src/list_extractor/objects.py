from dataclasses import dataclass, field
from typing import Union

@dataclass
class CultivarObject():
    text: str
    line_nr: int

@dataclass
class IpenObject():
    text: str
    line_nr: int
    index: int

class NameObject():

    def __init__(self,
                 canonical_name: str,
                 taxon_rank: str,
                 genus: str = None,
                 epithet: str = None,
                 infraspecific_epithet: str = None,
                 authorship: str = None,
                 source: str = None) -> None:
        self.canonical_name = canonical_name
        self.taxon_rank = taxon_rank
        self.genus = genus
        self.epithet = epithet
        self.infraspecific_epithet = infraspecific_epithet
        self.authorship = authorship
        self.source = source

    @property
    def full_name(self):
        return f"{self.canonical_name} {self.authorship if self.authorship else ''}".strip()
    
    def __repr__(self):
        def frmt(str):
            return 'None' if str is None else f"'{str}'"
        return f'{__class__.__name__}(' +\
            f"full_name={frmt(self.full_name)} " + \
            f"canonical_name={frmt(self.canonical_name)} " + \
            f"taxon_rank={frmt(self.taxon_rank)} " + \
            f"genus={frmt(self.genus)} " + \
            f"epithet={frmt(self.epithet)} " + \
            f"infraspecific_epithet={frmt(self.infraspecific_epithet)} " + \
            f"authorship={frmt(self.authorship)} " + \
            f"source={frmt(self.source)})"

@dataclass
class EpithetObject():
    epithet: str = None
    infraspecific_epithet: str = None

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
    match: Union[NameObject, EpithetObject] = None
    score: float = 0
    identical_canonicals: list[NameObject] = field(default_factory=lambda: [])

@dataclass
class CandidateObject():
    line_nr: int
    index: int
    start: int
    end: int
    option: str
    match: MatchObject = None


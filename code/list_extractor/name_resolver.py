import logging
import pickle
import sqlite3
import tfidf_matcher as tm
from pathlib import Path
from utils import clean_up_name, remove_abbreviations
from dataclasses import dataclass

@dataclass
class NameObject():
    full_name: str
    canonical_name: str = None
    genus: str = None
    epithet: str = None
    infraspecific_epithet: str = None
    authorship: str = None

@dataclass
class MatchObject():
    lookup: str
    match: NameObject = None
    score: float = 0
    
class NameResolver:

    pickle_file="./pickles/names_pickle"

    def __init__(self,
                 logger=None,
                 names_database=None,
                 force_names_reload=False,
                 pickle_names=True
                 ) -> None:

        self.force_names_reload=force_names_reload
        self.pickle_names=pickle_names
        self.logger=logger if logger else logging.getLogger()
        self.conn=None

        if names_database is None:
            if self.force_names_reload:
                raise ValueError("Cannot reload names without database")
            if not self.pickle_names:
                raise ValueError("Cannot load names without database")
            self.logger.info("No database, using cached names")
        else:
            if not Path(names_database).exists():
                raise FileNotFoundError("Database '%s' does not exist" % names_database)
            self.conn=self.connect_db(names_database)

        self.names={
            'genus': {},
            'species': {},
            'epithet': {}
        }

        self.load_names(names_database=names_database)

    @staticmethod
    def connect_db(db_file):
        conn=None
        try:
            conn=sqlite3.connect(db_file)
            conn.row_factory=sqlite3.Row
        except Exception as e:
            logging.error(str(e))
            raise(e)

        return conn

    def load_pickle(self):
        try:
            with open(self.pickle_file, 'rb') as file:
                data=pickle.load(file)
            return data
        except:
            pass

    def save_pickle(self, data):
        with open(self.pickle_file, 'wb') as file:
            pickle.dump(data, file)

    def load_names(self, names_database):
        if (names_database is None or not self.force_names_reload) and self.pickle_names:
            names=self.load_pickle()
            if names:
                self.names={
                    'genus': names['genus'],
                    'species': names['species'],
                    'epithet': names['epithet']
                }
                self.logger.info("Unpickled %s genera" % format(len(self.names['genus']), ','))
                self.logger.info("Unpickled %s species" % format(len(self.names['species']), ','))
                self.logger.info("Unpickled %s epithets" % format(len(self.names['epithet']), ','))
            return

        self.logger.debug("Reading names from database")
        cur=self.conn.cursor()
        cur.execute('select canonical_name, genus, epithet, infraspecific_epithet, authorship, taxon_rank \
                    from name_lookup \
                    where not (genus is null and epithet is null and infraspecific_epithet is null and authorship is null)')

        for row in cur.fetchall():

            if len(row['canonical_name'])==0:
                continue

            lookup_name = clean_up_name(remove_abbreviations(row['canonical_name'])).lower()

            record = {
                'canonical_name': row['canonical_name'],
                'genus': row['genus'],
                'epithet': row['epithet'], 
                'infraspecific_epithet': row['infraspecific_epithet'], 
                'authorship': row['authorship'], 
            }

            if row['taxon_rank'] in ['species', 'variety', 'form', 'subspecies', 'prole', 'forma', 'grex']:
                self.names['species'][lookup_name] = record

                if row['authorship'] and len(row['authorship'])>0:
                    self.names['species'][f"{lookup_name} {clean_up_name(remove_abbreviations(row['authorship'])).lower()}"] = record

                if row['genus'] and len(row['genus'])>0:
                    self.names['genus'][clean_up_name(remove_abbreviations(row['genus'])).lower()] = { 'genus': row['genus'] }

                if row['epithet'] and len(row['epithet'])>0:
                    self.names['epithet'][clean_up_name(remove_abbreviations(row['epithet'])).lower()] = { 'epithet': row['epithet'] }

            elif row['taxon_rank']=='genus':
                self.names['genus'][lookup_name] = record


        self.logger.info("Loaded %s genera" % format(len(self.names['genus']), ','))
        self.logger.info("Loaded %s species" % format(len(self.names['species']), ','))
        self.logger.info("Loaded %s epithets" % format(len(self.names['epithet']), ','))

        if self.pickle_names:
            self.save_pickle({
                'genus': self.names['genus'],
                'species': self.names['species'],
                'epithet': self.names['epithet'],
            })

            self.logger.info("Saved pickle")

    def match_exact(self, lookup, rank, strict=False):
        if rank not in self.names:
            raise ValueError(f"unknown rank '{rank}'")

        if lookup is None or len(lookup)==0:
            return MatchObject(lookup=lookup)

        if lookup.lower() in self.names[rank].keys():

            item=self.names[rank][lookup.lower()]

            if rank=='genus':
                genus=item['genus'] or item['canonical_name']
                match=NameObject(full_name=genus, genus=genus)
            elif rank=='epithet':
                epithet=item['epithet'] or item['canonical_name']
                match=NameObject(full_name=epithet, epithet=epithet)
            else:
                match=NameObject(
                    full_name=f"{item['canonical_name']} {item['authorship'] or ''}".strip(),
                    canonical_name=item['canonical_name'],
                    genus=item['genus'],
                    epithet=item['epithet'],
                    infraspecific_epithet=item['infraspecific_epithet'],
                    authorship=item['authorship'])

            if strict and lookup.lower() != match.full_name.lower():
                return MatchObject(lookup=lookup)

            return MatchObject(lookup=lookup, match=match, score=1)

        return MatchObject(lookup=lookup)

    def match_fuzzy(self, lookups, rank):
        matches = tm.matcher(original=lookups,
                             lookup=list(self.names[rank].keys()),
                             k_matches=1,
                             ngram_length=3)
        results=[]
        for _, match in matches.iterrows():
            results.append(MatchObject(lookup=match['Original Name'],
                                       match=self.match_exact(match['Lookup 1'], 'species').match,
                                       score=match['Lookup 1 Confidence']))

        return results

if __name__=="__main__":

    import argparse

    parser=argparse.ArgumentParser()
    parser.add_argument('-l','--lookup', type=str)
    parser.add_argument('-r','--rank', type=str, default='species')
    parser.add_argument('--fuzzy', action='store_true', default=False)
    parser.add_argument('-d','--names-database', type=str)
    parser.add_argument('--force-names-reload', action='store_true', default=False)
    parser.add_argument('--strict-matching', action='store_true', default=False, help='Exact matching must also match authorship (default False)')
    args=parser.parse_args()

    res = NameResolver(names_database=args.names_database, 
                       force_names_reload=args.force_names_reload)
    if args.fuzzy:
        match = res.match_fuzzy(lookups=[args.lookup], rank=args.rank)
    else:
        match = res.match_exact(lookup=args.lookup, rank=args.rank, strict=args.strict_matching)

    print(match)

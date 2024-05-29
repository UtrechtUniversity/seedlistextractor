import logging
import pickle
import sqlite3
import tfidf_matcher as tm
from objects import (NameObject, EpithetObject, MatchObject)
from pathlib import Path
from utils import (clean_up_name, remove_abbreviations)

class NameResolver:

    pickle_file="./pickles/names_pickle"

    def __init__(self,
                 logger=None,
                 names_database=None,
                 force_names_reload=False
                 ) -> None:

        self.logger = logger if logger else logging.getLogger()
        self.force_names_reload = force_names_reload

        if names_database is None:
            if self.force_names_reload:
                raise ValueError("Cannot reload names without database")
            self.logger.info("No database, using cached names")
            self.conn = None
        else:
            if not Path(names_database).exists():
                raise FileNotFoundError("Database '%s' does not exist" % names_database)
            self.conn = self.connect_db(names_database)

        self.names_lookup = {}
        self.epithets_lookup = {}
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
        if (names_database is None or not self.force_names_reload):
            names = self.load_pickle()
            self.names_lookup = names['names']
            self.epithets_lookup = names['epithets']
            self.logger.info("Unpickled %s names" % format(len(self.names_lookup), ','))
            self.logger.info("Unpickled %s epithets" % format(len(self.epithets_lookup), ','))
            return

        self.logger.debug("Reading names from database")

        def dict_factory(cursor, row):
            d = {}
            for idx, col in enumerate(cursor.description):
                d[col[0]] = row[idx]
            return d

        self.conn.row_factory = dict_factory
        cur=self.conn.cursor()
        cur.execute("select canonical_name, genus, epithet, infraspecific_epithet, authorship, taxon_rank, source \
                    from name_lookup \
                    where canonical_name is not null \
                    and genus is not null \
                    and taxon_rank in ('genus', 'species', 'subspecies', 'form', 'variety')")

        for record in cur.fetchall():
            lookup_name = clean_up_name(remove_abbreviations(record['canonical_name'])).lower()
            lookup_epithet = clean_up_name(remove_abbreviations(f"{record['epithet']} {record['infraspecific_epithet'] if record['infraspecific_epithet'] else ''}")).lower()
            self.names_lookup[lookup_name] = record
            self.epithets_lookup[lookup_epithet] = { 'epithet': record['epithet'], 'infraspecific_epithet': record['infraspecific_epithet'] }

        self.logger.info("Loaded %s names" % format(len(self.names_lookup), ','))
        self.logger.info("Loaded %s epithets" % format(len(self.epithets_lookup), ','))
        self.save_pickle({'names': self.names_lookup, 'epithets': self.epithets_lookup})
        self.logger.info("Saved pickle")

    def match_exact(self, lookup, rank=None):
        if rank and rank != 'epithet':
            raise ValueError('Rank can only be \'epithet\' or None for regular matching')

        if lookup is None or len(lookup)==0:
            return MatchObject(lookup=lookup)

        if rank=='epithet' and lookup.lower() not in self.epithets_lookup.keys():
            return MatchObject(lookup=lookup)
        elif rank is None and lookup.lower() not in self.names_lookup.keys():
            return MatchObject(lookup=lookup)

        if rank=='epithet':
            item = self.epithets_lookup[lookup.lower()]
            match = EpithetObject(epithet=item['epithet'], infraspecific_epithet=item['epithet'])
        else:
            item = self.names_lookup[lookup.lower()]

            if lookup[0].islower() and item['taxon_rank']=='genus':
                return MatchObject(lookup=lookup)

            match = NameObject(
                canonical_name=item['canonical_name'],
                genus=item['genus'],
                epithet=item['epithet'],
                infraspecific_epithet=item['infraspecific_epithet'],
                authorship=item['authorship'],
                taxon_rank=item['taxon_rank'],
                source=item['source'])

        return MatchObject(lookup=lookup, match=match, score=1)

    def match_fuzzy(self, lookups):
        # Tf-Idf
        matches = tm.matcher(original=lookups,
                             lookup=list(self.names_lookup.keys()),
                             k_matches=1,
                             ngram_length=3)

        results = []
        for _, match in matches.iterrows():
            exact_match = self.match_exact(match['Lookup 1']).match
            # exact_match can be None if the match is a genus but the lookup
            # doesn't start with a capital letter
            if exact_match:
                results.append(MatchObject(lookup=match['Original Name'],
                                        match=exact_match,
                                        score=match['Lookup 1 Confidence']))

        return results

if __name__=="__main__":

    import argparse

    parser=argparse.ArgumentParser()
    parser.add_argument('-l','--lookup', type=str)
    parser.add_argument('--epithet', action='store_true', default=False)
    parser.add_argument('--fuzzy', action='store_true', default=False)
    parser.add_argument('-d','--names-database', type=str)
    parser.add_argument('--force-names-reload', action='store_true', default=False)
    args=parser.parse_args()

    res = NameResolver(names_database=args.names_database, 
                       force_names_reload=args.force_names_reload)
    if args.fuzzy:
        match = res.match_fuzzy(lookups=[args.lookup])
    else:
        match = res.match_exact(lookup=args.lookup, rank='epithet' if args.epithet else None)

    print(match)

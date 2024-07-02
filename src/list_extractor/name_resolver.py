import logging
import pickle
import sqlite3
import tfidf_matcher as tm
from multiprocessing import (cpu_count, Pool)
from objects import (NameObject, EpithetObject, MatchObject)
from pathlib import Path
from utils import (clean_up_name, remove_abbreviations)

class NameResolver:

    pickle_file="./pickles/names_pickle"
    sources_sort_order = {'WCVP': 0, 'WFO': 1, 'CoL': 2, 'GBIF': 3, 'PlantList': 4}

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

        self.canonical_lookup = {}
        self.full_name_lookup = {}
        self.epithet_lookup = {}
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

            self.canonical_lookup = names['canonicals']
            self.full_name_lookup = names['full_names']
            self.epithet_lookup = names['epithets']

            self.logger.info("Unpickled %s canonical names" % format(len(self.canonical_lookup), ','))
            self.logger.info("Unpickled %s full names" % format(len(self.full_name_lookup), ','))
            self.logger.info("Unpickled %s epithets" % format(len(self.epithet_lookup), ','))
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
            canonical = clean_up_name(remove_abbreviations(record['canonical_name'])).lower()
            full_name = clean_up_name(remove_abbreviations(f"{record['canonical_name']} {record['authorship']}").strip()).lower()

            if full_name != canonical:
                self.full_name_lookup[full_name] = record

                if canonical in self.canonical_lookup:
                    self.canonical_lookup[canonical]['full_names'].append(full_name)
                else:
                    c_record = record.copy()
                    c_record['full_names'] = [full_name]
                    self.canonical_lookup[canonical] = c_record

            epithet = clean_up_name(remove_abbreviations(f"{record['epithet']} {record['infraspecific_epithet'] if record['infraspecific_epithet'] else ''}")).lower()
            self.epithet_lookup[epithet] = { 'epithet': record['epithet'], 'infraspecific_epithet': record['infraspecific_epithet'] }

        self.logger.info("Loaded %s canonical names" % format(len(self.canonical_lookup), ','))
        self.logger.info("Loaded %s full names" % format(len(self.full_name_lookup), ','))
        self.logger.info("Loaded %s epithets" % format(len(self.epithet_lookup), ','))

        self.save_pickle({'canonicals': self.canonical_lookup,
                          'full_names': self.full_name_lookup,
                          'epithets': self.epithet_lookup})
        
        self.logger.info("Saved pickle")

    def match_exact(self, lookup, rank=None, strict_genus_matching=True):
        if lookup is None:
            return MatchObject(lookup=lookup)

        if rank and rank != 'epithet':
            raise ValueError('Rank can only be \'epithet\' or None for regular matching')

        # same preprocessing as keys of the lookup dicts
        c_lookup = clean_up_name(remove_abbreviations(lookup)).lower()

        if len(c_lookup)==0:
            return MatchObject(lookup=lookup)

        if rank=='epithet' and c_lookup not in self.epithet_lookup:
            return MatchObject(lookup=lookup)

        elif not rank=='epithet' and c_lookup not in self.canonical_lookup \
            and c_lookup not in self.full_name_lookup:
            return MatchObject(lookup=lookup)

        identical_canonicals = []
        match = None

        if rank=='epithet':
            item = self.epithet_lookup[c_lookup]
            match = EpithetObject(epithet=item['epithet'], infraspecific_epithet=item['epithet'])
        else:
            if c_lookup in self.full_name_lookup:
                item = self.full_name_lookup[c_lookup]
                if strict_genus_matching and lookup[0].islower() and item['taxon_rank']=='genus':
                    return MatchObject(lookup=lookup)
            else:
                item = self.canonical_lookup[c_lookup]
                if strict_genus_matching and lookup[0].islower() and item['taxon_rank']=='genus':
                    return MatchObject(lookup=lookup)

                ident_canon = []
                for full_name in item['full_names']:
                    ident_canon.append(self.full_name_lookup[full_name])

                def sort_by_source(x):
                    if x['source'] in self.sources_sort_order:
                        return self.sources_sort_order[x['source']]
                    return 99

                for item in sorted(ident_canon, key=sort_by_source):
                    obj = NameObject(
                        canonical_name=item['canonical_name'],
                        genus=item['genus'],
                        epithet=item['epithet'],
                        infraspecific_epithet=item['infraspecific_epithet'],
                        authorship=item['authorship'],
                        taxon_rank=item['taxon_rank'],
                        source=item['source'])

                    if match is None:
                        match = obj
                    else:
                        identical_canonicals.append(obj)

        return MatchObject(lookup=lookup, match=match, score=1, identical_canonicals=identical_canonicals)

    def match_fuzzy(self, lookups, ngram_length=2, include_epithets=False):
        lookups=[clean_up_name(remove_abbreviations(x)) for x in lookups]

        names = list(self.canonical_lookup.keys())+list(self.full_name_lookup.keys())
        if include_epithets:
            names += list(self.epithet_lookup.keys())

        # Tf-Idf
        matches = tm.matcher(original=lookups,
                             lookup=names,
                             k_matches=1,
                             ngram_length=ngram_length)

        results = []
        for _, match in matches.iterrows():
            # results.append((match['Original Name'], match['Lookup 1'], match['Lookup 1 Confidence']))
            exact_match = self.match_exact(match['Lookup 1'])
            # # exact_match can be None if the match is a genus but the lookup
            # # doesn't start with a capital letter
            if exact_match.match:
                results.append(MatchObject(lookup=match['Original Name'],
                                           match=exact_match.match,
                                           score=match['Lookup 1 Confidence'],
                                           identical_canonicals=exact_match.identical_canonicals))

        return results

if __name__=="__main__":

    import argparse

    parser=argparse.ArgumentParser()
    parser.add_argument('-l','--lookup', type=str, nargs='+', required=True)
    parser.add_argument('--epithet', action='store_true', default=False)
    parser.add_argument('--fuzzy', action='store_true', default=False)
    parser.add_argument('-d','--names-database', type=str)
    parser.add_argument('--force-names-reload', action='store_true', default=False)
    args=parser.parse_args()

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)            

    res = NameResolver(logger=logger,
                       names_database=args.names_database, 
                       force_names_reload=args.force_names_reload)

    if args.fuzzy:
        matches = res.match_fuzzy(lookups=args.lookup, ngram_length=1)
        for match in matches:
            print(match)
            print()
    else:
        match = res.match_exact(lookup=args.lookup[0], rank='epithet' if args.epithet else None)
        print(match)
        for identical_canonical in match.identical_canonicals:
            print(identical_canonical.full_name)

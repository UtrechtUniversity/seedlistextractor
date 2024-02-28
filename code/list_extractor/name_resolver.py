import argparse
import sqlite3
import pickle
import logging
import tfidf_matcher as tm
from pathlib import Path

class NameResolver:

    def __init__(self,
                 logger,
                 names_database=None,
                 force_names_reload=False,
                 ) -> None:

        self.config={
            'pickle_file': Path("./pickles/names_pickle"),
            'names_query': 'select scientific_name, full_scientific_name, epithet, taxon_rank from name_lookup'
        }

        self.force_names_reload=force_names_reload
        self.logger=logger

        if names_database is None:
            self.logger.info('No database, using cached names')
        else:
            if not Path(names_database).exists():
                raise FileNotFoundError("Database '%s' does not exist" % names_database)

        self.names={
            'family': {},
            'genus': {},
            'species': {},
            'species_auth': {},
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

    def load_pickle(self, pickle_file):
        try:
            with open(pickle_file, 'rb') as file:
                data=pickle.load(file)
            return data
        except:
            pass

    def save_pickle(self, data, pickle_file):
        with open(pickle_file, 'wb') as file:
            pickle.dump(data, file)

    def load_names(self, names_database):

        if names_database is None or not self.force_names_reload:
            names=self.load_pickle(self.config['pickle_file'])
            if names:
                self.names={
                    'family': names['family'],
                    'genus': names['genus'],
                    'species': names['species'],
                    'species_auth': names['species_auth'],
                    'epithet': names['epithet']
                }

                self.logger.info("unpickled %s families" % format(len(self.names['family']), ','))
                self.logger.info("unpickled %s genera" % format(len(self.names['genus']), ','))
                self.logger.info("unpickled %s species" % format(len(self.names['species']), ','))
                self.logger.info("unpickled %s species w/ auth" % format(len(self.names['species_auth']), ','))
                self.logger.info("unpickled %s epithets" % format(len(self.names['epithet']), ','))

            return

        conn=self.connect_db(names_database)
        cur=conn.cursor()
        cur.execute(self.config['names_query'])

        for row in cur.fetchall():

            if len(row['scientific_name'])==0:
                continue

            if row['taxon_rank'] == 'family':
                self.names['family'][row['scientific_name']]=True

            if row['taxon_rank'] == 'genus':
                self.names['genus'][row['scientific_name']]=True

            if row['taxon_rank'] in ['species', 'variety', 'form', 'subspecies', 'prole', 'forma', 'grex']:
                self.names['species'][row['scientific_name']]=True

            if len(row['full_scientific_name'])>0:
                self.names['species_auth'][row['full_scientific_name']]=True

            if row['epithet'] and len(row['epithet'])>0:
                self.names['epithet'][row['epithet']]=True

        self.logger.info("loaded %s families" % format(len(self.names['family']), ','))
        self.logger.info("loaded %s genera" % format(len(self.names['genus']), ','))
        self.logger.info("loaded %s species" % format(len(self.names['species']), ','))
        self.logger.info("loaded %s species w/ auth" % format(len(self.names['species_auth']), ','))
        self.logger.info("loaded %s epithets" % format(len(self.names['epithet']), ','))

        self.save_pickle({
            'family': self.names['family'],
            'genus': self.names['genus'],
            'species': self.names['species'],
            'species_auth': self.names['species_auth'],
            'epithet': self.names['epithet'],
        }, self.config['pickle_file'])

        self.logger.info("saved pickle")

    def match_exact(self, lookup, rank):

        assert rank in self.names, f"unknown rank '{rank}'"

        if len(lookup)==0:
            return (None, 0)

        if lookup.lower() in self.names[rank].keys():
            return (lookup, 1)
        else:
            if rank=='species':
                return self.match_exact(lookup=lookup, rank='species_auth')
            return (None, 0)

    def match_fuzzy(self, lookups, rank):
        return tm.matcher(original=lookups,
                          lookup=list(self.names[rank].keys()),
                          k_matches=3,
                          ngram_length=2)

if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('-n','--name', required=True)
    parser.add_argument('-r','--rank', required=True)
    parser.add_argument('-d','--names-database')
    parser.add_argument('-f','--force-names-reload', action='store_true', default=False)
    parser.add_argument('--debug', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    nres=NameResolver(names_database=args.names_database,
                      force_names_reload=args.force_names_reload)

    # print("exact:", nres.match_exact(lookup=args.name,rank=args.rank))
    # print("fuzzy:", nres.match_fuzzy(lookup=args.name,rank=args.rank))
    # print(nres.fuzzy_match_single(lookup=args.name, rank=args.rank, score_cutoff=90))



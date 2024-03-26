import logging
import pickle
import sqlite3
import tfidf_matcher as tm
from pathlib import Path

class NameResolver:

    pickle_file="./pickles/names_pickle"

    def __init__(self,
                 logger,
                 names_database=None,
                 force_names_reload=False,
                 ) -> None:

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
        if names_database is None or not self.force_names_reload:
            names=self.load_pickle()
            if names:
                self.names={
                    'family': names['family'],
                    'genus': names['genus'],
                    'species': names['species'],
                    'species_auth': names['species_auth'],
                    'epithet': names['epithet']
                }
                self.logger.info("Unpickled %s families" % format(len(self.names['family']), ','))
                self.logger.info("Unpickled %s genera" % format(len(self.names['genus']), ','))
                self.logger.info("Unpickled %s species" % format(len(self.names['species']), ','))
                self.logger.info("Unpickled %s species w/ auth" % format(len(self.names['species_auth']), ','))
                self.logger.info("Unpickled %s epithets" % format(len(self.names['epithet']), ','))
            return

        conn=self.connect_db(names_database)
        cur=conn.cursor()
        cur.execute('select scientific_name, full_scientific_name, epithet, taxon_rank from name_lookup')

        for row in cur.fetchall():

            if len(row['scientific_name'])==0:
                continue

            if row['taxon_rank']=='family':
                self.names['family'][row['scientific_name']]=True
            elif row['taxon_rank']=='genus':
                self.names['genus'][row['scientific_name']]=True
            elif row['taxon_rank'] in ['species', 'variety', 'form', 'subspecies', 'prole', 'forma', 'grex']:
                self.names['species'][row['scientific_name']]=True

            if len(row['full_scientific_name'])>0:
                self.names['species_auth'][row['full_scientific_name']]=True

            if row['epithet'] and len(row['epithet'])>0:
                self.names['epithet'][row['epithet']]=True

        self.logger.info("Loaded %s families" % format(len(self.names['family']), ','))
        self.logger.info("Loaded %s genera" % format(len(self.names['genus']), ','))
        self.logger.info("Loaded %s species" % format(len(self.names['species']), ','))
        self.logger.info("Loaded %s species w/ auth" % format(len(self.names['species_auth']), ','))
        self.logger.info("Loaded %s epithets" % format(len(self.names['epithet']), ','))

        self.save_pickle({
            'family': self.names['family'],
            'genus': self.names['genus'],
            'species': self.names['species'],
            'species_auth': self.names['species_auth'],
            'epithet': self.names['epithet'],
        })

        self.logger.info("Saved pickle")

    def match_exact(self, lookup, rank):
        if rank not in self.names:
            raise ValueError(f"unknown rank '{rank}'")
        if len(lookup)==0:
            return (None, 0)
        if lookup.lower() in self.names[rank].keys():
            return (lookup, 1)
        if rank=='species':
            return self.match_exact(lookup=lookup, rank='species_auth')
        return (None, 0)

    def match_fuzzy(self, lookups, rank):
        return tm.matcher(original=lookups,
                          lookup=list(self.names[rank].keys()),
                          k_matches=3,
                          ngram_length=3)

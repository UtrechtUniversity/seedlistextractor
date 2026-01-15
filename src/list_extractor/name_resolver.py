import json
import logging
import Levenshtein
import os
import pickle
import polars as pl
import polars_distance as pld
import sqlite3
from math import ceil
from multiprocessing import Pool
from objects import (NameObject, EpithetObject, MatchObject)
from pathlib import Path
from tqdm import tqdm
from utils import (clean_up_name, remove_abbreviations, fully_clean)

# function outside class because multiprocessing needs to pickle
def match_fuzzy_lookup(lookups, names):
    results = []
    for lookup in lookups:
        idx = pl.DataFrame({
            'lookup': lookup,
            'names': names
        }).select(pld.col('lookup')
          .dist_str
          .levenshtein('names')
          .arg_min()
          .alias('index'))['index'].item()
        results.append((lookup, names[idx]))
    return results

class NameResolver:

    def __init__(self,
                 logger = None,
                 names_database = None,
                 multiprocessing = True,
                 pickle_file = None,
                 sources_sort_order = None
                 ) -> None:

        self.logger = logger if logger else logging.getLogger()
        self.multiprocessing = multiprocessing

        if names_database is None:
            if pickle_file is None:
                raise ValueError('Need names database or names cache pickle file')
            self.logger.info('Using cached names')
            self.conn = None
        else:
            if not Path(names_database).exists():
                raise FileNotFoundError('Database \'%s\' does not exist' % names_database)
            self.conn = self.connect_db(names_database)

        self.pickle_file = pickle_file
        self.sources_sort_order = sources_sort_order

        self.canonical_lookup = {}
        self.epithet_lookup = {}
        self.genus_lookup = {}
        self.load_names(names_database=names_database)

    @staticmethod
    def connect_db(db_file):
        conn=None
        try:
            conn = sqlite3.connect(db_file)
            conn.row_factory = sqlite3.Row
        except Exception as e:
            logging.error(str(e))
            raise e

        return conn

    def load_pickle(self):
        try:
            with open(self.pickle_file, 'rb') as file:
                data=pickle.load(file)
            return data
        except:
            pass

    def save_pickle(self, data):
        Path(self.pickle_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.pickle_file, 'wb') as file:
            pickle.dump(data, file)

    def load_names(self, names_database):
        if names_database is None \
        and not Path(self.pickle_file).is_file():
            raise ValueError(f"Fatal: no names database specified, and {self.pickle_file} doen't exist; exiting")

        if names_database is None \
        and self.pickle_file \
        and Path(self.pickle_file).is_file():
            names = self.load_pickle()

            self.canonical_lookup = names['canonicals']
            self.epithet_lookup = names['epithets']
            self.genus_lookup = names['genera']
            self.logger.info('Read %s canonical names from cache',
                             format(len(self.canonical_lookup), ','))
            self.logger.info('Read %s epithets from cache',
                             format(len(self.epithet_lookup), ','))
            self.logger.info('Read %s genera from cache',
                             format(len(self.genus_lookup), ','))
            return

        self.logger.debug('Reading names from database')

        def dict_factory(cursor, row):
            d = {}
            for idx, col in enumerate(cursor.description):
                d[col[0]] = row[idx]
            return d

        self.conn.row_factory = dict_factory
        cur = self.conn.cursor()
        order = ""
        if self.sources_sort_order:
            order = "order by case source " + \
                    " ".join([f"when {x!r} then {self.sources_sort_order[x]}"
                            for x in self.sources_sort_order.keys()]) + \
                    " end asc"

        cur.execute(f"select count(*) as total from name_lookup")
        total = cur.fetchone()['total']

        cur.execute(f"select canonical_name, genus, epithet, infraspecific_epithet, \
                      authorship, taxon_rank, source \
                      from name_lookup \
                      where canonical_name is not null \
                      and genus is not null \
                      and taxon_rank in ('genus', 'species', 'subspecies', 'form', 'variety') \
                      {order}")

        self.logger.info('Reading names from database')

        with tqdm(total=total) as pbar:
            for row in cur.fetchall():
                pbar.update(1)
                canonical = fully_clean(row['canonical_name']).lower()
                authorship = (row['authorship'], row['source'])

                if canonical not in self.canonical_lookup:
                    self.canonical_lookup[canonical] = row | {'authorships': [authorship]}
                elif authorship not in self.canonical_lookup[canonical]['authorships']:
                    self.canonical_lookup[canonical]['authorships'].append(authorship)

                if row['epithet']:
                    epithet = fully_clean(f"{row['epithet']} {row['infraspecific_epithet'] if row['infraspecific_epithet'] else ''}").lower()
                    self.epithet_lookup[epithet] = { 'epithet': row['epithet'],
                                                    'infraspecific_epithet': row['infraspecific_epithet'],
                                                    'taxon_rank': row['taxon_rank'],
                                                    'source': row['source'] }

                if row['taxon_rank']=='genus':
                    if canonical not in self.genus_lookup:
                        self.genus_lookup[canonical] = row | {'authorships': [authorship]}
                    elif authorship not in self.genus_lookup[canonical]['authorships']:
                        self.genus_lookup[canonical]['authorships'].append(authorship)

        self.logger.info('Loaded %s canonical names' % format(len(self.canonical_lookup), ','))
        self.logger.info('Loaded %s epithets' % format(len(self.epithet_lookup), ','))
        self.logger.info('Loaded %s genera' % format(len(self.genus_lookup), ','))

        if self.pickle_file:
            self.save_pickle({'canonicals': self.canonical_lookup,
                              'epithets': self.epithet_lookup,
                              'genera': self.genus_lookup})
            self.logger.info('Saved names cache')
        else:
            self.logger.info('Cannot save names cache (pickle file is undefined)')

    def match_exact(self, lookup, rank=None, strict_genus_matching=True):  # pylint: disable=too-many-branches,too-many-return-statements
        if lookup is None:
            return MatchObject(lookup=lookup)

        if rank and rank not in  ['epithet', 'genus']:
            raise ValueError("Rank can only be 'epithet', 'genus' or None for regular matching")

        c_lookup = fully_clean(lookup).lower()

        if len(c_lookup)==0:
            return MatchObject(lookup=lookup)

        if rank=='epithet':
            if c_lookup not in self.epithet_lookup:
                return MatchObject(lookup=lookup)

            item = self.epithet_lookup[c_lookup]
            match = EpithetObject(epithet=item['epithet'],
                                  infraspecific_epithet=item['infraspecific_epithet'],
                                  taxon_rank='epithet', 
                                  source=item['source'])
            return MatchObject(lookup=lookup, match=match, score=1)

        if rank=='genus':
            if strict_genus_matching and lookup[0].islower():
                return MatchObject(lookup=lookup)

            if c_lookup not in self.genus_lookup:
                return MatchObject(lookup=lookup)

            item = self.genus_lookup[c_lookup]
            match = NameObject(canonical_name=item['canonical_name'],
                               genus=item['genus'],
                               authorship=item['authorship'],
                               taxon_rank=item['taxon_rank'],
                               source=item['source'])
            return MatchObject(lookup=lookup, match=match, score=1)

        if c_lookup not in self.canonical_lookup:
            return MatchObject(lookup=lookup)

        item = self.canonical_lookup[c_lookup]

        if item['taxon_rank']=='genus' and strict_genus_matching and lookup[0].islower():
            return MatchObject(lookup=lookup)

        match = NameObject(
            canonical_name=item['canonical_name'],
            genus=item['genus'],
            epithet=item['epithet'],
            infraspecific_epithet=item['infraspecific_epithet'],
            authorship=item['authorship'],
            taxon_rank=item['taxon_rank'],
            source=item['source'])

        return MatchObject(lookup=lookup, match=match, score=1, authorships=item['authorships'])

    def match_fuzzy(self, lookups, include_epithets=False, score_cutoff=None):

        def chunks(lst, n):
            """Yield successive n-sized chunks from lst."""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        names = list(self.canonical_lookup.keys())
        if include_epithets:
            names += list(self.epithet_lookup.keys())

        if isinstance(lookups, str):
            lookups = [lookups]

        matched_names = []

        if self.multiprocessing:

            def match_fuzzy_callback(result):
                self.logger.debug(f"match_fuzzy_callback called ({len(result)} results)")
                matched_names.extend(result)

            proc_num = len(os.sched_getaffinity(0))
            self.logger.debug(f"Fuzzy matching # processes: {proc_num}")
            with Pool(processes=proc_num) as pool:
                for chunk in chunks([fully_clean(x) for x in lookups], ceil(len(lookups)/proc_num)):
                    pool.apply_async(match_fuzzy_lookup, args=(chunk, names,), 
                                                        callback=match_fuzzy_callback)
                pool.close()
                pool.join()
        else:

            matched_names.extend(match_fuzzy_lookup(lookups=[fully_clean(x) for x in lookups], names=names))

        results = []
        for lookup, name in matched_names:
            exact_match = self.match_exact(name)
            # exact_match can be None if the match is a genus but the lookup
            # doesn't start with a capital letter   
            if exact_match.match:
                score = self.levenshtein_ratio_normalized(str1=lookup,
                            str2=exact_match.match.canonical_name.lower(),
                            score_cutoff=score_cutoff)
                if score==0:
                    continue
                score = round(score, 2)
                self.logger.debug('Option: %s --> %s (%s)', lookup, exact_match.match, score)
                results.append(MatchObject(lookup=lookup,
                                           match=exact_match.match,
                                           score=score,
                                           authorships=exact_match.authorships))

        return results

    @staticmethod
    def levenshtein_ratio_normalized(str1, str2, score_cutoff):
        return Levenshtein.ratio(str1, str2, score_cutoff=score_cutoff)

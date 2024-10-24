import json
import logging
import os
import pickle
import polars as pl
import polars_distance as pld
import sqlite3
from Levenshtein import ratio as levenshtein_ratio
from math import ceil
from multiprocessing import Pool
from objects import (NameObject, EpithetObject, MatchObject)
from pathlib import Path
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
                 force_names_reload = False,
                 multiprocessing = True,
                 pickle_file = None,
                 sources_sort_order = None
                 ) -> None:

        self.logger = logger if logger else logging.getLogger()
        self.force_names_reload = force_names_reload
        self.multiprocessing = multiprocessing

        if names_database is None:
            if pickle_file is None:
                raise ValueError('Need names database or names cache pickle file')
            if self.force_names_reload:
                raise ValueError('Cannot reload names without database')
            self.logger.info('No database, using cached names')
            self.conn = None
        else:
            if not Path(names_database).exists():
                raise FileNotFoundError('Database \'%s\' does not exist' % names_database)
            self.conn = self.connect_db(names_database)

        self.pickle_file = pickle_file
        self.sources_sort_order = sources_sort_order

        self.canonical_lookup = {}
        self.full_name_lookup = {}
        self.epithet_lookup = {}
        self.genus_lookup = {}
        self.load_names(names_database=names_database)
        self.load_genera()

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
        with open(self.pickle_file, 'wb') as file:
            pickle.dump(data, file)

    def load_names(self, names_database):
        if (names_database is None or not self.force_names_reload) \
        and self.pickle_file \
        and Path(self.pickle_file).is_file():
            names = self.load_pickle()

            self.canonical_lookup = names['canonicals']
            self.full_name_lookup = names['full_names']
            self.epithet_lookup = names['epithets']

            self.logger.info('Read %s canonical names from cache',
                             format(len(self.canonical_lookup), ','))
            self.logger.info('Read %s full names from cache',
                             format(len(self.full_name_lookup), ','))
            self.logger.info('Read %s epithets from cache',
                             format(len(self.epithet_lookup), ','))
            return

        self.logger.debug('Reading names from database')

        def dict_factory(cursor, row):
            d = {}
            for idx, col in enumerate(cursor.description):
                d[col[0]] = row[idx]
            return d

        self.conn.row_factory = dict_factory
        cur = self.conn.cursor()
        if self.sources_sort_order:
            order = "order by case source " + \
                    " ".join([f"when {x!r} then {self.sources_sort_order[x]}"
                            for x in self.sources_sort_order.keys()]) + \
                    " end asc"
        else:
            order = ""

        cur.execute(f"select canonical_name, genus, epithet, infraspecific_epithet, \
                      authorship, taxon_rank, source \
                      from name_lookup \
                      where canonical_name is not null \
                      and genus is not null \
                      and taxon_rank in ('genus', 'species', 'subspecies', 'form', 'variety') \
                      {order}")

        for record in cur.fetchall():
            canonical = fully_clean(record['canonical_name']).lower()
            full_name = fully_clean(f"{record['canonical_name']} {record['authorship']}").strip().lower()
            epithet = fully_clean(f"{record['epithet']} {record['infraspecific_epithet']  if record['infraspecific_epithet'] else ''}").lower()

            if canonical not in self.canonical_lookup:
                self.canonical_lookup[canonical] = record | {'full_names': []}

            if full_name not in self.full_name_lookup and full_name != canonical:
                self.full_name_lookup[full_name] = record.copy()

            if full_name not in self.canonical_lookup[canonical]['full_names']:
                self.canonical_lookup[canonical]['full_names'].append(full_name)

            self.epithet_lookup[epithet] = { 'epithet': record['epithet'],
                                             'infraspecific_epithet': record['infraspecific_epithet'],
                                             'taxon_rank': record['taxon_rank'],
                                             'source': record['source'] }

        self.logger.info('Loaded %s canonical names' % format(len(self.canonical_lookup), ','))
        self.logger.info('Loaded %s full names' % format(len(self.full_name_lookup), ','))
        self.logger.info('Loaded %s epithets' % format(len(self.epithet_lookup), ','))

        if self.pickle_file:
            self.save_pickle({'canonicals': self.canonical_lookup,
                              'full_names': self.full_name_lookup,
                              'epithets': self.epithet_lookup})
            self.logger.info('Saved names cache')
        else:
            self.logger.info('Cannot save names cache (pickle file is undefined)')

    def load_genera(self):
        self.genus_lookup = {x: self.canonical_lookup[x] for x in self.canonical_lookup.keys()
                            if self.canonical_lookup[x]['taxon_rank']=='genus'}

        self.logger.info('Loaded %s genera' % format(len(self.genus_lookup), ','))

    def match_exact(self, lookup, rank=None, strict_genus_matching=True):  # pylint: disable=too-many-branches,too-many-return-statements
        if lookup is None:
            return MatchObject(lookup=lookup)

        if rank and rank not in  ['epithet', 'genus']:
            raise ValueError("Rank can only be 'epithet', 'genus' or None for regular matching")

        if rank and rank == 'genus' and not self.genus_lookup:
            raise ValueError("Rank can only be 'genus' if genus_lookup is True")

        # same preprocessing as keys of the lookup dicts
        c_lookup = fully_clean(lookup).lower()

        if len(c_lookup)==0:
            return MatchObject(lookup=lookup)

        if rank=='epithet' and c_lookup not in self.epithet_lookup:
            return MatchObject(lookup=lookup)

        if rank=='genus' and c_lookup not in self.genus_lookup:
            return MatchObject(lookup=lookup)

        if not rank=='epithet' and c_lookup not in self.canonical_lookup \
            and c_lookup not in self.full_name_lookup:
            return MatchObject(lookup=lookup)

        match = None
        identical_canonicals = []

        if rank=='epithet':
            item = self.epithet_lookup[c_lookup]
            match = EpithetObject(epithet=item['epithet'],
                                  infraspecific_epithet=item['infraspecific_epithet'],
                                  taxon_rank='epithet', 
                                  #taxon_rank=item['taxon_rank'],
                                  source=item['source'])

        else:
            if rank=='genus' and c_lookup in self.genus_lookup:
                item = self.genus_lookup[c_lookup]
            elif c_lookup in self.full_name_lookup:
                item = self.full_name_lookup[c_lookup]
            else:
                item = self.canonical_lookup[c_lookup]

            if strict_genus_matching and lookup[0].islower() and item['taxon_rank']=='genus':
                return MatchObject(lookup=lookup)

            ident_canon = []
            if 'full_names' in item:
                for full_name in item['full_names']:
                    ident_canon.append(self.full_name_lookup[full_name])

            def sort_by_source(x):
                if self.sources_sort_order and x['source'] in self.sources_sort_order:
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

    def match_fuzzy(self, lookups, include_epithets=False, score_cutoff=None):

        def chunks(lst, n):
            """Yield successive n-sized chunks from lst."""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        # names = list(self.canonical_lookup.keys())+list(self.full_name_lookup.keys())
        names = list(self.canonical_lookup.keys())
        if include_epithets:
            names += list(self.epithet_lookup.keys())

        if isinstance(lookups, str):
            lookups = [lookups]

        matched_names = []

        def match_fuzzy_callback(result):
            matched_names.extend(result)

        proc_num = len(os.sched_getaffinity(0)) if self.multiprocessing else 1
        with Pool(processes=proc_num) as pool:
            for lookup in chunks([fully_clean(x) for x in lookups], ceil(len(lookups)/proc_num)):
                pool.apply_async(match_fuzzy_lookup, args=(lookup, names,), 
                                                     callback=match_fuzzy_callback)
            pool.close()
            pool.join()

        results = []
        for lookup, name in matched_names:
            exact_match = self.match_exact(name)
            # exact_match can be None if the match is a genus but the lookup
            # doesn't start with a capital letter
            if exact_match.match:
                score = levenshtein_ratio(lookup, exact_match.match.canonical_name.lower(), 
                                          score_cutoff=score_cutoff)
                if score==0:
                    continue
                score = round(score, 2)
                self.logger.debug('Option: %s --> %s (%s)', lookup, exact_match.match, score)
                results.append(MatchObject(lookup=lookup,
                                           match=exact_match.match,
                                           score=score,
                                           identical_canonicals=exact_match.identical_canonicals))

        return results

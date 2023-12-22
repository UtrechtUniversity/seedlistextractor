import argparse
import sqlite3
import pickle
import logging
import multiprocessing 
from rapidfuzz import process, fuzz
from pathlib import Path

class NameResolver:

    def __init__(self, 
                 names_database=None,
                 force_names_reload=False,
                 no_caching=False) -> None:

        self.config={
            'pickle_file': Path("./pickles/names_pickle"),
            'names_query': 'select scientific_name, full_scientific_name, epithet, taxon_rank from name_lookup'
        }

        self.force_names_reload=force_names_reload
        self.no_caching=no_caching

        if names_database is None:
            logging.info('no database, using cached names')
        else:
            if not Path(names_database).exists():
                raise ValueError('database %s does not exist' % names_database)

        self.names={
            'family': {},
            'genus': {},
            'species': {},
            'species_auth': {},
            'epithet': {}
            }
        
        self.fuzzy_cache=[]
        self.lookups=0
        self.cache_hits=0

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

    def load_names_pickle(self):
        try:
            with open(self.config['pickle_file'], 'rb') as file:
                data=pickle.load(file)
            return data
        except:
            pass

    def save_names_pickle(self, data):
        with open(self.config['pickle_file'], 'wb') as file:
            pickle.dump(data, file)

    def load_names(self, names_database):

        if names_database is None or not self.force_names_reload:
            names=self.load_names_pickle()
            if names:
                self.names={
                    'family': names['family'],
                    'genus': names['genus'],
                    'species': names['species'],
                    'species_auth': names['species_auth'],
                    'epithet': names['epithet']
                }

                logging.info("unpickled %s families" % format(len(self.names['family']), ','))
                logging.info("unpickled %s genera" % format(len(self.names['genus']), ','))
                logging.info("unpickled %s species" % format(len(self.names['species']), ','))
                logging.info("unpickled %s species w/ auth" % format(len(self.names['species_auth']), ','))
                logging.info("unpickled %s epithets" % format(len(self.names['epithet']), ','))

                return

        conn=self.connect_db(names_database)
        cur=conn.cursor()
        cur.execute(self.config['names_query'])

        for row in cur.fetchall():

            if len(row['scientific_name'])==0:
                continue

            if row['taxon_rank'] in ['family']:
                    self.names['family'][row['scientific_name']]=True

            if row['taxon_rank'] in ['genus']:
                    self.names['genus'][row['scientific_name']]=True

            if row['taxon_rank'] in ['variety', 'species', 'form', 'subspecies', 'prole', 'forma', 'grex']:
                self.names['species'][row['scientific_name']]=True

                if len(row['full_scientific_name'])>0:
                    self.names['species_auth'][row['full_scientific_name']]=True

                if row['epithet'] and len(row['epithet'])>0:
                    self.names['epithet'][row['epithet']]=True

        logging.info("loaded %s families" % format(len(self.names['family']), ','))
        logging.info("loaded %s genera" % format(len(self.names['genus']), ','))
        logging.info("loaded %s species" % format(len(self.names['species']), ','))
        logging.info("loaded %s species w/ auth" % format(len(self.names['species_auth']), ','))
        logging.info("loaded %s epithets" % format(len(self.names['epithet']), ','))

        self.save_names_pickle({
            'family': self.names['family'],
            'genus': self.names['genus'],
            'species': self.names['species'],
            'species_auth': self.names['species_auth'],
            'epithet': self.names['epithet'],
        })

        logging.info("saved pickle")

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

    def run_lookup_queue(self, task_queue, return_dict, rank, score_cutoff=90):
        while not task_queue.empty():
            lookup, meta=task_queue.get()

            r=process.extractOne(lookup, self.names_select, scorer=fuzz.QRatio, score_cutoff=score_cutoff)

            if r is None and rank!='species':
                match, score=None, 0
            elif r is None and rank=='species':
                match, score=lookup, 0
            else:
                match, score, _=r

            if rank=='species':
                r={}
                for name in [k for k, _ in self.names['species_auth'].items() if match in k]:
                    r[name]=fuzz.QRatio(name, lookup)

                m=max(r, key=r.get, default=-1)
                if len(r)>0 and r[m]>score and r[m]>score_cutoff:
                    match, score=(m, r[m])
                else:
                    match=None if score==0 else match

            score /= 100
        
            return_dict[lookup]=((match, score), meta)
            
        return True

    def match_fuzzy(self, lookup, rank, assume_correct_start=1):

        assert rank in self.names, f"unknown rank '{rank}'"

        if assume_correct_start is not None:
            assert isinstance(assume_correct_start, int), f"'{assume_correct_start}' is not an int"

        if isinstance(lookup, str):
            lookup=[(lookup, None)]

        if isinstance(lookup, tuple):
            lookup=[lookup]

        lookup=[x if isinstance(x, tuple) else (x, None) for x in lookup]

        self.lookups += len(lookup)

        cached=[]
        if not self.no_caching:
            for item, meta in lookup:
                results=[x for x in self.fuzzy_cache if x[0]==item.lower()]
                if len(results)>0:
                    cached.append((results[0], meta))
                    self.cache_hits += 1

        spaces=set([name.count(' ') for name, _ in lookup])
        self.names_select={k:v for k, v in self.names[rank].items() if k.count(' ') in spaces}

        if assume_correct_start is not None:
            firsts=set([name[:assume_correct_start].lower() for name, _ in lookup])
            self.names_select={k:v for k, v in self.names_select.items() if k[:assume_correct_start] in firsts}

        self.names_select=set(list(self.names_select.keys()))

        queue=multiprocessing.Queue()

        for item in lookup:
            name, meta=item if isinstance(item, tuple) else (item,)
            if len(name)==0:
                continue
            if len([c_name for c_name, _ in cached if c_name==name.lower()])==0:
                queue.put((item[0].lower(), meta))

        manager=multiprocessing.Manager()
        return_dict=manager.dict()
        processes=[]

        score_cutoff=90

        for _ in range(multiprocessing.cpu_count()-1):
            p = multiprocessing.Process(target=self.run_lookup_queue, args=(queue, return_dict, rank, score_cutoff))
            processes.append(p)
            p.start()

        for p in processes:
            p.join()

        if not self.no_caching:
            for key, val in return_dict.items():
                self.fuzzy_cache.append((key.lower(), val))

        for item in cached:
            return_dict[item[0]]=item[1]

        logging.debug("%s: performed %s lookups, %s from cache" % (rank, self.lookups, self.cache_hits))

        return return_dict
    
    def fuzzy_match_single(self, lookup, rank, assume_correct_start=0, score_cutoff=0):

        if score_cutoff < 1:
            score_cutoff *= 100

        lookup=lookup.lower()

        self.names_select={k:v for k, v in self.names[rank].items() if k.count(' ')==lookup.count(' ')}

        if assume_correct_start is not None:
            self.names_select={k:v for k, v in self.names_select.items() if k[:assume_correct_start]==lookup[:assume_correct_start]}

        self.names_select=set(list(self.names_select.keys()))

        r=process.extractOne(lookup, self.names_select, scorer=fuzz.QRatio, score_cutoff=score_cutoff)

        if r is None and rank!='species':
            return (None, 0)

        if r is None and rank=='species':
            match, score=lookup, 0
        else:
            match, score, _=r

        if rank=='species':
            r={}
            for name in [k for k, _ in self.names['species_auth'].items() if match in k]:
                r[name]=fuzz.QRatio(name, lookup)

            m=max(r, key=r.get, default=-1)
            if len(r)>0 and r[m]>score and r[m]>score_cutoff:
                return (m, r[m])
            else:
                return (match, score)
        
        return (match, score)


if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('-n','--name', required=True)
    parser.add_argument('-r','--rank', required=True)
    parser.add_argument('-d','--names-database')
    parser.add_argument('-f','--force-names-reload', action='store_true', default=False)
    parser.add_argument('--no-caching', action='store_true', default=False)
    parser.add_argument('--debug', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    nres=NameResolver(names_database=args.names_database,
                      force_names_reload=args.force_names_reload,
                      no_caching=args.no_caching)

    # print("exact:", nres.match_exact(lookup=args.name,rank=args.rank))
    # print("fuzzy:", nres.match_fuzzy(lookup=args.name,rank=args.rank))
    print(nres.fuzzy_match_single(lookup=args.name, rank=args.rank, score_cutoff=90))

import argparse
import sqlite3
import pickle
import logging
from rapidfuzz.distance import DamerauLevenshtein, OSA
from pathlib import Path
from numpy.linalg import norm
from timer import Timer
from pprint import pprint
import numpy as np
from concurrent.futures import ProcessPoolExecutor


class NameResolver:

    all_names_query="select * from name_lookup"

    def __init__(self, 
                 name_database=None,
                 fuzzy_name_match=True,
                 force_name_reload=False,
                 no_caching=False) -> None:

        self.config={
            'pickle_file': Path("./pickles/names_pickle")
        }

        self.fuzzy_name_match=fuzzy_name_match
        self.force_name_reload=force_name_reload
        self.no_caching=no_caching

        if name_database is None:
            logging.info("no database, using cache only")
        else:
            if not Path(name_database).exists():
                raise ValueError("database %s does not exist" % name_database)

        if self.fuzzy_name_match:
            self.set_vocab_map()
            self.fuzzy_cache=[]

        self.names={'family': [],'genus': [],'species': [],'epithet': [] }

        self.timer=Timer()
        self.timer.start()

        self.load_names(name_database=name_database)


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

    def load_names(self, name_database):

        if name_database is None or not self.force_name_reload:
            names=self.load_names_pickle()
            if names:
                self.names={
                    'family': names['family'],
                    'genus': names['genus'],
                    'species': names['species'],
                    'epithet': names['epithet']
                }
                logging.info("unpickled %s families" % format(len(self.names['family']), ','))
                logging.info("unpickled %s genera" % format(len(self.names['genus']), ','))
                logging.info("unpickled %s species" % format(len(self.names['species']), ','))
                logging.info("unpickled %s epithets" % format(len(self.names['epithet']), ','))
                self.timer.checkpoint(label='loaded names')
                return

        species=[]

        conn=self.connect_db(name_database)
        cur=conn.cursor()
        cur.execute(self.all_names_query)
        for row in cur.fetchall():
            if len(row['scientific_name'])>0:
                if row['taxon_rank'] in ['family']:
                    self.names['family'].append(row['scientific_name'])

                if row['taxon_rank'] in ['genus']:
                    self.names['genus'].append(row['scientific_name'])

            if row['taxon_rank'] in ['variety', 'species', 'form', 'subspecies', 'prole', 'forma', 'grex']:
                if len(row['scientific_name'])>0:
                    species.append(row['scientific_name'])

                if len(row['full_scientific_name'])>0:
                    species.append(row['full_scientific_name'])

                if row['epithet'] and len(row['epithet'])>0:
                    self.names['epithet'].append(row['epithet'])

        self.names['family']=set(sorted(self.names['family'], key=len, reverse=True))
        self.names['genus']=set(sorted(self.names['genus'], key=len, reverse=True))
        species=set(sorted(species, key=len, reverse=True))
        self.names['epithet']=set(sorted(self.names['epithet'], key=len, reverse=True))

        logging.info("loaded %s families" % format(len(self.names['family']), ','))
        logging.info("loaded %s genera" % format(len(self.names['genus']), ','))
        logging.info("loaded %s species" % format(len(species), ','))
        logging.info("loaded %s epithets" % format(len(self.names['epithet']), ','))

        self.names['species']=self.vectorize_list(names_list=species)
        logging.info("calculated species vectors")

        self.save_names_pickle({
            'family': self.names['family'],
            'genus': self.names['genus'],
            'species': self.names['species'],
            'epithet': self.names['epithet'],
        })

        logging.info("saved pickle")

    
    def set_vocab_map(self):
        vocab=[chr(x) for x in [32]+list(range(97, 123))]
        self.vocab_map={}
        for i, token in enumerate(sorted(vocab)):
            self.vocab_map[token] = i

    def vectorize(self, name):
        encoded=[]
        for token in list(name.lower()):
            encoded.append(self.vocab_map[token])
        return encoded

    def vectorize_list(self, names_list):
        vectors=[]
        i = 0 
        for item in names_list:
            vectors.append((item, self.vectorize(item)))
            i += 1
            if i % 50000==0:
                logging.debug("vectorized %s names" % i)
        return vectors

    def fuzzy_search_vector(self, lookup, names_list):

        if len(lookup)==0:
            return (None, 0)

        lookup=lookup.lower()

        if not self.no_caching:
            cached=[x for x in self.fuzzy_cache if x[0]==lookup]
            if len(cached)>0:
                result=cached[0][1]
                logging.debug("%s, %s, %s (cached)" % (lookup, result[0], result[1]))
                return (result[0], result[1]/100)

        results=[]
        encoded=self.vectorize(lookup)
        
        for name, vector, _ in [(x[0], x[1], x[2] if 2 in x else None) for x in names_list if x[0].count(' ')==lookup.count(' ')]:
            # for performance' sake assuming there's never typo's in first character
            # also assuming same number of name parts
            if lookup[0]==name[0]:
                a=np.array(encoded + [self.vocab_map[' ']] * (max(len(encoded), len(vector))-len(encoded)))
                b=np.array(vector + [self.vocab_map[' ']] * (max(len(encoded), len(vector))-len(vector)))
                results.append((name, np.dot(a,b)/(norm(a)*norm(b))))

        if len(results)==0:
            return (None, 0)

        best=sorted(results, key=lambda x: -x[1])[0]

        #TODO: magic number
        if best[1]>0.85:
            logging.debug("%s, %s, %s" % (lookup, best[0], best[1]))
            self.fuzzy_cache.append((lookup, (best[0], best[1])))
            return (best[0], best[1])

        return 

    def fuzzy_search_damlev(self, lookup, names_list):
        lookup=lookup.lower()
        results=[]
        for name, vector in [x for x in names_list if x[0].count(' ')==lookup.count(' ')]:
            # for performance' sake assuming there's never typo's in first character
            # also assuming same number of name parts
            if lookup[0]==name[0]:
                score=DamerauLevenshtein.normalized_similarity(lookup, name)
                results.append((name, vector, score))

        candidates=[]

        if len(results)==0:
            return candidates

        results=sorted(results, key=lambda x: -x[2])

        for item in results:
            if item[2]>0.65:
                candidates.append(item)

        return candidates

    def fuzzy_search(self, lookup, names_list):

        if len(lookup)==0:
            return (None, 0)

        lookup=lookup.lower()

        if not self.no_caching:
            cached=[x for x in self.fuzzy_cache if x[0]==lookup]
            if len(cached)>0:
                result=cached[0][1]
                logging.debug("%s, %s, %s (cached)" % (lookup, result[0], result[1]))
                return (result[0], result[1]/100)

        candidates=self.fuzzy_search_damlev(lookup=lookup, names_list=names_list)
        result=self.fuzzy_search_vector(lookup=lookup, names_list=candidates)

        #TODO: magic number
        if result[1]>0.95:
            logging.debug("%s, %s, %s" % (lookup, result[0], result[1]))
            self.fuzzy_cache.append((lookup, result))
            return result
        
        return (None, 0)

    def match_exact(self, lookup, rank):

        if len(lookup)==0:
            return (None, 0)

        name_list=None

        if not lookup[0].isupper() and rank=='epithet': 
            name_list=self.names['epithet']
        elif lookup[0].isupper() and rank!='epithet' and rank in self.names:
            name_list=self.names[rank]

        if not name_list:
            return (None, 0)
        
        # if lookup.lower() in name_list:
        results=[x for x in name_list if x[0]==lookup.lower()]

        self.timer.checkpoint(label='exact')


        if len(results)>0:
            return (results[0], 1)

        return (None, 0)

    @staticmethod
    def cleaver(l, n):
        c_size=len(l)//n + 1
        for i in range(0, n):
            yield l[i*c_size:(i+1)*c_size]

    def match_fuzzy(self, lookup, rank):
        if not self.fuzzy_name_match:
            return (None, 0)

        if rank in self.names:

            # namelist=random.shuffle(self.names[rank])

            self.timer.checkpoint(label='--------------')

            _=self.fuzzy_search(lookup=lookup, names_list=self.names[rank])
            print(_)
            self.timer.checkpoint(label='fuzzy_search')

            _=self.fuzzy_search_vector(lookup=lookup, names_list=self.names[rank])
            print(_)
            self.timer.checkpoint(label='fuzzy_search_vector')

            _=self.fuzzy_search_damlev(lookup=lookup, names_list=self.names[rank])
            print(_[0])
            self.timer.checkpoint(label='fuzzy_search_damlev')

        # return _
    

if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('-n','--name', required=True)
    parser.add_argument('-r','--rank', required=True)
    parser.add_argument('-d','--name-database')
    parser.add_argument('-f','--force-name-reload', action='store_true', default=False)
    parser.add_argument('--no-caching', action='store_true', default=False)
    parser.add_argument('--debug', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    nres=NameResolver(name_database=args.name_database,
                      force_name_reload=args.force_name_reload,
                      no_caching=args.no_caching)

    # print(nres.match_exact(lookup=args.name,rank=args.rank))
    print(nres.match_fuzzy(lookup=args.name,rank=args.rank))

    pprint(sorted(nres.timer.get_checkpoints(), key=lambda x: x['key']), width=100, sort_dicts=False)

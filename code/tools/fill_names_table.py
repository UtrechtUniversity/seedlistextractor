import argparse
import re
import logging
import sqlite3
from pathlib import Path

class WFO:
    query = """
        select
            lower(taxonRank) as taxon_rank,
            lower(scientificName) as scientific_name,
            lower(scientificName||' '||scientificNameAuthorship) as full_scientific_name,
            lower(specificEpithet||' '||infraspecificEpithet) as epithet 
        from WFO_classification
        """
    ranks = {
        'family': ['family', 'subfamily', ],
        'genus': ['genus', 'subgenus', ],
        'species': ['species', ],
        'subspecies': ['subspecies', ],
        'form': ['form', 'subform', ],
        'variety': ['variety','subvariety', ],
        'prole': ['prole', ],
    }

class WCVP: 
    query = """
        select 
            lower(taxonrank) as taxon_rank, 
            lower(scientfiicname) as scientific_name, 
            lower(scientfiicnameauthorship) as full_scientific_name,
            lower(specificepithet||' '||infraspecificepithet) as epithet 
        from wcvp_taxon
        """
    ranks = {
        'genus': ['genus', ],
        'species': ['species', ],
        'subspecies': ['subspecies', 'nothosubsp.', ],
        'form': ['form', 'subform', 'nothof.', ],
        'variety': ['variety','subvariety', 'convariety', 'nothovar.', 'provar.' ],
        'prole': ['proles', 'subproles' ],
    }

class IPNI:
    query = """
        select 
            lower(col_rank) as taxon_rank, 
            lower(col_scientificName) as scientific_name, 
            lower(col_scientificName||' '||col_authorship) as full_scientific_name,
            null as epithet 
        from IPNI_Name
        """
    ranks = {
        'family': ['[infrafam.unranked]', 'fam.', 'nothof.', 'subf.', 'subfam.', ],
        'genus': ['[infragen.]', '[infragen.grex]', '[infragen.unranked]', '[infragen]', 'gen.', '"gen. ser."', 'infragen.grex', 'microgen.', 'nothosubgen.', 'subgen.', ],
        'species' : ['agamosp.', '[infrasp.unranked]', 'spec.', ],
        'subspecies': ['subsp.', 'subspec.', 'subsubforma', 'nothosubsp.', ],
        'forma': ['f.', 'forma', ],
        'variety': ['agamovar.', 'subsubvar.', 'subvar.', 'var.', 'nothovar.', 'provar.', ],
        'grex': ['grex', 'grex_sect.', 'nothogrex', ],
        'prole': ['prol.', 'proles', ],
    }

class CoL:
    query = """
        select 
            lower(col_rank) as taxon_rank, 
            lower(col_scientificName) as scientific_name, 
            lower(col_scientificName||' '||col_authorship) as full_scientific_name,
            lower(col_specificEpithet||' '||col_infraspecificEpithet) as epithet 
        from
            CoL_NameUsage
        where
            col_code = 'botanical'
        """
    ranks = {
        'family': ['family', 'subfamily', 'epifamily', 'superfamily',  ],
        'genus': ['genus', 'subgenus', ],
        'species': ['species', '"species aggregate"', ],
        'subspecies': ['subspecies', ],
        'form': ['form', 'subform', ],
        'variety': ['variety','subvariety', ],
        'prole': ['proles' ],
    }



class FillNamesTable:

    name_abbr=['aff', 'agg', 'ambig', 'cl', 'f', 'gx',
               'sensu lato', 'ssp', 'sp', 'subsp', 'subvar',
               'var', 'convar', ]

    def __init__(self, name_database) -> None:
        db = Path(name_database)
        if not db.exists():
            raise ValueError("database %s does not exist" % name_database)

        self.conn=self.connect_db(name_database)
        logging.debug("connected to '%s'" % name_database)

    @staticmethod
    def connect_db(db_file):
        conn=None
        try:
            conn=sqlite3.connect(db_file)
            conn.row_factory=sqlite3.Row
        except Exception as e:
            print(e)

        return conn

    def run(self, sources, clear_existing=True):

        def remove_abbreviations(name):
            return ' '.join([x for x in name.split() if x not in self.name_abbr])

        def cleanup(raw):
            if raw is None:
                return ""
            return re.sub(r'(\s){1,}', ' ', re.sub(r'[^a-z ]', '', raw)).strip()

        if not isinstance(sources, list):
            sources=[sources]

        cur=self.conn.cursor()
        cur.row_factory = sqlite3.Row

        cur.execute("DROP TABLE IF EXISTS tmp_name_lookup")
        cur.execute("CREATE TABLE tmp_name_lookup (scientific_name varchar(128), full_scientific_name varchar(256), epithet varchar(128), taxon_rank varchar(32))")
        cur.execute("CREATE UNIQUE INDEX full_scientific_name_idx on tmp_name_lookup(full_scientific_name)")

        if clear_existing:
            cur.execute("DROP TABLE IF EXISTS name_lookup")
            cur.execute("CREATE VIRTUAL TABLE name_lookup USING FTS5(scientific_name, full_scientific_name, epithet, taxon_rank)")
            logging.info("recreated table name_lookup")
       
        insert_query = """
            insert or ignore into tmp_name_lookup
                (scientific_name, full_scientific_name, epithet, taxon_rank)
            values
                (?, ?, ?, ?)
        """

        for source in sources:

            cur.execute(source.query)
            rows = cur.fetchall()

            n=0
            records=[]
            for row in rows:

                rank=[k for k, v in source.ranks.items() if row['taxon_rank'] in v ]
                if len(rank)==0:
                    continue

                rank=rank[0]

                # (scientific_name, full_scientific_name, epithet, taxon_rank)
                records.append((
                    remove_abbreviations(cleanup(row['scientific_name'])),
                    remove_abbreviations(cleanup(row['full_scientific_name'])),
                    None if len(cleanup(row['epithet']))==0 else cleanup(row['epithet']),
                    rank
                ))

                if len(records)==50000:
                    cur.executemany(insert_query, records)
                    n += len(records)
                    records=[]
                    logging.debug("%s: %s records" % (source.__name__, f'{n:>9,}'))

            if len(records)>0:
                cur.executemany(insert_query.format(table='tmp_name_lookup'), records)
                n += len(records)
            
            self.conn.commit()
            logging.info("%s: %s records" % (source.__name__, f'{n:>9,}'))


        cur.execute("INSERT INTO name_lookup SELECT * FROM tmp_name_lookup")
        cur.execute("DROP TABLE IF EXISTS tmp_name_lookup")
        self.conn.commit()

        cur.execute("SELECT count(*) as total FROM name_lookup")
        row=cur.fetchone()

        logging.info("total: %s unique records" % f'{row["total"]:>9,}')

if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('--name-database', required=True)
    parser.add_argument('--clear-existing', action='store_true', default=False)
    parser.add_argument('--debug', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    fnt=FillNamesTable(name_database=args.name_database)
    fnt.run(sources=[WFO, WCVP, IPNI, CoL], clear_existing=args.clear_existing)

import argparse
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

@dataclass
class PlantList:
    query = """
        select
            scientificName as canonical_name,
            genus as genus,
            specificEpithet as epithet,
            infraspecificEpithet as infraspecific_epithet,
            scientificNameAuthorship as authorship,
            lower(taxonRank) as taxon_rank
        from
            PlantList
        """
    table_name = 'PlantList'
    ranks = {
        'species': ['species', ],
        'subspecies': ['subspecies', ],
        'form': ['f.', ],
        'variety': ['variety', 'var', ],
    }

@dataclass
class GBIF:
    query = """
        select
            canonicalName as canonical_name,
            genericName as genus,
            specificEpithet as epithet,
            infraspecificEpithet as infraspecific_epithet,
            scientificNameAuthorship     as authorship,
            lower(taxonRank) as taxon_rank
        from
            GBIF_Taxon
        where
            kingdom = 'Plantae'
            and taxonRank != 'unranked'
        """
    table_name = 'GBIF_Taxon'
    ranks = {
        'family': ['family' ],
        'genus': ['genus', ],
        'species': ['species', ],
        'subspecies': ['subspecies', ],
        'form': ['form', ],
        'variety': ['variety', ],
    }

@dataclass
class WFO:
    query = """
        select
            scientificName as canonical_name,
            genus as genus,
            specificEpithet as epithet,
            infraspecificEpithet as infraspecific_epithet,
            scientificNameAuthorship as authorship,
            lower(taxonRank) as taxon_rank
        from WFO_classification
        """
    table_name = 'WFO_classification'
    ranks = {
        'family': ['family', 'subfamily', ],
        'genus': ['genus', 'subgenus', ],
        'species': ['species', ],
        'subspecies': ['subspecies', ],
        'form': ['form', 'subform', ],
        'variety': ['variety','subvariety', ],
        'prole': ['prole', ],
    }

@dataclass
class WCVP: 
    query = """
        select 
            scientfiicname as canonical_name,
            genus as genus,
            specificepithet as epithet,
            infraspecificepithet as infraspecific_epithet,
            scientfiicnameauthorship as authorship,
            lower(taxonrank) as taxon_rank
        from wcvp_taxon
        """
    table_name = 'wcvp_taxon'
    ranks = {
        'genus': ['genus', ],
        'species': ['species', ],
        'subspecies': ['subspecies', 'nothosubsp.', ],
        'form': ['form', 'subform', 'nothof.', ],
        'variety': ['variety','subvariety', 'convariety', 'nothovar.', 'provar.' ],
        'prole': ['proles', 'subproles' ],
    }

@dataclass
class IPNI:
    query = """
        select 
            `col:scientificName` as canonical_name,
            '' as genus,
            '' as epithet,
            '' as infraspecific_epithet,
            `col:authorship` as authorship,
            lower(`col:rank`) as taxon_rank
        from IPNI_Name
        """
    table_name = 'IPNI_Name'
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

@dataclass
class CoL:
    query = """
        select 
            `col:scientificName` as canonical_name,
            `col:genericName` as genus,
            `col:specificEpithet` as epithet,
            `col:infraspecificEpithet` as infraspecific_epithet,
            `col:authorship` as authorship,
            lower(`col:rank`) as taxon_rank
        from
            CoL_NameUsage
        where
            `col:code` = 'botanical'
        """
    table_name = 'CoL_NameUsage'
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
        logging.debug("Connected to '%s'" % name_database)

    @staticmethod
    def connect_db(db_file):
        conn=None
        try:
            conn=sqlite3.connect(db_file)
            conn.row_factory=sqlite3.Row
        except Exception as e:
            print(e)

        return conn

    def run(self, 
            sources, 
            delete_per_source=False,
            drop_source_tables=False):

        def preprocess_canonical(name):
            # replacing isolated x's with hybrid symbol ×
            return re.sub(r'\s{1}(x|X)\s{1}', ' × ', name).strip()

        if not isinstance(sources, list):
            sources=[sources]

        cur=self.conn.cursor()
        cur.row_factory = sqlite3.Row

        cur.execute("DROP TABLE IF EXISTS tmp_name_lookup")
        cur.execute("CREATE TABLE tmp_name_lookup (canonical_name varchar(128), genus varchar(64), epithet varchar(64), infraspecific_epithet varchar(64), authorship varchar(128), taxon_rank varchar(32), source varchar(16))")
        # cur.execute("CREATE UNIQUE INDEX canonical_name_authorship on tmp_name_lookup(canonical_name, authorship)")
        cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS name_lookup USING FTS5(canonical_name, genus, epithet, infraspecific_epithet, authorship, taxon_rank, source)")

        if not delete_per_source:
            cur.execute("delete from name_lookup")
            logging.info("Deleted all records")

        table_check_query = "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?"
        drop_query = "drop table if exists {table_name}"
        delete_query = "delete from name_lookup where source = ?"
        insert_query = """
            insert or ignore into tmp_name_lookup
                (canonical_name, genus, epithet, infraspecific_epithet, authorship, taxon_rank, source)
            values
                (?, ?, ?, ?, ?, ?, ?)
        """

        for source in sources:
            cur.execute(table_check_query, [source.table_name])
            row = cur.fetchone()
            if not row:
                logging.info("Skipping %s (source table '%s' does not exist)" % (source.__name__, source.table_name))
                continue

            if delete_per_source:
                cur.execute(delete_query, [source.__name__])
                logging.info("%s: deleted records" % source.__name__)
            cur.execute(source.query)
            rows = cur.fetchall()

            n=0
            records=[]
            for row in rows:

                rank=[k for k, v in source.ranks.items() if row['taxon_rank'] in v ]
                if len(rank)==0:
                    continue

                rank=rank[0]

                records.append((
                    preprocess_canonical(row['canonical_name']),
                    None if len(row['genus'])==0 else row['genus'],
                    None if len(row['epithet'])==0 else row['epithet'],
                    None if len(row['infraspecific_epithet'])==0 else row['infraspecific_epithet'],
                    None if len(row['authorship'])==0 else row['authorship'],
                    rank,
                    source.__name__
                ))

                if len(records)==50000:
                    cur.executemany(insert_query, records)
                    n += len(records)
                    records=[]
                    logging.debug("%s:%s records" % (source.__name__, f'{n:>9,}'))

            if len(records)>0:
                cur.executemany(insert_query.format(table='tmp_name_lookup'), records)
                n += len(records)
            
            self.conn.commit()
            logging.info("%s:%s records" % (source.__name__, f'{n:>9,}'))

            if drop_source_tables:
                cur.execute(drop_query.format(table_name=source.table_name))
                logging.info("%s:dropped source table" % source.__name__)

        cur.execute("INSERT INTO name_lookup SELECT * FROM tmp_name_lookup")
        cur.execute("DROP TABLE IF EXISTS tmp_name_lookup")
        self.conn.commit()

        cur.execute("SELECT count(*) as total FROM name_lookup")
        row=cur.fetchone()

        logging.info("total:%s unique records" % f'{row["total"]:>9,}')

if __name__=="__main__":

    parser=argparse.ArgumentParser(prog='python fill_names_table.py',
                                   description="""
    Program loads names from each available source table into central lookup table.
    Existing data for newly loaded sources is deleted automatically.
    If a source table does not exist, existing data is retained.
    """)
    parser.add_argument('--name-database', '-d', required=True, help='path to SQLite database file')
    parser.add_argument('--delete-per-source', action='store_true', default=False,
                        help='only delete existing records for each source you are loading, rather than begin by deleting all existing records.')
    parser.add_argument('--drop-source-tables', action='store_true', default=False, help='drop source database tables after loading')
    parser.add_argument('--debug', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    fnt=FillNamesTable(name_database=args.name_database)
    # skipping IPNI because of lack of higher taxonomy
    fnt.run(sources=[WCVP, WFO, CoL, GBIF, PlantList], 
            delete_per_source=args.delete_per_source, 
            drop_source_tables=args.drop_source_tables)
    

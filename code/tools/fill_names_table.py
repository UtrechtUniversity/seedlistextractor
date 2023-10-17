import re
import logging
import sqlite3
from pathlib import Path


"""
drop TABLE name_lookup;
CREATE VIRTUAL TABLE name_lookup
USING FTS5(scientificName, scientificNameAuthorship, genus, epithet, family, subfamily, tribe, subtribe, full_scientific_name, taxonrank);

"""
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

    def run(self):

        def remove_abbreviations(name):
            return ' '.join([x for x in name.split() if x not in self.name_abbr])

        def cleanup(name):
            return re.sub(r'(\s){1,}',' ',re.sub(r'[^a-z ]','',name))


        cur = self.conn.cursor()
        cur.row_factory = sqlite3.Row

        cur.execute("delete from name_lookup")
        cur.execute("SELECT scientificName, scientificNameAuthorship, family, subfamily, tribe, subtribe, taxonRank FROM classification")

        stmt = """
            insert into name_lookup
                (scientificName, scientificNameAuthorship, genus, epithet, family, subfamily, tribe, subtribe, full_scientific_name, taxonrank)
            values
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = cur.fetchall()
        
        records=[]
        for row in rows:

            sciName = row['scientificName'].lower()
            genus = sciName.split()[0]
            epithet = " ".join(sciName.split()[1:])

            records.append((
                remove_abbreviations(cleanup(sciName)),
                cleanup(row['scientificNameAuthorship'].lower()),
                cleanup(genus),
                cleanup(epithet),
                cleanup(row['family'].lower()),
                cleanup(row['subfamily'].lower()),
                cleanup(row['tribe'].lower()),
                cleanup(row['subtribe'].lower()),
                f"{remove_abbreviations(cleanup(sciName))} {cleanup(row['scientificNameAuthorship'].lower())}",
                row['taxonRank'].lower()
            ))

            if len(records)==50000:
                cur.executemany(stmt, records)
                records=[]

        if len(records)>0:
            cur.executemany(stmt, records)
        
        self.conn.commit()

if __name__=="__main__":

    fnt=FillNamesTable(name_database='/data/seedlists/WFO_backbone.db3')
    fnt.run()


import re
import logging
import sqlite3
from pathlib import Path


"""
CREATE VIRTUAL TABLE name_lookup
USING FTS5(scientificName, scientificNameAuthorship, genus, epithet, family, subfamily, tribe, subtribe, taxonrank);

"""
class FillNamesTable:

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
        cur = self.conn.cursor()
        cur.row_factory = sqlite3.Row

        cur.execute("delete from name_lookup")
        cur.execute("SELECT scientificName, scientificNameAuthorship, family, subfamily, tribe, subtribe, taxonRank FROM classification")

        stmt = "insert into name_lookup(scientificName, scientificNameAuthorship, genus, epithet, family, subfamily, tribe, subtribe, taxonrank) values (?,?,?,?,?,?,?,?,?)"
        rows = cur.fetchall()
        regex=r'[^a-z ]'
        records=[]
        for row in rows:

            sciName = row['scientificName'].lower()
            genus = sciName.split()[0]
            epithet = " ".join(sciName.split()[1:])

            records.append((
                re.sub(regex,'',sciName),
                re.sub(regex,'',row['scientificNameAuthorship'].lower()),
                re.sub(regex,'',genus),
                re.sub(regex,'',epithet),
                re.sub(regex,'',row['family'].lower()),
                re.sub(regex,'',row['subfamily'].lower()),
                re.sub(regex,'',row['tribe'].lower()),
                re.sub(regex,'',row['subtribe'].lower()),
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


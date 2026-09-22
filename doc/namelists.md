# Names database

To recognize names, the [extraction program](../README.md) uses a database with plant names. Names can come from any source or sources, and the more names there are in the database, the better the results of the extraction. This is especially true for synonyms (old names), as most seed lists are historical documents.

## Creating the database

### SQLite database
Create a local [SQLite3 database](https://www.sqlite.org/quickstart.html) for loading the various names databases and creating the lookup table used by the seedlist extractor program. The database file must be accessible to the extractor code at runtime (at least for the initial run).

The lookup table used by the program is automatically created during [loading](#loading) of  datafiles, but if you want to manually create the table, access the SQLite-database, and execute:

```sql
CREATE VIRTUAL TABLE name_lookupa USING FTS5(
  canonical_name,
  genus,
  epithet,
  infraspecific_epithet,
  authorship,
  taxon_rank,
  source
);
```

## Loading source databases

Data files for the various sources have to be downloaded and loaded manually. Below is a list of source databases and their versions that were used during the project for which the software was developed, and how to load them.

### Catalogue of Life

[www.catalogueoflife.org](https://www.catalogueoflife.org/)

Download: [www.catalogueoflife.org/data/download](https://www.catalogueoflife.org/data/download) (type: ColDP Archive)

<!-- Version used: The COL Checklist version 2024-09-25 (5.036.643 records) -->

Only the file `NameUsage.tsv` is required, all other files in the archive can be discarded.
To load names, run in SQLite:
```sql
drop table if exists CoL_NameUsage;
.mode ascii
.separator "\t" "\n"
.import CoL/NameUsage.tsv CoL_NameUsage
```

Quick checks to see if import was succesful:
```sql
-- number of loaded names
SELECT count(*) FROM CoL_NameUsage WHERE `col:code` = 'botanical';

-- 10 random records
SELECT 
    `col:scientificName` as canonical_name,
    `col:genericName` as genus,
    `col:specificEpithet` as epithet,
    `col:infraspecificEpithet` as infraspecific_epithet,
    `col:authorship` as authorship,
    lower(`col:rank`) as taxon_rank
FROM
    CoL_NameUsage
WHERE
    `col:code` = 'botanical'
ORDER BY
    RANDOM()
LIMIT
    10;
```



### GBIF Backbone Taxonomy

[Global Biodiversity Information Facility](https://www.gbif.org/)

Downloading:
+ You need to be logged in with a GBIF-account to be able to download. Registration is free and active immediately.
+ Go to [GBIF Backbone Taxonomy](https://www.gbif.org/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c/download)
+ Beneath 'Source archive', click 'Download'

<!-- Version used: GBIF Backbone Taxonomy; Publication date August 28, 2023 (backbone.zip) (7.696.224 records) -->

Only the file `Taxon.tsv` is required, all other files in the archive can be discarded.
To load names, run in SQLite:
```sql
drop table if exists GBIF_Taxon;
.mode ascii
.separator "\t" "\n"
.import GBIF/Taxon.tsv GBIF_Taxon
```

Quick checks to see if import was succesful:
```sql
-- number of loaded names
SELECT count(*) FROM GBIF_Taxon WHERE kingdom = 'Plantae' AND taxonRank != 'unranked';

-- 10 random records
SELECT
    canonicalName as canonical_name,
    genericName as genus,
    specificEpithet as epithet,
    infraspecificEpithet as infraspecific_epithet,
    scientificNameAuthorship     as authorship,
    lower(taxonRank) as taxon_rank
FROM
    GBIF_Taxon
WHERE
    kingdom = 'Plantae'
AND
    taxonRank != 'unranked'
ORDER BY
    RANDOM()
LIMIT
    10;
```


### The Plant List with literature
[gbif.org/dataset/d9a4eedb-e985-4456-ad46-3df8472e00e8](https://www.gbif.org/dataset/d9a4eedb-e985-4456-ad46-3df8472e00e8) (via GBIF)

Download: [zenodo.org/record/1194673/files/dwca.zip](https://zenodo.org/record/1194673/files/dwca.zip) (DwCA via Zenodo)

<!-- Version used: v1 (Mar 17, 2016); downloaded 2024-02-20 (1.692.926 records) -->

Only the file `taxa.txt` is required, all other files in the archive can be discarded.
To load names, run in SQLite:
```sql
drop table if exists PlantList;
.mode ascii
.separator "\t" "\n"
.import PlantList/taxa.txt PlantList
```

Quick checks to see if import was succesful:
```sql
-- number of loaded names
SELECT count(*) FROM PlantList;

-- 10 random records
SELECT
    scientificName as canonical_name,
    genus as genus,
    specificEpithet as epithet,
    infraspecificEpithet as infraspecific_epithet,
    scientificNameAuthorship as authorship,
    lower(taxonRank) as taxon_rank
FROM
    PlantList
ORDER BY
    RANDOM()
LIMIT
    10;
```


### WCVP: Plants Of The World Online (POWO) backbone

From [Kew Gardens](https://powo.science.kew.org/)

*Backbone: World Checklist of Vascular Plants (WCVP)*

Download (DwCA): [sftp.kew.org/pub/data-repositories/WCVP/wcvp_dwca.zip](http://sftp.kew.org/pub/data-repositories/WCVP/wcvp_dwca.zip)

[Same via GBIF](https://www.gbif.org/dataset/f382f0ce-323a-4091-bb9f-add557f3a9a2)

<!-- Version used: Publication date May 16, 2024 (1.427.810 records) -->

The DwCA contains just one file, `wcvp_taxon.csv`, which can be loaded directly:
```sql
drop table if exists wcvp_taxon;
.mode csv
.separator "|"
.import WCVP/wcvp_taxon.csv wcvp_taxon
```

Quick checks to see if import was succesful:
```sql
-- number of loaded names
SELECT count(*) FROM wcvp_taxon;

-- 10 random records
SELECT
    scientfiicname as canonical_name,
    genus as genus,
    specificepithet as epithet,
    infraspecificepithet as infraspecific_epithet,
    scientfiicnameauthorship as authorship,
    lower(taxonrank) as taxon_rank
FROM
    wcvp_taxon
ORDER BY
    RANDOM()
LIMIT
    10;
```


### WFO: World Flora Online

*World Flora Online Taxonomic Backbone*

[worldfloraonline.org/](https://www.worldfloraonline.org/)

[worldfloraonline.org/downloadData](https://www.worldfloraonline.org/downloadData)

[Latest Static Version](https://files.worldfloraonline.org/files/WFO_Backbone/_WFOCompleteBackbone/WFO_Backbone.zip)

<!-- Version: Taxonomic classification v.2024.06 (Jun. 22, 2024) 103MB (DwCA) (1.497.586 records) -->

To load names, run in SQLite:
```sql
drop table if exists WFO_classification;
.mode tabs
.import WFO/classification.csv WFO_classification
```

Quick checks to see if import was succesful:
```sql
-- number of loaded names
SELECT count(*) FROM WFO_classification;

-- 10 random records
SELECT
    scientificName as canonical_name,
    genus as genus,
    specificEpithet as epithet,
    infraspecificEpithet as infraspecific_epithet,
    scientificNameAuthorship as authorship,
    lower(taxonRank) as taxon_rank
FROM
    WFO_classification
ORDER BY
    RANDOM()
LIMIT
    10;
```

#### _Unused: IPNI (International Plant Names Index)_

https://www.ipni.org/

We are not using IPNI because the records lack higher taxonomy (genus).

<!-- Data via GBIF (DwC-A):

https://www.gbif.org/dataset/046bbc50-cae2-47ff-aa43-729fbf53f7c5

https://hosted-datasets.gbif.org/datasets/ipni.zip

Publication date:       October 31, 2019
Metadata last modified: November 11, 2019 

```bash
drop table IPNI_Name;
.mode tabs
.import IPNI/Name.tsv IPNI_Name
``` -->

## Filling the names table

### Schema

Names from the source database end up in a central lookup table with the following columns:

+ `canonical_name` (example: 'Osteospermum imbricatum var. helichrysoides')
+ `genus` ('Osteospermum')
+ `epithet` ('imbricatum')
+ `infraspecific_epithet` ('helichrysoides')
+ `authorship` ('(DC.) Norl.')
+ `taxon_rank` ('variety')
+ `source` ('WCVP')

The canonical name also forms the unique key, so the order of loading of different databases determines which source is the primary source. Currently, this is WCVP, which is considered the most up to date and complete.

The table, if it doesn't exist, is automatically created when you run the `fill_names_table` script described below.

### <a name="loading"></a>Loading

To load names from the source tables into the central names table, run the load program (located in `src/tools`):

```bash
usage: fill_names_table.py [-h] --name-database NAME_DATABASE \
    [--delete-per-source] \
    [--drop-source-tables] \
    [--debug]

optional arguments:
  -h, --help            show this help message and exit
  --name-database NAME_DATABASE, -d NAME_DATABASE
                        path to SQLite database file
  --delete-per-source   only delete existing records for each source you are loading, rather than begin by
                        deleting all existing records.
  --drop-source-tables  drop source database tables after loading
  --debug

```

By default, the program tries to load data from all the sources, but if one of the source tables doesn't exist, it skips that source.
Omit `--drop-source-tables` to keep the source tables (be aware they take up a lot of space).

The output will look something like this:
```bash
$ python fill_names_table.py --name-database /path/to/names.db --drop-source-tables
INFO:root:Connected to '/data/seedlists/database/names.db'
INFO:root:Deleted all records
INFO:root:WCVP:1,445,026 records
INFO:root:WCVP:dropped source table
INFO:root:WFO:1,647,979 records
INFO:root:WFO:dropped source table
INFO:root:CoL:2,076,431 records
INFO:root:CoL:dropped source table
INFO:root:GBIF:1,983,038 records
INFO:root:GBIF:dropped source table
INFO:root:PlantList:1,297,758 records
INFO:root:PlantList:dropped source table
INFO:root:total:8,450,232 unique records
```


### Using the database

The first time the [extraction program](../README.md) is run, it loads all names from the names table, and caches it in a pickle file, for faster loading during subsequent runs. In order to load an updated names table, run the program with the `--force_names_reload` flag.




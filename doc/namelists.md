# Names database

## 1. Local SQLite database
Create a local SQLite3 database for loading the various names databases and creating the lookup table used by the seedlist extractor program.

## 2. Names databases

### Catalogue of Life

[www.catalogueoflife.org](https://www.catalogueoflife.org/)

[www.catalogueoflife.org/data/download](https://www.catalogueoflife.org/data/download)

Version used: The COL Checklist version 2023-11-24 (5.036.643 records)

Some data is not correctly escaped, leading to errors during loading (unescaped " character). To fix this:
```bash
python tools/csv_requoter.py -i CoL/NameUsage.tsv -o CoL/NameUsage--quoted.tsv
```

To load names, run in SQLite:
```sql
drop table if exists CoL_NameUsage;
.mode tabs
.import CoL/NameUsage--quoted.tsv CoL_NameUsage
```

### GBIF Backbone Taxonomy

[Global Biodiversity Information Facility](https://www.gbif.org/)

[gbif.org/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c](https://www.gbif.org/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c)

Version used: GBIF Backbone Taxonomy 2024-02-20 (backbone.zip) (7.696.224 records)

Fix quoting:
```bash
python tools/csv_requoter.py -i GBIF/Taxon.tsv -o GBIF/Taxon--quoted.tsv GBIF_Taxon
```

To load names, run in SQLite:
```sql
drop table if exists GBIF_Taxon;
.mode tabs
.import GBIF/Taxon--quoted.tsv GBIF_Taxon
```


### The Plant List with literature
[gbif.org/dataset/d9a4eedb-e985-4456-ad46-3df8472e00e8](https://www.gbif.org/dataset/d9a4eedb-e985-4456-ad46-3df8472e00e8) (via GBIF)

[zenodo.org/record/1194673/files/dwca.zip](https://zenodo.org/record/1194673/files/dwca.zip) (via Zenodo)

Version used: downloaded 2024-02-20 (1.692.926 records)

Fix quoting:
```bash
python tools/csv_requoter.py -i PlantList/taxa.txt
```

To load names, run in SQLite:
```sql
drop table if exists PlantList;
.mode tabs
.import PlantList/taxa--quoted.tsv PlantList
```


### WCVP: Plants Of The World Online (POWO) backbone

From [Kew Gardens](https://powo.science.kew.org/)

*Backbone: World Checklist of Vascular Plants (WCVP)*

[sftp.kew.org/pub/data-repositories/WCVP/wcvp_dwca.zip](http://sftp.kew.org/pub/data-repositories/WCVP/wcvp_dwca.zip)

[Same via GBIF](https://www.gbif.org/dataset/f382f0ce-323a-4091-bb9f-add557f3a9a2)

Version used: Publication date May 16, 2024 (1.427.810 records)

To load names, run in SQLite:
```sql
drop table if exists wcvp_taxon;
.mode csv
.separator "|"
.import WCVP/wcvp_taxon.csv wcvp_taxon
```

### WFO: World Flora Online

*World Flora Online Taxonomic Backbone*

[worldfloraonline.org/](https://www.worldfloraonline.org/)

[worldfloraonline.org/downloadData](https://www.worldfloraonline.org/downloadData)

[Latest Static Version](https://files.worldfloraonline.org/files/WFO_Backbone/_WFOCompleteBackbone/WFO_Backbone.zip)

Version: Taxonomic classification v.2023.03 (Mar. 04, 2023) 103MB (DwCA) (1.497.586 records)

To load names, run in SQLite:
```sql
drop table if exists WFO_classification;
.mode tabs
.import WFO/classification.csv WFO_classification
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

## 3. Names table

### Schema

Names from the source database end up in a central lookup table with the following columns:

+ canonical_name (example: 'Osteospermum imbricatum var. helichrysoides')
+ genus ('Osteospermum')
+ epithet ('imbricatum')
+ infraspecific_epithet ('helichrysoides')
+ authorship ('(DC.) Norl.')
+ taxon_rank ('variety')
+ source ('WCVP')

The canonical name also forms the unique key, so the order of loading of different databases determines which source is the primary source. Currently, this is WCVP, which is considered the most up to date and complete.

### Loading

To load names from the source tables into the central names table, run the load program:

```bash
usage: fill_names_table.py [-h] --name-database NAME_DATABASE \
    [--delete-per-source] \
    [--drop-source-tables] \
    [--debug]

optional arguments:
  -h, --help            show this help message and exit
  --name-database NAME_DATABASE, -d NAME_DATABASE
                        path to SQLite database file
  --delete-per-source   only delete existing records for each source you are loading, rather than begin by deleting all existing records.
  --drop-source-tables  drop source database tables after loading
  --debug

```

By default, the program tries to load data from all the sources, but if one of the source tables doesn't exist, it skips that source.
Omit `--drop-source-tables` to keep the source tables (be aware they take up a lot of space).


## 4. Running the seedlist extractor

When running the seedlist extraction program the first time, you have to specify the path to the names database in order to allow the program to load all names:

```bash
python list_extractor/extract.py \
    -i '/data/input/' \
    -o '/data/output/'  \
    -d '/path/to/sqlite/names_database.db3'
```

For reasons of performance, the program will automatically cache its names list in a pickle file. As a result, it is unnecessary to pass the program the path to the names database on subsequent runs. However, if you want the program to explicitly reload the names database, for instance because you have added new data, you can force the program to reload the data:

```bash
python list_extractor/extract.py \
    -i '/data/input/' \
    -o '/data/output/'  \
    -d '/path/to/sqlite/names_database.db3' \
    --force-names-reload
```

See [README](../README.md) for a more detailed description of how to run the seedlist extractor.
# Names database

## Local SQLite database
Create a local SQLite3 database to load the various databases. 

## Databasee

### Catalogue of Life

[www.catalogueoflife.org](https://www.catalogueoflife.org/)

[www.catalogueoflife.org/data/download](https://www.catalogueoflife.org/data/download)

Used version: The COL Checklist version 2023-11-24 (5.036.643 records)

Some data is not correctly escaped, leading to errors during loading (unescaped " character); 
file has to be preprocessed to make it correctly quoted:
```bash
python csv_requoter.py -i CoL/NameUsage.tsv -o CoL/NameUsage--quoted.tsv
```

SQLite:
```sql
drop table if exists CoL_NameUsage;
.mode tabs
.import CoL/NameUsage--quoted.tsv CoL_NameUsage
```

### GBIF Backbone Taxonomy

[Global Biodiversity Information Facility](https://www.gbif.org/)

[gbif.org/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c](https://www.gbif.org/dataset/d7dddbf4-2cf0-4f39-9b2a-bb099caae36c)

Used version: GBIF Backbone Taxonomy 2024-02-20 (backbone.zip) (7.696.224 records)

Fix quoting:
```bash
python csv_requoter.py -i GBIF/Taxon.tsv -o GBIF/Taxon--quoted.tsv GBIF_Taxon
```

SQLite:
```sql
drop table if exists GBIF_Taxon;
.mode tabs
.import GBIF/Taxon--quoted.tsv GBIF_Taxon
```


### The Plant List with literature
[gbif.org/dataset/d9a4eedb-e985-4456-ad46-3df8472e00e8](https://www.gbif.org/dataset/d9a4eedb-e985-4456-ad46-3df8472e00e8) (via GBIF)

[zenodo.org/record/1194673/files/dwca.zip](https://zenodo.org/record/1194673/files/dwca.zip) (via Zenodo)

Version: downloaded 2024-02-20 (1.692.926 records)

Fix quoting:
```bash
python csv_requoter.py -i PlantList/taxa.txt
```

SQLite:
```sql
drop table if exists PlantList;
.mode tabs
.import PlantList/taxa--quoted.tsv PlantList
```


### WCVP: Plants Of The World Online (POWO) backbone

From [Kew Gardens](https://powo.science.kew.org/)

*Backbone: World Checklist of Vascular Plants (WCVP)*

[sftp.kew.org/pub/data-repositories/WCVP/wcvp_dwca.zip](http://sftp.kew.org/pub/data-repositories/WCVP/wcvp_dwca.zip)

[same endpoint via GBIF](https://www.gbif.org/dataset/f382f0ce-323a-4091-bb9f-add557f3a9a2)

1.422.868 records

SQLite:
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

SQLite:
```sql
drop table if exists WFO_classification;
.mode tabs
.import WFO/classification.csv WFO_classification
```






## import results
INFO:root:recreated table name_lookup
INFO:root:WFO: 1,495,010 records
INFO:root:WCVP: 1,419,022 records
INFO:root:CoL: 1,876,108 records
INFO:root:GBIF: 1,970,914 records
INFO:root:PlantList: 1,297,758 records
INFO:root:total: 3,600,640 unique records





Not using IPNI because lack of higher taxonomy


## IPNI: International Plant Names Index v
https://www.ipni.org/
No families:
    Plant names are dealt with in the ICN under genus and species. Families are a convenient way of grouping names but are ultimately a taxonomic, not nomenclatural, distinction. The families given in IPNI are usually those given for that genus at the time of its publication or earlier treatments, such as Brummitt’s Vascular Plant Families and Genera (1992).
No download from site

via GBIF (DwC-A):
https://www.gbif.org/dataset/046bbc50-cae2-47ff-aa43-729fbf53f7c5
https://hosted-datasets.gbif.org/datasets/ipni.zip
    Publication date:       October 31, 2019
    Metadata last modified: November 11, 2019 

drop table IPNI_Name;
.mode tabs
.import IPNI/Name.tsv IPNI_Name
1.768.158


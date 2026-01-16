# Seed List Plant Name Extractor

Seed List Plant Name Extractor extracts plant names and associated metadata from seed lists.

The Utrecht University Botanic Gardens have a unique archive of seed lists: records depicting and describing plants that have grown in the garden at a set point in time. Seed lists are offered for exchange between botanic gardens worldwide, and Utrecht's archive dates back to at least 1837. This tool extracts plant names and associated metadata from seed lists ([read more](https://www.uu.nl/en/news/historical-seed-lists-teach-researchers-about-plant-collections-of-the-past)).


## What it does

The program attempt to extract scientific names of plant species, subspecies, varieties, forma, and genera by matching strings within seedlist documents against a database with verified plantnames, both current and historical (synonyms). Additionally, it attempts to extract associated meta data, such as IPEN-identifiers. 

## Requirements

+ Python >= 3.10 
+ See [requirements.txt](requirements.txt)

## Names database

To recognize names, the program uses a database with plant names. Names can come from any source(s), and the more names there are in the database, the better the results of the extraction. This is especially true for synonyms (old names), as most seed lists are historical documents. For how to create the database, see [namelists.md](doc/namelists.md).

## Input

The program uses plain text files as input. For seed lists originally published on paper, text can be acquired through OCR'ing scanned documents. To convert born-digital seed lists (such as PDF or Word), there are various programs to convert them to plain text. Example usage of one such tool, Apache Tika, can be found in [tools/pdf2text.py](src/tools/pdf2text.py). Be aware that this example has not been extensivly tested.

## Output

The program will output a .tsv file for each input file, provided any data can be extracted from it. See [output.md](doc/output.md) for details.

## Running the program

See [Seedlist Names Extraction Pipeline](doc/pipeline.md)

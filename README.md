# Seed List Plant Name Extractor

The Utrecht University Botanic Gardens have a unique archive of seed lists: records depicting and describing plants that have grown in the garden at a set point in time. Seed lists are offered for exchange between botanic gardens worldwide, and Utrecht's archive dates back to at least 1837. This tool extracts plant names and associated metadata from seed lists.

https://www.uu.nl/en/news/historical-seed-lists-teach-researchers-about-plant-collections-of-the-past


## How it works

The program attempt to extract scientific names of plant species, subspecies, varieties, forma, and genera by matching strings within seedlist documents against a database with verified plantnames, both current and historical (synonyms). Additionally, it attempts to extract associated meta data, such as IPEN-identifiers. 

+ Conversion of seedlists to txt files
    + from PDF: [src/tools/pdf2text.py](src/tools/pdf2text.py)
    + from image: run some form of OCR. Multi-column pages must be converted to single column txt (the extraction program expects one plantname per line).





## Requirements

+ Python >= 3.10 
+ chardet
+ polars
+ polars_distance

## Names database

To recognize names, the program requires a database with plant names. Names can come from any source(s), and the more names there are in the database, the better the results of the extraction. This is especially true for synonyms (old names), as most seed lists are historical documents. For how to create the database, see [doc/namelists.md](doc/namelists.md)

## Text files
From PDF

From OCR

## Extracting names

First time:
```bash
python list_extractor/extract.py \
    -i '/data/input/' \
    -o '/data/output/'  \
    -d '/path/to/sqlite/names_database.db3'
```

After the first run, the names will be cached

```bash
python list_extractor/extract.py \
    -i '/data/input/' \
    -o '/data/output/'
```

```console
usage: extract.py [-h] -i INPUT_PATH [-o OUTPUT_PATH] [--names-database NAMES_DATABASE] [--force-names-reload] [--extract-ipen] [--fuzzy-match-threshold FUZZY_MATCH_THRESHOLD]
                  [--fuzzy-match-strategy {best_score,longest_name}] [--skip-existing] [--lines LINES [LINES ...]] [--debug] [--stdout]

options:
  -h, --help            show this help message and exit
  -i INPUT_PATH, --input-path INPUT_PATH
                        Path to file or directory (program will also go through subdirectories).
  -o OUTPUT_PATH, --output-path OUTPUT_PATH
                        Path to directory to write CSV's to. If input is a directory with subdirectories, structure will be maintained in the output.
  --names-database NAMES_DATABASE
                        Path to SQLite database with taxonomical names. See 'tools/fill_names_table.py' and 'doc/namelists.md' for details. Required during first run, afterwards, names are cached.
  --force-names-reload  Force reloading names from the database.
  --extract-ipen        Make program look for IPEN-codes.
  --fuzzy-match-threshold FUZZY_MATCH_THRESHOLD
                        Fuzzy matching confidence threshold. Value must be between 0 and 1; omit for no fuzzy matching.
  --fuzzy-match-strategy {best_score,longest_name}
                        Select the longest, or the highest scoring of all fuzzy matches for a single line (default: 'best_score').
  --skip-existing       Skip extraction if the output file already exists.
  --lines LINES [LINES ...]
                        If two values, line numbers of start and end (inclusive) of section to process; otherwise, specific lines to process. Separate values by spaces.
  --debug               Print debugging info. Also adds line numbers to the output files.
  --stdout              Print output to screen.


```
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

During the initial run, the program caches the names list for reasons of performance, and requires access to the names database:

```bash
python list_extractor/extract.py \
    -i '/data/input/' \
    -o '/data/output/'  \
    -d '/path/to/sqlite/names_database.db3'
```

For subsequent runs he names will be cached:

```bash
python list_extractor/extract.py \
    -i '/data/input/' \
    -o '/data/output/'
```

All options:

```console
usage: extract.py [-h] -i INPUT_PATH (-o OUTPUT_DIRECTORY | --output_in_situ)
                  [--skip_existing] [--names_database NAMES_DATABASE]
                  [--names_pickle_file NAMES_PICKLE_FILE]
                  [--fuzzy_threshold FUZZY_THRESHOLD]
                  [--fuzzy_strategy {best_score,longest_name}] [--fuzzy_near_blocks]
                  [--fuzzy_non_parallel] [--extract_ipen] [--debug]
                  [--logfile LOGFILE] [--stdout]

options:
  -h, --help            show this help message and exit
  -i INPUT_PATH, --input_path INPUT_PATH
                        Path to file or directory (program will also go through
                        subdirectories). (default: None)
  --extract_ipen        Attempt to extract IPEN-codes. (default: False)

output options:
  -o OUTPUT_DIRECTORY, --output_directory OUTPUT_DIRECTORY
                        Path to directory to write TSV's to. If input is a directory
                        with subdirectories, structure will be maintained in the
                        output. (default: None)
  --output_in_situ      Write output to corresponding input file's folder. (default:
                        False)
  --skip_existing       Skip extraction if the output file already exists. (default:
                        False)

names database:
  --names_database NAMES_DATABASE
                        Path to SQLite database with taxonomic names. See
                        documentation for details. Mandatory during first run; after
                        that, names are read from cache. To refresh the name cache,
                        run the program again with `--names_database` (default: None)
  --names_pickle_file NAMES_PICKLE_FILE
                        Path to pickle file with cached names. (default:
                        ./pickles/names_pickle)

fuzzy matching options:
  --fuzzy_threshold FUZZY_THRESHOLD
                        Fuzzy matching confidence threshold. Value must be between 0
                        and 1; omit for no fuzzy matching. (default: None)
  --fuzzy_strategy {best_score,longest_name}
                        Select the longest name, or the highest scoring of all fuzzy
                        matches for a single line. (default: best_score)
  --fuzzy_near_blocks   Only look for for fuzzy matches near blocks of exactly
                        matched names, rather than throughout the entire document.
                        Increases performance at risk of missing names. Documents of
                        1000 lines or less are always processed in its entirety.
                        (default: False)
  --fuzzy_non_parallel  Do not run fuzzy matching in parallel. (default: False)

debugging:
  --debug               Print debugging info. (default: False)
  --logfile LOGFILE     Logfile path. Omit for logging to screen only. (default:
                        None)
  --stdout              Print output to screen (besides file). (default: False)


```

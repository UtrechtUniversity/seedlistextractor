# Seedlist Names Extraction Pipeline

## Acquiring data

### OCR scanned documents

OCR. Multi-column pages must be converted to single column txt (the extraction program expects one plantname per line).

### Digitally native PDF to text 

[src/tools/pdf2text.py](src/tools/pdf2text.py)

### Downloading from YoDa

## Preparing names database

## Preprocessing documents

## Extracting names

### Configuration options

```
usage: extract.py [-h] -i INPUT_PATH [-o OUTPUT_DIRECTORY] [--skip_existing]
                  [--output_in_situ] [--fuzzy_threshold FUZZY_THRESHOLD]
                  [--fuzzy_strategy {best_score,longest_name}]
                  [--fuzzy_near_blocks] [--extract_ipen]
                  [--names_database NAMES_DATABASE] [--force_names_reload]
                  [--lines LINES [LINES ...]] [--debug] [--stdout]
                  [--logfile LOGFILE]

options:
  -h, --help            show this help message and exit
  -i INPUT_PATH, --input_path INPUT_PATH
                        Path to file or directory (program will also go through
                        subdirectories).
  -o OUTPUT_DIRECTORY, --output_directory OUTPUT_DIRECTORY
                        Path to directory to write TSV's to. If input is a
                        directory with subdirectories, structure will be
                        maintained in the output. Cannot be combined with
                        --output_in_situ
  --skip_existing       Skip extraction if the output file already exists
                        (default False).
  --output_in_situ      Write output to corresponding input file's folder
                        (default False). Cannot be combined with --output_path
  --fuzzy_threshold FUZZY_THRESHOLD
                        Fuzzy matching confidence threshold. Value must be
                        between 0 and 1; omit for no fuzzy matching.
  --fuzzy_strategy {best_score,longest_name}
                        Select the longest, or the highest scoring of all fuzzy
                        matches for a single line (default: 'best_score').
  --fuzzy_near_blocks   Only look for for fuzzy matches near blocks of exactly
                        matched names, rather than the entire document.
                        Increases performance at risk of missing names (default
                        False). Documents of 1000 lines or less are always
                        processed in its entirety.
  --extract_ipen        Extract IPEN-codes (default False).
  --names_database NAMES_DATABASE
                        Path to SQLite database with taxonomic names. See
                        documentation for details. Mandatory during first run;
                        after that, names are read from cache.
  --force_names_reload  Force reloading names from the database (recreates
                        names cache).
  --lines LINES [LINES ...]
                        If two values, line numbers of start and end
                        (inclusive) of section to process; otherwise, specific
                        lines to process. Separate values by spaces.
  --debug               Print debugging info.
  --stdout              Print output to screen (first 10 columns only) (default
                        False).
  --logfile LOGFILE     Logfile path. Leave empty for logging to screen only.

```

### Hardcoded configuration

in [extract.py](../src/list_extractor/extract.py):

```python
input_encoding = None   # None is auto
names_pickle_file = './pickles/names_pickle'
names_sources_sort_order = {'WCVP': 0, 'WFO': 1, 'CoL': 2, 'GBIF': 3, 'PlantList': 4}
field_order_in_input = ('name', 'ipen')
```

in [extraction_utils.py](../src/list_extractor/extraction_utils.py)
```python
# synonyms
r'((\[|\()(sin|syn)\.?\:? ([^\]\)]*)(\]|\)))'

# cultivar 
('‘','’'), '´', '"', "'", ('„', '”'), ('’','‘'):

# IPEN
r'(([A-Z]{2}|[a-z]{2})([-\.]{1})([O01]{1})([-\.]{1})([A-Z]{1,5}|[a-z]{1,5})([-\./_]{1})([^\s\]\:\)]+))'

# "repeat symbols", symbols indicating a repeated genus
['-', '–', '—', '——', '−']
```

in [seedlist_extractor.py](../src/list_extractor/seedlist_extractor.py)
```
[
    '*A*', '*F*', '*G*', '*P*',
    '(**)', '(*)', '**', '*',
    '(++)', '(+)', '++', '+',
    '^', '%', '#', 'º', '!',
    'CW', 'IAS', '(W)', 'Ø',
    'A', 'G', 'O', 'P', 'W', 'U', 'Z', 
    '☉', '⚇', '♃', '🌲', '🌳', '🌿', '🏠',
]
```

### Internal preprocessing

```
# tabs to spaces
text = re.sub(r'\t', ' ', text)
# homogenise dashes
# see https://en.wikipedia.org/wiki/Hyphen#Unicode for "dashes" (list omits \u2013, \u2014)
text = re.sub(r'[\u2013\u2014\u002D\u00AD\u2010\u2011\u2E5D\u058A\u05BE\u1806\u1B60\u2E17\u30FB\uFE63\uFF0D\uFF65\u1400\u2027\u2043\u2E1A\u2E40\u30A0]+', '-', text)  # pylint: disable=line-too-long
# remove standard title
text = re.sub(r'Index[\s]{1,}seminum', '', text, flags=re.IGNORECASE)
# replacing isolated x's with hybrid symbol ×
text = re.sub(r'\s{1}(x|X)\s{1}', ' × ', text)
# replace repeating (4 or more) non-alphanumeric characters with single character (dots in index)
text = re.sub(r'([^A-Za-z0-9])\1{4,}', r'\1', text)
# misc characters (OCR artefacts)
text = re.sub(r'■', ' ', text)
```



## Known issues
+ Many modern seedlists have a photo of a plant on the cover, often including its name in the subscript. These names, and others similarly appearing outside of the main plant list in a document, will also be extracted. This is probably fine, as gardens are bound to use photo's of plants they actually own, but the extracted entries will most likely not include any useful metadata.
+ Cultivar names that are not in quotes (but for instance in a separate column) will be passed over (but should end up in the metadata).
+ The field **extracted_metadata_next_lines** for the very last name in a list can include lines that don't actually pertain to the name, but rather are part of the text following the list of names (for the last entry, the program uses the average number of extracted metadata lines for all preceding names, rounded up, to judge where to stop collecting lines).
+ Gardens can be quite liberal with the format of the IPEN-number, and some of the more creative numbers might not match the regular expression used to extract them.
+ Legend: list of characters to look for is possibly incomplete, and can be expanded. Looking for the actula legend can be tricky.


## Joblog
Check to see if anything failed.
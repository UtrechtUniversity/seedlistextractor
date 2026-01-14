# Seedlist Names Extraction Pipeline

## Acquiring data

The main program expects plain text as input.

To convert images to text, scan them and perform OCR. Make sure multi-column pages are converted to single column txt (the extraction program expects one plantname per line).

To convert digitally native PDF to text, see [src/tools/pdf2text.py](src/tools/pdf2text.py) for a limited example of how to convert PDF to plain text. Be warned, because of the versatile nature of the PDF-format, the results of conversion to text can be unpredictable.

## Preparing names database

The name resolver requires a database with plant names to check against. See the [Names database document](namelists.md) for more information.

## Extracting data

As input, the program expects a folder containing OCR'd documents as .txt files (or .json, as exported by Apache Tika).

For each document in the input folder, the program calls the SeedlistExtractor-module, which follows these steps:

- _Preprocessing_; per line:
  - Tabs converted to spaces.
  - Dashes and dash-like symbold are homogenised.
  - Standard title 'Index seminum' removed.
  - Isolated x's are replaced with hybrid symbol × .
  - Repeating (4 or more) non-alphanumeric characters are replaced with single character (dots in index).
  - Some often occurring OCR artefacts are removed.

Next, per line are extracted:

- _'Repeater symbols'_, symbols indicating a repeated genus.
- _Synonyms_ (based on `[syn. ... ]`  etc.). Synonyms are _not_ resolved against the names' database, and stored as literal strings.
- _Genus name_ (based on list of genera from the names database).
- _Isolated epithets_ (names without genus, probably preceded with a repeater symbol).
- _Full name_ (species, subspecies, form, variety); must exactly match a name from the names database.
- _Cultivars & formas_ (quoted names directly following a matched full name) These are also  _not_ resolved, and stored as literal strings.
- _IPEN-code_

Next:

- _Fuzzy names_: for lines that do not have an exactly matched (sub)species, attempts to extract names by fuzzy matching.

- _Resolving isolated epithets_: attempts to combine isolated epithets with the genus of the preceding line into a complete name.
 
Finally:

- _Meta-data_:
  - Remaining tokens from a line are stored as its meta-data.
  - Lines without any identified data, following a line with an identified name are stored as the preceding lines meta-data.

- _Legend_:
  - Identification of legend items, using a hard-coded (TODO) [set of possible legend-symbols](https://github.com/UtrechtUniversity/seedlistextractor/blob/1439600073d43436b06f5f357e9b1d69c93ae104/src/list_extractor/seedlist_extractor.py#L541).
  - Using identified legend symbols, add legend(s) to all lines containing corresponding symbols.

- _Compare genera_: score the difference between resolved genus and genus part of resolved name [see 'Differences between species and genus name match'](output.md#differences-between-species-and-genus-name-match).


After processing is completed, the output module collects data from lines belonging together (for instance, the IPEN-number is sometimes printed on its own line, following the species name it represents), and writes the output to a .TSV-file (one file per input doc).


### Program options

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

## Known issues
+ Many modern seedlists have a photo of a plant on the cover, often including its name in the subscript. These names, and others similarly appearing outside of the main plant list in a document, will also be extracted. This is probably fine, as gardens are bound to use photo's of plants they actually own, but the extracted entries will most likely not include any useful metadata.
+ Cultivar names that are not in quotes (but for instance in a separate column) will be passed over (but should end up in the metadata).
+ The field **extracted_metadata_next_lines** for the very last name in a list can include lines that don't actually pertain to the name, but rather are part of the text following the list of names (for the last entry, the program uses the average number of extracted metadata lines for all preceding names, rounded up, to judge where to stop collecting lines).
+ Gardens can be quite liberal with the format of the IPEN-number, and some of the more creative numbers might not match the regular expression used to extract them.
+ Legend: list of characters to look for is possibly incomplete, and can be expanded. Looking for the actual legend can be tricky.


## Fuzzy name matching
/usr/lib/python3.10/multiprocessing/popen_fork.py:66: RuntimeWarning: Using fork() can cause Polars to deadlock in the child process.
In addition, using fork() with Python in general is a recipe for mysterious
deadlocks and crashes.

The most likely reason you are seeing this error is because you are using the
multiprocessing module on Linux, which uses fork() by default. This will be
fixed in Python 3.14. Until then, you want to use the "spawn" context instead.

See https://docs.pola.rs/user-guide/misc/multiprocessing/ for details.

If you really know what your doing, you can silence this warning with the warning module
or by setting POLARS_ALLOW_FORKING_THREAD=1.

  self.pid = os.fork()

## Logging and Joblog

If specified when executing the program, log-data s written to a joblog file.



Check to see if anything failed.

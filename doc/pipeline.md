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
  - Tabs are converted to spaces.
  - Dashes and dash-like symbold are homogenised.
  - Standard title 'Index seminum' is removed.
  - Isolated x's are replaced with hybrid symbol × (multiplication sign; U+00D7).
  - Repeating (4 or more) non-alphanumeric characters are replaced with single character (dots in index).
  - Some often occurring OCR artefacts are removed.

Next, per line, these fields are extracted:

- _'Repeater symbols'_, symbols indicating a repeated genus ([code](https://github.com/UtrechtUniversity/seedlistextractor/blob/4fd9d97a8a29cdc8dbfd5129f830056db4a0b7be/src/list_extractor/extraction_utils.py#L48)).
- _Synonyms_ (based on `[syn. ... ]`  etc.). Synonyms are _not_ resolved against the names' database, and stored as literal strings ([code](https://github.com/UtrechtUniversity/seedlistextractor/blob/4fd9d97a8a29cdc8dbfd5129f830056db4a0b7be/src/list_extractor/extraction_utils.py#L4)).
- _Genus name_ (based on list of genera from the names database).
- _Isolated epithets_ (names without genus, probably preceded with a repeater symbol).
- _Full name_ (species, subspecies, form, variety); must exactly match a name from the names database.
- _Cultivars & formas_ (quoted names directly following a matched full name) These are also  _not_ resolved, and stored as literal strings ([code](https://github.com/UtrechtUniversity/seedlistextractor/blob/4fd9d97a8a29cdc8dbfd5129f830056db4a0b7be/src/list_extractor/extraction_utils.py#L9)).
- _IPEN-code_ ([code](https://github.com/UtrechtUniversity/seedlistextractor/blob/4fd9d97a8a29cdc8dbfd5129f830056db4a0b7be/src/list_extractor/extraction_utils.py#L22))

Once all lines have been processed:

- _Fuzzy names_: for lines that do not have an exactly matched (sub)species, the program attempts to extract names by fuzzy matching.

- _Resolving isolated epithets_: the program attempts to combine isolated epithets with the genus of the preceding line into complete names.
 
Finally:

- _Meta-data_:
  - Remaining text from a line is stored as meta-data.
  - Lines without any identified data, but following a line with an identified name are stored as meta-data for that preceding line.

- _Legend_:
  - Identification of legend items, using a list of often occurring legend symbols ([code](https://github.com/UtrechtUniversity/seedlistextractor/blob/4fd9d97a8a29cdc8dbfd5129f830056db4a0b7be/src/list_extractor/seedlist_extractor.py#L539)).
  - Using the identified legend symbols, the program adds legend(s) to all lines containing corresponding symbols.

- _Compare genera_: score the difference between resolved genus and genus part of resolved name (see ['Differences between species and genus name match'](output.md#differences-between-species-and-genus-name-match)).


After processing is completed, the output module collects data from lines belonging together, and writes the output to a .TSV-file (one file per input doc). [Detailed description of the output fields](output.md).

## Running the program

During the initial run, the program caches the names list for reasons of performance, and requires access to the names database:

```bash
python extract.py \
    -i '/data/input/' \
    -o '/data/output/'  \
    -d '/path/to/sqlite/names_database.db3'
```

For subsequent runs the names will be read from a cache and the `-d` parameter can be omitted.

### All program options

```
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

## Joblog and logging
The program writes a joblog to a JSON-file in the output directory. The joblog specifies all settings used during a run of the program, plus an overview of what files were processed, and how long it took.

Beside logging to the terminal, the program can also write loglines to a file, by specifying the path to a logfile when executing the program

By default, only INFO, WARNING and ERROR messages are logged; use `--debug` to also log DEBUG-level messages.


## Known issues
+ Many modern seedlists have a photo of a plant on the cover, often including its name in the subscript. These names, and others similarly appearing outside of the main plant list in a document, will also be extracted. This is probably fine, as gardens are bound to use photo's of plants they actually own, but the extracted entries will most likely not include any useful metadata.
+ Cultivar names that are not in quotes (but for instance in a separate column) will be passed over (but should end up in the metadata).
+ Synonyms listed between regular brackets that also contain brackets in their name (example: `(syn. Lychnis flos-jovis (L.) Desr.)`) are not recognized.
+ The field `extracted_metadata_next_lines` for the very last name in a list can include lines that don't actually pertain to the name, but rather are part of the text following the list of names (for the last entry, the program uses the average number of extracted metadata lines for all preceding names, rounded up, to judge where to stop collecting lines).
+ Gardens can be quite liberal with the format of the IPEN-number, and some of the more creative numbers might not match the regular expression used to extract them.
+ Legend: list of characters to look for is possibly incomplete, and can be expanded.

### Fuzzy name matching parallelization error

Occasionally, fuzzy name matching, which can run in parallel, throws an error:

```
/usr/local/lib/python3.11/multiprocessing/popen_fork.py:66: RuntimeWarning: Using fork() can cause Polars to deadlock in the child process.
In addition, using fork() with Python in general is a recipe for mysterious
deadlocks and crashes.

The most likely reason you are seeing this error is because you are using the
multiprocessing module on Linux, which uses fork() by default. This will be
fixed in Python 3.14. Until then, you want to use the "spawn" context instead.

See https://docs.pola.rs/user-guide/misc/multiprocessing/ for details.

If you really know what your doing, you can silence this warning with the warning module
or by setting POLARS_ALLOW_FORKING_THREAD=1.

  self.pid = os.fork()
```

If this happens, try running the script again, of use `--fuzzy_non_parallel` (which will take more time). Python 3.14 is currently not supported.

### Hardcoded configuration
**(should be in a configuration file; TODO)**

_in [extract.py](../src/list_extractor/extract.py)_

```python
input_encoding = None
names_pickle_file = './pickles/names_pickle'
names_sources_sort_order = {'WCVP': 0, 'WFO': 1, 'CoL': 2, 'GBIF': 3, 'PlantList': 4}
field_order_in_input = ('name', 'ipen')
```
`input_encoding`: specifies the encoding of the input files. When set to `None`, the program tries to guess the correct encoding (using `chardet.detect()`).

`names_pickle_file`: path pointing to the pickle-file containing all names from the database (these are cached as a pickle for reasons of performance).

`names_sources_sort_order`: specifies the order of precedence of the different name sources (if a name matches names from multiple sources that have different taxonomies, the record from the source with the lowest sort order takes precedence.

`field_order_in_input`: expected order of the name and the IPEN-code in the original seedlist (relevant while collecting all data belonging with a name).

_in [extraction_utils.py](../src/list_extractor/extraction_utils.py)_

Various regular expressions and character classes for extracting data:

```python
# synonyms
r'((\[|\()(sin|syn)\.?\:? ([^\]\)]*)(\]|\)))'

# cultivar 
('‘','’'), '´', '"', "'", ('„', '”'), ('’','‘')

# IPEN
r'(([A-Z]{2}|[a-z]{2})([-\.]{1})([O01]{1})([-\.]{1})([A-Z]{1,5}|[a-z]{1,5})([-\./_]{1})([^\s\]\:\)]+))'

# "repeat symbols", symbols indicating a repeated genus
['-', '–', '—', '——', '−']
```

_in [seedlist_extractor.py](../src/list_extractor/seedlist_extractor.py)_

List of legend-symbols:

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

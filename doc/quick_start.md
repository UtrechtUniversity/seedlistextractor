# Seedlist Names Extraction Quick start

[Complete overview of the Seedlist Names Extraction Pipeline](pipeline.md)

## Install Python

Make sure Python is installed on the computer where you want to run the extraction program. The
program requires Python version >=3.10, <3.14.

[Python.org downloads page](https://www.python.org/downloads/)

## Clone the Git-repository

Install the source code from the [Seedlist Git-repository](https://github.com/UtrechtUniversity/seedlistextractor/tree/main)
on you local computer, either by cloning the repo using a Git-client, or by downloading the files as a ZIP-file and extracting them locally.

### Using a Git-client

This requires you have a Git-client installed on your computer. If you do not, you can
download the program as a ZIP-file (see next section).

Open a terminal on your computer, navigate to an appropriate folder, and run:

```bash
git clone https://github.com/UtrechtUniversity/seedlistextractor.git
```
This will download the source code into a subfolder called _seedlistextractor_.

### Downloading as ZIP-file

Open a browser and navigate to the [Seedlist Extractor Git-repository](https://github.com/UtrechtUniversity/seedlistextractor/tree/main).

Make sure the 'main' branch is selected (see select-box underneat the **seedlistextractor** header). At the right on the same
line, click the green '<> Code' button, and click 'Download ZIP' at the bottom of the menu.

Extract the contents of the ZIP-file to an appropriate folder. The code will be stored into a subfolder called
_seedlistextractor-main_.

## Installing required libraries

Open a terminal and navigate to the folder you have placed the source files in (_seedlistextractor_-subfolder if you
cloned the repository, _seedlistextractor-main_ if you downloaded the ZIP).

Run `python --version` to check if the right version of Python is installed (>=3.10, <3.14).

Run `pip install -r ./requirements.txt` to install the required libraries.


## Installing names database

The extraction program requires a database with plantnames to resolve extracted names.

You can create a database from scratch by following the instructions in the [names database document](namelists.md). 
As this process can be cumbersome, you can also use an existing version of the database, which is stored in Yoda.

To download the pre-loaded database, you need access to UU's [I-Lab Yoda instance](https://i-lab.yoda.uu.nl/).
Log in to Yoda, and navigate to [research-seedlists-cleaned > taxonomic database](https://i-lab.yoda.uu.nl/research/browse?dir=%2Fresearch-seedlists-cleaned%2Ftaxonomic%20database).
In it, you will find four files: 

+ *names_cache_202609*: complete names cache as pickle-file (file has no extension).
+ *names_cache_WCVP_only_202609*: idem, but a subset with only data from World Checklist of Vascular Plants (smaller file, useful for testing).
+ *names_database_202609.db*: SQLite-database with complete names table.
+ *names_database_202609.txt*: document describing the files and the contents of the names table.

(Note that these are the current filenames at the time of writing. Newer versions will have a more recent
date tag)

You only need the first file. Download *names_cache_202609* and store it on your computer. For the examples
below, it is assumed that you have saved the file in a folder called `/seedlists/names`. 

Please note that when you want to update the names database with a newer version of one of the source files,
the database and cache file need to be recreated. See the [names database document](namelists.md) for more
information. The version of each source file used is listed in *names_database_202609.txt*.

## Organising input data

These are the documents you want to extract names from. The program expects documents in plain text. 
It assumes there is only one plantname per line (no columns). Lines can have additional metadata associated
with the name. Lines that have no plantname will be treated as metadata belonging to the preceding plant.
If you do not have plain text documents, but rather scanned images or PDF's, you will have to convert them
first.

The text files you want to extract names from need to be in a folder on your computer. The extraction program
will go through the input folder recursively, so the input files can be organised in subfolders. The program
will copy the subfolder structure (relative to the root input folder) to the output folder, maintaining the
overall structure for the output. Note that there is also an option to save the result files (of which there
will be one for each input file) in the same folder as the corresponding input file.

For the example below it is assumed that your inout data is located in the folder `/seedlists/input`.

## Running the program

The program is run from the command line. Open a terminal and navigate to the folder you have placed the
source files in (_seedlistextractor_-subfolder if you cloned the repository, _seedlistextractor-main_ if
you downloaded the ZIP) and access the folder with source files:


```bash
$ cd src/list_extractor/
```

### Example 1 (output to separate folder)

Next, to run the program (Linux):

```bash
$ python extract.py \
    --input_path /seedlists/input \
    --output_directory /seedlists/output \
    --names_pickle_file /seedlists/names/names_cache_202609  \
    --fuzzy_threshold 0.75 \
    --extract_ipen \
    --skip_existing
```

This will read all .txt files from `/seedlists/input` and underlying folders, process them,
and write the results as .tsv files to the folder `/seedlists/output`, maintaining the
relative subfolder structure of the input folder.

`--names_pickle_file` points the program to the downloaded file with the cached names database.
If omitted, the program will look for the default file `./pickles/names_pickle`.

`--fuzzy_threshold 0.75` enables fuzzy matching, using a threshold value for inclusion of
0.75. Change the value to an appropriate number (between 0 and 1) to influence the number of
fuzzy matches. Omit the parameter to disable fuzzy matching. [More on fuzzy matching](fuzzy_matching.md).

`--extract_ipen` enables the extraction of IPEN-numbers. Omit this parameter if your input 
files are sure to have no IPEN-codes, or if you do not want them extracted.

`--skip_existing` enables that if you _restart_ the program with the same in- and output
folders, input files for which an output file already exists will not be processed again. If
you omit this parameter, all files will be procesed, and any existing output files will be
overwritten.

While it is running, you will be able to follow the progress of the extraction program on your
screen. This will look something like this:
```
2026-09-23 11:35:16,736::INFO::Reading names from database
2026-09-23 11:36:27,815::INFO::Loaded 2,100,949 canonical names
2026-09-23 11:36:27,815::INFO::Loaded 719,984 epithets
2026-09-23 11:36:27,815::INFO::Loaded 65,339 genera
2026-09-23 11:36:37,867::INFO::Saved names cache
2026-09-23 11:36:37,879::INFO::Job log: '/seedlists/output/joblog-2026-09-23T1136.json'
2026-09-23 11:36:37,909::INFO::Got 186 file(s) from '/seedlists/input/in'
2026-09-23 11:36:37,940::INFO::Processing '/seedlists/input/1852 OCR/OCR 1852/AMD_1852/AMD_1852-1.txt'
2026-09-23 11:36:37,940::INFO::Processing 491 lines
2026-09-23 11:36:37,973::INFO::Found 354 names by exact matching
2026-09-23 11:36:37,988::INFO::Found 145 names by resolving isolated epithets
2026-09-23 11:36:38,059::INFO::Wrote to 'outputseedlists/output/1852 OCR/OCR 1852/AMD_1852/AMD_1852-1.tsv'
2026-09-23 11:36:38,059::INFO::'/seedlists/input/in/1852 OCR/OCR 1852/AMD_1852/AMD_1852-1.txt' done (done: 1; skipped: 0; errors: 0; total: 186)
2026-09-23 11:36:38,062::INFO::Processing '/data/seedlists/sep26/in/1852 OCR/OCR 1852/BONN_1852/BONN_1852-1.txt'
[...]
```

### Example 2 (output "in situ", logging to file)

If you want the program to write the output files to the same (sub)folder of the corresponding
input file, use the `--output_in_situ` parameter:

```bash
$ python extract.py \
    --input_path /seedlists/input \
    --output_in_situ \
    --names_pickle_file /seedlists/names/names_cache_202609 \
    --logfile /seedlists/log/extract.log
```

The `--logfile` parameter causes the program's output to also be written to the specified logfile.

For all available parameters, see the [pipeline document](pipeline.md#all_options). 

## Output

Once done, there will be an .tsv file with extraction results for each input file, except
if no names could be extracted from a file. This will noted in the log output ("Extracted
no data; writing no output").

See the [output document](output.md) for details of what is in the output files.

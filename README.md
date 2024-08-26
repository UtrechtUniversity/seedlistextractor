# Seed List Plant Name Extractor

The Utrecht University Botanic Gardens have a unique archive of seed lists: records depicting and describing plants that have grown in the garden at a set point in time. Seed lists are offered for exchange between botanic gardens worldwide, and Utrecht's archive dates back to at least 1837. This tool extracts plant names and associated metadata from seed lists.

https://www.uu.nl/en/news/historical-seed-lists-teach-researchers-about-plant-collections-of-the-past

## Requirements

Python >= 3.10 
chardet
polars
polars_distance

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


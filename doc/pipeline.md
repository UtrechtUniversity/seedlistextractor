# Seedlist Names Extraction Pipeline

## Acquiring data

### OCR scanned documents

### Digitally native PDF to text 

### Downloading from YoDa

## Preparing names database

## Preprocessing documents

## Extracting names

+ Conversion of seedlists to txt files
    + from PDF: [src/tools/pdf2text.py](src/tools/pdf2text.py)
    + from image: run some form of OCR. Multi-column pages must be converted to single column txt (the extraction program expects one plantname per line).

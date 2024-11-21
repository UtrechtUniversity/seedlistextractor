# Output

For each input file, the program outputs a .tsv-file in the output folder, assuming there is output to write. If no data has been extracted from an input document, there will be no corresponding output file.

## Columns

Examples are based on the raw input line `13. Adianthum concinnum. H.B.K.p.`.

<ins>(Sub)species match</ins>

+ **extracted_name**: text string from the source document the matched name was matched with.
    + example: `Adianthum concinnum`
+ **matched_name**: canonical name from names-database, based on *extracted_name*.
    + example: `Adiantum concinnum` (the best fuzzy match in the database list of canonical names for the string `Adianthum concinnum`)
+ **matched_score**: normalized Levenshtein ratio of the comparison of *extracted_name* and *matched_name*. 1 for exact matches, between 0 and 1 for fuzzy matches (if enabled).
    + example: `0.92` (the normalized ratio between `Adianthum concinnum` and `Adiantum concinnum`)
+ **matched_rank**: taxonomic level the match was made on: genus, species or epithet ('species' represents species and lower, so includes subspecies, variety, forma etc.)
    + example: `species` (rank of `Adiantum concinnum`, as found in the database)
+ **matched_genus**: genus of the matched name, stored in the database as part of the *matched_name*\'s taxonomy.
    + example: `Adiantum` (part of the taxonomy of `Adiantum concinnum`, as found in the database)
+ **matched_epithet**: epithet of the matched name (if matched on epithet or species).
    + example: `concinnum` (part of the taxonomy of `Adiantum concinnum`, as found in the database)
+ **matched_infraspecific_epithet**: infraspecific epithet of the matched name (if matched on epithet or species).
    + example: None (not found as part of the taxonomy of `Adiantum concinnum`)
+ **matched_authorship**: list of different authorships present in the names-database for the matched canonical names, separated by semi-colon. Includes the source database for each, in straight brackets.
    + example: `Humb. & Bonpl. ex Willd. [WCVP]; Humb. & Bonpl. [GBIF]`
+ **match_is_hybrid**: whether the matched name is a hybrid (= has an × in it's name).
    + example: `False`
+ **match_source**: name of the database the matched name was found in.
    + example: `WCVP`

<ins>Genus match</ins>

+ **genus_extracted_name**: text string from the source document the matched genus was matched with.
    + example: `Adianthum`
+ **genus_match_genus**: genus from names-database, based on _genus extracted name_. 
    + example: `Adianthum` (see [remark below](#differences-between-species-and-genus-name-match) on the differences between species name matching and genus name matching).
+ **genus_match_score**: 
    + example: `1` (signifying an exact match of the string `Adianthum` with an entry in the database)
+ **genus_match_source**: 
    + example: `WCVP`
+ **genera_match_score**: normalized Levenshtein ratio, either between *matched_genus* and *genus_match_genus*, or if there's no *genus_match_genus*, between *matched_genus* and the first token (split by spaces) of *extracted_name*.
    + example: `0.941176470588235` (the normalized ratio between `Adiantum` and `Adiantum`)

<ins>Other name data & Metadata</ins>

Examples are based on the raw input lines:
```
178 O Silene flos-jovis (L.) Greuter & Burdet ’Nana‘ [syn. Lychnis flos-jovis (L.) Desr.]
    XX-0-TEBLI-00857 [ex BG Debrecen, Hungary]
```

+ **extracted_synonyms**: extracted synonym(s) that are printed in brackets after a species name with the prefix `sin.` or `syn.`.
    + example: `Lychnis flos-jovis (Lychnis flos-jovis)`
+ **extracted_cultivar_form**: extracted cultivar or form, that is printed in quotes after a species name (cultivar), or has `(<something> form)` after a species name (form).
    + example: `’Nana‘`
+ **extracted_ipen**: extracted IPEN number.
    + example: `XX-0-TEBLI-00857`
+ **extracted_metadata_remnant**: whatever was left on the same line as the extracted name, after all other information was extracted (typically includes index numbers, remnants of authorship that didn't match, symbols that refer to notes, etc.).
    + example: `178 O (L.) Greuter & Burdet  Desr.]`
+ **extracted_metadata_next_lines**: lines directly following the same line from which a name was extracted.
    + example: `[ex BG Debrecen, Hungary]`
+ **extracted_notes**: notes based on symbols present on the matched name's line, extracted from a list or legend elsewhere in the document.
    + example: `O – plant is cultivated outdoors`
+ **raw_line**: original text line the extracted name was extracted from (for reference).
    + example: `178 O Silene flos-jovis (L.) Greuter & Burdet ’Nana‘ [syn. Lychnis flos-jovis (L.) Desr.]`

<ins>Filename & garden info</ins>

Data based on the name of the input file. Example filename: `TEBLI-2020-G-x-a-1-I.txt`

+ **filename**: name of the file containing the analyzed text.
    + example: `TEBLI-2020-G-x-a-1-I.txt`
+ **garden code**: garden code, extracted from the file name. Extraction of garden code and year is based on a file name format, `\b((1|2)\d{3})\b` for year, `^[A-Za-z]{1,}\b` for garden code. If a regex doesn't produce a match, there will be no value.
    + example: `TEBLI`
+ **year**: year, extracted from the file name.
    + example: `2020`

Some columns can include more than one value; these will be separated by semi-colon.


## Differences between species and genus name match

`matched name` is based on a list of all unique canonical names that exist in the underlying names database for taxon rank genus and lower. When a name is matched, the matched name's taxonomy (genus, epithet, infraspecific epithet) is taken from the database and presented on the output. A second match `genus_match_genus` is made against a list of just genera (canonical names of those taxa in the database that hava taxon rank 'genus'). This means that theoretically, when using fuzzy matching, `matched name` can be of a genus that is different from `genus_match_genus`. For instance, `Adianthum` with an 'h' does exist as a valid genus in the database, while the name `Adiantum concinnum` only exists as a species in the genus `Adiantum`, without an 'h'. As a result, `genus_match_genus` will be different from `matched_genus`, with the calue for `genera_match_score` indicating how different they are.

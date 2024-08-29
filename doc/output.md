## Columns

+ **extracted_name**: text string from the source document the matched name was matched with.
+ **matched_name**: full taxonomic name from names-database, based on extracted name.
+ **matched_score**: match score. 1 for literal matches, between 0 and 1 for fuzzy matches (see below).
+ **matched_rank**: taxonimic level the match was made on (genus or species; species represents species and lower, so includes subspecies, variety, forma etc.).
+ **matched_genus**: genus of the matched name.
+ **matched_epithet**: epithet of the matched name (if matched on species).
+ **matched_infraspecific_epithet**: infraspecific epithet of the matched name (if matched on subspecies etc.).
+ **matched_authorship**: authorship of the matched name (if present in the names-database).
+ **match_is_hybrid**: whether the matched name is a hybrid (= has an × in it's name) (True/False).
+ **match_possibly_partial**: if the matched name is possibly a partial name (True/False). This can occur when a species name was also combined with an infraspecifis epithet on the next line (without a "repeater symbol"), to form a valid subspecies name. In that case, the program can't always be sure if either both the species and the subspecies are part of the collection, or the split over two lines was just due to space limitations, and only the subspecies is part of the collection.
    Example:

    `Adenophora triphylla (THUNB.) A.DC.` ↵ `var. japonica (REGEL) HARA`

    The first line (`Adenophora triphylla (THUNB.) A.DC`) will match a species name, and the first line plus the second line will match a variety's name  (`Adenophora triphylla (THUNB.) A.DC. var. japonica (REGEL) HARA`). If this is the case, both names will be extracted, with the first (species) name will be tagged as `match_possibly_partial=True`.

+ **match_source**: name of the database the matched name was found in.
+ **match_identical_canonical**: list of other matches that have the same canonical name, but a different author.
+ **extracted_synonyms**: extracted synonym(s) that are printed in brackets after a species name with the prefix `sin.` or `syn.`.
+ **extracted_cultivar_form**: extracted cultivar or form, that is printed in quotes after a species name (cultivar), or has `(<something> form)` after a species name (form).
+ **extracted_ipen**: extracted IPEN number.
+ **extracted_metadata_remnant**: whatever was left on the same line as the extracted name, after all other information was extracted (typically includes index numbers, remnants of authorship that didn't match, symbols that refer to notes, etc.).
+ **extracted_metadata_next_lines**: lines directly following the same line from which a name was extracted.
+ **extracted_notes**: notes based on symbols present on the matched name's line, extracted from a list or legend elsewhere in the document.
+ **raw_line**: original text line the extracted name was extracted from (for reference).
+ **filename**: name of the file containing the analyzed text.
+ **garden code**: garden code, extracted from the file name.
+ **year**: year, extracted from the file name.

Some columns can include more than one value; these are presented as separate quoted valus in square brackets (`['a', 'b', 'c']`).

### Matched score / Fuzzy matching
Values lower than 1 can only appear when extraction is run with `--fuzzy-match-threshold` set to the minimal value. If the threshold is set, the program will attempt fuzzy matching for all lines that didn't yield an exact match.

Because fuzzy matching is slow, the program looks for exact matches on all the document's lines first, and only after that looks for fuzzy matches, only scanning lines that are in, or close to, clusters of lines that already have exact matches (rather than go through the entire document). Matches are calculated using a Levenshtein algorithm that calculates a match score, normalized to a fraction of 1. The highest matching name with a score higher than or equal to the threshold is considered the best match and used.

Finding an appropriate value for the threshold is a matter of trial-and-error. A lower value gives more mismatches, but potentially also finds more gravely misspelled names (a lower value doesn't affect the performance).

Note that in rare cases, names can be present in the output with a score which is lower than the threshold. If the program finds a match for a name that was orignally split over two lines, it calculates the score for the new, joined name by multiplying the scores of the constituent parts. If these were both found through fuzzy matching and have scores above the threshold, the product of these scores might be below it. These cases are currently not filtered out. Example: say both the genus and the epithet were matched with a score of 0.91, both above a 0.9 threshold, then the resulting species name will get a score of 0.91 x 0.91 = 0.8281. 

### Known issues
+ Be aware that many seedlists have a photo of a plant on the cover, often including its name in the subscript. These names, and others similarly appearing outside of the main plant list in a document, will also be extracted. This is probably fine, as gardens are bound to use photo's of plants they actually own, but the extracted entries will most likely not include any useful metadata.
+ Cultivar names that are not in quotes (for instance in a separate column) are missed (but should end up in the metadata).
+ The field **extracted_metadata_next_lines** for the very last name in a document can include lines that don't actually pertain to the name, but rather are part of the text following the list of names (for the last entry, the program uses the average number of extracted metadata lines for all preceding names, rounded up, to judge where to stop collecting lines).
+ Gardens can be quite liberal with the format of the IPEN-number, and some of the more creative numbers might not match the regular expression used to extract them.




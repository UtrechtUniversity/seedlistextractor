# Fuzzy Matching

Fuzzy matching attempts to resolve names that do not exactly match a name from the names database (for instance because of typo's or OCR errors). Fuzzy matching is done by calculating the Levenshtein distance between candidate strings and entries in the names database, and selecting the closest match that crosses a match threshold.

For reasons of perfomance, the program takes into account only taxa of rank genus, species, subspecies, form, or variety while doing fuzzy matching.

## Arguments

Command line parameters realted to fuzzy matching:

+ `fuzzy_threshold`: fuzzy matching confidence threshold, value must be between 0 and 1 (default None).
+ `fuzzy_strategy`: either the longest, or the highest scoring of all fuzzy matches for a single line (`best_score` (default)  or `longest_name`).
+ `fuzzy_near_blocks`: only look for for fuzzy matches near blocks of exactly matched names, rather than throughout the entire document. Increases performance at risk of missing names (default `False`). 
+ `fuzzy_non_parallel`: do not run fuzzy matching in parallel (default `False`). 

Other relevant parameters oulined below can currently not be set directly.

## Workflow

After the program has extracted exact matches from the text, it attempts to extract names from all lines that didn't yield a match.

### Set document range

As fuzzy matching is compuational expensive, the program can limit the range of lines in a document in which to look for fuzzy matches. Depending on the value of `fuzzy_near_blocks`, it either goes through the entire document (False), or limits the search to sections of the text from which exact matches were already extracted (True). The second method is faster, but it might cause the program to miss names.

If `fuzzy_near_blocks = False`, the program goes through the entire document, processing all lines in which no exact match has been found. This is the default.

If `fuzzy_near_blocks = True`, the program tries avoiding analyzing more lines than necessary. To do so, it looks for blocks of lines that already have a sizeable amount of names identified by exact matching, and assumes these are the actual lists that are in each document (the other sections being the front page, introduction, index etc.). This is done by arranging lines into clusters in which succesive lines with exact matches are no more than 10 lines apart. Next, the program goes through the lines of each cluster, processing lines in which no exact match has been found.

### Generate candidates

For the relevant lines, the program generates a set of candidates (strings to look up). This is a unique list of all possible concatenated sequences of tokens. Each sequence has to be at least `fuzzy_options.min_tokens` (default 2) and at most `fuzzy_options.max_tokens` (default 8) tokens long. A token needs to be at least `fuzzy_options.min_token_length` (default 2) characters long to be included.

### Lookup best matches

For each candidate, the program finds the entry in the names database that is most similar. In order to do so, it calculates the normalized Levenshtein distance between each candidate string and the canonical name of each taxon in the names database of rank genus, species, subspecies, form, or variety. Canonical names contain only the Latinized name elements - genus, specific epithet, and infraspecific epithet if applicable - without the auhorship part (author and year). Before comparing, all names are cleaned up - abbreviations like sp., ssp., and var. are removed, as are all characters other than letters and spaces - and set to lower case. For each candidate, the name with the Levenshtein distance that exceeds `fuzzy_options.match_threshold` and is closest to 1 is returned as most likely match.

### Choosing most likely match

Per line, one name is selected from the most likely matches. If `fuzzy_options.match_strategy` is set to `best_score`, the match with the highest normalized Levenshtein distance is selected as most likely match. If there is more than one match with the same highest score, the longest (most tokens) of these is selected. If the match strategy is set to `longest_name`, the longest candidate is selected as most likely match.

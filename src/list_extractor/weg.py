import polars as pl
import polars_distance as pld

names = ["hella world", "hella", "polars_distance", "as", "pld", "helloz"]

b = pl.DataFrame({
    "lookup":"hello",
    "names":names
}).select(
    pld.col('lookup').dist_str.levenshtein('names').arg_max().alias('index')
)['index'].item()

print(names[b])


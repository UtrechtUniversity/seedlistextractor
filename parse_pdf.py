import camelot
import pandas as pd

def read_table_in_pdf(filename, pages = 'all'):
    tables = camelot.read_pdf(filename, pages = pages)
    dfs = []
    
    for table in tables:
        df = table.df
        dfs.append(df)
    return dfs

def concat_dfs(dfs):
    df = pd.concat(dfs, ignore_index=True)
    return df

def promote_row_to_header(df, row):
    df.columns = list(df.iloc[row, :])
    return df

def remove_header_from_rows(df):
    count_header = sum(df[df.columns[0]] == df.columns[0])
    print(f'DEBUG: header appears {count_header} times as row.')
    df = df[df[df.columns[0]] != df.columns[0]]
    return df

def remove_row_by_col_val(df, val, colnum, exact = True):
    if exact:
        count_rows = sum(df[df.columns[colnum]] == val)
        print(f'DEBUG: pattern appears in {count_rows} rows.')
        df = df[df[df.columns[colnum]] != val]
    else:
        count_rows = sum(df[df.columns[colnum]].str.contains(val))
        print(f'DEBUG: pattern appears in {count_rows} rows.')
        df = df[~df[df.columns[colnum]].str.contains(val)]
    return df

def drop_na_col(df):
    return df.drop(df.columns[pd.isna(df.columns)], axis=1)

# Example 1: 
# 
dfs = read_table_in_pdf("data/LI-2020-x-x-a-1-I.pdf")
data = concat_dfs(dfs)
data = promote_row_to_header(data, 0)
data = remove_header_from_rows(data)
data = drop_na_col(data)
data = remove_row_by_col_val(data, '', 0)
data = remove_row_by_col_val(data, 'Bitte bestellen Sie', 0, exact=False)
data = data.reset_index(drop=True)
# Malformatted row
row_idx = data[data[data.columns[0]].str.contains(' ')].index.tolist()
# separate
values = data.iloc[row_idx[0]][data.columns[0]].split()
data.iloc[row_idx[0]][data.columns[0]] = values[0]
data.iloc[row_idx[0]][data.columns[1]] = values[1]


# Example 2:
#
dfs = read_table_in_pdf("data/BGAT-2020-x-WI-a-1-I.pdf")
data = concat_dfs(dfs)
data = promote_row_to_header(data, 1)
data = remove_header_from_rows(data)
data = remove_row_by_col_val(data, 'Samen aus', 0, exact=False)
data = remove_row_by_col_val(data, 'Bestell', 0, exact=False)
data = drop_na_col(data)
data = remove_row_by_col_val(data, '', 0)
data = data.reset_index(drop=True)
# Fill family
empty = data[data[data.columns[1]] == ''].index
for idx in empty:
    prev_val = data[data.columns[1]].iloc[idx-1]
    data.iloc[idx][data.columns[1]] = prev_val

# Example 3:
dfs = read_table_in_pdf("data/G-2020-x-WI-a-1-x.pdf", pages = '6-25')
data = concat_dfs(dfs)
# Find header and clean
header = data.iloc[299].copy()
sep = header[1].split('  ')
header[1] = sep[0]
header[2] = sep[1]
data.columns = header
data = remove_header_from_rows(data)


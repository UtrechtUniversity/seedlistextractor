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
    return pd.concat(dfs)

def promote_row_to_header(df, row):
    df.columns = list(df.iloc[row, :])
    return df

def remove_header_from_rows(df):
    count_header = sum(df[df.columns[0]] == df.columns[0])
    print(f'DEBUG: header appears {count_header} times as row.')
    df = df[df[df.columns[0]] != df.columns[0]]
    return df

def remove_row_by_col_val(df, val, colnum):
    count_rows = sum(df[df.columns[colnum]].str.startswith(val))
    print(f'DEBUG: pattern appears in {count_rows} rows.')
    df = df[~df[df.columns[colnum]].str.startswith(val)]
    return df


# Example 1: 
# 
dfs = read_table_in_pdf("data/LI-2020-x-x-a-1-I.pdf")
data = concat_dfs(dfs)
data = promote_row_to_header(data, 0)
data = remove_header_from_rows(data)

# Example 2:
#
dfs = read_table_in_pdf("data/BGAT-2020-x-WI-a-1-I.pdf")
data = concat_dfs(dfs)
data = promote_row_to_header(data, 1)
data = remove_header_from_rows(data)
data = remove_row_by_col_val(data, 'Samen aus', 0)


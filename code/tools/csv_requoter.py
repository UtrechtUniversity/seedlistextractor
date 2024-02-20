import csv
import sys
import argparse
from pathlib import Path

def quoter(
        filename_in, 
        filename_out=None,
        delimiter="\t", 
        quotechar='"',
        suffix="tsv"):

    if filename_out is None:
        filename_out= Path(filename_in).parts[0] / Path(Path(filename_in).stem + "--quoted").with_suffix("."+suffix)

    csv.field_size_limit(sys.maxsize)    

    i=0

    with open(filename_out, 'w+') as csvfile_out:
        csvwriter = csv.writer(csvfile_out, delimiter=delimiter, quotechar=quotechar, quoting=csv.QUOTE_ALL)
        with open(filename_in) as csvfile_in:
            dialect = csv.Sniffer().sniff(csvfile_in.read(4096), delimiters=";,\t")
            csvfile_in.seek(0)
            csvreader = csv.reader(csvfile_in, dialect)
            for row in csvreader:
                csvwriter.writerow(row)
                i+=1
                if i%25000==0:
                    print(f"{i:>10,}") 

    print(f"Wrote '{filename_out}'")

if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('-i','--input', required=True)
    parser.add_argument('-o','--output')
    parser.add_argument('--delimiter', default="\t")
    parser.add_argument('--quotechar', default='"')
    parser.add_argument('--suffix', help='Suffix when not supplying -o', default="tsv")
    args=parser.parse_args()

    quoter(
        filename_in=args.input,
        filename_out=args.output,
        delimiter=args.delimiter,
        quotechar=args.quotechar,
        suffix=args.suffix,
        )

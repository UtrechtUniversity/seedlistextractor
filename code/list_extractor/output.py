import logging
import csv
from termcolor import colored

class Output:

    def __init__(self,
                 skip_existing=False) -> None:
        self.skip_existing=skip_existing

    def csv(self, lines, header, output_path):
        if output_path.is_file() and self.skip_existing:
            logging.info("skipped existing file '%s'" % output_path)
            return

        with open(output_path, 'w') as file:
            csv_writer=csv.writer(file)
            csv_writer.writerow(header)
            for record in lines:
                csv_writer.writerow(record)

        logging.info("wrote %s name(s) to '%s'" % (len(lines), output_path))



    def csv1(self, lists, header, output_path):
        if output_path.is_file() and self.skip_existing:
            logging.info("skipped existing file '%s'" % output_path)
            return

        n=0
        with open(output_path, 'w') as file:
            rows=[]
            csv_writer=csv.writer(file)
            for key, records in enumerate(lists):
                rows.append([f"list #{key+1} ({len(records)})"])
                rows.append(header)
                for record in records:
                    rows.append(record)
                csv_writer.writerows(rows)
                csv_writer.writerow([])
                rows=[]
                n += len(records)

        logging.info("wrote %s name(s) in %s list(s) to '%s'" % (n, len(lists), output_path))

    def stdout(self, lines, header):

        print(tuple(header))
        for line in lines:
            print(line)

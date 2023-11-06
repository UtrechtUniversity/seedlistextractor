import logging
import csv
from termcolor import colored

class Output:

    def __init__(self,
                 skip_existing=False) -> None:
        self.skip_existing=skip_existing

    def csv(self, lists, header, output_path):
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


    def stdout(self, lists, header):
        for key, records in enumerate(lists):

            max_col_width=37
            max_lengths={}
            max_col=max([len(row) for row in header])
            for i in range(0, max_col):
                if i not in max_lengths:
                    max_lengths[i]=0

                for row in records:
                    try:
                        max_lengths[i]=len(str(row[i])) if len(str(row[i])) > max_lengths[i] else max_lengths[i]
                        max_lengths[i]=max_col_width if max_lengths[i]>max_col_width else max_lengths[i]
                        max_lengths[i]=len(header[i]) if max_lengths[i]<len(header[i]) else max_lengths[i]
                    except:
                        pass

            pos_colors={'color': 'white', 'on_color': 'on_black'}
            neg_colors={'color': 'black', 'on_color': 'on_light_grey'}
            col_buffer=1

            print(colored(text=f"list #{key+1} ({len(records)})",attrs=['bold']))

            for rkey, record in enumerate(records):

                if rkey==0:
                    for ckey, head in enumerate(header):
                        print(colored(
                            text=f"{head:<{max_lengths[ckey]}}",
                            **(pos_colors)), end="")
                        print(' ' * col_buffer, end="")
                    print()

                    for key in max_lengths:
                        print('-' * max_lengths[key], end="")
                        print(' ' * col_buffer, end="")
                    print()


                for ckey, cell in enumerate(record):
                    mcell=str(cell if cell else '')
                    mcell=mcell if len(mcell)<max_col_width else mcell[:max_col_width-1]+'…'
                    
                    print(
                        colored(
                            text=f"{mcell:<{max_lengths[ckey]}}",
                            **(neg_colors if rkey%2==0 else pos_colors)
                            ), end="")

                    print(
                        colored(
                            text=f"{'┊':<{col_buffer}}",
                            **(pos_colors)
                            ), end="")
                print()
            print()

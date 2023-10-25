import csv
import logging
from termcolor import colored

class Output:

    def __init__(self, config) -> None:
        self.config=config


    def make_rows(self, key, names_list):
        rows=[[f"list #{key+1}"]]
        rows.append(["page", "index", "family", "name", "ipen", "name_residue", "meta"])
        for name in names_list:
            row=[]
            row.append(name['page_nr'])
            row.append(name['list_index_text'] if 'list_index_text' in name else None)
            row.append(name['family_text'] if 'family_text' in name else None)
            row.append(name['name'])
            row.append(name['ipen_text'] if 'ipen_text' in name else None)

            meta=[]
            if 'name_removed' in name:
                meta.extend(name['name_removed'])
            row.append("; ".join(meta))

            meta=[]
            if 'meta' in name:
                meta.extend([getattr(x,'text') for x in name['meta'].itertuples()])
            row.append("; ".join(meta))
            rows.append(row)        
        return rows


    def csv(self, output_path, lists):
        n=0
        with open(output_path, 'w') as file:
            csv_writer=csv.writer(file)
            for key, names_list in enumerate(lists):
                rows=self.make_rows(key=key, names_list=names_list)
                csv_writer.writerows(rows)
                csv_writer.writerow([])
                n += len(names_list)

        logging.info("wrote %s name(s) in %s list(s) to to '%s'" % (n, key+1, output_path))

    def stdout(self, lists):
        for key, names_list in enumerate(lists):
            rows=self.make_rows(key=key, names_list=names_list)

            max_col_width=50
            max_lengths={}
            max_col=max([len(row) for row in rows])
            for i in range(0, max_col):
                if i not in max_lengths:
                    max_lengths[i]=0

                for row in rows:
                    try:
                        max_lengths[i]=len(str(row[i])) if len(str(row[i])) > max_lengths[i] else max_lengths[i]
                        max_lengths[i]=max_col_width if max_lengths[i]>max_col_width else max_lengths[i]
                    except:
                        pass

            pos_colors={'color': 'white', 'on_color': 'on_black'}
            neg_colors={'color': 'black', 'on_color': 'on_light_grey'} if self.config['debug_colored_stdout'] else pos_colors
            col_buffer=1

            for rkey, row in enumerate(rows):         
                if rkey==1:
                    for key in max_lengths:
                        print('-' * max_lengths[key], end="")
                        print(' ' * col_buffer, end="")
                    print()

                for ckey, cell in enumerate(row):
                    mcell=str(cell if cell else '')
                    mcell=mcell if len(mcell)<max_col_width else mcell[:max_col_width-1]+'…'
                    
                    print(
                        colored(
                            text=f"{mcell:<{max_lengths[ckey]}}",
                            **(pos_colors if rkey%2==0 else neg_colors)
                            ), end="")
                    if rkey >0:
                        print(
                            colored(
                                text=f"{'┊':<{col_buffer}}",
                                **(pos_colors)
                                ), end="")
                print()
            print()


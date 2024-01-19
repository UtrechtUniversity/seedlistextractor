import logging
import csv
import statistics
from pathlib import Path
from itertools import groupby

class Output:

    header=['list', 'index', 'family', 'name', 'ipen', 'metadata (rest)' , 'metadata (next)']

    def __init__(self,
                 output_path=None,
                 skip_existing=False) -> None:
        if output_path:
            self.output_path=Path(output_path)
            self.output_path.mkdir(parents=True, exist_ok=True)

        self.skip_existing=skip_existing


    def get_output_path(self, file):
        if self.output_path:
            output_path=self.output_path / Path((Path(file).parts[-1])).with_suffix(".csv")
            output_path=Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            return output_path

    @staticmethod
    def collect_lists(lines):

        def get_item_order(families, names, ipens):
            item_order=['species', 'ipen']

            if len(ipens)==0:
                item_order.remove('ipen')
            else:
                item_order.remove(first)
                item_order.insert(0, first)

            if len(families)>0:
                item_order.insert(0, 'family')

            if len(names)==0:
                item_order=[]

            return item_order

        pages=[]
        groups=[]

        for page, group in groupby(lines, key=lambda x: x['page']):
            groups.append((page, list(group)))

        families=[]
        names=[]
        ipens=[]
        indexes=[]
        first=None
        start_page=None

        for page, group in groups:
            start_page=page if start_page is None else start_page
            empty=0
            empty_sections=[]
            for line in group:
                if len(line['species'])>0 or len(line['ipen'])>0:
                    empty_sections.append(empty)
                    empty=0
                else:
                    empty+=1

                families.append((line['family'], line['line_nr']))
                names.append((line['species'], line['line_nr']))
                ipens.append((line['ipen'], line['line_nr']))
                indexes.append((line['index'], line['line_nr']))

                families=[x for x in families if len(x[0])>0]
                names=[x for x in names if len(x[0])>0]
                ipens=[x for x in ipens if len(x[0])>0]
                indexes=[x for x in indexes if len(x[0])>0]

                if len(line['species'])>0 and first is None:
                    first='species'

                if len(line['ipen'])>0 and first is None:
                    first='ipen'

            empty_sections.append(empty)

            if len(set([x for x in empty_sections if x>0]))>1:
                mean=statistics.mean([x for x in empty_sections if x>0])
                stddev=statistics.stdev([x for x in empty_sections if x>0], xbar=mean)
                list_ends=empty>(mean+stddev)
            else:
                list_ends=False

            if list_ends:
                pages.append({
                    'page': start_page,
                    'families': families,
                    'names': names,
                    'ipens': ipens,
                    'indexes': indexes,
                    'item_order': get_item_order(families, names, ipens),
                    'list_ends': list_ends,
                    'records': []
                    })

                names=[]
                ipens=[]
                indexes=[]
                start_page=None

        if len(names)>0:
            pages.append({
                'page': start_page,
                'families': families,
                'names': names,
                'ipens': ipens,
                'indexes': indexes,
                'item_order': get_item_order(families, names, ipens),
                'list_ends': list_ends,
                'records': []
                })

        return pages

    @staticmethod
    def compile_records(lines, pages):

        def get_assoc_attribute_value(attribute, 
                                      attribute_values, 
                                      item_order, 
                                      current_name, 
                                      prev_name=None, 
                                      next_name=None):

            same_line_match=[x for x in attribute_values if x[1]==current_name[1]]

            if len(same_line_match)>0:
                return same_line_match[0]

            prev=0 if prev_name is None else prev_name[1]
            next=1e6 if next_name is None else next_name[1]

            result=None
            if attribute in item_order:
                if item_order.index(attribute) < item_order.index('species'):
                    candidates=[x for x in attribute_values if x[1]<=current_name[1] and x[1]>prev]
                    candidates=sorted(candidates, key=lambda x: -x[1])
                else:
                    candidates=[x for x in ipens if x[1]>=current_name[1] and x[1]<next]
                    candidates=sorted(candidates, key=lambda x: x[1])
            
                if len(candidates)>0:
                    result=candidates[0]

            return result

        records=[]
        for page in pages:
            if len(page['item_order'])==0:
                continue

            families=page['families'].copy()
            names=page['names'].copy()
            ipens=page['ipens'].copy()
            indexes=page['indexes'].copy()

            prev_name=None

            while len(names)>0:
                current_name=names.pop(0)

                if len(names)>0:
                    next_name=names[0]
                else:
                    next_name=None

                index=get_assoc_attribute_value(
                    attribute='index',
                    item_order=page['item_order'],
                    attribute_values=indexes,
                    current_name=current_name
                )

                if index:
                    indexes.remove(index)

                ipen=get_assoc_attribute_value(
                    attribute='ipen',
                    item_order=page['item_order'],
                    attribute_values=ipens,
                    current_name=current_name,
                    prev_name=prev_name,
                    next_name=next_name
                )

                if ipen:
                    ipens.remove(ipen)

                family=get_assoc_attribute_value(
                    attribute='family',
                    item_order=page['item_order'],
                    attribute_values=families,
                    current_name=current_name
                )

                records.append({
                    'name': current_name,
                    'index': index,
                    'ipen': ipen,
                    'family': family,
                    'meta_rest': lines[current_name[1]]['rest_texts'],
                    'meta_next': lines[current_name[1]]['next_lines']
                    })
                
                prev_name=current_name

            page.update({'records': records})

        return pages

    @staticmethod
    def compile_output(lists):
        lines=[]
        for key, page in enumerate(lists):
            for record in page['records']:
                index=record['index'][0][0] if isinstance(record['index'], tuple) else ''
                family=record['family'][0][0] if isinstance(record['family'], tuple) else ''
                ipen=record['ipen'][0][0] if isinstance(record['ipen'], tuple) else ''
                name=record['name'][0][0]
                lines.append((key, index, family, name, ipen, " ".join(record['meta_rest']), " ".join(record['meta_next'])))
        return lines

    def stdout(self, lines):

        print(tuple(self.header))
        for line in lines:
            print(line)

    def csv(self, lines, output_path):
        if output_path.is_file() and self.skip_existing:
            logging.info("skipped existing file '%s'" % output_path)
            return

        with open(output_path, 'w') as file:
            csv_writer=csv.writer(file)
            csv_writer.writerow(self.header)
            for record in lines:
                csv_writer.writerow(record)

        logging.info("wrote %s name(s) to '%s'" % (len(lines), output_path))

    #TODO: can this go?
    def csv1(self, lists, output_path):
        if output_path.is_file() and self.skip_existing:
            logging.info("skipped existing file '%s'" % output_path)
            return

        n=0
        with open(output_path, 'w') as file:
            rows=[]
            csv_writer=csv.writer(file)
            for key, records in enumerate(lists):
                rows.append([f"list #{key+1} ({len(records)})"])
                rows.append(self.header)
                for record in records:
                    rows.append(record)
                csv_writer.writerows(rows)
                csv_writer.writerow([])
                rows=[]
                n += len(records)

        logging.info("wrote %s name(s) in %s list(s) to '%s'" % (n, len(lists), output_path))


import argparse
import logging
import re
from name_resolver import NameResolver
from utils import InputDocs

class ScanPreprocessor:

    def __init__(self,
                 filename,
                 document,
                 logger,
                 name_resolver) -> None:
        self.logger=logger
        self.name_resolver=name_resolver
        self.filename=filename
        self.document=document
        self.main()

    def get_matches(self, text, matches):
        tokens=text.split()
        for i in range(0, len(tokens)-1):
            match=self.name_resolver.match_exact(lookup=" ".join(tokens[-1*i:]), rank='species')
            if match[0] is not None:
                # self.matches.append(match)
                matches.append(match)
                remains=" ".join(tokens[:-1*i])
                self.get_matches(text=remains, matches=matches)

    
    def main(self):
        # self.document=['1062.	Cryptotaenia canadensis D. C. 1063.	Daucus grandiflorus Scop. 1064.	Eryngium planum L. 1065.	— Serra Cham. et Schlecht. io66.	*Ferula galbaniflua Boiss. et Buchse. 1067 Foeniculum vulgare Mill. 1068^ Heracleum flavescens Baumg. Lagoëcia cuminoides L. m^o. Laserpitium Siler L. 1071. Levisticum officinalis Koch. 1072. — paludapifolium Aschers. 1073. Libanotis montana Crantz. i074	.*Magydaris tomentosa Koch. 1075} Pastinaca sativa L.']
        self.document=['1073. Juniperus phoenicea L. 1074. Koelreuteria formosana Hayata   1075 Pastinaca sativa L.']
        for line in self.document:
            matches=[]
            self.get_matches(text=''.join([x for x in line if x ==' ' or x.isalpha()]).strip(), matches=matches)
            print(line, matches)
            print()
        exit()


if __name__=="__main__":

    parser=argparse.ArgumentParser()
    parser.add_argument('-i','--input-path', type=str, required=True)
    parser.add_argument('-o','--output-path', type=str)
    parser.add_argument('-d','--names-database', type=str)
    parser.add_argument('--ext','--extension', type=str, default=".json")
    parser.add_argument('--force-names-reload', action='store_true', default=False)
    parser.add_argument('--fuzzy-match-threshold', type=float, help='Value of 0<1; None for no fuzzy matching')
    parser.add_argument('--skip-existing', action='store_true', default=False)
    parser.add_argument('--debug', action='store_true', default=False)
    args=parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    logger=logging.getLogger()

    name_resolver=NameResolver(
        names_database=args.names_database,
        force_names_reload=args.force_names_reload,
        logger=logger)

    for filename, document in InputDocs(input_path=args.input_path, extension=args.ext, logger=logger):   

        ScanPreprocessor(
            filename=filename,
            document=document,
            name_resolver=name_resolver,
            logger=logger)


# python scan_preprocess.py -i '/data/seedlists/scans' --ext .txt

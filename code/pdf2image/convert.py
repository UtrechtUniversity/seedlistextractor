import argparse
import logging
import pdf2image
import re
import tika
import cv2
from tika import parser
from PIL import ImageOps
from pathlib import Path
import matplotlib.pyplot as plt

class PdfToImage:

    def __init__(self, 
                 path, 
                 output,
                 img_format=False,
                 grayscale=False,
                 skip_existing=False,
                 remove_lines=False,
                 extract_word_list=True) -> None:
        self.files=[]

        if path:
            p = Path(path)
        
            if p.is_dir():
                self.files=list(p.glob('**/*.pdf'))
            elif p.is_file():
                self.files.append(p)

        if output:
            self.output=Path(output)
            self.output.mkdir(parents=True, exist_ok=True)

        logging.info("got %s file(s) from '%s'" % (len(self.files), p))

        self.grayscale=grayscale
        self.img_format=img_format
        self.extract_word_list=extract_word_list
        self.skip_existing=skip_existing
        self.remove_lines=remove_lines

        if self.grayscale:
            logging.info("converting to grayscale")

        if self.skip_existing:
            logging.info("skipping existing")

        if self.remove_lines:
            logging.info("removing lines")

    def convert(self):
        img_spec=('PNG', '.png')
        if self.img_format=='JPG':
            img_spec=('JPEG', '.jpg')

        for file in self.files:
            path=Path(self.output / file.stem)
            path.mkdir(exist_ok=True)
            try:
                for key, image in enumerate(pdf2image.convert_from_path(pdf_path=file, dpi=200)):

                    image_path=path / Path(f"page_{key:03d}{img_spec[1]}")

                    if self.skip_existing and image_path.exists():
                        logging.debug("skipping '%s' (file exists)" % image_path)
                        continue

                    if self.grayscale:
                        image=self.convert_to_grayscale(image)


                    image.save(image_path, img_spec[0])

                    if self.remove_lines:
                        self.do_remove_lines(image_path)


                logging.info("saved %s images to '%s'" % (str(key+1), path))

            except Exception as e:
                logging.error("couldn't process '%s': %s" % (file, str(e)))

            if self.extract_word_list:
                logging.info("extracting word list")

                word_list_path=path / Path('wordlist.txt')

                if self.skip_existing and word_list_path.exists():
                    logging.debug("skipping '%s' (file exists)" % word_list_path)
                    continue

                word_list=set(self.extract_tokens(path=file))

                with open(word_list_path,'w') as f:
                    for word in word_list:
                        f.write(f'{word}\n')

                logging.info("wrote %s words to '%s'" % (len(word_list), word_list_path))

    def convert_to_grayscale(self, image):
        return ImageOps.grayscale(image)

    def do_remove_lines(self, path):
        image = cv2.imread(str(path))
    
        result = image.copy()
        gray = cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

        # Remove horizontal lines
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50,1))
        remove_horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        
        cnts = cv2.findContours(remove_horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        for c in cnts:
            cv2.drawContours(result, [c], -1, (255,255,255), 5)

        # Remove vertical lines
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1,50))
        remove_vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        #remove_vertical =cv2.dilate(remove_vertical , vertical_kernel, iterations=2)
        cnts = cv2.findContours(remove_vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        for c in cnts:
            cv2.drawContours(result, [c], -1, (255,255,255), 5)

        # out_path=self._make_out_path(file)
        cv2.imwrite(str(path), result)
        logging.info("remove_lines in %s" % path)

    @staticmethod
    def extract_tokens(path):
        tokens=[]
        try:
            parsed = tika.parser.from_file(str(path))
            # print(parsed["metadata"])
            tokens=parsed["content"].split()
        except Exception as e:
            logging.error("couldn't extract tokens from '%s': %s" % (path, str(e)))

        return tokens

    @staticmethod
    def cleanup_word_list(word_list):
        def remove_non_alpha(token):
            return "".join([x for x in token if x.isalpha() or x.isnumeric()])
       
        word_list=[x for x in word_list if not remove_non_alpha(x).isnumeric()]
        word_list=[x for x in word_list if len(remove_non_alpha(x))>3]
        word_list=[re.sub(r'(^[^A-Za-z]{1,}|[^A-Za-z]{1,}$)', '', x) for x in word_list]
        return word_list


if __name__=="__main__":

    logging.basicConfig(level=logging.INFO)

    parser=argparse.ArgumentParser()
    parser.add_argument('-p','--path', required=True)
    parser.add_argument('-o','--output', required=True)
    parser.add_argument('--grayscale', action='store_true')
    parser.add_argument('--img-format', default='PNG', choices=['PNG', 'JPEG'])
    parser.add_argument('--skip-extract-word-list', action='store_true')
    parser.add_argument('--skip-existing', action='store_true', default=False)
    parser.add_argument('--remove-lines', action='store_true', default=False)
    args=parser.parse_args()
    
    pti=PdfToImage(
        path=args.path, 
        output=args.output, 
        grayscale=args.grayscale, 
        img_format=args.img_format,
        skip_existing=args.skip_existing,
        remove_lines=args.remove_lines,
        extract_word_list=not args.skip_extract_word_list)
    pti.convert()


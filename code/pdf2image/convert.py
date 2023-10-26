import argparse
import logging
import pdf2image
import re
import tika
from tika import parser
from PIL import ImageOps
from pathlib import Path

class PdfToImage:

    def __init__(self, 
                 path, 
                 output,
                 img_format=False,
                 grayscale=False,
                 skip_existing=False,
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

        if self.grayscale:
            logging.info("converting to grayscale")

        if self.skip_existing:
            logging.info("skipping existing")


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
    args=parser.parse_args()
    
    pti=PdfToImage(
        path=args.path, 
        output=args.output, 
        grayscale=args.grayscale, 
        img_format=args.img_format,
        skip_existing=args.skip_existing,
        extract_word_list=not args.skip_extract_word_list)
    pti.convert()


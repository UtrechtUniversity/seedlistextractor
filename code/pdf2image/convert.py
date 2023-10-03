import argparse
import logging
import pdf2image
from PIL import ImageOps
from pathlib import Path

class PdfToImage:

    def __init__(self, 
                 path, 
                 output,
                 grayscale=False) -> None:
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

        if self.grayscale:
            logging.info("converting to grayscale")

    def convert(self):
        for file in self.files:
            path=Path(self.output / file.stem)
            path.mkdir(exist_ok=True)
            try:
                for key, image in enumerate(pdf2image.convert_from_path(pdf_path=file, dpi=200)):
                    if self.grayscale:
                        image=self.convert_to_grayscale(image)
                    image.save(path / Path('page_'+ f"{key:03d}" +'.jpg'), 'JPEG')
                logging.info("saved %s images to '%s'" % (str(key+1), path))
            except Exception as e:
                logging.error("couldn't process '%s': %s" % (file, str(e)))

    def convert_to_grayscale(self, image):
        return ImageOps.grayscale(image)


if __name__=="__main__":

    logging.basicConfig(level=logging.DEBUG)

    parser=argparse.ArgumentParser()
    parser.add_argument('-p','--path', required=True)
    parser.add_argument('-o','--output', required=True)
    parser.add_argument('--grayscale', action='store_true')
    args=parser.parse_args()
    
    pti=PdfToImage(path=args.path, output=args.output, grayscale=args.grayscale)
    pti.convert()


import argparse
import cv2
import matplotlib.pyplot as plt
import logging
from pathlib import Path

class ImagePreprocessor:

    def __init__(self, 
                 path,
                 output=None,
                 postfix=None) -> None:
        self.files=[]

        if path:
            p = Path(path)
        
            if p.is_dir():
                self.files=list(p.glob('**/*.jpg'))
            elif p.is_file():
                self.files.append(p)

            self.files.sort()

        logging.info("got %s file(s) from '%s'" % (len(self.files), p))

        self.output=output
        self.postfix=postfix

    def _make_out_path(self, path):
        if self.output is None:
            output=path.parent
        else:
            output=Path(self.output)

        postfix='' if self.postfix is None else self.postfix

        return str(Path(output / f"{path.stem}{postfix}{path.suffix}"))

    def remove_lines(self):
        for file in self.files:
            image = cv2.imread(str(file))
        
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

            out_path=self._make_out_path(file)
            cv2.imwrite(out_path, result)
            logging.info("remove_lines: wrote %s" % out_path)
            # plt.imshow(result)
            # plt.show()



if __name__=="__main__":

    logging.basicConfig(level=logging.INFO)

    parser=argparse.ArgumentParser()
    parser.add_argument('-p','--path', required=True)
    parser.add_argument('-o','--output')
    parser.add_argument('-x','--postfix')
    args=parser.parse_args()
    
    ipp=ImagePreprocessor(
        path=args.path, 
        output=args.output, 
        postfix=args.postfix)
    ipp.remove_lines()




# remove_lines('/data/seedlists/2020_sample_seedlists/jpg/NEU-2020-G-WI-a-1-I/page_001.jpg')
import pickle
import logging
import pytesseract
import pandas as pd
from pathlib import Path
from hashlib import md5
from pytesseract import Output

class OCR:

    def __init__(self, config) -> None:
        self.config=config
        self.pickle_folder=Path(self.config['pickle_folder'])
        self.pickle_folder.mkdir(exist_ok=True)
        self.block_counter=0
        
    def load_pickle(self, file, label):
        try:
            f_hash=md5(str(file).encode('utf-8')).hexdigest()
            p = Path(self.pickle_folder / f"{f_hash}-{label}")
            with open(p, 'rb') as file:
                data=pickle.load(file)
            return data
        except:
            pass

    def save_pickle(self, file, label, data):
        f_hash=md5(str(file).encode('utf-8')).hexdigest()
        p = Path(self.pickle_folder / f"{f_hash}-{label}")
        with open(p, 'wb') as file:
            pickle.dump(data, file)

    def get_ocr_data(self, files, include_pages, force_ocr):
        pages=[]
        for key, file in enumerate(files):

            if include_pages and key not in include_pages:
                continue

            ocr_data=None
            if not force_ocr:
                ocr_data=self.load_pickle(file, "ocr")
            
            if ocr_data is None:

                # better single digit numbers by resizing, but overall drop in recognition
                # image=cv2.imread(str(file))
                # resize_factor=2
                # height, width, _=image.shape
                # image=cv2.resize(image, (height*resize_factor, width*resize_factor), interpolation=cv2.INTER_CUBIC)

                ocr_data=pytesseract.image_to_data(
                        str(file),
                        output_type=Output.DATAFRAME,
                        config=r'--psm 12')

                logging.debug("OCR'd '%s'" % str(file))
                self.save_pickle(file, "ocr", ocr_data)

            pages.append({
                'key': key,
                'page': file.name,
                'page_nr': int(''.join([x for x in file.name if x.isnumeric()])),
                'data': ocr_data})

        return pages

    def preprocess_ocr_data(self, ocr_data):
        # remove rows with empty text cells
        ocr_data=ocr_data[~ocr_data.text.isna()]

        if len(ocr_data)==0:
            return pd.DataFrame()

        # group by block, concat grouped text, take mean of OCR confidence
        ocr_data=(ocr_data
            .groupby('block_num')
            .apply(
                lambda group: pd.Series(
                    [
                        group["left"].min(),
                        group["top"].min(),
                        group["width"].max(),
                        group["height"].max(),
                        group["conf"].mean(),
                        group["text"].astype(str).str.cat(sep=" "),
                    ]
                )
            )
            .reset_index(drop=True)
            .reset_index()
            .rename(
                columns={
                    0: "x_1",
                    1: "y_1",
                    2: "width",
                    3: "height",
                    4: "mean_conf",
                    5: "text",
                    "index": "id",
                }
            )
            .assign(
                x_2=lambda x: x.x_1 + x.width,
                y_2=lambda x: x.y_1 + x.height,
                page_nr=None,
                index=None,
                species_match=None,
                epithet_match=None,
                genus_match=None,
                family_match=None,
                ipen=None,
            ))

        ocr_data.insert(0, 'gid', range(self.block_counter, self.block_counter+len(ocr_data)))
        self.block_counter+=len(ocr_data)

        if self.config['debug_print_ocr_data']:
            print(ocr_data)
            # exit()

        return ocr_data


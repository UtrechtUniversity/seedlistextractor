import argparse
import logging
import json
import tika
from datetime import datetime
from tika import parser
from pathlib import Path
from pprint import pprint

class PdfToText:

    def __init__(self, 
                 path, 
                 output,
                 xml=False,
                 write_text=False,
                 skip_existing=False) -> None:

        tika.TikaClientOnly = True
        self.skip_existing=skip_existing
        self.xml=xml
        self.write_text=write_text
        self.files=[]
        self.output=None

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

    def convert(self):
        for file in self.files:

            if self.output:
                outfile=f"{self.output}/{file.stem}.{'txt' if self.write_text else 'json'}"

            if self.skip_existing and Path(outfile).exists():
                logging.info("skipping '%s' (file exists)" % outfile)
                continue

            doc=self.parse_pdf(path=file, xml=self.xml)
                
            if doc['content']:
                if self.output:
                    self.write_file(outfile=outfile, file=file, doc=doc)
                else:
                    self.write_stdout(doc)
            else:
                logging.warning(f"couldn't read '{file}'")


    def write_file(self, outfile, file, doc):
        with open(outfile, "w") as f_out:
            if self.write_text:
                f_out.write(doc['content'])
            else:
                json.dump({
                    'filename': f"{file.stem}{file.suffix}",
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'parser': f"{tika.__name__} {tika.__version__} (Python)",
                    'document': doc, 
                }, f_out)
        logging.info(f"wrote {len(doc['content'].split()):,} tokens to '{outfile}'")

    def write_stdout(self, doc):
        pprint(doc['content'])

    @staticmethod
    def parse_pdf(path, xml=False):
        if xml:
            parsed=tika.parser.from_file(str(path), xmlContent=True)
        else:
            parsed=tika.parser.from_file(str(path))

        return {
            'metadata': parsed["metadata"],
            'content': parsed["content"]
        }

if __name__=="__main__":

    logging.basicConfig(level=logging.INFO)

    parser=argparse.ArgumentParser()
    parser.add_argument('-p','--path', required=True)
    parser.add_argument('-o','--output')
    parser.add_argument('--xml', action='store_true', default=False, help='Write document body as XML')
    parser.add_argument('--write-text', action='store_true', default=False, help='Write only body text (as .txt)')
    parser.add_argument('--skip-existing', action='store_true', default=False)
    args=parser.parse_args()

    ptt=PdfToText(
        path=args.path, 
        output=args.output,
        xml=args.xml,
        write_text=args.write_text,
        skip_existing=args.skip_existing)

    ptt.convert()

import shutil
import logging

class Checks:

    def __init__(self,
                 file,
                 output, 
                 header,
                 raise_exception=False) -> None:
        self.file=file
        self.output=output
        self.header=header
        self.raise_exception=raise_exception
        self.errors=0

    def report(self, msg):
        if self.raise_exception:
            raise ValueError(msg)
        logging.warning(msg)

    def check_families(self,
                       families_seen):
        fam_key=self.header.index('family')
        seen=set(families_seen)
        used=[]
        for records in self.output:
            for record in records:
                for cell in [v for k, v in enumerate(record) if k==fam_key]:
                    used.append(cell)

        #TODO: magic number
        if (len(set(used))/len(seen))<0.9:
            self.errors+=1
            self.report("of %s family names in document only %s appear in output" % (len(seen), len(set(used))))

    def copy_erroneous(self, target_path):
        if self.errors>0 and target_path:
            shutil.copy(self.file, target_path)
            logging.info("copied erroneous file '%s' to '%s" % (self.file, target_path))

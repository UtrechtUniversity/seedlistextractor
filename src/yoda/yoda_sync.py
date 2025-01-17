from getpass import getpass
from ibridges.data_operations import sync
from ibridges.path import IrodsPath
from ibridges.session import Session
from pathlib import Path
from typing import Union

class YodaSync:

    def __init__(self,
                 irods_env: dict,
                 password: str,
                 irods_path: str,
                 local_path: Path,
                 action: str,
                 overwrite: bool,
                 copy_empty_folders: bool,
                 out_file: Path,
                 dry_run: bool = False,
                 file_mask: Union[str, list[str]] = ['.txt', '.tsv']):

        if isinstance(file_mask, str):
            file_mask = [file_mask]
        elif not isinstance(file_mask, list) and file_mask is not None:
            raise ValueError("file_mask should be a string or a list of strings (omit for no mask)")

        if action not in ['upload', 'download']:
            raise ValueError("%s is not a valid action", action)

        session = Session(irods_env=irods_env, password=password)
        remote_path = IrodsPath(session, irods_path)

        print(f"Source: {remote_path if action=='download' else local_path}")
        print(f"Target: {local_path if action=='download' else remote_path}")
        print(f"Calculating...")

        ops = sync(session=session,
                   source=remote_path if action=='download' else local_path,
                   target=local_path if action=='download' else remote_path,
                   copy_empty_folders=False,
                   dry_run=True)

        if file_mask:
            ops.download = [x for x in ops.download if Path(str(x[0])).suffix in file_mask]
            ops.upload = [x for x in ops.upload if Path(str(x[0])).suffix in file_mask]

        if action=='download':
            print(f"Downloading {len(ops.download)} files")
        else:
            print(f"Uploading {len(ops.upload)} files")

        if not dry_run:
            ops.execute(session=session)
        else:
            print()
            print("Dry run, not executing operations")
            print()

        if out_file:
            f_out = open(out_file, 'w')
            f_out.write("source\ttarget\n")
        else:
            f_out = None


        if action=='download':
            print("Files downloaded:")

            w_max = max([len(str(x[0])) for x in ops.download])-len(str(remote_path))+1

            for file in ops.download:
                print(f"{str(file[0])[len(str(remote_path))+1:]:<{w_max}}{'--> ':<5}{str(file[1])[len(str(local_path))+1:]}")
                if f_out:
                    f_out.write(f"{str(file[0])}\t{str(file[1])}\n")
        else:
            print("Files uploaded:")

            w_max = max([len(str(x[0])) for x in ops.upload])-len(str(local_path))+1

            for file in ops.upload:
                print(f"{str(file[0])[len(str(local_path))+1:]:<{w_max}}{'--> ':<5}{str(file[1])[len(str(remote_path))+1:]}")
                if f_out:
                    f_out.write(f"{str(file[0])}\t{str(file[1])}\n")


if __name__=="__main__":

    import argparse
    import json

    argparse = argparse.ArgumentParser()
    argparse.add_argument('--env_path', type=str, required=True)
    argparse.add_argument('--irods_path', type=str, required=True)
    argparse.add_argument('--local_path', type=Path, required=True)
    argparse.add_argument('--out_file', type=Path)
    argparse.add_argument('--action', choices=["upload", "download"], required=True)
    argparse.add_argument('--overwrite', action='store_false', default=True)
    argparse.add_argument('--copy_empty_folders', action='store_true', default=False)
    argparse.add_argument('--dry_run', action='store_true', default=False)
    args = argparse.parse_args()
   
    with open(args.env_path, 'r') as f:
        irods_env = json.load(f)

    password = getpass(f"Data access password for {irods_env['irods_user_name']}@{irods_env['irods_host']}: ")
  
    YodaSync(
        irods_env=irods_env, 
        password=password,
        irods_path=args.irods_path,
        local_path=args.local_path,
        file_mask=['.txt', '.tsv'],
        action=args.action,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        copy_empty_folders=args.copy_empty_folders,
        out_file=args.out_file
    )    

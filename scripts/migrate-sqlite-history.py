"""Import old local completed reports into the configured v1.9 database."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from researchops_backend.storage.repository import Repository

parser=argparse.ArgumentParser()
parser.add_argument('old_database',type=Path)
args=parser.parse_args()
source=args.old_database.resolve()
if not source.is_file():raise SystemExit('Old database was not found.')
repo=Repository()
if repo.engine.dialect.name=='sqlite' and Path(repo.engine.url.database).resolve()==source:
    raise SystemExit('Use a different v1.9 destination database. Keep the old file as a backup.')
old=sqlite3.connect(f'file:{source.as_posix()}?mode=ro',uri=True);old.row_factory=sqlite3.Row
imported=0
for row in old.execute("SELECT * FROM jobs WHERE status='completed' AND result_json IS NOT NULL"):
    if repo.get(row['id'],include_archived=True):continue
    request=json.loads(row['request_json'] or '{}')
    if repo.import_completed(row['id'],row['question'],request,json.loads(row['result_json'])):imported+=1
old.close()
print(f'Imported {imported} completed reports. Original database was read-only and unchanged.')

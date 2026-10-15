"""Consistent complete SQLite backup and offline restore, including accounts and files."""
import argparse
import os
from pathlib import Path
import shutil
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument('command', choices=['backup','restore'])
parser.add_argument('path', help='backup SQLite file path')
args = parser.parse_args()
live = Path(os.environ.get('DATA_DIR','./data')).resolve() / 'housing.sqlite3'
snapshot = Path(args.path).resolve()
if snapshot == live:
    raise SystemExit('Backup must be a different file')
if args.command == 'backup':
    if not live.exists() or snapshot.exists():
        raise SystemExit('Source missing or destination already exists')
    snapshot.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(f'{live.as_uri()}?mode=ro',uri=True) as source, sqlite3.connect(snapshot) as destination:
        source.backup(destination)
    print('Complete backup saved. Contains password hashes and private files; keep private.')
else:
    if not snapshot.exists() or live.exists():
        raise SystemExit('Stop the service and move the existing database and WAL/SHM files aside before restoring')
    with sqlite3.connect(f'{snapshot.as_uri()}?mode=ro',uri=True) as source:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('Backup is damaged')
        for table in ('parts','users','sessions','audit','meta'):
            source.execute('SELECT 1 FROM '+table+' LIMIT 1')
        live.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(live) as destination:
            source.backup(destination)
            destination.execute('DELETE FROM sessions')
            destination.commit()
    print('Restored. All users must log in again.')

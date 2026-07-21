"""Switch FinTracker between your real data and dummy/sample data — safely.

  python demo_data.py dummy     # back up real data, then load sample/dummy data
  python demo_data.py restore   # restore the most recent real-data backup
  python demo_data.py backup    # just make a timestamped backup, change nothing

Backups live in instance/backups/. Your real data is copied to a
finance-REAL-<timestamp>.db backup before anything is overwritten, so this is
non-destructive. Stop the app before running.
"""
import os
import sys
import glob
import shutil
import subprocess
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
INST = os.path.join(BASE, 'instance')
DB = os.path.join(INST, 'finance.db')
BACKUPS = os.path.join(INST, 'backups')


def _ts():
    return datetime.now().strftime('%Y%m%d-%H%M%S')


def backup(tag='REAL'):
    """Copy the current DB to instance/backups/finance-<tag>-<ts>.db. Returns path or None."""
    os.makedirs(BACKUPS, exist_ok=True)
    if not os.path.exists(DB) or os.path.getsize(DB) == 0:
        print('No current database to back up.')
        return None
    dest = os.path.join(BACKUPS, f'finance-{tag}-{_ts()}.db')
    shutil.copy2(DB, dest)
    print(f'Backed up current data → {dest}')
    return dest


def _remove_db_files():
    for f in glob.glob(DB + '*'):     # finance.db, finance.db-wal, finance.db-shm
        try:
            os.remove(f)
        except OSError:
            pass


def load_dummy():
    backup('REAL')                    # safeguard your real data first
    _remove_db_files()
    print('Loading dummy/sample data…')
    subprocess.run([sys.executable, os.path.join(BASE, 'init_db.py'), '--force'], check=False)
    print('Done. Dummy data is active. Your real data is safe in instance/backups/finance-REAL-*.db')


def restore():
    reals = sorted(glob.glob(os.path.join(BACKUPS, 'finance-REAL-*.db')))
    if not reals:
        print('No finance-REAL-*.db backup found in instance/backups/. Nothing to restore.')
        return
    latest = reals[-1]
    backup('DUMMY')                   # keep the dummy state too, just in case
    _remove_db_files()
    shutil.copy2(latest, DB)
    print(f'Restored your real data from {latest}')


if __name__ == '__main__':
    cmd = (sys.argv[1] if len(sys.argv) > 1 else '').lower()
    if cmd == 'dummy':
        load_dummy()
    elif cmd == 'restore':
        restore()
    elif cmd == 'backup':
        backup('MANUAL')
    else:
        print(__doc__)

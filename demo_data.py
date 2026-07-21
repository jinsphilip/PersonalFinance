"""Switch FinTracker between your real data and dummy/sample data — safely.

  python demo_data.py list             # show every backup with its row counts
  python demo_data.py dummy            # back up real data, then load sample data
  python demo_data.py restore          # restore the newest REAL backup
  python demo_data.py restore <file>   # restore a specific backup (from `list`)
  python demo_data.py backup           # just make a timestamped backup

Backups live in instance/backups/. Real data is copied to a backup before it's
overwritten, so this is non-destructive. Stop the app before running.

A marker file (instance/.is_dummy) tracks whether the active DB is dummy data,
so switching to dummy twice never mislabels dummy data as a REAL backup.
"""
import os
import sys
import glob
import shutil
import sqlite3
import subprocess
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
INST = os.path.join(BASE, 'instance')
DB = os.path.join(INST, 'finance.db')
BACKUPS = os.path.join(INST, 'backups')
MARKER = os.path.join(INST, '.is_dummy')


def _ts():
    return datetime.now().strftime('%Y%m%d-%H%M%S')


def _counts(path):
    """(stocks, mutual_funds, accounts) row counts for a DB file; -1 on error."""
    try:
        con = sqlite3.connect(f'file:{path}?immutable=1', uri=True)
        out = tuple(con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                    for t in ('stocks', 'mutual_funds', 'accounts'))
        con.close()
        return out
    except Exception:
        return (-1, -1, -1)


def backup(tag='REAL'):
    os.makedirs(BACKUPS, exist_ok=True)
    if not os.path.exists(DB) or os.path.getsize(DB) == 0:
        print('No current database to back up.')
        return None
    dest = os.path.join(BACKUPS, f'finance-{tag}-{_ts()}.db')
    shutil.copy2(DB, dest)
    print(f'Backed up current data → {os.path.basename(dest)}')
    return dest


def _remove_db_files():
    for f in glob.glob(DB + '*'):     # finance.db, -wal, -shm
        try:
            os.remove(f)
        except OSError:
            pass


def list_backups():
    files = sorted(glob.glob(os.path.join(BACKUPS, 'finance-*.db')))
    if not files:
        print('No backups in instance/backups/.')
        return
    print(f'{"file":42} {"size":>8}  stocks  funds  accounts')
    print('-' * 76)
    for f in files:
        s, m, a = _counts(f)
        kb = os.path.getsize(f) // 1024
        print(f'{os.path.basename(f):42} {kb:>6}KB  {s:>6}  {m:>5}  {a:>8}')
    if os.path.exists(DB):
        s, m, a = _counts(DB)
        print('-' * 76)
        print(f'{"(current) finance.db":42} {os.path.getsize(DB)//1024:>6}KB  {s:>6}  {m:>5}  {a:>8}')
    print('\nRestore a specific one with:  python demo_data.py restore <file>')


def load_dummy():
    # Only back up as REAL if the active DB isn't already dummy (avoids mislabeling).
    if os.path.exists(MARKER):
        print('Active data is already dummy — not creating a REAL backup.')
    else:
        backup('REAL')
    _remove_db_files()
    print('Loading dummy/sample data…')
    subprocess.run([sys.executable, os.path.join(BASE, 'init_db.py'), '--force'], check=False)
    open(MARKER, 'w').close()          # mark active DB as dummy
    print('Done. Dummy data is active. Real data is in instance/backups/finance-REAL-*.db')


def restore(which=None):
    if which:
        src = which if os.path.isabs(which) else os.path.join(BACKUPS, which)
        if not os.path.exists(src):
            print(f'Not found: {src}'); return
    else:
        reals = sorted(glob.glob(os.path.join(BACKUPS, 'finance-REAL-*.db')))
        if not reals:
            print('No finance-REAL-*.db backup found. Run `python demo_data.py list` '
                  'and restore a specific file.'); return
        src = reals[-1]
    backup('PRE-RESTORE')             # snapshot whatever is active now
    _remove_db_files()
    shutil.copy2(src, DB)
    if os.path.exists(MARKER):
        os.remove(MARKER)             # restored DB is treated as real
    print(f'Restored from {os.path.basename(src)}  ({_counts(src)[0]} stocks)')


if __name__ == '__main__':
    cmd = (sys.argv[1] if len(sys.argv) > 1 else '').lower()
    if cmd == 'list':
        list_backups()
    elif cmd == 'dummy':
        load_dummy()
    elif cmd == 'restore':
        restore(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == 'backup':
        backup('MANUAL')
    else:
        print(__doc__)

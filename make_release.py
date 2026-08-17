"""Build a shareable FinTracker deployment package.

  python make_release.py

Produces  dist/FinTracker-<YYYYMMDD>.zip  containing a clean copy of the app
with a freshly-seeded demo database and setup instructions — ready to hand to
someone else. The recipient just unzips and runs run.bat (Windows) or
./run.sh (macOS/Linux); the launcher builds a virtualenv, installs
dependencies and starts the app at http://localhost:5000.

What is EXCLUDED (never shipped): your real data (instance/, *.db, backups/),
secrets (set_api_key.bat, password.txt, .flask_secret), and local build junk
(venv/, __pycache__/, dist/, build/, node_modules/, .git/).
"""
import io
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
PKG = 'FinTracker'                     # top-level folder inside the zip
EXCLUDE_DIRS = {'venv', '.venv', 'env', '.git', '__pycache__', 'backups',
                'dist', 'build', 'node_modules', 'instance', '.idea', '.vscode'}
EXCLUDE_FILES = {'set_api_key.bat', 'password.txt', '.flask_secret', '.DS_Store'}
EXCLUDE_EXT = ('.db', '.db-wal', '.db-shm', '.sqlite3', '.pyc')

INSTALL_MD = """# FinTracker — Install & Run

A personal finance tracker (Flask + SQLite). This package includes **sample
seed data** so you can explore it immediately, then replace it with your own.

## Requirements
- **Python 3.9+** installed and on your PATH  (https://www.python.org/downloads/)
  - On Windows, tick **"Add Python to PATH"** in the installer.

## Run it

### Windows
1. Unzip this folder anywhere.
2. Double-click **run.bat**  (or run it from a terminal).
3. Your browser opens at **http://localhost:5000**.

### macOS / Linux
1. Unzip this folder anywhere.
2. In a terminal:  `cd FinTracker && ./run.sh`
   (first time only: `chmod +x run.sh`)
3. Open **http://localhost:5000** in your browser.

The first launch creates a virtual environment and installs dependencies
(takes a minute); later launches are instant.

## Your data
- Data lives in **instance/finance.db** on your machine — nothing is uploaded.
- This package ships with **demo data**. To start clean, stop the app, delete
  `instance/finance.db`, and run the launcher again to reseed sample data — or
  just edit/delete the sample entries in the UI.
- Back up your data by copying `instance/finance.db` somewhere safe.

## Optional features (safe to ignore)
- **AI Portfolio Analysis / AI Analyst**: copy `set_api_key.bat.example` to
  `set_api_key.bat` and add an Anthropic API key. Without it, those pages are
  simply disabled — the rest of the app works fully.
- **Login password / remote access**: see `set_api_key.bat.example`.

## Troubleshooting
- *"Python was not found"* → install Python 3 and reopen the terminal.
- *Port 5000 in use* → stop the other app, or change the port at the bottom of
  `app.py`.
- Excel export needs `openpyxl` — it's installed automatically by the launcher.
"""


def _seed_demo_db():
    """Run init_db against a throwaway path and return the seeded bytes."""
    fd, tmp = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.remove(tmp)                     # let the app create it fresh
    env = dict(os.environ, FINTRACKER_DB=tmp)
    print('Seeding demo database…')
    subprocess.run([sys.executable, 'init_db.py', '--force'],
                   cwd=BASE, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    # The app runs SQLite in WAL mode, so freshly written data can still live in
    # the -wal sidecar. Fold it into the main file (and drop the WAL) so the
    # single shipped finance.db is complete and self-contained.
    import sqlite3
    con = sqlite3.connect(tmp)
    con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    con.execute('PRAGMA journal_mode=DELETE')
    con.commit()
    con.close()
    with open(tmp, 'rb') as f:
        data = f.read()
    for suffix in ('', '-wal', '-shm'):
        try:
            os.remove(tmp + suffix)
        except OSError:
            pass
    return data


def _iter_files():
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f in EXCLUDE_FILES or f.endswith(EXCLUDE_EXT):
                continue
            full = os.path.join(root, f)
            yield full, os.path.relpath(full, BASE)


def main():
    out_dir = os.path.join(BASE, 'dist')
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f'FinTracker-{date.today().isoformat()}.zip')

    seed = _seed_demo_db()

    print('Building package…')
    n = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for full, rel in _iter_files():
            z.write(full, f'{PKG}/{rel}')
            n += 1
        z.writestr(f'{PKG}/instance/finance.db', seed)      # pre-seeded demo data
        z.writestr(f'{PKG}/INSTALL.md', INSTALL_MD)
    size = os.path.getsize(zip_path) / 1024
    print(f'\nDone: {zip_path}')
    print(f'  {n} files + seeded instance/finance.db  ({size:.0f} KB)')
    print('  Share this zip. Recipient: unzip, then run run.bat (Windows) or ./run.sh (mac/Linux).')


if __name__ == '__main__':
    main()

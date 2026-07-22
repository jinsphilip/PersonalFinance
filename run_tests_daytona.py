"""Run the FinTracker test suite inside a fresh Daytona sandbox.

  python run_tests_daytona.py

Packages this project (excluding venv/instance/.git/backups), uploads it to a
throwaway Daytona sandbox, installs dependencies + pytest, runs the tests against
a temp DB, prints the output, and deletes the sandbox. Isolated CI without a
local test environment.

Requires DAYTONA_API_KEY in the environment (or in set_api_key.bat, which the app
loads — here, export it or set it before running).
"""
import io
import os
import sys
import tarfile

BASE = os.path.dirname(os.path.abspath(__file__))
EXCLUDE = {'venv', '.venv', 'instance', '.git', '__pycache__', 'backups', 'dist', 'build', 'node_modules'}


def _tarball():
    """Tar.gz of the repo (secrets and heavy/local dirs excluded)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for root, dirs, files in os.walk(BASE):
            dirs[:] = [d for d in dirs if d not in EXCLUDE]
            for f in files:
                if f in ('set_api_key.bat', 'password.txt', '.flask_secret') or f.endswith(('.db', '.db-wal', '.db-shm')):
                    continue
                full = os.path.join(root, f)
                tar.add(full, arcname=os.path.relpath(full, BASE))
    return buf.getvalue()


def main():
    key = os.environ.get('DAYTONA_API_KEY')
    if not key:
        print('DAYTONA_API_KEY is not set. Export it (or set it in your shell) and retry.')
        sys.exit(2)
    try:
        from daytona import Daytona, DaytonaConfig
    except ImportError:
        print('The `daytona` package is not installed. Run: pip install daytona')
        sys.exit(2)

    daytona = Daytona(DaytonaConfig(api_key=key))
    sandbox = None
    try:
        print('Creating sandbox…')
        sandbox = daytona.create()
        print('Uploading project…')
        sandbox.fs.upload_file(_tarball(), '/tmp/app.tar.gz')
        cmd = ('set -e; mkdir -p /tmp/app && tar xzf /tmp/app.tar.gz -C /tmp/app && '
               'cd /tmp/app && pip install -q -r requirements-dev.txt && '
               'FINTRACKER_DB=/tmp/test.db python -m pytest -q')
        print('Running tests in the sandbox…\n')
        resp = sandbox.process.exec(cmd)
        out = getattr(resp, 'result', None) or str(resp)
        print(out)
        code = getattr(resp, 'exit_code', None)
        if code not in (None, 0):
            sys.exit(1)
    finally:
        if sandbox is not None:
            for attempt in (lambda: sandbox.delete(),
                            lambda: daytona.delete(sandbox),
                            lambda: daytona.remove(sandbox)):
                try:
                    attempt()
                    break
                except Exception:
                    continue


if __name__ == '__main__':
    main()

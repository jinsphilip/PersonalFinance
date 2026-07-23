"""Launch FinTracker inside a Daytona sandbox and get a public preview URL.

  python run_preview_daytona.py

Uploads this project to a fresh Daytona sandbox, seeds a throwaway demo
database, starts the real Flask server on 0.0.0.0:5000, and prints a public
preview URL you can open in any browser or on your phone. Nothing touches your
machine or your real portfolio.

Because the app blocks remote access unless a login password is set, this sets a
demo password inside the sandbox and prints it so you can log in.

The sandbox is LEFT RUNNING so you can keep using the URL. Stop it when done —
either press Ctrl-C here (it will delete the sandbox) or delete it from
https://app.daytona.io/dashboard/sandboxes.

Requires DAYTONA_API_KEY in the environment (see set_api_key.bat).
"""
import io
import os
import sys
import tarfile

BASE = os.path.dirname(os.path.abspath(__file__))
EXCLUDE = {'venv', '.venv', 'instance', '.git', '__pycache__', 'backups', 'dist', 'build', 'node_modules'}
PORT = 5000
DEMO_PASSWORD = os.environ.get('FINTRACKER_DEMO_PASSWORD', 'fintracker')

REMOTE_SCRIPT = r'''
set -e
cd /tmp/app
pip install -q -r requirements.txt
export FINTRACKER_DB=/tmp/preview.db
export FINTRACKER_PASSWORD='__PASSWORD__'
python init_db.py --force
# Bind to 0.0.0.0 so the Daytona preview proxy can reach it.
nohup python -c "import app; app.app.run(host='0.0.0.0', port=__PORT__, debug=False)" > /tmp/server.log 2>&1 &
for i in $(seq 1 40); do
  if curl -sf -o /dev/null http://127.0.0.1:__PORT__/login; then echo "server up"; exit 0; fi
  sleep 0.5
done
echo "server did not start"; tail -n 30 /tmp/server.log; exit 1
'''


def _tarball():
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


def _preview_url(sandbox):
    """Preview link across SDK versions; returns (url, token) or (None, None)."""
    for call in (lambda: sandbox.get_preview_link(PORT),
                 lambda: sandbox.get_preview_url(PORT)):
        try:
            link = call()
        except Exception:
            continue
        url = getattr(link, 'url', None) or (link if isinstance(link, str) else None)
        token = getattr(link, 'token', None)
        if url:
            return url, token
    return None, None


def main():
    key = os.environ.get('DAYTONA_API_KEY')
    if not key:
        print('DAYTONA_API_KEY is not set. Run `call set_api_key.bat` first, then retry.')
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
        script = (REMOTE_SCRIPT.replace('__PASSWORD__', DEMO_PASSWORD)
                  .replace('__PORT__', str(PORT)))
        sandbox.fs.upload_file(script.encode(), '/tmp/_preview.sh')
        print('Installing deps, seeding demo data, starting the server…')
        resp = sandbox.process.exec(
            'mkdir -p /tmp/app && tar xzf /tmp/app.tar.gz -C /tmp/app && bash /tmp/_preview.sh')
        out = getattr(resp, 'result', None) or str(resp)
        print(out)
        if getattr(resp, 'exit_code', 0) not in (None, 0):
            sys.exit(1)

        url, token = _preview_url(sandbox)
        print('\n' + '=' * 60)
        if url:
            print('FinTracker is live at:\n    ' + url)
        else:
            print('Server is running on port %d, but I could not fetch a preview\n'
                  'URL from this SDK version. Open the sandbox in the Daytona\n'
                  'dashboard and expose port %d manually.' % (PORT, PORT))
        if token:
            print('\nPreview access token (if the URL asks for one):\n    ' + token)
        print('\nLog in with password:  ' + DEMO_PASSWORD)
        print('=' * 60)
        print('\nSandbox is LEFT RUNNING. Press Ctrl-C here to stop and delete it,')
        print('or delete it later at https://app.daytona.io/dashboard/sandboxes')
        try:
            input('\nPress Enter (or Ctrl-C) to shut down the sandbox… ')
        except (KeyboardInterrupt, EOFError):
            pass
    finally:
        if sandbox is not None:
            print('\nDeleting sandbox…')
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

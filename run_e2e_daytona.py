"""Boot the FinTracker app inside a fresh Daytona sandbox and smoke-test it live.

  python run_e2e_daytona.py

Unlike run_tests_daytona.py (which runs pytest), this starts the *real* Flask
server on a throwaway demo database inside the sandbox, then hits its actual
HTTP endpoints — the same requests a browser makes — and reports pass/fail for
each. Nothing touches your machine or your real data; the sandbox is deleted at
the end.

Requires DAYTONA_API_KEY in the environment (see set_api_key.bat).
"""
import io
import os
import sys
import tarfile

BASE = os.path.dirname(os.path.abspath(__file__))
EXCLUDE = {'venv', '.venv', 'instance', '.git', '__pycache__', 'backups', 'dist', 'build', 'node_modules'}

# Runs *inside* the sandbox: seed a demo DB, start the server, curl endpoints.
REMOTE_SCRIPT = r'''
set -e
cd /tmp/app
pip install -q -r requirements.txt

export FINTRACKER_DB=/tmp/e2e.db
# Fresh demo data in the throwaway DB (never the real one).
python init_db.py --force

# Start the real server in the background; disable the debug reloader.
FLASK_RUN_FROM_CLI=false nohup python -c "import app; app.app.run(host='127.0.0.1', port=5000, debug=False)" > /tmp/server.log 2>&1 &
SERVER_PID=$!

# Wait for it to come up (up to ~20s).
for i in $(seq 1 40); do
  if curl -sf -o /dev/null http://127.0.0.1:5000/api/dashboard; then break; fi
  sleep 0.5
done

python - <<'PY'
import json, sys, urllib.request
BASE = "http://127.0.0.1:5000"
def check(path, want=200, kind=None):
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            body = r.read()
            ok = r.status == want
            note = ""
            if kind == "json":
                data = json.loads(body)
                note = f"{type(data).__name__}"
                if isinstance(data, list): note += f"[{len(data)}]"
            elif kind == "html":
                note = f"{len(body)} bytes"
            print(f"  {'PASS' if ok else 'FAIL'}  {r.status}  {path}  {note}")
            return ok
    except Exception as e:
        print(f"  FAIL  ---  {path}  {e}")
        return False

print("\nEndpoint smoke test:")
results = [
    check("/", kind="html"),
    check("/stocks", kind="html"),
    check("/api/dashboard", kind="json"),
    check("/api/accounts", kind="json"),
    check("/api/stocks", kind="json"),
    check("/api/mutual-funds", kind="json"),
    check("/api/loans", kind="json"),
    check("/api/categories", kind="json"),
]
print(f"\n{sum(results)}/{len(results)} endpoints passed")
sys.exit(0 if all(results) else 1)
PY
RC=$?
kill $SERVER_PID 2>/dev/null || true
echo "--- server.log (tail) ---"
tail -n 20 /tmp/server.log || true
exit $RC
'''


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
        sandbox.fs.upload_file(REMOTE_SCRIPT.encode(), '/tmp/_e2e_remote.sh')
        cmd = 'mkdir -p /tmp/app && tar xzf /tmp/app.tar.gz -C /tmp/app && bash /tmp/_e2e_remote.sh'
        print('Booting the app and smoke-testing it…')
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

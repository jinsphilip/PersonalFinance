#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
#  FinTracker - one-click launcher for macOS / Linux
#  Creates a virtual environment, installs dependencies, seeds the database
#  on first run, then starts the app at http://localhost:5000
# ──────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if [ ! -x "venv/bin/python" ]; then
    echo "[setup] Creating virtual environment..."
    "$PY" -m venv venv
fi

VPY="venv/bin/python"

echo "[setup] Installing dependencies..."
"$VPY" -m pip install --upgrade pip >/dev/null
"$VPY" -m pip install -r requirements.txt

if [ ! -f "finance.db" ] && [ ! -f "instance/finance.db" ]; then
    echo "[setup] Initialising database with sample data..."
    "$VPY" init_db.py
fi

echo
echo "[run] Starting FinTracker at http://localhost:5000  (Ctrl+C to stop)"
echo
"$VPY" app.py

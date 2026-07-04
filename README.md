# PersonalFinance — FinTracker

A self-hosted personal finance tracker that brings your whole financial life into one
dashboard: mutual funds across platforms, stocks across demat accounts, bank accounts,
loans (housing/car), chit funds, fixed deposits, interest-free credits given to friends,
and income from salary + dividends. Amounts in INR.

![Net worth, assets vs liabilities, and asset allocation at a glance.](#)

## Features

- **Dashboard** — net worth, asset-allocation doughnut, assets-vs-liabilities chart, recent income.
- **Mutual Funds** — holdings per platform with **live NAVs** from AMFI.
- **Stocks** — holdings grouped by demat account with **live prices** from Yahoo Finance.
- **Bank Accounts**, **Fixed Deposits**, **Loans** (with payoff progress), **Chit Funds**
  (auction status), **Credits Given** (repayment status), **Income** (salary + dividends).
- Full add / edit / delete on every module; one-click **Refresh Prices**.

## Quick Start

**One-click launcher** (creates a virtual environment, installs dependencies, seeds the
database on first run, and starts the app):

- **Windows** — double-click `run.bat` (or run it from a terminal).
- **macOS / Linux** — `bash run.sh`

**Manual** (if you prefer to run the steps yourself):

```bash
python -m pip install -r requirements.txt
python init_db.py     # initialise finance.db with sample data (first run only)
python app.py         # http://localhost:5000
```

> On Windows, if `python` isn't found use the launcher: `py -3 -m pip install ...`.
> Using a virtual environment (`python -m venv venv`) is recommended — the launcher
> scripts above do this for you.

Open <http://localhost:5000> in your browser.

## Live Prices

Click **Refresh NAVs / Prices** on the Mutual Funds or Stocks page, or
`POST /api/refresh-prices`. Mutual funds need an **AMFI scheme code**; stocks use the
**ticker + exchange** (NSE/BSE). Symbols that can't be fetched keep their stored value.

## Access from your phone

The app runs on your PC and can be opened from a phone. There are two levels.

### Same Wi-Fi (LAN)
1. Ensure your phone and PC are on the same network.
2. On the PC, find its IP: `ipconfig` → **IPv4 Address** (e.g. `192.168.1.42`).
3. On the phone browser open `http://192.168.1.42:5000`.
4. Allow **Python** through the Windows Firewall when prompted (Private networks).

> The app must listen on all interfaces for this. If it only binds to
> `127.0.0.1`, change the last line of `app.py` to
> `app.run(host='0.0.0.0', port=5000, debug=True)`.

### Any network (internet) — via a tunnel
This exposes your PC's app over the internet, so **set a login password first**
(see below). Then use a tunnel; the app only needs to listen on `localhost:5000`.

**One-click (`run_remote.bat`, recommended):** uses **ngrok** with a stable
static domain so the phone URL never changes. Setup:
1. Install ngrok: `winget install --id ngrok.ngrok`, then once:
   `ngrok config add-authtoken <your-token>`.
2. Create a free static domain at ngrok.com → **Domains** (e.g.
   `yourname.ngrok-free.dev`).
3. In `set_api_key.bat` set `FINTRACKER_PASSWORD` and
   `NGROK_DOMAIN=yourname.ngrok-free.dev`.
4. Run **`run_remote.bat`** — it starts the app and opens
   `https://<NGROK_DOMAIN>`, refusing to run without a password. Same URL every
   time.

**Manual alternatives:**
- ngrok: `ngrok http --url=yourname.ngrok-free.dev 5000` (stable) or
  `ngrok http 5000` (random URL).
- Cloudflare quick tunnel: `cloudflared tunnel --url http://localhost:5000`
  (random URL each run; a *named* tunnel with your own domain gives a stable one).

Keep the PC on and the app running while you use it remotely. If you want it
online without your PC, host it (Render/Railway/Fly.io/PythonAnywhere) instead.

## Authentication (login password)

A session login is built in and **off by default** (frictionless local use).
The password is resolved from the first of: the `FINTRACKER_PASSWORD`
**environment variable**, a plain **`password.txt`** file, or your
`set_api_key.bat` — so it works no matter how you launch (`run.bat`,
`run_remote.bat`, or a bare `python app.py`).

**Easiest setup:** create a file named **`password.txt`** in the project folder,
put your password on the first line, save, and restart. That's it. (`password.txt`
is gitignored.)

You can also set it via
`set_api_key.bat` (loaded by `run.bat`) or the shell:

```
set "FINTRACKER_PASSWORD=your-strong-password"
```

When set, every page requires the password (styled login page, stays signed in
via a 30-day cookie; **Logout** is in the sidebar). APIs return 401 until you
sign in. The session secret is stored in a gitignored `.flask_secret` file so
logins survive restarts.

**Fail-closed remote access:** if no `FINTRACKER_PASSWORD` is set, the app serves
**localhost only** — any request arriving over a tunnel or from another machine
(ngrok/Cloudflare/LAN) is blocked with a 403 until you set a password and
restart. So a forgotten password can never expose your data publicly. Set the
password (and use `run_remote.bat`, or export it before `python app.py`) to
enable remote/LAN access.

## Tech

Python · Flask · SQLAlchemy · SQLite · Chart.js · vanilla JS.

See [`SPEC.md`](SPEC.md) for the full data model, API reference, and net-worth formula.

## Your data & backups

- Your data lives in **`instance/finance.db`** (gitignored, never committed). The
  app pins this exact path so it can't drift between locations across library
  versions.
- On **every startup** the app writes a timestamped copy to
  **`instance/backups/finance-<date-time>.db`**, keeping the newest 10. If
  anything ever goes wrong, restore the latest good one (stop the app, replace
  `instance/finance.db` with the backup).
- **`init_db.py` is destructive** — it resets to sample data. It now **refuses to
  run if real data exists**; a reset requires `python init_db.py --force`.

## Note

For local use no login is needed; enable `FINTRACKER_PASSWORD` before any
internet exposure (see Authentication).

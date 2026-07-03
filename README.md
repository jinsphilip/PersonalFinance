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

**Cloudflare Tunnel (free, recommended):**
1. Install `cloudflared` (Windows: `winget install --id Cloudflare.cloudflared`,
   or download from Cloudflare).
2. Start FinTracker (`run.bat`).
3. In another terminal run: `cloudflared tunnel --url http://localhost:5000`
4. It prints a public `https://<random>.trycloudflare.com` URL — open it on your
   phone from anywhere. (This quick URL changes each run. For a **stable** URL,
   create a free Cloudflare account and a *named* tunnel: `cloudflared tunnel
   login`, `cloudflared tunnel create fintracker`, map it to a hostname, then
   `cloudflared tunnel run fintracker`.)

**ngrok** is an alternative: `ngrok http 5000` prints a public URL.

Keep the PC on and the app running while you use it remotely. If you want it
online without your PC, host it (Render/Railway/Fly.io/PythonAnywhere) instead.

## Authentication (login password)

A session login is built in and **off by default** (frictionless local use).
Turn it on by setting an environment variable before launching — either in your
`set_api_key.bat` (loaded by `run.bat`) or the shell:

```
set "FINTRACKER_PASSWORD=your-strong-password"
```

When set, every page requires the password (styled login page, stays signed in
via a 30-day cookie; **Logout** is in the sidebar). APIs return 401 until you
sign in. **Always set this before exposing the app through a tunnel.** The
session secret is stored in a gitignored `.flask_secret` file so logins survive
restarts.

## Tech

Python · Flask · SQLAlchemy · SQLite · Chart.js · vanilla JS.

See [`SPEC.md`](SPEC.md) for the full data model, API reference, and net-worth formula.

## Note

Data lives in `finance.db`, which is gitignored and never committed. For local
use no login is needed; enable `FINTRACKER_PASSWORD` before any internet exposure.

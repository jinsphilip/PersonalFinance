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

## Tech

Python · Flask · SQLAlchemy · SQLite · Chart.js · vanilla JS.

See [`SPEC.md`](SPEC.md) for the full data model, API reference, and net-worth formula.

## Note

This app has **no authentication** — it is intended for local/personal use. Your data
lives in `finance.db`, which is gitignored and never committed.

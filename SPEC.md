# Personal Finance Tracker — Specification

## Purpose

A single self-hosted web application to track a fragmented personal financial life in
one place: investments, banking, debt, informal lending, and income. Built for
individual/local use (no authentication) with amounts in INR.

## Tracked Domains

| # | Domain | What it captures |
|---|--------|------------------|
| 1 | **Dashboard** | Net worth, asset allocation, assets vs liabilities, recent income |
| 2 | **Mutual Funds** | Holdings across platforms (Groww, Zerodha Coin, …) with live NAV |
| 3 | **Stocks** | Equity across multiple demat accounts with live prices |
| 4 | **Bank Accounts** | Multiple accounts and balances |
| 5 | **Loans** | Housing / car / personal loans with EMI and payoff progress |
| 6 | **Chit Funds** | Contributions and auction status (pending / auctioned) |
| 7 | **Fixed Deposits** | Principal, rate, maturity value, interest earned |
| 8 | **Credits Given** | Interest-free money lent to friends, with repayment status |
| 9 | **Income** | Salary and stock dividend income |

## Tech Stack

- **Backend**: Python, Flask, Flask-SQLAlchemy
- **Database**: SQLite (`finance.db`)
- **Frontend**: Server-rendered Jinja templates + vanilla JS (`fetch`), Chart.js for charts
- **Live prices**: `requests` against AMFI (NAV) and Yahoo Finance (stocks)

## Data Model

All models live in `models.py`; each exposes `to_dict()` with computed fields.

**MutualFund** — `platform`, `fund_name`, `folio_number`, `units`, `avg_nav`,
`current_nav`, `investment_date`, `scheme_code` (AMFI), `last_updated`.
Computed: `invested_value`, `current_value`, `gain_loss`, `gain_loss_pct`.

**Stock** — `demat_account`, `company_name`, `ticker`, `quantity`, `avg_price`,
`current_price`, `sector`, `exchange` (NSE/BSE), `last_updated`.
Computed: `invested_value`, `current_value`, `gain_loss`, `gain_loss_pct`.

**BankAccount** — `bank_name`, `account_number`, `account_type`, `balance`.

**Loan** — `loan_type` (housing/car/…), `lender`, `principal_amount`,
`outstanding_amount`, `interest_rate`, `emi_amount`, `tenure_months`, `start_date`,
`next_due_date`. Computed: `amount_paid`, `progress_pct`.

**ChitFund** — `chit_name`, `total_value`, `monthly_contribution`, `tenure_months`,
`start_date`, `auction_status` (pending/auctioned), `auction_amount`, `auction_date`,
`organizer`.

**FixedDeposit** — `bank_name`, `account_number`, `principal_amount`, `interest_rate`,
`start_date`, `maturity_date`, `maturity_amount`, `fd_type` (cumulative/non-cumulative).
Computed: `interest_earned`.

**CreditGiven** — `person_name`, `amount`, `date_given`, `notes`, `status`
(outstanding/returned), `returned_date`.

**Income** — `income_type` (salary/dividend), `amount`, `date`, `description`,
`stock_name` (dividend), `employer` (salary).

## REST API

Each resource supports list/create/update/delete. Bodies are JSON.

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/dashboard` | Net worth, asset breakdown, recent income |
| GET / POST | `/api/mutual-funds` | List / create |
| PUT / DELETE | `/api/mutual-funds/<id>` | Update / delete |
| GET / POST | `/api/stocks` | List / create |
| PUT / DELETE | `/api/stocks/<id>` | Update / delete |
| GET / POST | `/api/bank-accounts` | List / create |
| PUT / DELETE | `/api/bank-accounts/<id>` | Update / delete |
| GET / POST | `/api/loans` | List / create |
| PUT / DELETE | `/api/loans/<id>` | Update / delete |
| GET / POST | `/api/chit-funds` | List / create |
| PUT / DELETE | `/api/chit-funds/<id>` | Update / delete |
| GET / POST | `/api/fixed-deposits` | List / create |
| PUT / DELETE | `/api/fixed-deposits/<id>` | Update / delete |
| GET / POST | `/api/credits` | List / create |
| PUT / DELETE | `/api/credits/<id>` | Update / delete |
| GET / POST | `/api/income` | List / create |
| DELETE | `/api/income/<id>` | Delete |
| POST | `/api/refresh-prices` | Refresh MF NAVs + stock prices |

## Net Worth Formula

```
Total Assets      = sum(bank balances)
                  + sum(MF units × current NAV)
                  + sum(stock qty × current price)
                  + sum(FD principal)
                  + sum(outstanding credits given)
Total Liabilities = sum(loan outstanding)
Net Worth         = Total Assets − Total Liabilities
```

## Live Price Sources (`prices.py`)

- **Mutual fund NAVs** — AMFI daily feed `https://www.amfiindia.com/spages/NAVAll.txt`,
  matched by `scheme_code`. One download covers all funds.
- **Stock prices** — Yahoo Finance chart API
  `https://query1.finance.yahoo.com/v8/finance/chart/<TICKER>.<NS|BO>`, one call per ticker.

`POST /api/refresh-prices` updates `current_nav` / `current_price` and stamps
`last_updated`. Failures are non-fatal: the stored value is kept and the symbol is
returned in the response `failed` list. Outbound HTTPS honours `HTTPS_PROXY`.

## Run

```bash
pip install -r requirements.txt
python init_db.py     # creates finance.db with sample data
python app.py         # serves on http://localhost:5000
```

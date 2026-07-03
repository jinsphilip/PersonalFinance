"""Populate database with realistic Indian financial sample data (ledger model).

DESTRUCTIVE: this drops all tables and reseeds demo data. It refuses to run if
the database already contains real data, unless you pass --force. This guard
exists because an accidental run once wiped a user's real portfolio.
"""
import sys
from datetime import date

from app import app
from models import (
    db, MutualFund, Stock, Loan, ChitFund, FixedDeposit, CreditGiven,
    Account, Transaction, NetWorthSnapshot,
)
import services

FORCE = '--force' in sys.argv

with app.app_context():
    has_data = False
    try:
        has_data = any([
            Account.query.first(), Stock.query.first(), MutualFund.query.first(),
            Loan.query.first(), FixedDeposit.query.first(), ChitFund.query.first(),
        ])
    except Exception:
        has_data = False   # tables don't exist yet → safe to seed
    if has_data and not FORCE:
        print("[init_db] The database already contains data — refusing to wipe it.")
        print("[init_db] This would DELETE your real portfolio and load demo data.")
        print("[init_db] If you REALLY want to reset to sample data, run:")
        print("[init_db]     python init_db.py --force")
        sys.exit(0)

    db.drop_all()
    db.create_all()
    services.seed_masters()

    # ── Mutual Funds (valuation positions) ────────────────────────────────────
    db.session.add_all([
        MutualFund(platform='Groww', fund_name='Mirae Asset Large Cap Fund - Direct Growth',
                   folio_number='GRW1234567', units=245.678, avg_nav=82.45, current_nav=96.30,
                   investment_date='2022-04-15', scheme_code='118825'),
        MutualFund(platform='Zerodha Coin', fund_name='Axis Bluechip Fund - Direct Growth',
                   folio_number='ZRD9876543', units=312.450, avg_nav=45.20, current_nav=52.75,
                   investment_date='2021-11-01', scheme_code='120465'),
        MutualFund(platform='Groww', fund_name='HDFC Mid-Cap Opportunities Fund - Direct Growth',
                   folio_number='GRW7654321', units=180.000, avg_nav=110.00, current_nav=138.60,
                   investment_date='2023-01-10', scheme_code='118989'),
    ])

    # ── Stocks (valuation positions) ──────────────────────────────────────────
    db.session.add_all([
        Stock(demat_account='Zerodha', company_name='Tata Consultancy Services Ltd',
              ticker='TCS', quantity=15, avg_price=3350.00, current_price=3892.50,
              sector='Information Technology', exchange='NSE'),
        Stock(demat_account='Zerodha', company_name='Infosys Ltd',
              ticker='INFY', quantity=30, avg_price=1420.00, current_price=1678.20,
              sector='Information Technology', exchange='NSE'),
        Stock(demat_account='Angel One', company_name='Reliance Industries Ltd',
              ticker='RELIANCE', quantity=20, avg_price=2480.00, current_price=2956.75,
              sector='Energy & Conglomerates', exchange='NSE'),
    ])

    # ── Ledger accounts (banks + wallet) ──────────────────────────────────────
    sbi = Account(name='State Bank of India', account_type_code='BANK',
                  current_balance=125000.00, subtype='bank', meta='XXXX XXXX 4821')
    hdfc = Account(name='HDFC Bank', account_type_code='BANK',
                   current_balance=87500.50, subtype='bank', meta='XXXX XXXX 9034')
    icici = Account(name='ICICI Bank', account_type_code='BANK',
                    current_balance=45000.00, subtype='bank', meta='XXXX XXXX 2267')
    gpay = Account(name='GPay', account_type_code='WALLET',
                   current_balance=2500.00, subtype='wallet', meta='')
    db.session.add_all([sbi, hdfc, icici, gpay])
    db.session.flush()

    # ── Loans (formal liabilities) ────────────────────────────────────────────
    db.session.add_all([
        Loan(loan_type='housing', lender='SBI Home Loans',
             principal_amount=4500000.00, outstanding_amount=3820000.00,
             interest_rate=8.50, emi_amount=39850.00,
             tenure_months=240, start_date='2020-06-01', next_due_date='2026-07-05'),
        Loan(loan_type='car', lender='HDFC Bank Auto Loans',
             principal_amount=750000.00, outstanding_amount=310000.00,
             interest_rate=9.25, emi_amount=15620.00,
             tenure_months=60, start_date='2022-03-15', next_due_date='2026-07-15'),
    ])

    # ── Fixed Deposits ────────────────────────────────────────────────────────
    db.session.add_all([
        FixedDeposit(bank_name='State Bank of India', account_number='FD-SBI-009812',
                     principal_amount=200000.00, interest_rate=7.10,
                     start_date='2024-04-01', maturity_date='2026-04-01',
                     maturity_amount=230436.00, fd_type='cumulative'),
        FixedDeposit(bank_name='HDFC Bank', account_number='FD-HDFC-447231',
                     principal_amount=100000.00, interest_rate=7.40,
                     start_date='2025-01-15', maturity_date='2026-01-15',
                     maturity_amount=107400.00, fd_type='non-cumulative'),
        FixedDeposit(bank_name='ICICI Bank', account_number='FD-ICICI-335610',
                     principal_amount=150000.00, interest_rate=7.25,
                     start_date='2024-10-01', maturity_date='2026-10-01',
                     maturity_amount=166351.00, fd_type='cumulative'),
    ])

    # ── Chit Funds (with linked CHIT ledger accounts) ─────────────────────────
    chit1 = ChitFund(chit_name='Sri Lakshmi Chit Fund - 5 Lakhs',
                     total_value=500000.00, monthly_contribution=20833.00,
                     tenure_months=24, start_date='2025-01-01', auction_status='pending',
                     organizer='Sri Lakshmi Finance Pvt Ltd')
    chit2 = ChitFund(chit_name='Margadarsi Chit Fund - 2 Lakhs',
                     total_value=200000.00, monthly_contribution=8333.00,
                     tenure_months=24, start_date='2023-07-01', auction_status='auctioned',
                     auction_amount=185000.00, auction_date='2024-03-10',
                     organizer='Margadarsi Chit Fund Ltd')
    for ch in (chit1, chit2):
        acct = Account(name=ch.chit_name, account_type_code='CHIT', current_balance=0,
                       subtype='chit', meta=ch.organizer,
                       is_liability=(ch.auction_status == 'auctioned'))
        db.session.add(acct)
        db.session.flush()
        ch.account_id = acct.id
        db.session.add(ch)
    db.session.flush()

    # Pre-auction chit contributions accumulate as an asset balance.
    services.record_chit_installment(chit1, from_account_id=sbi.id, amount=20833.00, date='2025-06-01')
    services.record_chit_installment(chit1, from_account_id=sbi.id, amount=20833.00, date='2025-07-01')

    # ── Credits Given (friendly-loan asset book) ──────────────────────────────
    ramesh = CreditGiven(person_name='Ramesh Kumar', amount=50000.00, date_given='2025-11-20',
                         notes='For medical emergency, to be returned in 3 months', status='outstanding')
    priya = CreditGiven(person_name='Priya Sharma', amount=25000.00, date_given='2025-09-05',
                        notes='Personal loan for home renovation', status='returned',
                        returned_date='2026-01-10')
    suresh = CreditGiven(person_name='Suresh Babu', amount=15000.00, date_given='2026-02-14',
                         notes='Business expense advance', status='outstanding')
    db.session.add_all([ramesh, priya, suresh])
    db.session.flush()
    # Ramesh & Suresh outstanding (deduct from bank); Priya already recovered (net zero).
    services.open_loan_asset(ramesh, from_account_id=sbi.id, amount=50000.00, date='2025-11-20')
    services.open_loan_asset(suresh, from_account_id=hdfc.id, amount=15000.00, date='2026-02-14')
    priya_acct = Account(name='Loan · Priya Sharma', account_type_code='LOAN_ASSET',
                         current_balance=0, subtype='loan_asset', meta='Priya Sharma')
    db.session.add(priya_acct)
    db.session.flush()
    priya.account_id = priya_acct.id

    # ── Income (INFLOW transactions) ──────────────────────────────────────────
    services.post_transaction(to_account_id=sbi.id, from_account_id=None, amount=125000.00,
                              category_code='SALARY', transaction_date='2026-06-01',
                              description='Monthly salary - June 2026 · Tech Mahindra Ltd', commit=False)
    services.post_transaction(to_account_id=sbi.id, from_account_id=None, amount=125000.00,
                              category_code='SALARY', transaction_date='2026-05-01',
                              description='Monthly salary - May 2026 · Tech Mahindra Ltd', commit=False)
    services.post_transaction(to_account_id=sbi.id, from_account_id=None, amount=4500.00,
                              category_code='DIVIDEND', transaction_date='2026-05-20',
                              description='TCS interim dividend', commit=False)
    services.post_transaction(to_account_id=sbi.id, from_account_id=None, amount=2100.00,
                              category_code='DIVIDEND', transaction_date='2026-04-15',
                              description='Infosys final dividend', commit=False)

    # ── Expenses (OUTFLOW transactions) ───────────────────────────────────────
    services.post_transaction(from_account_id=gpay.id, to_account_id=None, amount=450.00,
                              category_code='EXPENSE_FOOD', transaction_date='2026-06-20',
                              description='Zomato order', commit=False)
    services.post_transaction(from_account_id=hdfc.id, to_account_id=None, amount=2000.00,
                              category_code='EXPENSE_FUEL', transaction_date='2026-06-18',
                              description='Petrol at HP bunk', commit=False)
    services.post_transaction(from_account_id=sbi.id, to_account_id=None, amount=1850.00,
                              category_code='EXPENSE_UTILITIES', transaction_date='2026-06-15',
                              description='Electricity bill', commit=False)
    services.post_transaction(from_account_id=hdfc.id, to_account_id=None, amount=3200.00,
                              category_code='EXPENSE_SHOPPING', transaction_date='2026-06-10',
                              description='Amazon purchase', commit=False)
    services.post_transaction(from_account_id=gpay.id, to_account_id=None, amount=620.00,
                              category_code='EXPENSE_TRANSPORT', transaction_date='2026-06-05',
                              description='Uber rides', commit=False)

    # ── Transfers ─────────────────────────────────────────────────────────────
    services.post_transaction(from_account_id=sbi.id, to_account_id=gpay.id, amount=5000.00,
                              category_code='TRANSFER', transaction_date='2026-06-01',
                              description='Monthly GPay top-up', commit=False)
    services.post_transaction(from_account_id=hdfc.id, to_account_id=sbi.id, amount=10000.00,
                              category_code='TRANSFER', transaction_date='2026-06-12',
                              description='Transfer to SBI for EMI', commit=False)

    # ── Net-worth history (demo trend; real installs accrue daily) ─────────────
    import datetime
    base = -3050000.0   # roughly current net worth; trend climbs toward today
    today = datetime.date.today()
    for i in range(6, 0, -1):
        d = (today.replace(day=1) - datetime.timedelta(days=30 * i)).isoformat()
        nw = base + (6 - i) * 18000
        db.session.add(NetWorthSnapshot(date=d, net_worth=round(nw, 2),
                                        total_assets=round(nw + 4130000, 2),
                                        total_liabilities=4130000))

    db.session.commit()
    print("Database initialised with sample data successfully!")

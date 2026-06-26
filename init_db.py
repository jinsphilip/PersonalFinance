"""Populate database with realistic Indian financial sample data."""
from app import app
from models import db, MutualFund, Stock, BankAccount, Loan, ChitFund, FixedDeposit, CreditGiven, Income, Expense, Transfer

with app.app_context():
    db.drop_all()
    db.create_all()

    # ── Mutual Funds ──────────────────────────────────────────────────────────
    mfs = [
        MutualFund(platform='Groww', fund_name='Mirae Asset Large Cap Fund - Direct Growth',
                   folio_number='GRW1234567', units=245.678, avg_nav=82.45, current_nav=96.30,
                   investment_date='2022-04-15', scheme_code='118825'),
        MutualFund(platform='Zerodha Coin', fund_name='Axis Bluechip Fund - Direct Growth',
                   folio_number='ZRD9876543', units=312.450, avg_nav=45.20, current_nav=52.75,
                   investment_date='2021-11-01', scheme_code='120465'),
        MutualFund(platform='Groww', fund_name='HDFC Mid-Cap Opportunities Fund - Direct Growth',
                   folio_number='GRW7654321', units=180.000, avg_nav=110.00, current_nav=138.60,
                   investment_date='2023-01-10', scheme_code='118989'),
    ]
    db.session.add_all(mfs)

    # ── Stocks ────────────────────────────────────────────────────────────────
    stocks = [
        Stock(demat_account='Zerodha', company_name='Tata Consultancy Services Ltd',
              ticker='TCS', quantity=15, avg_price=3350.00, current_price=3892.50,
              sector='Information Technology', exchange='NSE'),
        Stock(demat_account='Zerodha', company_name='Infosys Ltd',
              ticker='INFY', quantity=30, avg_price=1420.00, current_price=1678.20,
              sector='Information Technology', exchange='NSE'),
        Stock(demat_account='Angel One', company_name='Reliance Industries Ltd',
              ticker='RELIANCE', quantity=20, avg_price=2480.00, current_price=2956.75,
              sector='Energy & Conglomerates', exchange='NSE'),
    ]
    db.session.add_all(stocks)

    # ── Bank Accounts ─────────────────────────────────────────────────────────
    banks = [
        BankAccount(bank_name='State Bank of India', account_number='XXXX XXXX 4821',
                    account_type='Savings', account_subtype='bank', balance=125000.00),
        BankAccount(bank_name='HDFC Bank', account_number='XXXX XXXX 9034',
                    account_type='Savings', account_subtype='bank', balance=87500.50),
        BankAccount(bank_name='ICICI Bank', account_number='XXXX XXXX 2267',
                    account_type='Current', account_subtype='bank', balance=45000.00),
        BankAccount(bank_name='GPay', account_number='',
                    account_type='Wallet', account_subtype='wallet', balance=2500.00),
    ]
    db.session.add_all(banks)
    db.session.flush()  # get IDs before adding expenses/transfers
    sbi, hdfc, icici, gpay = banks

    # ── Loans ─────────────────────────────────────────────────────────────────
    loans = [
        Loan(loan_type='housing', lender='SBI Home Loans',
             principal_amount=4500000.00, outstanding_amount=3820000.00,
             interest_rate=8.50, emi_amount=39850.00,
             tenure_months=240, start_date='2020-06-01', next_due_date='2026-07-05'),
        Loan(loan_type='car', lender='HDFC Bank Auto Loans',
             principal_amount=750000.00, outstanding_amount=310000.00,
             interest_rate=9.25, emi_amount=15620.00,
             tenure_months=60, start_date='2022-03-15', next_due_date='2026-07-15'),
    ]
    db.session.add_all(loans)

    # ── Chit Funds ────────────────────────────────────────────────────────────
    chits = [
        ChitFund(chit_name='Sri Lakshmi Chit Fund - 5 Lakhs',
                 total_value=500000.00, monthly_contribution=20833.00,
                 tenure_months=24, start_date='2025-01-01',
                 auction_status='pending', auction_amount=0,
                 auction_date='', organizer='Sri Lakshmi Finance Pvt Ltd'),
        ChitFund(chit_name='Margadarsi Chit Fund - 2 Lakhs',
                 total_value=200000.00, monthly_contribution=8333.00,
                 tenure_months=24, start_date='2023-07-01',
                 auction_status='auctioned', auction_amount=185000.00,
                 auction_date='2024-03-10', organizer='Margadarsi Chit Fund Ltd'),
    ]
    db.session.add_all(chits)

    # ── Fixed Deposits ────────────────────────────────────────────────────────
    fds = [
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
    ]
    db.session.add_all(fds)

    # ── Credits Given ─────────────────────────────────────────────────────────
    credits = [
        CreditGiven(person_name='Ramesh Kumar', amount=50000.00,
                    date_given='2025-11-20',
                    notes='For medical emergency, to be returned in 3 months',
                    status='outstanding', returned_date=''),
        CreditGiven(person_name='Priya Sharma', amount=25000.00,
                    date_given='2025-09-05',
                    notes='Personal loan for home renovation',
                    status='returned', returned_date='2026-01-10'),
        CreditGiven(person_name='Suresh Babu', amount=15000.00,
                    date_given='2026-02-14',
                    notes='Business expense advance',
                    status='outstanding', returned_date=''),
    ]
    db.session.add_all(credits)

    # ── Income ────────────────────────────────────────────────────────────────
    incomes = [
        Income(income_type='salary', amount=125000.00, date='2026-06-01',
               description='Monthly salary - June 2026', stock_name='', employer='Tech Mahindra Ltd'),
        Income(income_type='salary', amount=125000.00, date='2026-05-01',
               description='Monthly salary - May 2026', stock_name='', employer='Tech Mahindra Ltd'),
        Income(income_type='dividend', amount=4500.00, date='2026-05-20',
               description='TCS interim dividend @ ₹9/share x 500 shares',
               stock_name='TCS', employer=''),
        Income(income_type='dividend', amount=2100.00, date='2026-04-15',
               description='Infosys final dividend @ ₹35/share x 60 shares',
               stock_name='INFY', employer=''),
    ]
    db.session.add_all(incomes)

    # ── Expenses ──────────────────────────────────────────────────────────────
    expenses = [
        Expense(date='2026-06-20', category='Food', description='Zomato order',
                amount=450.00, account_id=gpay.id, account_name='GPay'),
        Expense(date='2026-06-18', category='Fuel', description='Petrol at HP bunk',
                amount=2000.00, account_id=hdfc.id, account_name='HDFC Bank'),
        Expense(date='2026-06-15', category='Utilities', description='Electricity bill',
                amount=1850.00, account_id=sbi.id, account_name='State Bank of India'),
        Expense(date='2026-06-10', category='Shopping', description='Amazon purchase',
                amount=3200.00, account_id=hdfc.id, account_name='HDFC Bank'),
        Expense(date='2026-06-05', category='Transport', description='Uber rides',
                amount=620.00, account_id=gpay.id, account_name='GPay'),
    ]
    # Deduct from account balances
    gpay.balance   -= (450.00 + 620.00)
    hdfc.balance   -= (2000.00 + 3200.00)
    sbi.balance    -= 1850.00
    db.session.add_all(expenses)

    # ── Transfers ─────────────────────────────────────────────────────────────
    transfers = [
        Transfer(date='2026-06-01', from_account_id=sbi.id, to_account_id=gpay.id,
                 from_account_name='State Bank of India', to_account_name='GPay',
                 amount=5000.00, notes='Monthly GPay top-up'),
        Transfer(date='2026-06-12', from_account_id=hdfc.id, to_account_id=sbi.id,
                 from_account_name='HDFC Bank', to_account_name='State Bank of India',
                 amount=10000.00, notes='Transfer to SBI for EMI'),
    ]
    sbi.balance  += (5000.00 - 10000.00)   # received 5k, sent 10k net
    hdfc.balance -= 10000.00
    gpay.balance += 5000.00
    db.session.add_all(transfers)

    db.session.commit()
    print("Database initialised with sample data successfully!")

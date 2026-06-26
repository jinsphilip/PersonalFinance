import os
import sys
from datetime import date

from flask import Flask, request, jsonify, render_template
from models import db, MutualFund, Stock, BankAccount, Loan, ChitFund, FixedDeposit, CreditGiven, Income, Expense, Transfer
import prices

# When packaged as a standalone executable (PyInstaller), bundled files live in a
# temporary extraction dir exposed as sys._MEIPASS, while the database must be stored
# in a persistent, writable location next to the executable.
FROZEN = getattr(sys, 'frozen', False)
if FROZEN:
    BUNDLE_DIR = sys._MEIPASS                       # read-only: templates + static
    APP_DIR = os.path.dirname(sys.executable)       # writable: finance.db lives here
    app = Flask(
        __name__,
        template_folder=os.path.join(BUNDLE_DIR, 'templates'),
        static_folder=os.path.join(BUNDLE_DIR, 'static'),
    )
    db_path = os.path.join(APP_DIR, 'finance.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
else:
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()
    # Migrate: add account_subtype if missing (existing DBs created before this column)
    with db.engine.connect() as conn:
        cols = [r[1] for r in conn.execute(db.text("PRAGMA table_info(bank_accounts)")).fetchall()]
        if 'account_subtype' not in cols:
            conn.execute(db.text("ALTER TABLE bank_accounts ADD COLUMN account_subtype VARCHAR(20) DEFAULT 'bank'"))
            conn.commit()
        # Migrate: add expenses and transfers tables columns if tables exist but missing cols
        exp_cols = [r[1] for r in conn.execute(db.text("PRAGMA table_info(expenses)")).fetchall()]
        if exp_cols and 'account_name' not in exp_cols:
            conn.execute(db.text("ALTER TABLE expenses ADD COLUMN account_name VARCHAR(100)"))
            conn.commit()
        tr_cols = [r[1] for r in conn.execute(db.text("PRAGMA table_info(transfers)")).fetchall()]
        if tr_cols and 'from_account_name' not in tr_cols:
            conn.execute(db.text("ALTER TABLE transfers ADD COLUMN from_account_name VARCHAR(100)"))
            conn.execute(db.text("ALTER TABLE transfers ADD COLUMN to_account_name VARCHAR(100)"))
            conn.commit()


# ─── Page routes ───────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/mutual-funds')
def mutual_funds_page():
    return render_template('mutual_funds.html')

@app.route('/stocks')
def stocks_page():
    return render_template('stocks.html')

@app.route('/bank-accounts')
def bank_accounts_page():
    return render_template('bank_accounts.html')

@app.route('/loans')
def loans_page():
    return render_template('loans.html')

@app.route('/chit-funds')
def chit_funds_page():
    return render_template('chit_funds.html')

@app.route('/fixed-deposits')
def fixed_deposits_page():
    return render_template('fixed_deposits.html')

@app.route('/credits')
def credits_page():
    return render_template('credits.html')

@app.route('/income')
def income_page():
    return render_template('income.html')

@app.route('/expenses')
def expenses_page():
    return render_template('expenses.html')

@app.route('/transfers')
def transfers_page():
    return render_template('transfers.html')


# ─── Dashboard API ─────────────────────────────────────────────────────────────

@app.route('/api/dashboard')
def api_dashboard():
    bank_total = sum(b.balance for b in BankAccount.query.all())
    mf_total = sum(f.units * f.current_nav for f in MutualFund.query.all())
    stock_total = sum(s.quantity * s.current_price for s in Stock.query.all())
    fd_total = sum(f.principal_amount for f in FixedDeposit.query.all())
    credit_total = sum(c.amount for c in CreditGiven.query.filter_by(status='outstanding').all())
    loan_total = sum(l.outstanding_amount for l in Loan.query.all())

    total_assets = bank_total + mf_total + stock_total + fd_total + credit_total
    net_worth = total_assets - loan_total

    income_entries = Income.query.order_by(Income.date.desc()).limit(5).all()
    recent_income = [i.to_dict() for i in income_entries]

    this_month = date.today().strftime('%Y-%m')
    monthly_expenses_rows = Expense.query.filter(Expense.date.startswith(this_month)).all()
    monthly_expenses = sum(e.amount for e in monthly_expenses_rows)
    expense_by_category = {}
    for e in monthly_expenses_rows:
        expense_by_category[e.category] = expense_by_category.get(e.category, 0) + e.amount
    expense_by_category = {k: round(v, 2) for k, v in expense_by_category.items()}

    return jsonify({
        'net_worth': round(net_worth, 2),
        'total_assets': round(total_assets, 2),
        'total_liabilities': round(loan_total, 2),
        'breakdown': {
            'Bank Accounts': round(bank_total, 2),
            'Mutual Funds': round(mf_total, 2),
            'Stocks': round(stock_total, 2),
            'Fixed Deposits': round(fd_total, 2),
            'Credits Given': round(credit_total, 2),
        },
        'recent_income': recent_income,
        'monthly_expenses': round(monthly_expenses, 2),
        'expense_by_category': expense_by_category,
    })


# ─── Mutual Funds ──────────────────────────────────────────────────────────────

@app.route('/api/mutual-funds', methods=['GET', 'POST'])
def api_mutual_funds():
    if request.method == 'GET':
        return jsonify([f.to_dict() for f in MutualFund.query.all()])
    data = request.json
    mf = MutualFund(
        platform=data['platform'],
        fund_name=data['fund_name'],
        folio_number=data.get('folio_number', ''),
        units=float(data['units']),
        avg_nav=float(data['avg_nav']),
        current_nav=float(data['current_nav']),
        investment_date=data.get('investment_date', ''),
        scheme_code=data.get('scheme_code', ''),
        last_updated=data.get('last_updated', ''),
    )
    db.session.add(mf)
    db.session.commit()
    return jsonify(mf.to_dict()), 201


@app.route('/api/mutual-funds/<int:id>', methods=['PUT', 'DELETE'])
def api_mutual_fund(id):
    mf = MutualFund.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(mf)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    mf.platform = data.get('platform', mf.platform)
    mf.fund_name = data.get('fund_name', mf.fund_name)
    mf.folio_number = data.get('folio_number', mf.folio_number)
    mf.units = float(data.get('units', mf.units))
    mf.avg_nav = float(data.get('avg_nav', mf.avg_nav))
    mf.current_nav = float(data.get('current_nav', mf.current_nav))
    mf.investment_date = data.get('investment_date', mf.investment_date)
    mf.scheme_code = data.get('scheme_code', mf.scheme_code)
    db.session.commit()
    return jsonify(mf.to_dict())


# ─── Stocks ────────────────────────────────────────────────────────────────────

@app.route('/api/stocks', methods=['GET', 'POST'])
def api_stocks():
    if request.method == 'GET':
        return jsonify([s.to_dict() for s in Stock.query.all()])
    data = request.json
    s = Stock(
        demat_account=data['demat_account'],
        company_name=data['company_name'],
        ticker=data['ticker'],
        quantity=int(data['quantity']),
        avg_price=float(data['avg_price']),
        current_price=float(data['current_price']),
        sector=data.get('sector', ''),
        exchange=data.get('exchange', 'NSE'),
        last_updated=data.get('last_updated', ''),
    )
    db.session.add(s)
    db.session.commit()
    return jsonify(s.to_dict()), 201


@app.route('/api/stocks/<int:id>', methods=['PUT', 'DELETE'])
def api_stock(id):
    s = Stock.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(s)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    s.demat_account = data.get('demat_account', s.demat_account)
    s.company_name = data.get('company_name', s.company_name)
    s.ticker = data.get('ticker', s.ticker)
    s.quantity = int(data.get('quantity', s.quantity))
    s.avg_price = float(data.get('avg_price', s.avg_price))
    s.current_price = float(data.get('current_price', s.current_price))
    s.sector = data.get('sector', s.sector)
    s.exchange = data.get('exchange', s.exchange)
    db.session.commit()
    return jsonify(s.to_dict())


# ─── Bank Accounts ─────────────────────────────────────────────────────────────

@app.route('/api/bank-accounts', methods=['GET', 'POST'])
def api_bank_accounts():
    if request.method == 'GET':
        return jsonify([b.to_dict() for b in BankAccount.query.all()])
    data = request.json
    b = BankAccount(
        bank_name=data['bank_name'],
        account_number=data.get('account_number', ''),
        account_type=data['account_type'],
        account_subtype=data.get('account_subtype', 'bank'),
        balance=float(data['balance']),
    )
    db.session.add(b)
    db.session.commit()
    return jsonify(b.to_dict()), 201


@app.route('/api/bank-accounts/<int:id>', methods=['PUT', 'DELETE'])
def api_bank_account(id):
    b = BankAccount.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(b)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    b.bank_name = data.get('bank_name', b.bank_name)
    b.account_number = data.get('account_number', b.account_number)
    b.account_type = data.get('account_type', b.account_type)
    b.account_subtype = data.get('account_subtype', b.account_subtype)
    b.balance = float(data.get('balance', b.balance))
    db.session.commit()
    return jsonify(b.to_dict())


# ─── Loans ─────────────────────────────────────────────────────────────────────

@app.route('/api/loans', methods=['GET', 'POST'])
def api_loans():
    if request.method == 'GET':
        return jsonify([l.to_dict() for l in Loan.query.all()])
    data = request.json
    l = Loan(
        loan_type=data['loan_type'],
        lender=data['lender'],
        principal_amount=float(data['principal_amount']),
        outstanding_amount=float(data['outstanding_amount']),
        interest_rate=float(data['interest_rate']),
        emi_amount=float(data['emi_amount']),
        tenure_months=int(data['tenure_months']),
        start_date=data.get('start_date', ''),
        next_due_date=data.get('next_due_date', ''),
    )
    db.session.add(l)
    db.session.commit()
    return jsonify(l.to_dict()), 201


@app.route('/api/loans/<int:id>', methods=['PUT', 'DELETE'])
def api_loan(id):
    l = Loan.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(l)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    l.loan_type = data.get('loan_type', l.loan_type)
    l.lender = data.get('lender', l.lender)
    l.principal_amount = float(data.get('principal_amount', l.principal_amount))
    l.outstanding_amount = float(data.get('outstanding_amount', l.outstanding_amount))
    l.interest_rate = float(data.get('interest_rate', l.interest_rate))
    l.emi_amount = float(data.get('emi_amount', l.emi_amount))
    l.tenure_months = int(data.get('tenure_months', l.tenure_months))
    l.start_date = data.get('start_date', l.start_date)
    l.next_due_date = data.get('next_due_date', l.next_due_date)
    db.session.commit()
    return jsonify(l.to_dict())


# ─── Chit Funds ────────────────────────────────────────────────────────────────

@app.route('/api/chit-funds', methods=['GET', 'POST'])
def api_chit_funds():
    if request.method == 'GET':
        return jsonify([c.to_dict() for c in ChitFund.query.all()])
    data = request.json
    c = ChitFund(
        chit_name=data['chit_name'],
        total_value=float(data['total_value']),
        monthly_contribution=float(data['monthly_contribution']),
        tenure_months=int(data['tenure_months']),
        start_date=data.get('start_date', ''),
        auction_status=data.get('auction_status', 'pending'),
        auction_amount=float(data.get('auction_amount', 0)),
        auction_date=data.get('auction_date', ''),
        organizer=data.get('organizer', ''),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict()), 201


@app.route('/api/chit-funds/<int:id>', methods=['PUT', 'DELETE'])
def api_chit_fund(id):
    c = ChitFund.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(c)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    c.chit_name = data.get('chit_name', c.chit_name)
    c.total_value = float(data.get('total_value', c.total_value))
    c.monthly_contribution = float(data.get('monthly_contribution', c.monthly_contribution))
    c.tenure_months = int(data.get('tenure_months', c.tenure_months))
    c.start_date = data.get('start_date', c.start_date)
    c.auction_status = data.get('auction_status', c.auction_status)
    c.auction_amount = float(data.get('auction_amount', c.auction_amount))
    c.auction_date = data.get('auction_date', c.auction_date)
    c.organizer = data.get('organizer', c.organizer)
    db.session.commit()
    return jsonify(c.to_dict())


# ─── Fixed Deposits ────────────────────────────────────────────────────────────

@app.route('/api/fixed-deposits', methods=['GET', 'POST'])
def api_fixed_deposits():
    if request.method == 'GET':
        return jsonify([f.to_dict() for f in FixedDeposit.query.all()])
    data = request.json
    f = FixedDeposit(
        bank_name=data['bank_name'],
        account_number=data.get('account_number', ''),
        principal_amount=float(data['principal_amount']),
        interest_rate=float(data['interest_rate']),
        start_date=data.get('start_date', ''),
        maturity_date=data.get('maturity_date', ''),
        maturity_amount=float(data['maturity_amount']),
        fd_type=data.get('fd_type', 'cumulative'),
    )
    db.session.add(f)
    db.session.commit()
    return jsonify(f.to_dict()), 201


@app.route('/api/fixed-deposits/<int:id>', methods=['PUT', 'DELETE'])
def api_fixed_deposit(id):
    f = FixedDeposit.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(f)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    f.bank_name = data.get('bank_name', f.bank_name)
    f.account_number = data.get('account_number', f.account_number)
    f.principal_amount = float(data.get('principal_amount', f.principal_amount))
    f.interest_rate = float(data.get('interest_rate', f.interest_rate))
    f.start_date = data.get('start_date', f.start_date)
    f.maturity_date = data.get('maturity_date', f.maturity_date)
    f.maturity_amount = float(data.get('maturity_amount', f.maturity_amount))
    f.fd_type = data.get('fd_type', f.fd_type)
    db.session.commit()
    return jsonify(f.to_dict())


# ─── Credits Given ─────────────────────────────────────────────────────────────

@app.route('/api/credits', methods=['GET', 'POST'])
def api_credits():
    if request.method == 'GET':
        return jsonify([c.to_dict() for c in CreditGiven.query.all()])
    data = request.json
    c = CreditGiven(
        person_name=data['person_name'],
        amount=float(data['amount']),
        date_given=data.get('date_given', ''),
        notes=data.get('notes', ''),
        status=data.get('status', 'outstanding'),
        returned_date=data.get('returned_date', ''),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict()), 201


@app.route('/api/credits/<int:id>', methods=['PUT', 'DELETE'])
def api_credit(id):
    c = CreditGiven.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(c)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    c.person_name = data.get('person_name', c.person_name)
    c.amount = float(data.get('amount', c.amount))
    c.date_given = data.get('date_given', c.date_given)
    c.notes = data.get('notes', c.notes)
    c.status = data.get('status', c.status)
    c.returned_date = data.get('returned_date', c.returned_date)
    db.session.commit()
    return jsonify(c.to_dict())


# ─── Income ────────────────────────────────────────────────────────────────────

@app.route('/api/income', methods=['GET', 'POST'])
def api_income():
    if request.method == 'GET':
        return jsonify([i.to_dict() for i in Income.query.order_by(Income.date.desc()).all()])
    data = request.json
    i = Income(
        income_type=data['income_type'],
        amount=float(data['amount']),
        date=data.get('date', ''),
        description=data.get('description', ''),
        stock_name=data.get('stock_name', ''),
        employer=data.get('employer', ''),
    )
    db.session.add(i)
    db.session.commit()
    return jsonify(i.to_dict()), 201


@app.route('/api/income/<int:id>', methods=['DELETE'])
def api_income_entry(id):
    i = Income.query.get_or_404(id)
    db.session.delete(i)
    db.session.commit()
    return jsonify({'message': 'Deleted'})


# ─── Live Price Refresh ────────────────────────────────────────────────────────

@app.route('/api/refresh-prices', methods=['POST'])
def api_refresh_prices():
    """Refresh mutual fund NAVs (AMFI) and stock prices (Yahoo Finance).

    Rows without a scheme_code (MF) are skipped. Any symbol that cannot be
    fetched is left at its stored value and reported in `failed`.
    """
    today = date.today().isoformat()
    updated_mf = 0
    updated_stocks = 0
    failed = []

    # Mutual funds — one AMFI download covers every fund.
    funds = [f for f in MutualFund.query.all() if f.scheme_code]
    if funds:
        try:
            nav_map = prices.fetch_amfi_navs()
        except Exception:
            nav_map = {}
            failed.append('AMFI NAV feed unreachable')
        for f in funds:
            nav = nav_map.get(str(f.scheme_code).strip())
            if nav is not None:
                f.current_nav = nav
                f.last_updated = today
                updated_mf += 1
            else:
                failed.append(f'{f.fund_name} (scheme {f.scheme_code})')

    # Stocks — one request per ticker.
    for s in Stock.query.all():
        price = prices.fetch_stock_price(s.ticker, s.exchange)
        if price is not None:
            s.current_price = price
            s.last_updated = today
            updated_stocks += 1
        else:
            failed.append(f'{s.ticker} ({s.exchange})')

    db.session.commit()
    return jsonify({
        'updated_mf': updated_mf,
        'updated_stocks': updated_stocks,
        'failed': failed,
    })


# ─── Expenses ──────────────────────────────────────────────────────────────────

@app.route('/api/expenses', methods=['GET', 'POST'])
def api_expenses():
    if request.method == 'GET':
        return jsonify([e.to_dict() for e in Expense.query.order_by(Expense.date.desc()).all()])
    data = request.json
    acct = BankAccount.query.get_or_404(int(data['account_id']))
    e = Expense(
        date=data['date'],
        category=data['category'],
        description=data.get('description', ''),
        amount=float(data['amount']),
        account_id=acct.id,
        account_name=acct.bank_name,
    )
    acct.balance -= e.amount
    db.session.add(e)
    db.session.commit()
    return jsonify(e.to_dict()), 201


@app.route('/api/expenses/<int:id>', methods=['PUT', 'DELETE'])
def api_expense(id):
    e = Expense.query.get_or_404(id)
    if request.method == 'DELETE':
        acct = BankAccount.query.get(e.account_id)
        if acct:
            acct.balance += e.amount
        db.session.delete(e)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    old_acct = BankAccount.query.get(e.account_id)
    if old_acct:
        old_acct.balance += e.amount  # reverse old deduction
    new_acct = BankAccount.query.get_or_404(int(data['account_id']))
    e.date = data.get('date', e.date)
    e.category = data.get('category', e.category)
    e.description = data.get('description', e.description)
    e.amount = float(data.get('amount', e.amount))
    e.account_id = new_acct.id
    e.account_name = new_acct.bank_name
    new_acct.balance -= e.amount
    db.session.commit()
    return jsonify(e.to_dict())


# ─── Transfers ─────────────────────────────────────────────────────────────────

@app.route('/api/transfers', methods=['GET', 'POST'])
def api_transfers():
    if request.method == 'GET':
        return jsonify([t.to_dict() for t in Transfer.query.order_by(Transfer.date.desc()).all()])
    data = request.json
    from_acct = BankAccount.query.get_or_404(int(data['from_account_id']))
    to_acct = BankAccount.query.get_or_404(int(data['to_account_id']))
    amount = float(data['amount'])
    t = Transfer(
        date=data['date'],
        from_account_id=from_acct.id,
        to_account_id=to_acct.id,
        from_account_name=from_acct.bank_name,
        to_account_name=to_acct.bank_name,
        amount=amount,
        notes=data.get('notes', ''),
    )
    from_acct.balance -= amount
    to_acct.balance += amount
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@app.route('/api/transfers/<int:id>', methods=['PUT', 'DELETE'])
def api_transfer(id):
    t = Transfer.query.get_or_404(id)
    if request.method == 'DELETE':
        from_acct = BankAccount.query.get(t.from_account_id)
        to_acct = BankAccount.query.get(t.to_account_id)
        if from_acct:
            from_acct.balance += t.amount
        if to_acct:
            to_acct.balance -= t.amount
        db.session.delete(t)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    # Reverse old transfer
    old_from = BankAccount.query.get(t.from_account_id)
    old_to = BankAccount.query.get(t.to_account_id)
    if old_from:
        old_from.balance += t.amount
    if old_to:
        old_to.balance -= t.amount
    # Apply new transfer
    new_from = BankAccount.query.get_or_404(int(data['from_account_id']))
    new_to = BankAccount.query.get_or_404(int(data['to_account_id']))
    new_amount = float(data.get('amount', t.amount))
    t.date = data.get('date', t.date)
    t.from_account_id = new_from.id
    t.to_account_id = new_to.id
    t.from_account_name = new_from.bank_name
    t.to_account_name = new_to.bank_name
    t.amount = new_amount
    t.notes = data.get('notes', t.notes)
    new_from.balance -= new_amount
    new_to.balance += new_amount
    db.session.commit()
    return jsonify(t.to_dict())


if __name__ == '__main__':
    if FROZEN:
        # Standalone .exe: ensure tables exist, open the browser, run a plain server.
        import threading
        import webbrowser
        with app.app_context():
            db.create_all()
        threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()
        app.run(host='127.0.0.1', port=5000, debug=False)
    else:
        app.run(debug=True, port=5000)

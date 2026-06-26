from flask import Flask, request, jsonify, render_template
from models import db, MutualFund, Stock, BankAccount, Loan, ChitFund, FixedDeposit, CreditGiven, Income

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()


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


if __name__ == '__main__':
    app.run(debug=True, port=5000)

import os
import sys
import uuid
from datetime import date, timedelta

from flask import Flask, request, jsonify, render_template, session, redirect
from models import (
    db, MutualFund, Stock, BankAccount, Loan, ChitFund, FixedDeposit,
    CreditGiven, Income, Expense, Transfer,
    Account, Transaction, AccountTypeMaster, TransactionCategoryMaster, StagedTransaction,
    NetWorthSnapshot, AnalysisReport,
)
import prices
import services
import ingestion
import analysis

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
    # Pin to ONE explicit absolute file so the DB can never silently move between
    # the project root and instance/ across Flask-SQLAlchemy versions (which is
    # what caused a fresh/empty DB to be read while real data sat in the other
    # file). Prefer an existing finance.db; default to instance/finance.db.
    _BASE = os.path.dirname(os.path.abspath(__file__))
    _inst = os.path.join(_BASE, 'instance', 'finance.db')
    _root = os.path.join(_BASE, 'finance.db')
    if os.path.exists(_inst):
        db_path = _inst
    elif os.path.exists(_root):
        db_path = _root
    else:
        os.makedirs(os.path.join(_BASE, 'instance'), exist_ok=True)
        db_path = _inst
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Wait up to 30s for a busy lock instead of failing immediately (sqlite default 5s).
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'timeout': 30}}
db.init_app(app)


# ─── Authentication (session login) ──────────────────────────────────────────
# A password gate for exposing the app beyond localhost (e.g. via a tunnel).
# It is OFF by default so local desktop use is frictionless: set the env var
# FINTRACKER_PASSWORD to turn it on. The session secret is persisted so logins
# survive restarts.
_WRITABLE_DIR = APP_DIR if 'APP_DIR' in dir() else os.path.dirname(os.path.abspath(__file__))


def _load_or_create_secret():
    path = os.path.join(_WRITABLE_DIR, '.flask_secret')
    try:
        with open(path) as fh:
            key = fh.read().strip()
            if key:
                return key
    except OSError:
        pass
    import secrets as _secrets
    key = _secrets.token_hex(32)
    try:
        with open(path, 'w') as fh:
            fh.write(key)
    except OSError:
        pass
    return key


_PW_PLACEHOLDER = 'choose-a-strong-password'


def _read_text_any_encoding(path):
    """Read a text file, tolerating UTF-8 (with/without BOM), UTF-16, or latin-1
    (editors save .bat/.txt in various encodings). Returns '' if unreadable."""
    try:
        with open(path, 'rb') as fh:
            raw = fh.read()
    except OSError:
        return ''
    for enc in ('utf-8-sig', 'utf-16', 'latin-1'):
        try:
            return raw.decode(enc)
        except (UnicodeError, LookupError):
            continue
    return raw.decode('utf-8', errors='ignore')


def _clean_pw(val):
    val = (val or '').strip().strip('"').strip()
    return '' if not val or val == _PW_PLACEHOLDER else val


def _password_from_txt():
    """Simplest option: a plain password.txt whose entire content is the password."""
    return _clean_pw(_read_text_any_encoding(os.path.join(_WRITABLE_DIR, 'password.txt')))


def _password_from_bat():
    """Read FINTRACKER_PASSWORD out of set_api_key.bat (any encoding)."""
    import re
    text = _read_text_any_encoding(os.path.join(_WRITABLE_DIR, 'set_api_key.bat'))
    m = re.search(r'FINTRACKER_PASSWORD\s*=\s*"?([^"\r\n]+)"?', text, re.IGNORECASE)
    return _clean_pw(m.group(1)) if m else ''


def _resolve_password():
    """Login password from (in order): env var, password.txt, set_api_key.bat.
    Works regardless of how the app is launched."""
    return (os.environ.get('FINTRACKER_PASSWORD') or _password_from_txt()
            or _password_from_bat())


app.secret_key = os.environ.get('FINTRACKER_SECRET') or _load_or_create_secret()
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
APP_PASSWORD = _resolve_password()


def _is_local_request():
    """True only for genuine localhost access with no proxy/tunnel in front.
    Tunnels (ngrok/cloudflared) reach a non-loopback Host and add X-Forwarded-*
    headers, so this also defeats a spoofed `Host: localhost`."""
    host = (request.host or '').split(':')[0].lower()
    if host not in ('localhost', '127.0.0.1', '::1', '[::1]'):
        return False
    if request.headers.get('X-Forwarded-For') or request.headers.get('X-Forwarded-Host'):
        return False
    return True


@app.before_request
def _require_login():
    if not APP_PASSWORD:
        # No password configured: allow localhost (desktop), but FAIL CLOSED for
        # anything arriving over a tunnel / from another host, so a forgotten
        # password can never expose data publicly.
        if _is_local_request():
            return
        return (
            '<h2>Remote access is disabled</h2><p>This app is running without a '
            'login password, so it only serves the local machine. To use it over '
            'a tunnel or your network, set <code>FINTRACKER_PASSWORD</code> and '
            'restart.</p>', 403
        )
    if request.endpoint == 'static' or request.path.startswith('/login'):
        return
    if session.get('authed'):
        return
    if request.path.startswith('/api/'):
        return jsonify({'error': 'unauthorized'}), 401
    return redirect('/login')


# Every new SQLite connection: enable WAL (readers don't block the writer) and a
# generous busy timeout, so the price-refresh write can't collide with the
# browser's concurrent reads and raise "database is locked". Registered on the
# Engine class so it applies without needing an app context at import time.
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, 'connect')
def _sqlite_pragmas(dbapi_connection, _record):
    import sqlite3
    if isinstance(dbapi_connection, sqlite3.Connection):
        cur = dbapi_connection.cursor()
        cur.execute('PRAGMA journal_mode=WAL')
        cur.execute('PRAGMA busy_timeout=30000')
        cur.close()


app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0   # let asset-version query control caching


def _asset_version():
    """Max mtime of the CSS/JS so their ?v= changes when they change → browsers
    fetch the new file automatically (no hard-refresh needed, esp. on mobile)."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    latest = 0
    for name in ('style.css', 'app.js'):
        try:
            latest = max(latest, int(os.path.getmtime(os.path.join(base, name))))
        except OSError:
            pass
    return latest


@app.context_processor
def _inject_asset_v():
    return {'asset_v': _asset_version()}


@app.after_request
def _no_cache_api(response):
    """Stop the browser from serving stale JSON after a mutation (e.g. a loan
    prepayment): the dashboard/loans GETs must always hit the server."""
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


# ─── Legacy → ledger migration ──────────────────────────────────────────────

# Old expense category labels → new ledger category codes.
_LEGACY_EXPENSE_MAP = {
    'Food': 'EXPENSE_FOOD', 'Transport': 'EXPENSE_TRANSPORT', 'Shopping': 'EXPENSE_SHOPPING',
    'Health': 'EXPENSE_HEALTH', 'Entertainment': 'EXPENSE_ENTERTAINMENT',
    'Utilities': 'EXPENSE_UTILITIES', 'Rent': 'EXPENSE_RENT', 'Education': 'EXPENSE_EDUCATION',
    'Fuel': 'EXPENSE_FUEL', 'Chit Contribution': 'CHIT_INSTALLMENT', 'EMI': 'EMI',
    'Other': 'EXPENSE_OTHER',
}


def ensure_legacy_columns():
    """Add columns introduced after a table first shipped.

    db.create_all() creates missing tables but never alters existing ones, so a
    pre-existing finance.db keeps its old `credits` / `chit_funds` schema. The
    ORM then selects columns (account_id, …) that aren't there yet and crashes.
    Patch them in with raw SQL — guarded by PRAGMA — before any ORM query runs.
    """
    patches = {
        'credits': [('account_id', 'INTEGER')],
        'chit_funds': [('account_id', 'INTEGER')],
        'stocks': [('currency', "VARCHAR(8) DEFAULT 'INR'"), ('fx_rate', 'FLOAT DEFAULT 1.0')],
        'mutual_funds': [
            ('is_sip', 'BOOLEAN DEFAULT 0'), ('sip_amount', 'FLOAT DEFAULT 0'),
            ('sip_day', 'INTEGER'), ('sip_frequency', "VARCHAR(15) DEFAULT 'monthly'"),
            ('sip_start_date', 'VARCHAR(20)'), ('sip_status', "VARCHAR(15) DEFAULT 'active'"),
            ('sip_account_id', 'INTEGER'),
        ],
        'loans': [('advance_amount', 'FLOAT DEFAULT 0')],
        'bank_accounts': [('account_subtype', "VARCHAR(20) DEFAULT 'bank'")],
        'expenses': [('account_name', 'VARCHAR(100)')],
        'transfers': [('from_account_name', 'VARCHAR(100)'),
                      ('to_account_name', 'VARCHAR(100)')],
    }
    with db.engine.connect() as conn:
        for table, cols in patches.items():
            existing = [r[1] for r in conn.execute(db.text(f"PRAGMA table_info({table})")).fetchall()]
            if not existing:
                continue  # table doesn't exist on this DB — create_all handles it
            for name, decl in cols:
                if name not in existing:
                    conn.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {name} {decl}"))
        conn.commit()


def migrate_legacy_if_needed():
    """One-time move of pre-ledger cash data into accounts + transactions.

    Runs only when the ledger is empty but legacy bank accounts exist. Existing
    BankAccount balances already net out their expenses/transfers, so historical
    transactions are recorded WITHOUT re-applying balance effects (no double count).
    """
    if Account.query.first() is not None:
        return  # ledger already populated (fresh seed or prior migration)
    if BankAccount.query.first() is None:
        return  # nothing legacy to migrate

    services.seed_masters()

    # Banks / wallets → accounts, keeping an old-id → new-account map.
    id_map = {}
    for b in BankAccount.query.all():
        is_wallet = (b.account_subtype or '').lower() == 'wallet' or (b.account_type or '').lower() == 'wallet'
        subtype = 'wallet' if is_wallet else 'bank'
        acct = Account(
            name=b.bank_name,
            account_type_code='WALLET' if subtype == 'wallet' else 'BANK',
            current_balance=b.balance or 0,
            subtype=subtype,
            meta=b.account_number or '',
        )
        db.session.add(acct)
        db.session.flush()
        id_map[b.id] = acct.id

    def _hist(**kw):
        """Insert a historical transaction without touching balances."""
        db.session.add(Transaction(status='posted', source='manual', **kw))

    for e in Expense.query.all():
        _hist(
            from_account_id=id_map.get(e.account_id),
            amount=e.amount or 0,
            category_code=_LEGACY_EXPENSE_MAP.get(e.category, 'EXPENSE_OTHER'),
            transaction_date=e.date, description=e.description or '',
        )
    for t in Transfer.query.all():
        _hist(
            from_account_id=id_map.get(t.from_account_id),
            to_account_id=id_map.get(t.to_account_id),
            amount=t.amount or 0, category_code='TRANSFER',
            transaction_date=t.date, description=t.notes or '',
        )
    for i in Income.query.all():
        cat = 'SALARY' if i.income_type == 'salary' else ('DIVIDEND' if i.income_type == 'dividend' else 'OTHER_INCOME')
        _hist(
            amount=i.amount or 0, category_code=cat,
            transaction_date=i.date,
            description=i.description or i.employer or i.stock_name or '',
        )

    # Friendly loans → LOAN_ASSET accounts holding the outstanding receivable.
    for c in CreditGiven.query.all():
        outstanding = (c.amount or 0) if c.status == 'outstanding' else 0
        acct = Account(
            name=f'Loan · {c.person_name}', account_type_code='LOAN_ASSET',
            current_balance=outstanding, subtype='loan_asset', meta=c.person_name,
        )
        db.session.add(acct)
        db.session.flush()
        c.account_id = acct.id

    # Chits → linked CHIT accounts holding accumulated contributions.
    for ch in ChitFund.query.all():
        acct = Account(
            name=ch.chit_name, account_type_code='CHIT',
            current_balance=0, subtype='chit', meta=ch.organizer or '',
            is_liability=(ch.auction_status == 'auctioned'),
        )
        db.session.add(acct)
        db.session.flush()
        ch.account_id = acct.id

    db.session.commit()


def _backup_db(keep=10):
    """Snapshot the DB into backups/ on every startup, keeping the newest `keep`.
    A consistent copy via the sqlite backup API (handles WAL). Best-effort."""
    try:
        if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
            return
        import sqlite3 as _sq, glob as _glob, shutil as _shutil
        from datetime import datetime as _dt
        bdir = os.path.join(os.path.dirname(db_path) or '.', 'backups')
        os.makedirs(bdir, exist_ok=True)
        dest = os.path.join(bdir, 'finance-' + _dt.now().strftime('%Y%m%d-%H%M%S') + '.db')
        src = _sq.connect(db_path)
        dst = _sq.connect(dest)
        with dst:
            src.backup(dst)
        src.close(); dst.close()
        for old in sorted(_glob.glob(os.path.join(bdir, 'finance-*.db')))[:-keep]:
            try:
                os.remove(old)
            except OSError:
                pass
    except Exception:
        pass   # never let a backup failure stop the app


if not APP_PASSWORD:
    print('[warn] No FINTRACKER_PASSWORD set — remote/tunnel access is blocked; '
          'localhost only. Set it to enable login + remote access.')

with app.app_context():
    _backup_db()              # snapshot current data before doing anything
    db.create_all()
    ensure_legacy_columns()   # patch new columns onto pre-existing tables first
    services.seed_masters()
    migrate_legacy_if_needed()


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
@app.route('/accounts')
def accounts_page():
    return render_template('accounts.html')

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

@app.route('/transactions')
@app.route('/income')
@app.route('/expenses')
@app.route('/transfers')
def transactions_page():
    return render_template('transactions.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not APP_PASSWORD:
        return redirect('/')            # auth disabled
    error = ''
    if request.method == 'POST':
        if request.form.get('password') == APP_PASSWORD:
            session.permanent = True
            session['authed'] = True
            return redirect('/')
        error = 'Incorrect password'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@app.route('/analysis')
def analysis_page():
    return render_template('analysis.html')

@app.route('/import')
def import_page():
    return render_template('import.html')


# ─── Master reference ──────────────────────────────────────────────────────────

@app.route('/api/account-types')
def api_account_types():
    return jsonify([t.to_dict() for t in AccountTypeMaster.query.filter_by(is_active=True).all()])

@app.route('/api/categories')
def api_categories():
    return jsonify([c.to_dict() for c in TransactionCategoryMaster.query.all()])


# ─── Dashboard API ─────────────────────────────────────────────────────────────

@app.route('/api/dashboard')
def api_dashboard():
    # Ledger accounts split into assets vs liabilities (chit flips post-auction).
    asset_accounts = 0.0
    liability_accounts = 0.0
    for a in Account.query.filter(Account.account_type_code != 'EXTERNAL').all():
        bal = float(a.current_balance or 0)
        if a.is_liability:
            liability_accounts += bal
        else:
            asset_accounts += bal

    mf_total = sum(f.units * f.current_nav for f in MutualFund.query.all())
    # Convert each holding to INR via its fx_rate (1 for INR-quoted stocks).
    stock_total = sum(s.quantity * s.current_price * (s.fx_rate or 1.0) for s in Stock.query.all())
    fd_total = sum(f.principal_amount for f in FixedDeposit.query.all())
    loan_total = sum(l.outstanding_amount for l in Loan.query.all())

    total_assets = asset_accounts + mf_total + stock_total + fd_total
    total_liabilities = loan_total + liability_accounts
    net_worth = total_assets - total_liabilities

    # Recent income = latest INFLOW transactions.
    recent_income = [t.to_dict() for t in (
        Transaction.query.join(TransactionCategoryMaster)
        .filter(TransactionCategoryMaster.direction == 'INFLOW', Transaction.status == 'posted')
        .order_by(Transaction.transaction_date.desc()).limit(5).all()
    )]

    # This-month spending by category, from OUTFLOW transactions.
    this_month = date.today().strftime('%Y-%m')
    outflows = (
        Transaction.query.join(TransactionCategoryMaster)
        .filter(TransactionCategoryMaster.direction == 'OUTFLOW',
                Transaction.status == 'posted',
                Transaction.transaction_date.startswith(this_month)).all()
    )
    monthly_expenses = sum(float(t.amount) for t in outflows)
    expense_by_category = {}
    for t in outflows:
        label = t.category.display_name if t.category else t.category_code
        expense_by_category[label] = round(expense_by_category.get(label, 0) + float(t.amount), 2)

    # Recurring monthly commitments: loan EMIs, active SIPs, chit contributions.
    emi_items = [{'type': 'EMI', 'name': f"{l.lender} ({l.loan_type})",
                  'amount': (l.emi_amount or 0) + (l.advance_amount or 0), 'due': l.next_due_date}
                 for l in Loan.query.all() if (l.emi_amount or 0) + (l.advance_amount or 0) > 0]
    sip_items = [{'type': 'SIP', 'name': f.fund_name,
                  'amount': f._monthly_sip(), 'due': f._next_sip_date()}
                 for f in MutualFund.query.all() if f._monthly_sip() > 0]
    chit_items = [{'type': 'Chit', 'name': c.chit_name,
                   'amount': c.monthly_contribution, 'due': None}
                  for c in ChitFund.query.all()
                  if c.monthly_contribution and c.auction_status != 'completed']
    emi_total = round(sum(i['amount'] for i in emi_items), 2)
    sip_total = round(sum(i['amount'] for i in sip_items), 2)
    chit_total = round(sum(i['amount'] for i in chit_items), 2)

    # Capture / refresh today's net-worth snapshot for the trend chart.
    today_str = date.today().isoformat()
    snap = NetWorthSnapshot.query.filter_by(date=today_str).first()
    if not snap:
        snap = NetWorthSnapshot(date=today_str)
        db.session.add(snap)
    snap.net_worth = round(net_worth, 2)
    snap.total_assets = round(total_assets, 2)
    snap.total_liabilities = round(total_liabilities, 2)
    db.session.commit()

    return jsonify({
        'net_worth': round(net_worth, 2),
        'total_assets': round(total_assets, 2),
        'total_liabilities': round(total_liabilities, 2),
        'breakdown': {
            'Cash & Wallets': round(sum(float(a.current_balance or 0) for a in
                Account.query.filter(Account.account_type_code.in_(['BANK', 'WALLET'])).all()), 2),
            'Trading Cash': round(sum(float(a.current_balance or 0) for a in
                Account.query.filter_by(account_type_code='DEMAT').all()), 2),
            'Mutual Funds': round(mf_total, 2),
            'Stocks': round(stock_total, 2),
            'Fixed Deposits': round(fd_total, 2),
            'Loans Given': round(sum(float(a.current_balance or 0) for a in
                Account.query.filter_by(account_type_code='LOAN_ASSET').all()), 2),
        },
        'recent_income': recent_income,
        'monthly_expenses': round(monthly_expenses, 2),
        'expense_by_category': expense_by_category,
        'monthly_commitments': {
            'emi': emi_total, 'sip': sip_total, 'chit': chit_total,
            'total': round(emi_total + sip_total + chit_total, 2),
            'items': sorted(emi_items + sip_items + chit_items,
                            key=lambda i: i['amount'], reverse=True),
        },
    })


@app.route('/api/networth-history')
def api_networth_history():
    """Daily net-worth snapshots for the trend chart, oldest first."""
    snaps = NetWorthSnapshot.query.order_by(NetWorthSnapshot.date).all()
    return jsonify([s.to_dict() for s in snaps])


# ─── Accounts (unified ledger accounts) ─────────────────────────────────────────

_SUBTYPE_TO_TYPE = {'bank': 'BANK', 'wallet': 'WALLET', 'demat': 'DEMAT'}


@app.route('/api/accounts', methods=['GET', 'POST'])
@app.route('/api/bank-accounts', methods=['GET', 'POST'])   # back-compat alias
def api_accounts():
    if request.method == 'GET':
        accts = Account.query.filter(Account.account_type_code != 'EXTERNAL').all()
        return jsonify([a.to_dict() for a in accts])
    data = request.json
    subtype = data.get('subtype', 'bank')
    type_code = data.get('account_type_code') or _SUBTYPE_TO_TYPE.get(subtype, 'BANK')
    a = Account(
        name=data.get('name') or data.get('bank_name'),
        account_type_code=type_code,
        current_balance=float(data.get('current_balance', data.get('balance', 0)) or 0),
        subtype=subtype,
        meta=data.get('meta', data.get('account_number', '')),
    )
    db.session.add(a)
    db.session.commit()
    return jsonify(a.to_dict()), 201


@app.route('/api/accounts/<int:id>', methods=['PUT', 'DELETE'])
@app.route('/api/bank-accounts/<int:id>', methods=['PUT', 'DELETE'])
def api_account(id):
    a = Account.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(a)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    a.name = data.get('name', data.get('bank_name', a.name))
    if 'account_type_code' in data:
        a.account_type_code = data['account_type_code']
    if 'subtype' in data:
        a.subtype = data['subtype']
        # Only remap the cash-account family (bank/wallet/demat); leave CHIT/LOAN_ASSET.
        if a.account_type_code in ('BANK', 'WALLET', 'DEMAT'):
            a.account_type_code = _SUBTYPE_TO_TYPE.get(data['subtype'], 'BANK')
    if 'current_balance' in data or 'balance' in data:
        a.current_balance = float(data.get('current_balance', data.get('balance', a.current_balance)))
    a.meta = data.get('meta', data.get('account_number', a.meta))
    db.session.commit()
    return jsonify(a.to_dict())


@app.route('/api/accounts/<int:id>/pnl', methods=['POST'])
def api_account_pnl(id):
    """Record realised trading P&L on a demat account: gain credits it, loss
    debits it. Posts a TRADING_GAIN/TRADING_LOSS transaction so it shows in
    history and the balance updates atomically."""
    a = Account.query.get_or_404(id)
    data = request.json
    amount = float(data['amount'])
    kind = (data.get('kind') or 'gain').lower()
    when = data.get('date') or date.today().isoformat()
    note = data.get('note', '') or f"Option trading {kind}"
    if kind == 'loss':
        txn = services.post_transaction(
            from_account_id=a.id, to_account_id=None, amount=amount,
            category_code='TRADING_LOSS', transaction_date=when, description=note)
    else:
        txn = services.post_transaction(
            from_account_id=None, to_account_id=a.id, amount=amount,
            category_code='TRADING_GAIN', transaction_date=when, description=note)
    return jsonify({'account': db.session.get(Account, a.id).to_dict(),
                    'transaction': txn.to_dict()}), 201


# ─── Transactions (the ledger) ──────────────────────────────────────────────────

@app.route('/api/transactions', methods=['GET', 'POST'])
def api_transactions():
    if request.method == 'GET':
        q = Transaction.query.filter_by(status='posted')
        direction = request.args.get('direction')
        if direction:
            q = q.join(TransactionCategoryMaster).filter(TransactionCategoryMaster.direction == direction)
        txns = q.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).all()
        return jsonify([t.to_dict() for t in txns])

    data = request.json
    txn = services.post_transaction(
        from_account_id=int(data['from_account_id']) if data.get('from_account_id') else None,
        to_account_id=int(data['to_account_id']) if data.get('to_account_id') else None,
        amount=float(data['amount']),
        category_code=data['category_code'],
        transaction_date=data['transaction_date'],
        description=data.get('description', ''),
    )
    return jsonify(txn.to_dict()), 201


@app.route('/api/transactions/<int:id>', methods=['PUT', 'DELETE'])
def api_transaction(id):
    txn = Transaction.query.get_or_404(id)
    if request.method == 'DELETE':
        services.reverse_transaction(txn)
        return jsonify({'message': 'Deleted'})
    # Edit = reverse old effect, then re-post with new values.
    data = request.json
    services.reverse_transaction(txn, delete=True, commit=False)
    new = services.post_transaction(
        from_account_id=int(data['from_account_id']) if data.get('from_account_id') else None,
        to_account_id=int(data['to_account_id']) if data.get('to_account_id') else None,
        amount=float(data['amount']),
        category_code=data['category_code'],
        transaction_date=data['transaction_date'],
        description=data.get('description', ''),
    )
    return jsonify(new.to_dict())


# ─── Mutual Funds ──────────────────────────────────────────────────────────────

def _apply_sip_fields(mf, data):
    """Persist SIP metadata from a request body onto a MutualFund."""
    is_sip = data.get('is_sip')
    mf.is_sip = is_sip in (True, 'true', 'on', 1, '1') if is_sip is not None else bool(mf.is_sip)
    if mf.is_sip:
        mf.sip_amount = float(data.get('sip_amount') or mf.sip_amount or 0)
        mf.sip_day = int(data['sip_day']) if data.get('sip_day') else mf.sip_day
        mf.sip_frequency = data.get('sip_frequency') or mf.sip_frequency or 'monthly'
        mf.sip_start_date = data.get('sip_start_date', mf.sip_start_date)
        mf.sip_status = data.get('sip_status') or mf.sip_status or 'active'
        if data.get('sip_account_id'):
            mf.sip_account_id = int(data['sip_account_id'])


@app.route('/api/mutual-funds', methods=['GET', 'POST'])
def api_mutual_funds():
    if request.method == 'GET':
        return jsonify([f.to_dict() for f in MutualFund.query.all()])
    data = request.json
    mf = MutualFund(
        platform=data['platform'], fund_name=data['fund_name'],
        folio_number=data.get('folio_number', ''), units=float(data['units']),
        avg_nav=float(data['avg_nav']), current_nav=float(data['current_nav']),
        investment_date=data.get('investment_date', ''), scheme_code=data.get('scheme_code', ''),
        last_updated=data.get('last_updated', ''),
    )
    _apply_sip_fields(mf, data)
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
    _apply_sip_fields(mf, data)
    db.session.commit()
    return jsonify(mf.to_dict())


def _invest_in_fund(mf, amount, nav, account_id, when):
    """Buy `amount` worth of units at `nav`, updating units + weighted avg NAV,
    and debit the paying account. Shared by /invest and /buy."""
    units_bought = amount / nav
    new_invested = mf.units * mf.avg_nav + amount
    mf.units = mf.units + units_bought
    mf.avg_nav = new_invested / mf.units if mf.units else nav
    if not mf.current_nav:
        mf.current_nav = nav
    acct = None
    if account_id:
        acct = Account.query.get_or_404(int(account_id))
        services.post_transaction(
            from_account_id=acct.id, to_account_id=None, amount=amount,
            category_code='MF_INVESTMENT', transaction_date=when,
            description=f'Invest · {mf.fund_name}', commit=False,
        )
    return acct


@app.route('/api/mutual-funds/<int:id>/invest', methods=['POST'])
def api_mutual_fund_invest(id):
    """Invest money from a bank account into this fund (SIP installment or lump sum)."""
    mf = MutualFund.query.get_or_404(id)
    data = request.json
    amount = float(data['amount'])
    nav = float(data.get('nav') or mf.current_nav or 0)
    if amount <= 0 or nav <= 0:
        return jsonify({'error': 'amount and NAV must be positive'}), 400
    acct = _invest_in_fund(mf, amount, nav, data.get('account_id'), data.get('date') or date.today().isoformat())
    db.session.commit()
    return jsonify({'fund': mf.to_dict(),
                    'account': acct.to_dict() if acct else None}), 201


@app.route('/api/mutual-funds/buy', methods=['POST'])
def api_mutual_funds_buy():
    """Buy into a fund from the Transactions screen. Existing fund (fund_id) →
    average up; otherwise create a new fund under the given platform, then invest."""
    data = request.json
    amount = float(data['amount'])
    if data.get('fund_id'):
        mf = MutualFund.query.get_or_404(int(data['fund_id']))
        nav = float(data.get('nav') or mf.current_nav or 0)
    else:
        nav = float(data.get('nav') or data.get('avg_nav') or 0)
        if not data.get('platform') or not data.get('fund_name'):
            return jsonify({'error': 'platform and fund_name required for a new fund'}), 400
        mf = MutualFund(
            platform=data['platform'], fund_name=data['fund_name'],
            folio_number=data.get('folio_number', ''), units=0,
            avg_nav=nav, current_nav=nav, scheme_code=data.get('scheme_code', ''),
            investment_date=data.get('date', ''),
        )
        db.session.add(mf)
        db.session.flush()
    if amount <= 0 or nav <= 0:
        return jsonify({'error': 'amount and NAV must be positive'}), 400
    acct = _invest_in_fund(mf, amount, nav, data.get('account_id'), data.get('date') or date.today().isoformat())
    db.session.commit()
    return jsonify({'fund': mf.to_dict(), 'account': acct.to_dict() if acct else None}), 201


# ─── AI portfolio analysis ───────────────────────────────────────────────────

@app.route('/api/analysis', methods=['GET'])
def api_analysis_list():
    reports = AnalysisReport.query.order_by(AnalysisReport.id.desc()).all()
    return jsonify([r.to_dict() for r in reports])


@app.route('/api/analysis/<int:id>', methods=['GET'])
def api_analysis_get(id):
    r = AnalysisReport.query.get_or_404(id)
    return jsonify(r.to_dict(include_html=True))


@app.route('/api/analysis/run', methods=['POST'])
def api_analysis_run():
    data = request.json or {}
    try:
        report = analysis.run_portfolio_analysis(overlap_text=data.get('overlap_text', ''))
    except analysis.AnalysisError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(report.to_dict(include_html=True)), 201


# ─── Stocks ────────────────────────────────────────────────────────────────────

@app.route('/api/stocks', methods=['GET', 'POST'])
def api_stocks():
    if request.method == 'GET':
        return jsonify([s.to_dict() for s in Stock.query.all()])
    data = request.json
    currency = (data.get('currency') or 'INR').upper()
    # Resolve fx: explicit value > live lookup for non-INR > 1.0 fallback.
    if data.get('fx_rate'):
        fx_rate = float(data['fx_rate'])
    elif currency != 'INR':
        fx_rate = prices.fetch_fx_rate(currency, 'INR') or 1.0
    else:
        fx_rate = 1.0
    s = Stock(
        demat_account=data['demat_account'], company_name=data['company_name'],
        ticker=data['ticker'], quantity=int(data['quantity']),
        avg_price=float(data['avg_price']), current_price=float(data['current_price']),
        sector=data.get('sector', ''), exchange=data.get('exchange', 'NSE'),
        last_updated=data.get('last_updated', ''),
        currency=currency, fx_rate=fx_rate,
    )
    db.session.add(s)
    db.session.commit()
    return jsonify(s.to_dict()), 201


@app.route('/api/stocks/buy', methods=['POST'])
def api_stocks_buy():
    """Buy a stock from the Transactions screen. If (demat, ticker) already
    exists, average up (qty + weighted avg price); otherwise create the holding
    under that demat. Debits the paying account by qty*price (in INR)."""
    data = request.json
    demat = data['demat_account'].strip()
    ticker = data['ticker'].strip().upper()
    qty = int(data['quantity'])
    price = float(data['price'])
    if qty <= 0 or price <= 0:
        return jsonify({'error': 'quantity and price must be positive'}), 400
    currency = (data.get('currency') or 'INR').upper()

    existing = Stock.query.filter_by(demat_account=demat, ticker=ticker).first()
    if existing:
        total = existing.quantity + qty
        existing.avg_price = (existing.quantity * existing.avg_price + qty * price) / total
        existing.quantity = total
        if not existing.current_price:
            existing.current_price = price
        stock = existing
    else:
        if data.get('fx_rate'):
            fx_rate = float(data['fx_rate'])
        elif currency != 'INR':
            fx_rate = prices.fetch_fx_rate(currency, 'INR') or 1.0
        else:
            fx_rate = 1.0
        stock = Stock(
            demat_account=demat, company_name=data.get('company_name') or ticker,
            ticker=ticker, quantity=qty, avg_price=price, current_price=price,
            sector=data.get('sector', ''), exchange=data.get('exchange', 'NSE'),
            currency=currency, fx_rate=fx_rate,
        )
        db.session.add(stock)
        db.session.flush()

    acct = None
    if data.get('account_id'):
        acct = Account.query.get_or_404(int(data['account_id']))
        amount_inr = qty * price * (stock.fx_rate or 1.0)
        services.post_transaction(
            from_account_id=acct.id, to_account_id=None, amount=amount_inr,
            category_code='STOCK_PURCHASE', transaction_date=data.get('date') or date.today().isoformat(),
            description=f'Buy {qty} {ticker} @ {ccy_prefix(currency)}{price}', commit=False,
        )
    db.session.commit()
    return jsonify({'stock': stock.to_dict(), 'account': acct.to_dict() if acct else None}), 201


def ccy_prefix(currency):
    return '$' if (currency or 'INR').upper() == 'USD' else '₹'


@app.route('/api/stocks/sell', methods=['POST'])
def api_stocks_sell():
    """Sell part/all of a holding (double-entry): reduce quantity and credit the
    sale proceeds into a bank/demat account. Cost basis (avg) is unchanged on a
    partial sell; a full sell removes the holding. Reports realized gain/loss."""
    data = request.json
    stock = Stock.query.get_or_404(int(data['stock_id']))
    qty = int(data['quantity'])
    price = float(data['price'])
    if qty <= 0 or qty > stock.quantity:
        return jsonify({'error': f'quantity must be 1..{stock.quantity}'}), 400
    if price <= 0:
        return jsonify({'error': 'price must be positive'}), 400

    fx = stock.fx_rate or 1.0
    proceeds_inr = qty * price * fx
    realized_inr = (price - stock.avg_price) * qty * fx
    ticker, currency = stock.ticker, stock.currency

    stock.quantity -= qty
    stock_dict = stock.to_dict() if stock.quantity > 0 else None
    if stock.quantity <= 0:
        db.session.delete(stock)

    acct = None
    if data.get('account_id'):
        acct = Account.query.get_or_404(int(data['account_id']))
        services.post_transaction(
            from_account_id=None, to_account_id=acct.id, amount=proceeds_inr,
            category_code='STOCK_SELL', transaction_date=data.get('date') or date.today().isoformat(),
            description=f'Sell {qty} {ticker} @ {ccy_prefix(currency)}{price}', commit=False,
        )
    db.session.commit()
    return jsonify({
        'stock': stock_dict,
        'account': db.session.get(Account, acct.id).to_dict() if acct else None,
        'realized': round(realized_inr, 2),
    }), 201


@app.route('/api/stocks/<int:id>/history')
def api_stock_history(id):
    """OHLC price history for the in-app chart, plus the holding's avg/current
    price so the frontend can draw the buy-price line."""
    s = Stock.query.get_or_404(id)
    rng = request.args.get('range', '1y')
    candles, currency = prices.fetch_stock_history(s.ticker, s.exchange, rng=rng)
    return jsonify({
        'ticker': s.ticker, 'exchange': s.exchange,
        'symbol': f'{s.exchange}:{s.ticker}',
        'currency': currency or s.currency or 'INR',
        'avg_price': s.avg_price, 'current_price': s.current_price,
        'candles': candles,
    })


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
    if 'currency' in data:
        s.currency = (data.get('currency') or 'INR').upper()
        if s.currency == 'INR':
            s.fx_rate = 1.0
    if 'fx_rate' in data:
        s.fx_rate = float(data.get('fx_rate') or s.fx_rate or 1.0)
    db.session.commit()
    return jsonify(s.to_dict())


# ─── Loans ─────────────────────────────────────────────────────────────────────

@app.route('/api/loans', methods=['GET', 'POST'])
def api_loans():
    if request.method == 'GET':
        return jsonify([l.to_dict() for l in Loan.query.all()])
    data = request.json
    l = Loan(
        loan_type=data['loan_type'], lender=data['lender'],
        principal_amount=float(data['principal_amount']),
        outstanding_amount=float(data['outstanding_amount']),
        interest_rate=float(data['interest_rate']), emi_amount=float(data['emi_amount']),
        advance_amount=float(data.get('advance_amount') or 0),
        tenure_months=int(data['tenure_months']), start_date=data.get('start_date', ''),
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
    l.advance_amount = float(data.get('advance_amount', l.advance_amount or 0) or 0)
    l.tenure_months = int(data.get('tenure_months', l.tenure_months))
    l.start_date = data.get('start_date', l.start_date)
    l.next_due_date = data.get('next_due_date', l.next_due_date)
    db.session.commit()
    return jsonify(l.to_dict())


@app.route('/api/loans/<int:id>/prepay', methods=['POST'])
def api_loan_prepay(id):
    """Make an extra principal payment: debit a bank account through the ledger
    and reduce the loan's outstanding. Net worth stays flat (cash down, debt down)."""
    l = Loan.query.get_or_404(id)
    data = request.json or {}
    try:
        amount = float(data.get('amount') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid amount'}), 400
    if amount <= 0:
        return jsonify({'error': 'amount must be > 0'}), 400
    if amount > l.outstanding_amount + 1e-6:
        return jsonify({'error': 'amount exceeds outstanding balance'}), 400

    account_id = data.get('account_id')
    when = data.get('date') or date.today().isoformat()
    if account_id:
        services.post_transaction(
            from_account_id=int(account_id), to_account_id=None,
            amount=amount, category_code='LOAN_PREPAYMENT',
            transaction_date=when,
            description=f'Prepayment · {l.lender} ({l.loan_type})',
            commit=False,
        )
    l.outstanding_amount = round(l.outstanding_amount - amount, 2)
    db.session.commit()
    acct = Account.query.get(int(account_id)) if account_id else None
    return jsonify({'loan': l.to_dict(), 'account': acct.to_dict() if acct else None})


# ─── Chit Funds ────────────────────────────────────────────────────────────────

@app.route('/api/chit-funds', methods=['GET', 'POST'])
def api_chit_funds():
    if request.method == 'GET':
        return jsonify([c.to_dict() for c in ChitFund.query.all()])
    data = request.json
    c = ChitFund(
        chit_name=data['chit_name'], total_value=float(data['total_value']),
        monthly_contribution=float(data['monthly_contribution']),
        tenure_months=int(data['tenure_months']), start_date=data.get('start_date', ''),
        auction_status=data.get('auction_status', 'pending'),
        auction_amount=float(data.get('auction_amount', 0)),
        auction_date=data.get('auction_date', ''), organizer=data.get('organizer', ''),
    )
    # Every chit gets a linked CHIT ledger account to hold its running balance.
    acct = Account(
        name=c.chit_name, account_type_code='CHIT', current_balance=0,
        subtype='chit', meta=c.organizer or '',
        is_liability=(c.auction_status == 'auctioned'),
    )
    db.session.add(acct)
    db.session.flush()
    c.account_id = acct.id
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict()), 201


@app.route('/api/chit-funds/<int:id>', methods=['PUT', 'DELETE'])
def api_chit_fund(id):
    c = ChitFund.query.get_or_404(id)
    if request.method == 'DELETE':
        if c.account_id:
            acct = db.session.get(Account, c.account_id)
            if acct:
                db.session.delete(acct)
        db.session.delete(c)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    c.chit_name = data.get('chit_name', c.chit_name)
    c.total_value = float(data.get('total_value', c.total_value))
    c.monthly_contribution = float(data.get('monthly_contribution', c.monthly_contribution))
    c.tenure_months = int(data.get('tenure_months', c.tenure_months))
    c.start_date = data.get('start_date', c.start_date)
    c.organizer = data.get('organizer', c.organizer)
    db.session.commit()
    return jsonify(c.to_dict())


@app.route('/api/chit-funds/<int:id>/auction', methods=['POST'])
def api_chit_auction(id):
    """Record the auction event: chit account → bank, flip chit to a liability."""
    c = ChitFund.query.get_or_404(id)
    if not c.account_id:
        return jsonify({'error': 'Chit has no linked ledger account'}), 400
    data = request.json
    txn = services.record_chit_auction(
        c, to_account_id=int(data['to_account_id']),
        amount=float(data['amount']),
        date=data.get('date') or date.today().isoformat(),
    )
    return jsonify({'chit': c.to_dict(), 'transaction': txn.to_dict()}), 201


# ─── Fixed Deposits ────────────────────────────────────────────────────────────

@app.route('/api/fixed-deposits', methods=['GET', 'POST'])
def api_fixed_deposits():
    if request.method == 'GET':
        return jsonify([f.to_dict() for f in FixedDeposit.query.all()])
    data = request.json
    f = FixedDeposit(
        bank_name=data['bank_name'], account_number=data.get('account_number', ''),
        principal_amount=float(data['principal_amount']), interest_rate=float(data['interest_rate']),
        start_date=data.get('start_date', ''), maturity_date=data.get('maturity_date', ''),
        maturity_amount=float(data.get('maturity_amount') or 0),  # auto-computed from rate+dates
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


# ─── Credits Given (friendly-loan asset book) ───────────────────────────────────

@app.route('/api/credits', methods=['GET', 'POST'])
def api_credits():
    if request.method == 'GET':
        return jsonify([c.to_dict() for c in CreditGiven.query.all()])
    data = request.json
    c = CreditGiven(
        person_name=data['person_name'], amount=float(data['amount']),
        date_given=data.get('date_given', ''), notes=data.get('notes', ''),
        status='outstanding',
    )
    db.session.add(c)
    db.session.flush()
    # Open a LOAN_ASSET receivable; deduct from the funding bank account if given.
    from_id = int(data['from_account_id']) if data.get('from_account_id') else None
    if from_id:
        services.open_loan_asset(c, from_account_id=from_id, amount=c.amount,
                                 date=c.date_given or date.today().isoformat())
    else:
        acct = Account(name=f'Loan · {c.person_name}', account_type_code='LOAN_ASSET',
                       current_balance=c.amount, subtype='loan_asset', meta=c.person_name)
        db.session.add(acct)
        db.session.flush()
        c.account_id = acct.id
        db.session.commit()
    return jsonify(c.to_dict()), 201


@app.route('/api/credits/<int:id>', methods=['PUT', 'DELETE'])
def api_credit(id):
    c = CreditGiven.query.get_or_404(id)
    if request.method == 'DELETE':
        if c.account_id:
            acct = db.session.get(Account, c.account_id)
            if acct:
                db.session.delete(acct)
        db.session.delete(c)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    data = request.json
    c.person_name = data.get('person_name', c.person_name)
    c.date_given = data.get('date_given', c.date_given)
    c.notes = data.get('notes', c.notes)
    db.session.commit()
    return jsonify(c.to_dict())


@app.route('/api/credits/<int:id>/recover', methods=['POST'])
def api_credit_recover(id):
    """Friend repays part/all: LOAN_ASSET → bank; closes the credit at zero."""
    c = CreditGiven.query.get_or_404(id)
    if not c.account_id:
        return jsonify({'error': 'Credit has no linked ledger account'}), 400
    data = request.json
    txn = services.record_loan_recovery(
        c, to_account_id=int(data['to_account_id']), amount=float(data['amount']),
        date=data.get('date') or date.today().isoformat(),
    )
    return jsonify({'credit': c.to_dict(), 'transaction': txn.to_dict()}), 201


# ─── Live Price Refresh ────────────────────────────────────────────────────────

@app.route('/api/refresh-prices', methods=['POST'])
def api_refresh_prices():
    """Refresh mutual fund NAVs (AMFI) and stock prices (Yahoo Finance)."""
    today = date.today().isoformat()
    updated_mf = 0
    updated_stocks = 0
    failed = []

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

    fx_cache = {'INR': 1.0}   # currency → INR rate, fetched at most once per refresh
    for s in Stock.query.all():
        price, currency = prices.fetch_stock_price(s.ticker, s.exchange)
        if price is not None:
            s.current_price = price
            s.last_updated = today
            cur = (currency or s.currency or 'INR').upper()
            s.currency = cur
            if cur not in fx_cache:
                fx_cache[cur] = prices.fetch_fx_rate(cur, 'INR')
            rate = fx_cache.get(cur)
            if rate:
                s.fx_rate = rate
            elif cur != 'INR' and not s.fx_rate:
                failed.append(f'{cur}→INR rate unavailable')
            updated_stocks += 1
        else:
            failed.append(f'{s.ticker} ({s.exchange})')

    db.session.commit()
    return jsonify({'updated_mf': updated_mf, 'updated_stocks': updated_stocks, 'failed': failed})


# ─── Statement Ingestion ───────────────────────────────────────────────────────

@app.route('/api/ingest/upload', methods=['POST'])
def api_ingest_upload():
    """Parse an uploaded PDF into staged rows for review. Nothing posts yet."""
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file uploaded'}), 400
    default_account = request.form.get('account_id')
    default_account = int(default_account) if default_account else None

    rows = ingestion.parse_statement(f)
    batch_id = uuid.uuid4().hex[:12]
    for r in rows:
        db.session.add(StagedTransaction(
            batch_id=batch_id, raw_text=r['raw_text'], parsed_date=r['parsed_date'],
            parsed_amount=r['parsed_amount'], direction=r['direction'],
            suggested_category=r['suggested_category'], suggested_account_id=default_account,
            status='pending',
        ))
    db.session.commit()
    return jsonify({'batch_id': batch_id, 'count': len(rows),
                    'rows': [s.to_dict() for s in StagedTransaction.query.filter_by(batch_id=batch_id).all()]})


@app.route('/api/ingest/staged')
def api_ingest_staged():
    rows = StagedTransaction.query.filter_by(status='pending').order_by(StagedTransaction.id).all()
    return jsonify([s.to_dict() for s in rows])


@app.route('/api/ingest/approve', methods=['POST'])
def api_ingest_approve():
    """Post selected staged rows to the ledger. Each row may carry overrides."""
    data = request.json
    posted = 0
    for item in data.get('rows', []):
        staged = db.session.get(StagedTransaction, int(item['id']))
        if not staged or staged.status != 'pending':
            continue
        category = item.get('category_code') or staged.suggested_category
        account_id = item.get('account_id') or staged.suggested_account_id
        direction = item.get('direction') or staged.direction
        if not account_id or not category:
            continue
        from_id = account_id if direction == 'OUTFLOW' else None
        to_id = account_id if direction == 'INFLOW' else None
        # TRANSFER staged rows need both sides supplied via overrides.
        if direction == 'TRANSFER':
            from_id = item.get('from_account_id')
            to_id = item.get('to_account_id')
        services.post_transaction(
            from_account_id=int(from_id) if from_id else None,
            to_account_id=int(to_id) if to_id else None,
            amount=float(item.get('amount', staged.parsed_amount)),
            category_code=category,
            transaction_date=item.get('date') or staged.parsed_date or date.today().isoformat(),
            description=staged.raw_text[:120], source='ingested', commit=False,
        )
        staged.status = 'approved'
        posted += 1
    db.session.commit()
    return jsonify({'posted': posted})


@app.route('/api/ingest/reject', methods=['POST'])
def api_ingest_reject():
    data = request.json
    ids = [int(i) for i in data.get('ids', [])]
    for sid in ids:
        staged = db.session.get(StagedTransaction, sid)
        if staged and staged.status == 'pending':
            staged.status = 'rejected'
    db.session.commit()
    return jsonify({'rejected': len(ids)})


if __name__ == '__main__':
    if FROZEN:
        import threading
        import webbrowser
        with app.app_context():
            db.create_all()
        threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()
        app.run(host='127.0.0.1', port=5000, debug=False)
    else:
        app.run(debug=True, port=5000)

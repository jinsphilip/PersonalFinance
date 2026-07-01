"""Ledger engine — the single place where account balances move.

Every cash mutation (manual entry, transfer, chit installment/auction, friendly
loan given/recovered, approved statement import) flows through post_transaction
so balances stay consistent. SQLite is single-writer, so one db.session
transaction per operation gives the same atomicity the spec asks SELECT FOR
UPDATE to provide on Postgres.
"""

from decimal import Decimal

from models import (
    db, Account, Transaction, AccountTypeMaster, TransactionCategoryMaster,
    ChitFund, CreditGiven,
)


# ─── Master reference data ──────────────────────────────────────────────────

ACCOUNT_TYPES = [
    ('BANK',       'Bank Account',   'bank'),
    ('WALLET',     'Wallet',         'wallet'),
    ('DEMAT',      'Demat / Trading', 'chart'),
    ('CHIT',       'Chit Fund',      'chit'),
    ('LOAN_ASSET', 'Loan Given',     'handshake'),
    ('EXTERNAL',   'External',       'globe'),
]

# (code, display_name, direction)
CATEGORIES = [
    ('SALARY',            'Salary',             'INFLOW'),
    ('DIVIDEND',          'Dividend',           'INFLOW'),
    ('OTHER_INCOME',      'Other Income',       'INFLOW'),
    ('EXPENSE_FOOD',          'Food',           'OUTFLOW'),
    ('EXPENSE_TRANSPORT',     'Transport',      'OUTFLOW'),
    ('EXPENSE_SHOPPING',      'Shopping',       'OUTFLOW'),
    ('EXPENSE_HEALTH',        'Health',         'OUTFLOW'),
    ('EXPENSE_ENTERTAINMENT', 'Entertainment',  'OUTFLOW'),
    ('EXPENSE_UTILITIES',     'Utilities',      'OUTFLOW'),
    ('EXPENSE_RENT',          'Rent',           'OUTFLOW'),
    ('EXPENSE_EDUCATION',     'Education',      'OUTFLOW'),
    ('EXPENSE_FUEL',          'Fuel',           'OUTFLOW'),
    ('EXPENSE_OTHER',         'Other Expense',  'OUTFLOW'),
    ('EMI',               'Loan EMI',           'OUTFLOW'),
    ('MF_INVESTMENT',     'Mutual Fund Investment', 'OUTFLOW'),
    ('STOCK_PURCHASE',    'Stock Purchase',     'OUTFLOW'),
    ('TRADING_GAIN',      'Trading Gain',       'INFLOW'),
    ('TRADING_LOSS',      'Trading Loss',       'OUTFLOW'),
    ('BROKERAGE',         'Brokerage & Charges','OUTFLOW'),
    ('TRANSFER',          'Transfer',           'TRANSFER'),
    ('CHIT_INSTALLMENT',  'Chit Installment',   'TRANSFER'),
    ('CHIT_AUCTION',      'Chit Auction Payout','TRANSFER'),
    ('LOAN_GIVEN',        'Loan Given',         'TRANSFER'),
    ('LOAN_RECOVERED',    'Loan Recovered',     'TRANSFER'),
]


def seed_masters():
    """Idempotently insert the master reference rows. Safe to call on every boot."""
    changed = False
    for code, name, icon in ACCOUNT_TYPES:
        if not db.session.get(AccountTypeMaster, code):
            db.session.add(AccountTypeMaster(code=code, display_name=name, icon_slug=icon))
            changed = True
    for code, name, direction in CATEGORIES:
        if not db.session.get(TransactionCategoryMaster, code):
            db.session.add(TransactionCategoryMaster(code=code, display_name=name, direction=direction))
            changed = True
    if changed:
        db.session.commit()


def get_external_account():
    """The shared EXTERNAL counter-party used for inflows/outflows that have no
    internal account on one side (salary source, merchant, etc.)."""
    acct = Account.query.filter_by(account_type_code='EXTERNAL').first()
    if not acct:
        acct = Account(name='External', account_type_code='EXTERNAL', current_balance=0, subtype='external')
        db.session.add(acct)
        db.session.commit()
    return acct


# ─── Core ledger operations ─────────────────────────────────────────────────

def _apply(txn, sign):
    """Apply (sign=+1) or reverse (sign=-1) a posted transaction's balance effects."""
    amt = Decimal(str(txn.amount)) * sign
    if txn.from_account_id:
        fa = db.session.get(Account, txn.from_account_id)
        if fa:
            fa.current_balance = Decimal(str(fa.current_balance)) - amt
    if txn.to_account_id:
        ta = db.session.get(Account, txn.to_account_id)
        if ta:
            ta.current_balance = Decimal(str(ta.current_balance)) + amt


def post_transaction(*, from_account_id, to_account_id, amount, category_code,
                     transaction_date, description='', source='manual', commit=True):
    """Create a posted transaction and move balances atomically.

    Direction is derived from the category. INFLOW fills to_account (external →
    internal), OUTFLOW drains from_account (internal → external), TRANSFER moves
    between two internal accounts. Missing sides are auto-filled with EXTERNAL.
    """
    cat = db.session.get(TransactionCategoryMaster, category_code)
    if not cat:
        raise ValueError(f'Unknown category: {category_code}')

    if Decimal(str(amount)) <= 0:
        raise ValueError('amount must be > 0')

    ext = None
    if cat.direction == 'INFLOW' and not from_account_id:
        ext = ext or get_external_account()
        from_account_id = ext.id
    if cat.direction == 'OUTFLOW' and not to_account_id:
        ext = ext or get_external_account()
        to_account_id = ext.id

    txn = Transaction(
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount=Decimal(str(amount)),
        category_code=category_code,
        transaction_date=transaction_date,
        description=description or '',
        source=source,
        status='posted',
    )
    db.session.add(txn)
    db.session.flush()          # assign id before applying
    _apply(txn, 1)
    if commit:
        db.session.commit()
    return txn


def reverse_transaction(txn, *, delete=True, commit=True):
    """Undo a transaction's balance effects; optionally delete the row."""
    _apply(txn, -1)
    if delete:
        db.session.delete(txn)
    if commit:
        db.session.commit()


# ─── Chit dual-state engine ─────────────────────────────────────────────────

def record_chit_installment(chit, *, from_account_id, amount, date):
    """Pre-auction monthly contribution: bank → chit account (asset grows)."""
    return post_transaction(
        from_account_id=from_account_id,
        to_account_id=chit.account_id,
        amount=amount,
        category_code='CHIT_INSTALLMENT',
        transaction_date=date,
        description=f'Installment · {chit.chit_name}',
    )


def record_chit_auction(chit, *, to_account_id, amount, date):
    """Auction event: chit account → bank, and flip the chit to a liability.

    After the prize money is taken, remaining contributions become an obligation,
    so the linked CHIT account is marked is_liability=True for net-worth purposes.
    """
    txn = post_transaction(
        from_account_id=chit.account_id,
        to_account_id=to_account_id,
        amount=amount,
        category_code='CHIT_AUCTION',
        transaction_date=date,
        description=f'Auction payout · {chit.chit_name}',
        commit=False,
    )
    acct = db.session.get(Account, chit.account_id)
    if acct:
        acct.is_liability = True
    chit.auction_status = 'auctioned'
    chit.auction_amount = amount
    chit.auction_date = date
    db.session.commit()
    return txn


# ─── Friendly-loan asset book ───────────────────────────────────────────────

def open_loan_asset(credit, *, from_account_id, amount, date):
    """Money lent to a friend: bank → LOAN_ASSET account (receivable)."""
    acct = Account(
        name=f'Loan · {credit.person_name}',
        account_type_code='LOAN_ASSET',
        current_balance=0,
        subtype='loan_asset',
        meta=credit.person_name,
    )
    db.session.add(acct)
    db.session.flush()
    credit.account_id = acct.id
    post_transaction(
        from_account_id=from_account_id,
        to_account_id=acct.id,
        amount=amount,
        category_code='LOAN_GIVEN',
        transaction_date=date,
        description=f'Loan given · {credit.person_name}',
        commit=False,
    )
    db.session.commit()
    return acct


def record_loan_recovery(credit, *, to_account_id, amount, date):
    """Friend repays: LOAN_ASSET account → bank. Closes the credit at zero."""
    txn = post_transaction(
        from_account_id=credit.account_id,
        to_account_id=to_account_id,
        amount=amount,
        category_code='LOAN_RECOVERED',
        transaction_date=date,
        description=f'Loan recovered · {credit.person_name}',
        commit=False,
    )
    acct = db.session.get(Account, credit.account_id)
    if acct and Decimal(str(acct.current_balance)) <= 0:
        credit.status = 'returned'
        credit.returned_date = date
    db.session.commit()
    return txn

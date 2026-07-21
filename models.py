from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


# ─────────────────────────────────────────────────────────────────────────────
# Ledger engine — unified accounts + double-entry-inspired transactions.
# Money uses Numeric(15,2) to avoid IEEE-754 float drift on running balances.
# ─────────────────────────────────────────────────────────────────────────────

def _money(value):
    """Coerce a Numeric/Decimal/None DB value to a plain float for JSON."""
    return float(value) if value is not None else 0.0


class NetWorthSnapshot(db.Model):
    """One row per calendar day capturing net worth, so the dashboard can plot a
    trend. Upserted whenever the dashboard is loaded (latest value for the day)."""
    __tablename__ = 'networth_snapshots'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), unique=True, nullable=False)   # YYYY-MM-DD
    net_worth = db.Column(db.Float, nullable=False, default=0)
    total_assets = db.Column(db.Float, nullable=False, default=0)
    total_liabilities = db.Column(db.Float, nullable=False, default=0)

    def to_dict(self):
        return {
            'date': self.date,
            'net_worth': round(self.net_worth, 2),
            'total_assets': round(self.total_assets, 2),
            'total_liabilities': round(self.total_liabilities, 2),
        }


class AccountTypeMaster(db.Model):
    __tablename__ = 'account_types_master'
    code = db.Column(db.String(30), primary_key=True)      # BANK, WALLET, CHIT, LOAN_ASSET, EXTERNAL
    display_name = db.Column(db.String(100), nullable=False)
    icon_slug = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'code': self.code,
            'display_name': self.display_name,
            'icon_slug': self.icon_slug,
            'is_active': self.is_active,
        }


class TransactionCategoryMaster(db.Model):
    __tablename__ = 'transaction_categories_master'
    code = db.Column(db.String(30), primary_key=True)      # SALARY, DIVIDEND, EXPENSE_FOOD, EMI, TRANSFER...
    display_name = db.Column(db.String(100), nullable=False)
    direction = db.Column(db.String(10), nullable=False)   # INFLOW | OUTFLOW | TRANSFER

    def to_dict(self):
        return {
            'code': self.code,
            'display_name': self.display_name,
            'direction': self.direction,
        }


class Account(db.Model):
    __tablename__ = 'accounts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    account_type_code = db.Column(db.String(30), db.ForeignKey('account_types_master.code'), nullable=False)
    current_balance = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    is_liability = db.Column(db.Boolean, default=False)    # flipped True for a chit after auction
    subtype = db.Column(db.String(20), default='bank')     # bank | wallet (for BANK-family accounts)
    meta = db.Column(db.String(200))                       # account number / organizer / friend name

    account_type = db.relationship('AccountTypeMaster')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'account_type_code': self.account_type_code,
            'account_type_name': self.account_type.display_name if self.account_type else self.account_type_code,
            'current_balance': _money(self.current_balance),
            'is_liability': bool(self.is_liability),
            'subtype': self.subtype,
            'meta': self.meta,
        }


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    from_account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    to_account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    category_code = db.Column(db.String(30), db.ForeignKey('transaction_categories_master.code'), nullable=False)
    transaction_date = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(200))
    source = db.Column(db.String(20), default='manual')    # manual | ingested
    status = db.Column(db.String(20), default='posted')    # posted | staged

    from_account = db.relationship('Account', foreign_keys=[from_account_id])
    to_account = db.relationship('Account', foreign_keys=[to_account_id])
    category = db.relationship('TransactionCategoryMaster')

    def to_dict(self):
        return {
            'id': self.id,
            'from_account_id': self.from_account_id,
            'to_account_id': self.to_account_id,
            'from_account_name': self.from_account.name if self.from_account else None,
            'to_account_name': self.to_account.name if self.to_account else None,
            'amount': _money(self.amount),
            'category_code': self.category_code,
            'category_name': self.category.display_name if self.category else self.category_code,
            'direction': self.category.direction if self.category else None,
            'transaction_date': self.transaction_date,
            'description': self.description,
            'source': self.source,
            'status': self.status,
        }


class StagedTransaction(db.Model):
    __tablename__ = 'staged_transactions'
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(40), nullable=False)
    raw_text = db.Column(db.String(400))
    parsed_date = db.Column(db.String(20))
    parsed_amount = db.Column(db.Numeric(15, 2))
    direction = db.Column(db.String(10))                   # INFLOW | OUTFLOW | TRANSFER
    suggested_category = db.Column(db.String(30))
    suggested_account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    status = db.Column(db.String(20), default='pending')   # pending | approved | rejected

    def to_dict(self):
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'raw_text': self.raw_text,
            'parsed_date': self.parsed_date,
            'parsed_amount': _money(self.parsed_amount),
            'direction': self.direction,
            'suggested_category': self.suggested_category,
            'suggested_account_id': self.suggested_account_id,
            'status': self.status,
        }


class MutualFund(db.Model):
    __tablename__ = 'mutual_funds'
    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(100), nullable=False)
    fund_name = db.Column(db.String(200), nullable=False)
    folio_number = db.Column(db.String(50))
    units = db.Column(db.Float, nullable=False, default=0)
    avg_nav = db.Column(db.Float, nullable=False, default=0)
    current_nav = db.Column(db.Float, nullable=False, default=0)
    investment_date = db.Column(db.String(20))
    scheme_code = db.Column(db.String(20))      # AMFI scheme code for live NAV
    last_updated = db.Column(db.String(20))     # date NAV was last refreshed
    # SIP (recurring investment) metadata — informational, no auto-debit.
    is_sip = db.Column(db.Boolean, default=False)
    sip_amount = db.Column(db.Float, default=0)
    sip_day = db.Column(db.Integer)             # day of month, 1-28
    sip_frequency = db.Column(db.String(15), default='monthly')  # monthly/quarterly/weekly
    sip_start_date = db.Column(db.String(20))
    sip_status = db.Column(db.String(15), default='active')      # active/paused/stopped
    sip_account_id = db.Column(db.Integer)                       # default source bank for SIP

    def _next_sip_date(self):
        """Next SIP occurrence from sip_day relative to today (active SIPs only)."""
        if not self.is_sip or (self.sip_status or 'active') != 'active' or not self.sip_day:
            return None
        from datetime import date as _date
        import calendar
        today = _date.today()
        day = max(1, min(int(self.sip_day), 28))
        y, m = today.year, today.month
        if today.day > day:                     # this month's date passed → next month
            m += 1
            if m > 12:
                m = 1; y += 1
        last = calendar.monthrange(y, m)[1]
        return _date(y, m, min(day, last)).isoformat()

    def _monthly_sip(self):
        """SIP amount normalised to a monthly figure (for commitment totals)."""
        if not self.is_sip or (self.sip_status or 'active') != 'active':
            return 0.0
        amt = self.sip_amount or 0
        freq = (self.sip_frequency or 'monthly').lower()
        if freq == 'quarterly':
            return amt / 3
        if freq == 'weekly':
            return amt * 52 / 12
        return amt

    def _cagr(self, invested, current):
        import returns
        c = returns.cagr(invested, current, self.investment_date)
        return round(c * 100, 2) if c is not None else None

    def to_dict(self):
        invested = self.units * self.avg_nav
        current = self.units * self.current_nav
        gain = current - invested
        gain_pct = (gain / invested * 100) if invested > 0 else 0
        return {
            'id': self.id,
            'platform': self.platform,
            'fund_name': self.fund_name,
            'folio_number': self.folio_number,
            'units': self.units,
            'avg_nav': self.avg_nav,
            'current_nav': self.current_nav,
            'investment_date': self.investment_date,
            'scheme_code': self.scheme_code,
            'last_updated': self.last_updated,
            'invested_value': round(invested, 2),
            'current_value': round(current, 2),
            'gain_loss': round(gain, 2),
            'gain_loss_pct': round(gain_pct, 2),
            'cagr_pct': self._cagr(invested, current),
            'is_sip': bool(self.is_sip),
            'sip_amount': self.sip_amount or 0,
            'sip_day': self.sip_day,
            'sip_frequency': self.sip_frequency or 'monthly',
            'sip_start_date': self.sip_start_date,
            'sip_status': self.sip_status or 'active',
            'sip_account_id': self.sip_account_id,
            'next_sip_date': self._next_sip_date(),
            'monthly_sip': round(self._monthly_sip(), 2),
        }


class Stock(db.Model):
    __tablename__ = 'stocks'
    id = db.Column(db.Integer, primary_key=True)
    demat_account = db.Column(db.String(100), nullable=False)
    company_name = db.Column(db.String(200), nullable=False)
    ticker = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    avg_price = db.Column(db.Float, nullable=False, default=0)
    current_price = db.Column(db.Float, nullable=False, default=0)
    sector = db.Column(db.String(100))
    exchange = db.Column(db.String(10), default='NSE')   # NSE/BSE/NYSE/NASDAQ for live price
    last_updated = db.Column(db.String(20))              # date price was last refreshed
    currency = db.Column(db.String(8), default='INR')    # native quote currency
    fx_rate = db.Column(db.Float, default=1.0)           # INR per 1 unit of `currency`
    purchase_date = db.Column(db.String(20))             # for CAGR (optional)

    def to_dict(self):
        # avg_price / current_price are in the native currency; portfolio totals
        # are reported in INR using fx_rate (INR per unit currency; 1 for INR).
        fx = self.fx_rate or 1.0
        invested_native = self.quantity * self.avg_price
        current_native = self.quantity * self.current_price
        invested = invested_native * fx
        current = current_native * fx
        gain = current - invested
        gain_pct = (gain / invested * 100) if invested > 0 else 0
        return {
            'id': self.id,
            'demat_account': self.demat_account,
            'company_name': self.company_name,
            'ticker': self.ticker,
            'quantity': self.quantity,
            'avg_price': self.avg_price,            # native currency
            'current_price': self.current_price,    # native currency
            'sector': self.sector,
            'exchange': self.exchange,
            'last_updated': self.last_updated,
            'currency': self.currency or 'INR',
            'fx_rate': fx,
            'invested_native': round(invested_native, 2),
            'current_native': round(current_native, 2),
            'invested_value': round(invested, 2),   # INR
            'current_value': round(current, 2),     # INR
            'gain_loss': round(gain, 2),            # INR
            'gain_loss_pct': round(gain_pct, 2),
            'purchase_date': self.purchase_date,
            'cagr_pct': self._cagr(invested_native, current_native),
        }

    def _cagr(self, invested_native, current_native):
        import returns
        c = returns.cagr(invested_native, current_native, self.purchase_date)
        return round(c * 100, 2) if c is not None else None


class BankAccount(db.Model):
    __tablename__ = 'bank_accounts'
    id = db.Column(db.Integer, primary_key=True)
    bank_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(50))
    account_type = db.Column(db.String(50), nullable=False)
    account_subtype = db.Column(db.String(20), nullable=True, default='bank')  # bank | wallet
    balance = db.Column(db.Float, nullable=False, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'bank_name': self.bank_name,
            'account_number': self.account_number,
            'account_type': self.account_type,
            'account_subtype': self.account_subtype or 'bank',
            'balance': self.balance,
        }


class Loan(db.Model):
    __tablename__ = 'loans'
    id = db.Column(db.Integer, primary_key=True)
    loan_type = db.Column(db.String(20), nullable=False)  # housing/car
    lender = db.Column(db.String(100), nullable=False)
    principal_amount = db.Column(db.Float, nullable=False, default=0)
    outstanding_amount = db.Column(db.Float, nullable=False, default=0)
    interest_rate = db.Column(db.Float, nullable=False, default=0)
    emi_amount = db.Column(db.Float, nullable=False, default=0)
    advance_amount = db.Column(db.Float, nullable=False, default=0)  # fixed extra principal paid monthly on top of EMI
    tenure_months = db.Column(db.Integer, nullable=False, default=0)
    start_date = db.Column(db.String(20))
    next_due_date = db.Column(db.String(20))

    def to_dict(self):
        paid = self.principal_amount - self.outstanding_amount
        progress = (paid / self.principal_amount * 100) if self.principal_amount > 0 else 0
        return {
            'id': self.id,
            'loan_type': self.loan_type,
            'lender': self.lender,
            'principal_amount': self.principal_amount,
            'outstanding_amount': self.outstanding_amount,
            'interest_rate': self.interest_rate,
            'emi_amount': self.emi_amount,
            'advance_amount': self.advance_amount or 0,
            'monthly_total': round((self.emi_amount or 0) + (self.advance_amount or 0), 2),
            'tenure_months': self.tenure_months,
            'start_date': self.start_date,
            'next_due_date': self.next_due_date,
            'amount_paid': round(paid, 2),
            'progress_pct': round(progress, 2),
        }


class ChitFund(db.Model):
    __tablename__ = 'chit_funds'
    id = db.Column(db.Integer, primary_key=True)
    chit_name = db.Column(db.String(200), nullable=False)
    total_value = db.Column(db.Float, nullable=False, default=0)
    monthly_contribution = db.Column(db.Float, nullable=False, default=0)
    tenure_months = db.Column(db.Integer, nullable=False, default=0)
    start_date = db.Column(db.String(20))
    auction_status = db.Column(db.String(20), default='pending')  # pending/auctioned
    auction_amount = db.Column(db.Float, default=0)
    auction_date = db.Column(db.String(20))
    organizer = db.Column(db.String(100))
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)  # linked CHIT ledger account

    def to_dict(self):
        return {
            'id': self.id,
            'chit_name': self.chit_name,
            'account_id': self.account_id,
            'total_value': self.total_value,
            'monthly_contribution': self.monthly_contribution,
            'tenure_months': self.tenure_months,
            'start_date': self.start_date,
            'auction_status': self.auction_status,
            'auction_amount': self.auction_amount,
            'auction_date': self.auction_date,
            'organizer': self.organizer,
        }


class FixedDeposit(db.Model):
    __tablename__ = 'fixed_deposits'
    id = db.Column(db.Integer, primary_key=True)
    bank_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(50))
    principal_amount = db.Column(db.Float, nullable=False, default=0)
    interest_rate = db.Column(db.Float, nullable=False, default=0)
    start_date = db.Column(db.String(20))
    maturity_date = db.Column(db.String(20))
    maturity_amount = db.Column(db.Float, nullable=False, default=0)
    fd_type = db.Column(db.String(20), default='cumulative')  # cumulative/non-cumulative

    def to_dict(self):
        from datetime import date as _date, datetime as _dt

        def _pd(s):
            try:
                return _dt.strptime(s, '%Y-%m-%d').date()
            except (TypeError, ValueError):
                return None

        def _value(asof):
            """FD value at `asof`. Cumulative compounds quarterly (Indian norm);
            non-cumulative accrues simple interest (interest is paid out)."""
            start = _pd(self.start_date)
            p, r = self.principal_amount or 0, self.interest_rate or 0
            if not start or not asof or asof <= start or p <= 0 or r <= 0:
                return p
            years = (asof - start).days / 365.25
            if (self.fd_type or '').lower().startswith('non'):
                return p * (1 + r / 100 * years)
            return p * (1 + r / 400) ** (4 * years)

        start = _pd(self.start_date)
        mat = _pd(self.maturity_date)
        today = _date.today()
        # Accrual stops at maturity even if today is later.
        asof = mat if (mat and today > mat) else today

        auto_maturity = round(_value(mat), 2) if mat else 0
        # Use the auto value; fall back to any manually stored amount only if no dates.
        maturity_amount = auto_maturity or (self.maturity_amount or 0)
        current_value = round(_value(asof), 2)
        interest_earned = round(current_value - (self.principal_amount or 0), 2)
        matured = bool(mat and today >= mat)
        days_to_maturity = (mat - today).days if (mat and not matured) else 0

        return {
            'id': self.id,
            'bank_name': self.bank_name,
            'account_number': self.account_number,
            'principal_amount': self.principal_amount,
            'interest_rate': self.interest_rate,
            'start_date': self.start_date,
            'maturity_date': self.maturity_date,
            'maturity_amount': maturity_amount,          # auto-computed from rate + dates
            'fd_type': self.fd_type,
            'current_value': current_value,              # accrued value as of today
            'interest_earned': interest_earned,          # earned so far (to today)
            'maturity_interest': round(maturity_amount - (self.principal_amount or 0), 2),
            'matured': matured,
            'days_to_maturity': days_to_maturity,
        }


class CreditGiven(db.Model):
    __tablename__ = 'credits'
    id = db.Column(db.Integer, primary_key=True)
    person_name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)
    date_given = db.Column(db.String(20))
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='outstanding')  # outstanding/returned
    returned_date = db.Column(db.String(20))
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)  # linked LOAN_ASSET account

    def to_dict(self):
        d = {
            'id': self.id,
            'person_name': self.person_name,
            'amount': self.amount,
            'date_given': self.date_given,
            'notes': self.notes,
            'status': self.status,
            'returned_date': self.returned_date,
            'account_id': self.account_id,
        }
        # Outstanding receivable comes from the linked ledger account when present.
        if self.account_id is not None:
            from sqlalchemy.orm import object_session
            acct = object_session(self).get(Account, self.account_id) if object_session(self) else None
            d['outstanding'] = _money(acct.current_balance) if acct else self.amount
        else:
            d['outstanding'] = self.amount if self.status == 'outstanding' else 0.0
        return d


class Income(db.Model):
    __tablename__ = 'income'
    id = db.Column(db.Integer, primary_key=True)
    income_type = db.Column(db.String(20), nullable=False)  # salary/dividend
    amount = db.Column(db.Float, nullable=False, default=0)
    date = db.Column(db.String(20))
    description = db.Column(db.Text)
    stock_name = db.Column(db.String(100))   # for dividend
    employer = db.Column(db.String(100))      # for salary

    def to_dict(self):
        return {
            'id': self.id,
            'income_type': self.income_type,
            'amount': self.amount,
            'date': self.date,
            'description': self.description,
            'stock_name': self.stock_name,
            'employer': self.employer,
        }


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    amount = db.Column(db.Float, nullable=False, default=0)
    account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=False)
    account_name = db.Column(db.String(100))  # denormalised

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'category': self.category,
            'description': self.description,
            'amount': self.amount,
            'account_id': self.account_id,
            'account_name': self.account_name,
        }


class AnalysisReport(db.Model):
    """One AI portfolio-analysis run. Stored so the user can compare periodic
    audits over time. `report_html` is a self-contained HTML fragment rendered
    in a sandboxed iframe on the analysis page."""
    __tablename__ = 'analysis_reports'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.String(30), nullable=False)   # ISO-8601 UTC
    model = db.Column(db.String(60))
    holdings_snapshot = db.Column(db.Text)                  # JSON of analyzed holdings
    overlap_input = db.Column(db.Text)                      # optional pasted 1Finance overlap
    report_html = db.Column(db.Text)                        # the rendered dashboard
    summary = db.Column(db.String(300))                    # short one-line description
    status = db.Column(db.String(10), default='ok')        # ok | error
    error = db.Column(db.Text)

    def to_dict(self, include_html=False):
        d = {
            'id': self.id,
            'created_at': self.created_at,
            'model': self.model,
            'summary': self.summary,
            'status': self.status,
            'error': self.error,
        }
        if include_html:
            d['report_html'] = self.report_html or ''
            d['overlap_input'] = self.overlap_input or ''
            d['holdings_snapshot'] = self.holdings_snapshot or ''
        return d


class Transfer(db.Model):
    __tablename__ = 'transfers'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    from_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=False)
    to_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=False)
    from_account_name = db.Column(db.String(100))
    to_account_name = db.Column(db.String(100))
    amount = db.Column(db.Float, nullable=False, default=0)
    notes = db.Column(db.String(200))

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'from_account_id': self.from_account_id,
            'to_account_id': self.to_account_id,
            'from_account_name': self.from_account_name,
            'to_account_name': self.to_account_name,
            'amount': self.amount,
            'notes': self.notes,
        }

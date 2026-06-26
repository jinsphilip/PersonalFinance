from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


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
    exchange = db.Column(db.String(10), default='NSE')   # NSE/BSE for live price
    last_updated = db.Column(db.String(20))              # date price was last refreshed

    def to_dict(self):
        invested = self.quantity * self.avg_price
        current = self.quantity * self.current_price
        gain = current - invested
        gain_pct = (gain / invested * 100) if invested > 0 else 0
        return {
            'id': self.id,
            'demat_account': self.demat_account,
            'company_name': self.company_name,
            'ticker': self.ticker,
            'quantity': self.quantity,
            'avg_price': self.avg_price,
            'current_price': self.current_price,
            'sector': self.sector,
            'exchange': self.exchange,
            'last_updated': self.last_updated,
            'invested_value': round(invested, 2),
            'current_value': round(current, 2),
            'gain_loss': round(gain, 2),
            'gain_loss_pct': round(gain_pct, 2),
        }


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

    def to_dict(self):
        return {
            'id': self.id,
            'chit_name': self.chit_name,
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
        gain = self.maturity_amount - self.principal_amount
        return {
            'id': self.id,
            'bank_name': self.bank_name,
            'account_number': self.account_number,
            'principal_amount': self.principal_amount,
            'interest_rate': self.interest_rate,
            'start_date': self.start_date,
            'maturity_date': self.maturity_date,
            'maturity_amount': self.maturity_amount,
            'fd_type': self.fd_type,
            'interest_earned': round(gain, 2),
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

    def to_dict(self):
        return {
            'id': self.id,
            'person_name': self.person_name,
            'amount': self.amount,
            'date_given': self.date_given,
            'notes': self.notes,
            'status': self.status,
            'returned_date': self.returned_date,
        }


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

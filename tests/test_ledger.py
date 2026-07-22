"""Ledger engine tests — balances move correctly and reverse cleanly."""
from decimal import Decimal

import services
from models import db, Account


def _bank(name, bal=0):
    a = Account(name=name, account_type_code='BANK', current_balance=bal, subtype='bank')
    db.session.add(a)
    db.session.commit()
    return a


def test_transfer_moves_balance(app_ctx):
    a = _bank('A', 1000)
    b = _bank('B', 0)
    services.post_transaction(from_account_id=a.id, to_account_id=b.id,
                              amount=250, category_code='TRANSFER',
                              transaction_date='2026-01-01')
    assert float(db.session.get(Account, a.id).current_balance) == 750
    assert float(db.session.get(Account, b.id).current_balance) == 250


def test_outflow_drains_and_autofills_external(app_ctx):
    a = _bank('A', 500)
    txn = services.post_transaction(from_account_id=a.id, to_account_id=None,
                                    amount=200, category_code='EXPENSE_FOOD',
                                    transaction_date='2026-01-01')
    assert float(db.session.get(Account, a.id).current_balance) == 300
    assert txn.to_account_id is not None      # EXTERNAL auto-filled


def test_reverse_restores_balance(app_ctx):
    a = _bank('A', 500)
    txn = services.post_transaction(from_account_id=a.id, to_account_id=None,
                                    amount=200, category_code='EXPENSE_FOOD',
                                    transaction_date='2026-01-01')
    services.reverse_transaction(txn)
    assert float(db.session.get(Account, a.id).current_balance) == 500


def test_amount_must_be_positive(app_ctx):
    a = _bank('A', 500)
    import pytest
    with pytest.raises(ValueError):
        services.post_transaction(from_account_id=a.id, to_account_id=None,
                                  amount=0, category_code='EXPENSE_FOOD',
                                  transaction_date='2026-01-01')

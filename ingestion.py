"""PDF statement ingestion — parse only, never post.

Extracts text rows from a bank/dividend statement PDF with pdfplumber, then runs
a regex matching engine over each line to guess a date, amount, direction, and
category. Results are returned as plain dicts for the caller to persist as
StagedTransaction rows; nothing touches the ledger until the user approves a
batch in the review UI (spec §5.1, Staging Review Validation Matrix).
"""

import re
from datetime import datetime

# Amount like 1,23,456.78 or 12345.67
_AMOUNT = r'(?P<amount>[\d,]+\.\d{2})'

# Date formats commonly seen in Indian statements.
_DATE_PATTERNS = [
    (re.compile(r'(\d{2})[/-](\d{2})[/-](\d{4})'), '%d/%m/%Y'),
    (re.compile(r'(\d{2})[/-](\d{2})[/-](\d{2})\b'), '%d/%m/%y'),
    (re.compile(r'(\d{4})-(\d{2})-(\d{2})'), '%Y-%m-%d'),
    (re.compile(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})'), '%d %b %Y'),
]

# Ordered category matchers — first hit wins. Each maps to (category, direction).
_CATEGORY_RULES = [
    (re.compile(r'DIVIDEND', re.I),                         ('DIVIDEND', 'INFLOW')),
    (re.compile(r'\bSALARY\b|SAL\s+CREDIT|NEFT.*SALARY', re.I), ('SALARY', 'INFLOW')),
    (re.compile(r'\bEMI\b|LOAN\s+INST|HOUSING\s+LOAN', re.I),   ('EMI', 'OUTFLOW')),
    (re.compile(r'CHIT', re.I),                             ('CHIT_INSTALLMENT', 'TRANSFER')),
    (re.compile(r'FUEL|PETROL|HPCL|IOCL|BPCL', re.I),       ('EXPENSE_FUEL', 'OUTFLOW')),
    (re.compile(r'SWIGGY|ZOMATO|RESTAURANT|CAFE', re.I),    ('EXPENSE_FOOD', 'OUTFLOW')),
    (re.compile(r'UBER|OLA|IRCTC|METRO', re.I),             ('EXPENSE_TRANSPORT', 'OUTFLOW')),
    (re.compile(r'AMAZON|FLIPKART|MYNTRA', re.I),           ('EXPENSE_SHOPPING', 'OUTFLOW')),
    (re.compile(r'ELECTRICITY|BILL\s*PAY|RECHARGE|BROADBAND', re.I), ('EXPENSE_UTILITIES', 'OUTFLOW')),
]

# Direction hints from explicit Dr/Cr or credit/debit columns.
_CREDIT_HINT = re.compile(r'\bCR\b|\bCREDIT\b', re.I)
_DEBIT_HINT = re.compile(r'\bDR\b|\bDEBIT\b', re.I)


def _parse_date(line):
    for pat, fmt in _DATE_PATTERNS:
        m = pat.search(line)
        if m:
            try:
                return datetime.strptime(m.group(0), fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
    return None


def _classify(line):
    for pat, (cat, direction) in _CATEGORY_RULES:
        if pat.search(line):
            return cat, direction
    # Fall back on Dr/Cr hint, else leave it for manual review.
    if _CREDIT_HINT.search(line):
        return 'OTHER_INCOME', 'INFLOW'
    if _DEBIT_HINT.search(line):
        return 'EXPENSE_OTHER', 'OUTFLOW'
    return 'EXPENSE_OTHER', 'OUTFLOW'


def parse_lines(lines):
    """Core matcher over a list of text lines. Separated out for testability."""
    rows = []
    amount_re = re.compile(_AMOUNT)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        amt_m = amount_re.search(line)
        if not amt_m:
            continue
        amount = float(amt_m.group('amount').replace(',', ''))
        if amount <= 0:
            continue
        category, direction = _classify(line)
        rows.append({
            'raw_text': line[:400],
            'parsed_date': _parse_date(line),
            'parsed_amount': amount,
            'direction': direction,
            'suggested_category': category,
        })
    return rows


def parse_statement(file_storage):
    """Parse an uploaded PDF (werkzeug FileStorage) into candidate rows.

    Returns [] gracefully if pdfplumber is unavailable or the file can't be read,
    so the upload endpoint can report a clean "nothing detected" instead of 500.
    """
    try:
        import pdfplumber
    except Exception:
        # Library missing or its native deps failed to load — degrade to "no rows"
        # rather than 500 so the upload endpoint can report nothing detected.
        return []

    lines = []
    try:
        with pdfplumber.open(file_storage) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ''
                lines.extend(text.splitlines())
    except Exception:
        return []

    return parse_lines(lines)

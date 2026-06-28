"""PDF statement ingestion — parse only, never post.

Extracts text from a bank/dividend statement PDF and reconstructs transactions.
Real Indian bank statements (Axis, HDFC, SBI, …) print the date, the particulars
and the amounts on *separate* lines, and the money line carries two numbers — the
transaction amount and the running balance — with no Dr/Cr marker (debit vs credit
is encoded only by column position, which plain-text extraction loses).

So the primary parser is balance-driven: it tracks the running balance and infers
both the amount and the direction from how the balance moves (up = credit/INFLOW,
down = debit/OUTFLOW). This is far more reliable than keyword guessing and also
self-validates (the stated amount must equal the balance delta). A simple
keyword/line matcher remains as a fallback for statements without a balance column.

Results are returned as plain dicts; nothing touches the ledger until the user
approves a batch in the review UI (spec §5.1, Staging Review Validation Matrix).
"""

import re

_MONEY = r'[\d,]+\.\d{2}'
_NUM = re.compile(_MONEY)
# A money line ends with "<amount> <balance>" optionally followed by a branch code.
_PAIR = re.compile(r'(' + _MONEY + r')\s+(' + _MONEY + r')(?:\s+\d+)?\s*$')
_DATE_DMY = re.compile(r'\b(\d{2})-(\d{2})-(\d{4})\b')
_OPENING = re.compile(r'OPENING\s+BALANCE\s+(' + _MONEY + r')', re.I)


def _num(s):
    return float(s.replace(',', ''))


# Keyword → (category, fallback direction). Used to label the description; the
# balance-derived direction always wins when available.
_CATEGORY_RULES = [
    (re.compile(r'DIVIDEND', re.I),                            ('DIVIDEND', 'INFLOW')),
    (re.compile(r'\bSALARY\b|PAYROLL', re.I),                  ('SALARY', 'INFLOW')),
    (re.compile(r'\bINT\.?\s*P[Dd]\b|INTEREST\s+PAID', re.I),  ('OTHER_INCOME', 'INFLOW')),
    (re.compile(r'\bEMI\b|LOAN\s+INST|HOUSING\s+LOAN', re.I),  ('EMI', 'OUTFLOW')),
    (re.compile(r'CHIT', re.I),                                ('CHIT_INSTALLMENT', 'TRANSFER')),
    (re.compile(r'FUEL|PETROL|HPCL|IOCL|BPCL', re.I),          ('EXPENSE_FUEL', 'OUTFLOW')),
    (re.compile(r'SWIGGY|ZOMATO|RESTAURANT|\bCAFE\b|HOTEL', re.I), ('EXPENSE_FOOD', 'OUTFLOW')),
    (re.compile(r'UBER|\bOLA\b|IRCTC|METRO|RAILWAY', re.I),    ('EXPENSE_TRANSPORT', 'OUTFLOW')),
    (re.compile(r'AMAZON|FLIPKART|MYNTRA', re.I),              ('EXPENSE_SHOPPING', 'OUTFLOW')),
    (re.compile(r'ELECTRICITY|BILL\s*PAY|RECHARGE|BROADBAND|BESCOM|KSEB', re.I), ('EXPENSE_UTILITIES', 'OUTFLOW')),
]

_CREDIT_HINT = re.compile(r'\bCR\b|\bCREDIT\b', re.I)
_DEBIT_HINT = re.compile(r'\bDR\b|\bDEBIT\b', re.I)


def _classify(text, direction=None):
    """Pick a category for a description, honouring a known direction if given."""
    for pat, (cat, _dir) in _CATEGORY_RULES:
        if pat.search(text):
            # Only use a keyword hit if it agrees with the known cash direction.
            if direction is None or _dir == direction or _dir == 'TRANSFER':
                return cat
    if direction == 'INFLOW':
        return 'SALARY' if re.search(r'SALARY|PAYROLL', text, re.I) else 'OTHER_INCOME'
    if direction == 'OUTFLOW':
        return 'EXPENSE_OTHER'
    if _CREDIT_HINT.search(text):
        return 'OTHER_INCOME'
    return 'EXPENSE_OTHER'


def parse_balance_statement(lines):
    """Reconstruct transactions from a statement that has a running-balance column.

    Returns [] if no opening balance / balance column is detected, so the caller
    can fall back to the keyword matcher.
    """
    prev_balance = None
    row_date = None        # date on the current transaction's own line(s)
    buf = []               # accumulated particulars text since the last posting
    rows = []

    for line in lines:
        mo = _OPENING.search(line)
        if mo:
            prev_balance = _num(mo.group(1))
            buf = []
            continue

        pm = _PAIR.search(line)
        head = line[:pm.start()] if pm else line

        # A date appearing in the head (not inside the trailing amounts) dates this txn.
        dm = _DATE_DMY.search(head)
        if dm:
            row_date = f'{dm.group(3)}-{dm.group(2)}-{dm.group(1)}'

        if pm and prev_balance is not None:
            amount = _num(pm.group(1))
            balance = _num(pm.group(2))
            delta = round(balance - prev_balance, 2)
            if abs(abs(delta) - amount) <= 0.01 and amount > 0:
                direction = 'INFLOW' if delta > 0 else 'OUTFLOW'
                head_txt = _DATE_DMY.sub('', head).strip()
                desc = re.sub(r'\s+', ' ', ' '.join(buf + [head_txt])).strip()
                rows.append({
                    'raw_text': desc[:400],
                    'parsed_date': row_date,
                    'parsed_amount': amount,
                    'direction': direction,
                    'suggested_category': _classify(desc, direction),
                })
                prev_balance = balance
                buf = []
                continue

        # Not a posting line → accumulate as particulars (skip bare dates / numbers).
        txt = _DATE_DMY.sub('', line).strip()
        if txt and not re.fullmatch(_MONEY, txt):
            buf.append(txt)

    return rows


def parse_lines(lines):
    """Keyword/line fallback matcher: one amount per line, direction by Dr/Cr hint."""
    rows = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = _NUM.search(line)
        if not m:
            continue
        amount = _num(m.group(0))
        if amount <= 0:
            continue
        direction = 'INFLOW' if _CREDIT_HINT.search(line) else 'OUTFLOW'
        rows.append({
            'raw_text': line[:400],
            'parsed_date': _parse_any_date(line),
            'parsed_amount': amount,
            'direction': direction,
            'suggested_category': _classify(line, direction),
        })
    return rows


def _parse_any_date(line):
    from datetime import datetime
    m = _DATE_DMY.search(line)
    if m:
        return f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', line)
    if m:
        return m.group(0)
    m = re.search(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', line)
    if m:
        try:
            return datetime.strptime(m.group(0), '%d %b %Y').strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


def _extract_text(file_storage):
    """Pull text from a PDF. Tries pypdf first (light, dependency-clean), then
    pdfplumber. Returns '' if neither is available or the file can't be read."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_storage)
        return '\n'.join((p.extract_text() or '') for p in reader.pages)
    except Exception:
        pass
    try:
        import pdfplumber
        out = []
        with pdfplumber.open(file_storage) as pdf:
            for page in pdf.pages:
                out.append(page.extract_text() or '')
        return '\n'.join(out)
    except Exception:
        return ''


def parse_statement(file_storage):
    """Parse an uploaded PDF (werkzeug FileStorage) into candidate rows.

    Prefers the balance-driven reconstruction; falls back to the keyword matcher
    for statements with no running-balance column.
    """
    text = _extract_text(file_storage)
    if not text:
        return []
    lines = text.splitlines()
    rows = parse_balance_statement(lines)
    if rows:
        return rows
    return parse_lines(lines)

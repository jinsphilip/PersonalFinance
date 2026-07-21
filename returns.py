"""Return metrics — CAGR (point-to-point) and XIRR (money-weighted).

CAGR annualizes a single start→end value change. XIRR solves for the annual rate
that makes a series of dated cashflows net to zero (the IRR for irregular dates),
which is the right way to measure a portfolio built from investments made on
different dates. Both are pure-Python (no numpy) and fail safe (return None when
inputs are insufficient), so callers can show '—'.
"""

from datetime import date, datetime


def _parse_date(v):
    if isinstance(v, date):
        return v
    if not v:
        return None
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(str(v)[:10], fmt).date()
        except ValueError:
            continue
    return None


def years_between(start, end=None):
    start = _parse_date(start)
    end = _parse_date(end) or date.today()
    if not start or end <= start:
        return None
    return (end - start).days / 365.25


def cagr(invested, current, start, end=None):
    """Compound annual growth rate as a fraction (0.12 = 12%), or None."""
    yrs = years_between(start, end)
    if not yrs or yrs < 0.05 or invested is None or invested <= 0 or current is None or current <= 0:
        return None
    return (current / invested) ** (1.0 / yrs) - 1.0


def _npv(rate, flows, d0):
    total = 0.0
    for d, amt in flows:
        t = (d - d0).days / 365.25
        total += amt / (1.0 + rate) ** t
    return total


def xirr(cashflows):
    """Money-weighted annual return for dated cashflows.

    `cashflows` = list of (date, amount); outflows (investments) negative,
    inflows (current value / sells / dividends) positive. Returns a fraction or
    None if it can't be solved (needs both signs and ≥2 flows).
    """
    flows = [(_parse_date(d), float(a)) for d, a in cashflows if _parse_date(d) is not None]
    if len(flows) < 2:
        return None
    if not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        return None
    flows.sort(key=lambda f: f[0])
    d0 = flows[0][0]

    # Newton's method, then bisection fallback for robustness.
    rate = 0.1
    for _ in range(100):
        try:
            f = _npv(rate, flows, d0)
            # numerical derivative
            h = 1e-6
            fp = (_npv(rate + h, flows, d0) - f) / h
            if fp == 0:
                break
            new = rate - f / fp
            if new <= -0.9999:
                new = (rate - 0.9999) / 2
            if abs(new - rate) < 1e-7:
                return new
            rate = new
        except (OverflowError, ZeroDivisionError):
            break

    lo, hi = -0.9999, 100.0
    flo, fhi = _npv(lo, flows, d0), _npv(hi, flows, d0)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = _npv(mid, flows, d0)
        if abs(fm) < 1e-6:
            return mid
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2

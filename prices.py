"""Live price/NAV fetching for mutual funds (AMFI) and stocks (Yahoo Finance).

Outbound HTTPS automatically honours the HTTPS_PROXY environment variable, so no
special configuration is needed in a proxied environment. All network calls are
wrapped defensively: on any failure the caller keeps the previously stored value
and the symbol is reported as failed instead of raising.
"""
import requests

AMFI_NAV_URL = 'https://www.amfiindia.com/spages/NAVAll.txt'
YAHOO_CHART_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'

# Yahoo expects a browser-ish User-Agent or it sometimes returns 403.
_HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; FinTracker/1.0)'}

_EXCHANGE_SUFFIX = {'NSE': 'NS', 'BSE': 'BO'}


def fetch_amfi_navs(timeout=20):
    """Download and parse the AMFI NAVAll feed.

    Returns a dict mapping scheme_code (str) -> nav (float). The file is a
    semicolon-delimited table; data rows look like:
        Scheme Code;ISIN Div Payout;ISIN Div Reinvest;Scheme Name;Net Asset Value;Date
    Header rows, AMC name rows, and blank lines are skipped.
    """
    resp = requests.get(AMFI_NAV_URL, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    navs = {}
    for line in resp.text.splitlines():
        parts = line.split(';')
        if len(parts) < 6:
            continue
        code, nav = parts[0].strip(), parts[4].strip()
        if not code.isdigit():
            continue
        try:
            navs[code] = float(nav)
        except ValueError:
            continue  # 'N.A.' or similar
    return navs


def fetch_stock_price(ticker, exchange='NSE', timeout=15):
    """Return the latest market price for a ticker, or None on failure."""
    suffix = _EXCHANGE_SUFFIX.get((exchange or 'NSE').upper(), 'NS')
    symbol = f'{ticker.strip().upper()}.{suffix}'
    try:
        resp = requests.get(
            YAHOO_CHART_URL.format(symbol=symbol),
            headers=_HEADERS, timeout=timeout,
        )
        resp.raise_for_status()
        meta = resp.json()['chart']['result'][0]['meta']
        price = meta.get('regularMarketPrice')
        return float(price) if price is not None else None
    except Exception:
        return None

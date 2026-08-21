"""Live price/NAV fetching for mutual funds (AMFI) and stocks (Yahoo Finance).

Outbound HTTPS automatically honours the HTTPS_PROXY environment variable, so no
special configuration is needed in a proxied environment. All network calls are
wrapped defensively: on any failure the caller keeps the previously stored value
and the symbol is reported as failed instead of raising.
"""
from concurrent.futures import ThreadPoolExecutor

import requests

AMFI_NAV_URL = 'https://www.amfiindia.com/spages/NAVAll.txt'
YAHOO_CHART_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
# Yahoo serves the same chart API from two hosts; query1 intermittently 404s /
# rate-limits individual symbols that query2 returns fine, so we try both.
_YAHOO_HOSTS = ('query1.finance.yahoo.com', 'query2.finance.yahoo.com')

# Yahoo expects a browser-ish User-Agent or it sometimes returns 403.
_HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; FinTracker/1.0)'}

_EXCHANGE_SUFFIX = {'NSE': 'NS', 'BSE': 'BO'}
# US exchanges use the bare ticker on Yahoo (no suffix).
_US_EXCHANGES = {'NYSE', 'NASDAQ', 'NMS', 'NYQ', 'US', 'AMEX', 'ARCA'}


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


def _yahoo_symbol(ticker, exchange):
    """Map a ticker + exchange to a Yahoo symbol. US exchanges → bare ticker;
    NSE/BSE → .NS/.BO suffix. A suffix the user already typed (e.g. entering
    'STOVEKRAFT.NS') is stripped first so we never double-suffix into an
    unresolvable 'STOVEKRAFT.NS.NS'."""
    t = ticker.strip().upper()
    for suf in ('.NS', '.BO'):
        if t.endswith(suf):
            t = t[:-len(suf)]
            break
    ex = (exchange or 'NSE').upper()
    if ex in _US_EXCHANGES:
        return t
    suffix = _EXCHANGE_SUFFIX.get(ex, 'NS')
    return f'{t}.{suffix}'


YAHOO_SEARCH_URL = 'https://query1.finance.yahoo.com/v1/finance/search'
# Yahoo exchange codes -> our exchange labels.
_YEX = {'NSI': 'NSE', 'BSE': 'BSE', 'BOM': 'BSE', 'NMS': 'NASDAQ', 'NGM': 'NASDAQ',
        'NCM': 'NASDAQ', 'NYQ': 'NYSE', 'ASE': 'NYSE', 'PCX': 'NYSE'}


def search_symbols(query, timeout=8, limit=10):
    """Symbol lookup for the ticker autocomplete. Returns a list of
    {symbol, ticker, name, exchange, currency} for equities matching `query`.
    Empty list on any failure (offline, blocked, no matches)."""
    q = (query or '').strip()
    if len(q) < 2:
        return []
    for host in _YAHOO_HOSTS:
        try:
            resp = requests.get(
                YAHOO_SEARCH_URL.replace('query1.finance.yahoo.com', host),
                params={'q': q, 'quotesCount': limit, 'newsCount': 0},
                headers=_HEADERS, timeout=timeout,
            )
            if resp.status_code != 200:
                continue
            out = []
            for it in resp.json().get('quotes', []):
                if it.get('quoteType') != 'EQUITY' or not it.get('symbol'):
                    continue
                sym = it['symbol'].upper()
                ex_code = (it.get('exchange') or '').upper()
                if sym.endswith('.NS'):
                    exch, cur, ticker = 'NSE', 'INR', sym[:-3]
                elif sym.endswith('.BO'):
                    exch, cur, ticker = 'BSE', 'INR', sym[:-3]
                else:
                    exch = _YEX.get(ex_code, 'NASDAQ')
                    cur, ticker = 'USD', sym
                out.append({
                    'symbol': sym, 'ticker': ticker,
                    'name': it.get('shortname') or it.get('longname') or ticker,
                    'exchange': exch, 'currency': cur,
                })
                if len(out) >= limit:
                    break
            return out
        except Exception:
            continue
    return []


def _yahoo_quote(symbol, timeout):
    """Query a single Yahoo symbol across both hosts. Returns (price, currency,
    prev_close) or None if neither host resolves it."""
    for host in _YAHOO_HOSTS:
        try:
            resp = requests.get(
                f'https://{host}/v8/finance/chart/{symbol}',
                headers=_HEADERS, timeout=timeout,
            )
            if resp.status_code != 200:
                continue
            meta = resp.json()['chart']['result'][0]['meta']
            price = meta.get('regularMarketPrice')
            if price is None:
                continue
            prev = meta.get('chartPreviousClose', meta.get('previousClose'))
            return (float(price), meta.get('currency'),
                    float(prev) if prev is not None else None)
        except Exception:
            continue
    return None


def fetch_stock_price(ticker, exchange='NSE', timeout=15):
    """Return (price, currency, prev_close) for a ticker, or (None, None, None).

    Tries both Yahoo hosts for the resolved symbol, and for Indian tickers falls
    back to the other exchange suffix (.NS <-> .BO) when the primary doesn't
    resolve. `currency` comes from Yahoo's meta; `prev_close` is the previous
    trading day's close (native currency) for the daily change.
    """
    candidates = [_yahoo_symbol(ticker, exchange)]
    ex = (exchange or 'NSE').upper()
    if ex in _EXCHANGE_SUFFIX:                    # Indian: try the sibling exchange too
        alt = 'BSE' if ex == 'NSE' else 'NSE'
        candidates.append(_yahoo_symbol(ticker, alt))
    for sym in candidates:
        res = _yahoo_quote(sym, timeout)
        if res is not None:
            return res
    return (None, None, None)


def fetch_stock_prices_bulk(items, timeout=8, max_workers=12):
    """Fetch many stock quotes concurrently.

    `items` is an iterable of objects with `.ticker` and `.exchange`. Returns a
    dict keyed by id(item) -> (price, currency, prev_close), so the caller applies results
    to the ORM objects on the main thread (network in threads, DB writes single-
    threaded). One slow ticker no longer blocks the rest.
    """
    items = list(items)
    if not items:
        return {}
    workers = min(max_workers, len(items))

    def _one(it):
        return id(it), fetch_stock_price(it.ticker, it.exchange, timeout=timeout)

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for key, val in pool.map(_one, items):
            results[key] = val
    return results


def fetch_stock_history(ticker, exchange='NSE', rng='1y', interval='1d', timeout=20):
    """Return (candles, currency) for a ticker. candles is a list of
    {time, open, high, low, close} (time = UNIX seconds), oldest first. On any
    failure returns ([], None) so the caller can show an empty chart."""
    symbol = _yahoo_symbol(ticker, exchange)
    try:
        resp = requests.get(
            YAHOO_CHART_URL.format(symbol=symbol),
            headers=_HEADERS, params={'range': rng, 'interval': interval}, timeout=timeout,
        )
        resp.raise_for_status()
        res = resp.json()['chart']['result'][0]
        ts = res.get('timestamp') or []
        q = res['indicators']['quote'][0]
        o, h, l, c = q.get('open', []), q.get('high', []), q.get('low', []), q.get('close', [])
        out = []
        for i, t in enumerate(ts):
            try:
                oo, hh, ll, cc = o[i], h[i], l[i], c[i]
            except IndexError:
                continue
            if None in (oo, hh, ll, cc):
                continue
            out.append({'time': int(t), 'open': oo, 'high': hh, 'low': ll, 'close': cc})
        return out, res.get('meta', {}).get('currency')
    except Exception:
        return [], None


MFAPI_URL = 'https://api.mfapi.in/mf/{scheme}'


def fetch_mf_history(scheme_code, timeout=20, max_points=1500):
    """Historical NAV for an AMFI scheme code via mfapi.in.

    Returns a list of {time: 'YYYY-MM-DD', value: nav} oldest first, or [] on
    failure. mfapi returns dates as DD-MM-YYYY, newest first."""
    try:
        resp = requests.get(MFAPI_URL.format(scheme=str(scheme_code).strip()),
                            headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        data = resp.json().get('data') or []
        out = []
        for row in data:
            d, nav = row.get('date'), row.get('nav')
            try:
                dd, mm, yy = d.split('-')
                out.append({'time': f'{yy}-{mm}-{dd}', 'value': float(nav)})
            except (ValueError, AttributeError, TypeError):
                continue
        out.sort(key=lambda r: r['time'])          # oldest first
        return out[-max_points:]
    except Exception:
        return []


def fetch_fx_rate(base='USD', quote='INR', timeout=15):
    """Latest FX rate: how many `quote` units per 1 `base` (e.g. USD→INR ≈ 83).
    Returns None on failure so the caller can keep the stored rate."""
    if (base or '').upper() == (quote or '').upper():
        return 1.0
    symbol = f'{base.upper()}{quote.upper()}=X'
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

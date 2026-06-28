"""Bulk importer for demat holdings.

Inserts each broker's scrips into the `stocks` table. Idempotent: a scrip already
present in the same demat account is updated (qty + avg price) rather than
duplicated. The same ticker held in two demats stays two separate rows because
uniqueness is keyed on (demat_account, ticker).

current_price is seeded to the buy price — run "Refresh Prices" in the app (or
POST /api/refresh-prices) afterwards to pull live NSE prices.

Usage:
    python import_stocks.py            # import all brokers below
    python import_stocks.py angel      # import only ANGEL
    python import_stocks.py iifl       # import only IIFL
"""
import sys

from app import app
from models import db, Stock

EXCHANGE = 'NSE'

# (ticker, qty, avg_buy_price) — tickers upper-cased, commas stripped.
IIFL_HOLDINGS = [
    ('63MOONS',     350,   449.09),
    ('AJAXENGG',     23,   629.00),
    ('BEL',         450,   411.89),
    ('CDSL',         65,  1211.81),
    ('ENGINERSIN', 2200,   235.31),
    ('GOLDBEES',   2000,    90.98),
    ('IDFCFIRSTB', 1700,    61.45),
    ('KOTAKBANK',   100,   366.67),
    ('LICI',       2000,   477.14),
    ('RAILTEL',     350,   347.03),
    ('RVNL',       1700,   291.45),
    ('SOUTHBANK',  2000,    29.55),
    ('STOVEKRAFT',  300,   774.52),
    ('SUZLON',     2000,    63.35),
    ('WAAREEENER',  240,  3413.35),
]

ANGEL_HOLDINGS = [
    ('ANANTRAJ',     200,   530.40),
    ('ASHOKA',      1300,   221.42),
    ('ENGINERSIN',  2400,   262.83),
    ('GATEWAY',      500,   110.13),
    ('GENUSPOWER',   350,   379.90),
    ('IDFCFIRSTB', 12250,    79.01),
    ('INDUSTOWER',   136,   362.60),
    ('ITBEES',      2200,    38.56),
    ('JWL',          390,   352.66),
    ('NCC',          600,   326.47),
    ('WAAREEENER',    30,  2792.84),
    ('WELSPUNLIV',   250,   182.22),
    ('UNIONBANK',    500,   175.16),
]

KOTAK_HOLDINGS = [
    ('JPPOWER',    1300,    19.07),
    ('KNRCON',      293,   342.27),
    ('LICI',        590,   509.50),
    ('MICEL',      1000,   101.38),
    ('NHPC',        900,    94.35),
    ('PRAJIND',     225,   800.75),
    ('RAILTEL',     226,   462.08),
    ('STOVEKRAFT',  121,   906.74),
    ('VPRPL',       916,   196.61),
]

# Includes a few bonds/ETFs (1050KSL27-F, LIQUIDCASE, PHARMABEES) that won't
# resolve on live NSE price refresh — they keep their buy price.
ZERODHA_HOLDINGS = [
    ('1050KSL27-F',    3, 100000.00),
    ('ADANIPOWER',   500,    230.00),
    ('BANKINDIA',   4500,    109.76),
    ('BEL',          100,    380.00),
    ('CCAVENUE',    4000,     26.33),
    ('ENGINERSIN',   400,    201.19),
    ('ETERNAL',      155,    308.15),
    ('GATEWAY',     1000,     60.50),
    ('IDFCFIRSTB',  7500,     71.51),
    ('INDHOTEL',      62,    688.72),
    ('IOC',         4550,    153.26),
    ('ITC',         2000,    333.68),
    ('KCP',          550,    225.29),
    ('KEC',          200,    715.00),
    ('LIQUIDCASE',   348,    114.63),
    ('MOREPENLAB',  1000,     48.90),
    ('NATIONALUM',   200,    306.65),
    ('NCLIND',       400,    230.30),
    ('NTPC',         135,    336.71),
    ('ORIENTHOT',    400,    181.78),
    ('PATELENG',    1000,     44.06),
    ('PGEL',          60,    510.48),
    ('PHARMABEES',  3000,     23.15),
    ('PPLPHARMA',   1020,    215.72),
    ('PREMIERENE',   328,    866.85),
    ('RUSHIL',      9300,     34.64),
    ('SAIL',         914,    121.10),
    ('SEPC',       11000,     12.83),
    ('SHAKTIPUMP',   595,    693.35),
    ('SULA',         245,    512.54),
    ('TATACHEM',      57,    867.34),
    ('TATACONSUM',    56,   1104.00),
    ('TATAPOWER',     88,    402.38),
    ('TATASTEEL',    290,    169.47),
    ('TCS',          128,   3256.97),
    ('TITAN',          2,   4168.25),
    ('TMCV',         291,    241.02),
    ('TMPV',         645,    431.62),
    ('VOLTAS',        82,   1352.62),
    ('WAAREEENER',   280,   3183.75),
    ('ZUARIIND',     100,    365.00),
]

BROKERS = {
    'IIFL': IIFL_HOLDINGS,
    'ANGEL': ANGEL_HOLDINGS,
    'KOTAK': KOTAK_HOLDINGS,
    'ZERODHA': ZERODHA_HOLDINGS,
}


def import_holdings(broker, holdings, exchange=EXCHANGE):
    inserted = updated = 0
    for ticker, qty, price in holdings:
        existing = Stock.query.filter_by(demat_account=broker, ticker=ticker).first()
        if existing:
            existing.quantity = qty
            existing.avg_price = price
            if not existing.current_price:
                existing.current_price = price
            updated += 1
        else:
            db.session.add(Stock(
                demat_account=broker,
                company_name=ticker,      # friendly name unknown; refresh fills price
                ticker=ticker,
                quantity=qty,
                avg_price=price,
                current_price=price,      # seed; refresh pulls live NSE price
                sector='',
                exchange=exchange,
            ))
            inserted += 1
    db.session.commit()
    print(f"{broker}: inserted {inserted}, updated {updated}.")


def run(which=None):
    targets = BROKERS if not which else {which.upper(): BROKERS[which.upper()]}
    with app.app_context():
        for broker, holdings in targets.items():
            import_holdings(broker, holdings)


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg and arg.upper() not in BROKERS:
        print(f"Unknown broker '{arg}'. Choose from: {', '.join(BROKERS)} (or omit for all).")
        sys.exit(1)
    run(arg)

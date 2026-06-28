"""One-off importer for IIFL holdings.

Inserts the listed scrips into the `stocks` table. Idempotent: a scrip already
present in the same demat account is updated (qty + avg price) rather than
duplicated. current_price is seeded to the buy price — run "Refresh Prices" in
the app (or POST /api/refresh-prices) afterwards to pull live NSE prices.

Usage:  python import_stocks.py
"""
from app import app
from models import db, Stock

BROKER = 'IIFL'
EXCHANGE = 'NSE'

# (ticker, qty, avg_buy_price)
HOLDINGS = [
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


def run():
    inserted = updated = 0
    with app.app_context():
        for ticker, qty, price in HOLDINGS:
            existing = Stock.query.filter_by(demat_account=BROKER, ticker=ticker).first()
            if existing:
                existing.quantity = qty
                existing.avg_price = price
                if not existing.current_price:
                    existing.current_price = price
                updated += 1
            else:
                db.session.add(Stock(
                    demat_account=BROKER,
                    company_name=ticker,      # friendly name unknown; refresh fills price
                    ticker=ticker,
                    quantity=qty,
                    avg_price=price,
                    current_price=price,      # seed; refresh pulls live NSE price
                    sector='',
                    exchange=EXCHANGE,
                ))
                inserted += 1
        db.session.commit()
    print(f"Done. Inserted {inserted}, updated {updated} ({BROKER}).")


if __name__ == '__main__':
    run()

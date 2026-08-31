"""API endpoint smoke/behaviour tests via the Flask test client."""


def test_accounts_crud(client):
    assert client.get('/api/accounts').get_json() == []
    r = client.post('/api/accounts', json={'name': 'HDFC', 'subtype': 'bank', 'current_balance': 1000})
    assert r.status_code == 201
    accts = client.get('/api/accounts').get_json()
    assert len(accts) == 1 and accts[0]['name'] == 'HDFC'


def test_mutual_fund_create_and_list(client):
    r = client.post('/api/mutual-funds', json={
        'platform': 'Groww', 'fund_name': 'Test Fund', 'units': 100,
        'avg_nav': 50, 'current_nav': 60, 'investment_date': '2024-01-01',
    })
    assert r.status_code == 201
    funds = client.get('/api/mutual-funds').get_json()
    assert len(funds) == 1
    f = funds[0]
    assert f['invested_value'] == 5000 and f['current_value'] == 6000
    assert f['cagr_pct'] is not None                    # has an investment_date


def test_stock_create_with_cagr(client):
    r = client.post('/api/stocks', json={
        'demat_account': 'ZERODHA', 'company_name': 'Tata', 'ticker': 'TCS',
        'quantity': 10, 'avg_price': 3000, 'current_price': 3600,
        'exchange': 'NSE', 'currency': 'INR', 'purchase_date': '2023-07-21',
    })
    assert r.status_code == 201
    s = client.get('/api/stocks').get_json()[0]
    assert s['invested_value'] == 30000 and s['current_value'] == 36000
    assert s['cagr_pct'] is not None


def test_stock_sell_credits_broker_account(client):
    client.post('/api/stocks', json={
        'demat_account': 'Zerodha', 'company_name': 'Tata', 'ticker': 'TCS',
        'quantity': 10, 'avg_price': 3000, 'current_price': 3600,
        'exchange': 'NSE', 'currency': 'INR',
    })
    sid = client.get('/api/stocks').get_json()[0]['id']

    # Partial sell, no account_id -> matching broker (DEMAT) account is created/credited.
    r = client.post('/api/stocks/sell', json={'stock_id': sid, 'quantity': 4, 'price': 4000})
    assert r.status_code == 201
    body = r.get_json()
    assert body['realized'] == 4000            # (4000-3000)*4
    assert body['account']['name'] == 'Zerodha'
    assert body['account']['account_type_code'] == 'DEMAT'
    assert body['account']['current_balance'] == 16000   # 4*4000
    assert client.get('/api/stocks').get_json()[0]['quantity'] == 6

    # Full sell removes the holding and adds to the same broker account.
    r2 = client.post('/api/stocks/sell', json={'stock_id': sid, 'quantity': 6, 'price': 4000})
    assert r2.get_json()['stock'] is None
    assert r2.get_json()['account']['current_balance'] == 40000   # 16000 + 6*4000
    assert client.get('/api/stocks').get_json() == []


def test_dashboard_shape(client):
    d = client.get('/api/dashboard').get_json()
    for key in ('net_worth', 'total_assets', 'total_liabilities', 'breakdown',
                'monthly_commitments', 'portfolio_xirr'):
        assert key in d


def test_categories_seeded(client):
    codes = {c['code'] for c in client.get('/api/categories').get_json()}
    assert {'TRANSFER', 'MF_INVESTMENT', 'STOCK_PURCHASE', 'LOAN_PREPAYMENT'} <= codes

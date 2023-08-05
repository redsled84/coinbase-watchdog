from flask import Flask, jsonify, url_for, request, redirect, render_template
import requests
import json, hmac, hashlib, time, base64

app = Flask(__name__)

class Object:
    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, 
            sort_keys=True, indent=4)

# change the keys to your keys
secret_key = "YOUR_SECRET_KEY"
api_key = "YOUR_API_KEY"

# change the list of tickers to the ones you own
current_holdings = ['BTC', 'ETH', 'LTC']

# specified endpoint for read access to accounts, orders, and products
v3_endpoint = {
    'account': '/api/v3/brokerage/accounts',
    'order': '/api/v3/brokerage/orders/historical/batch',
    'product': '/api/v3/brokerage/products'
}

v3_URI = {
    'account': 'https://api.coinbase.com/api/v3/brokerage/accounts?limit=250',
    'order': 'https://api.coinbase.com/api/v3/brokerage/orders/historical/batch?order_status=OPEN',
    'product': 'https://api.coinbase.com/api/v3/brokerage/products?limit=250'
}


def get_v3_endpoint(end_point, URI):
    # signing reference:
    # https://docs.cloud.coinbase.com/advanced-trade-api/docs/rest-api-auth
    timestamp = str(int(time.time()))
    end_point = end_point
    body = ""
    message = timestamp + "GET" + end_point + str(body or '')
    signature = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        digestmod=hashlib.sha256).hexdigest()

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "CB-ACCESS-KEY": api_key,
        "CB-ACCESS-SIGN": signature,
        "CB-ACCESS-TIMESTAMP": timestamp
    }

    response = requests.get(URI, headers=headers)
    return response

"""
Note: this isn't comprehensive, just the fields
      I wanted to parameterize using an object

Account Schema:
    active: True boolean
    available_balance: {
        currency: BTC string
        value: 1.00 string
    }
    currency: BTC string
    updated_at: Date string
"""

def get_accounts():
    end_point = v3_endpoint['account']
    URI = v3_URI['account']

    accounts = get_v3_endpoint(end_point=end_point, URI=URI).json()
    min_coins_per_acc = 2.0

    filtered_accounts = [acc
        for acc in accounts['accounts']
            if float(acc['available_balance']['value']) > min_coins_per_acc]

    return filtered_accounts

class Account(Object):
    def __init__(self, active: bool,
                       available_balance: dict,
                       currency: str,
                       updated_at: str):
        self.active = active
        self.available_balance = float(available_balance["value"])
        self.currency = currency
        self.updated_at = updated_at

    def get_currency(self) -> str:
        return self.currency

def aggregate_accounts(accounts: list[Account], to_json: bool):
    my_accounts = {}
    for account in accounts:
        display_ticker = account['currency']

        existing_account = Account(
            active=account['active'],
            available_balance=account['available_balance'],
            currency=display_ticker,
            updated_at=account['updated_at']
        )
        if to_json:
            my_accounts[display_ticker] = json.loads(existing_account.to_json())
            my_accounts[display_ticker]['raw'] = account
        else:
            my_accounts[display_ticker] = existing_account

    return my_accounts

"""
Orders Schema:
    average_filled_price: 0 string
    outstanding_hold_amount: 1.75 string
    total_value_after_fees: 631.21 string
    product_id: BCH-USDC string
    side: SELL string
"""

def get_orders():
    end_point = v3_endpoint['order']
    URI = v3_URI['order']

    orders = get_v3_endpoint(end_point=end_point, URI=URI).json()

    return orders['orders']

class Order(Object):
    def __init__(self, average_filled_price: str,
                       outstanding_hold_amount: str,
                       total_value_after_fees: str,
                       product_id: str,
                       side: str):
        self.average_filled_price = average_filled_price
        self.outstanding_hold_amount = outstanding_hold_amount
        self.total_value_after_fees = total_value_after_fees
        self.product_id = product_id
        self.side = side

def aggregate_orders(orders: list[Order], to_json: bool):
    my_orders = {}
    for order in orders:
        display_ticker=order['product_id'].split('-')[0]

        existing_order = Order(
            average_filled_price=order['average_filled_price'],
            outstanding_hold_amount=order['outstanding_hold_amount'],
            total_value_after_fees=order['total_value_after_fees'],
            product_id=display_ticker,
            side=order['side']
        )

        if display_ticker not in my_orders:
            my_orders[display_ticker] = []
            my_orders[display_ticker + '-raw'] = []

        if to_json:
            my_orders[display_ticker].append(json.loads(existing_order.to_json()))
        else:
            my_orders[display_ticker].append(existing_order)

        my_orders[display_ticker + '-raw'].append(order)

    return my_orders

"""
Product Schema:
    base_display_symbol: BTC string
    base_name: Bitcoin string
    price: 28994.76 string
    price_percentage_change_24h: "-0.8833" % string
    quote_display_symbol: USD string
"""

def get_products():
    end_point = v3_endpoint['product']
    URI = v3_URI['product']

    products = get_v3_endpoint(end_point=end_point, URI=URI).json()

    return products["products"]

class Product(Object):
    def __init__(self, base_display_symbol: str,
                       base_name: str,
                       price: str,
                       price_percentage_change_24h: str,
                       quote_display_symbol: str):
        self.base_display_symbol = base_display_symbol
        self.base_name = base_name
        self.price = price
        self.price_percentage_change_24h = price_percentage_change_24h
        self.quote_display_symbol = quote_display_symbol

def aggregate_products(products: list[Product], current_holdings: list[str], to_json: bool):
    #
    # formatting data to pass to templates
    #
    my_products = {}
    for product in products:
        display_ticker = product['base_display_symbol']
        quote_symbol = product['quote_display_symbol']

        if display_ticker in current_holdings and quote_symbol == 'USD':
            existing_product = Product(
                base_display_symbol=product['base_display_symbol'],
                base_name=product['base_name'],
                price=product['price'],
                price_percentage_change_24h=product['price_percentage_change_24h'],
                quote_display_symbol=product['quote_display_symbol']
            )

            if to_json:
                my_products[display_ticker] = json.loads(existing_product.to_json())
                my_products[display_ticker]['raw'] = product
            else:
                my_products[display_ticker] = existing_product

    return my_products

# you can view the json data retrieved from each endpoint here
@app.route('/api', methods=['GET'])
def get_json():
    if request.method != 'GET':
        return jsonify({})

    accounts = get_accounts()
    products = get_products()
    orders = get_orders()

    my_accounts = aggregate_accounts(accounts, True)
    my_products = aggregate_products(products, current_holdings, True)
    my_orders = aggregate_orders(orders, True)

    return {'accounts': my_accounts, 'products': my_products, 'orders': my_orders}

# main dashboard
@app.route('/', methods=['GET'])
def get_portfolio_metrics():
    json_data = get_json()

    total_liquid_cash = 0.0
    total_inliquid_cash = 0.0
    total_potential_inliquid = 0.0

    for key in current_holdings:
        my_accounts = json_data['accounts']
        my_products = json_data['products']

        num_coins = float(my_accounts[key]["available_balance"])
        spot_price = float(my_products[key]["price"])

        total_liquid_cash += num_coins * spot_price

        try:
            my_orders = json_data['orders'][key]
            num_coins_inliquid = sum([float(order["outstanding_hold_amount"])
                    for order in my_orders])

            total_inliquid_cash += num_coins_inliquid * spot_price
            total_potential_inliquid += sum([float(order["total_value_after_fees"])
                    for order in my_orders])
        except KeyError:
            continue

    payload = {
        'liquid': total_liquid_cash,
        'inliquid': total_inliquid_cash,
        'potential_sale': total_potential_inliquid,
        'total_networth': total_liquid_cash + total_inliquid_cash,
        'potential_network': total_liquid_cash + total_potential_inliquid,
        'accounts': json_data['accounts'],
        'orders': json_data['orders'],
        'products': json_data['products']
    }

    return render_template('index.html', payload=payload)

# todo:: custom func to exit at moon (sell everything when BTC hits ~$90k)
#        that's a realistic target in the next year if crypto != securities for Coinbase

import datetime
import json
import pytz
import requests

import config as cfg
from exceptions import ThirdPartyApiUnavailable

# quandl_url = 'https://www.quandl.com/api/v3/datasets/BCHARTS/KRAKENUSD.csv?api_key=yynH4Pnq-X7AhiFsFdEa'
# bitfinex_url = 'https://api-pub.bitfinex.com/v2/tickers?symbols=tBTCUSD'
# boc_url = 'https://www.bankofcanada.ca/valet/observations/FXCADUSD/json?'



def update_btcusd_csv():
    try:
        data = requests.get(cfg.quandl_url, timeout=2)
    except requests.exceptions.Timeout:
        print('[ERROR] Quandl API not responding.')
        raise ThirdPartyApiUnavailable
    with open('../data/btcusd.csv', 'wb+') as btcusd:
        btcusd.write(data.content)


def get_usd_price():
    price = call_exchange_api()
    return price


def call_exchange_api():
    response = None
    try:
        response = requests.get(cfg.bitfinex_url, timeout=4)
    except requests.exceptions.Timeout:
        print('[ERROR] Exchange API not responding.')
        raise ThirdPartyApiUnavailable
    return json.loads(response.text)[0][1]


def call_fx_api(start_date, end_date):
    response = None
    try:
        response = requests.get(cfg.boc_url + 'start_date=' + start_date +
                                '&end_date=' + end_date, timeout=4)
    except requests.exceptions.Timeout:
        print('[ERROR] Bank of Canada API not responding.')
        raise ThirdPartyApiUnavailable
    return json.loads(response.text)


def format_payload(json_response):
    if payload_is_not_empty(json_response):
        return strip_payload(json_response)
    else:
        return {}


def payload_is_not_empty(payload):
    return len(payload['observations']) != 0


def strip_payload(payload):
    return {i['d']: i['FXCADUSD']['v'] for i in payload['observations']}


def get_fx_cadusd_rates(start_date, end_date=None):
    if end_date is None:
        json_response = call_fx_api(start_date, end_date=str(datetime.date.today()))
        observations = format_payload(json_response)
        api_data = [{'start_date': start_date, 'end_date': get_current_date_for_exchange_api()}, observations]
    else:
        json_response = call_fx_api(start_date, end_date)
        observations = format_payload(json_response)
        api_data = [{'start_date': start_date, 'end_date': end_date}, observations]
    fx_rates = fill_missing_day_rates(api_data)
    return fx_rates[::-1]


def fill_missing_day_rates(rates):
    start_date = datetime.datetime.strptime(rates[0]['start_date'], '%Y-%m-%d')
    end_date = datetime.datetime.strptime(rates[0]['end_date'], '%Y-%m-%d')
    result = []
    curr = start_date
    result_has_data = False
    while True:
        if curr.strftime('%Y-%m-%d') in rates[1].keys():
            result.append(rates[1][curr.strftime('%Y-%m-%d')])
            result_has_data = True
        else:  # FX shows no day data, duplicate last observation or use avg.
            result.append(result[-1]) if result_has_data else result.append(cfg.AVG_FX_CADUSD)
        curr = curr + datetime.timedelta(days=1)
        if curr > end_date:
            break
    return result


def get_current_date_for_exchange_api():
    tz = pytz.timezone('Europe/London')
    ct = datetime.datetime.now(tz=tz)
    return ct.strftime('%Y-%m-%d')

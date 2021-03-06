from exceptions import InitializationDataNotFound
from tools import update_btcusd_csv
import config as cfg
import pandas as pd
import datetime


class PriceData:
    def __init__(self):
        self.df_btcusd = load_btcusd_csv()
        self.df_btcusd = fill_missing_days(self.df_btcusd)

    def get_btcusd_df(self):
        return self.df_btcusd


def load_btcusd_csv():
    update_btcusd_csv()
    try:
        df_btcusd = pd.read_csv(cfg.BTCUSD_INPUT_FILE)
    except FileNotFoundError:
        print(f'[ERROR] Could not find file btcusd.csv file - {cfg.BTCUSD_INPUT_FILE}.')
        raise InitializationDataNotFound
    df_btcusd['Date'] = pd.to_datetime(df_btcusd['Date'])
    df_btcusd['Last'] = pd.to_numeric(df_btcusd['Close'])
    return df_btcusd


def fill_missing_days(df):
    df2 = pd.DataFrame()
    expected = 0
    for index, row in df.iterrows():
        if index == 0:
            expected = row['Date'] - datetime.timedelta(days=1)
            continue
        else:
            curr = row['Date']
            prev = df.iloc[index]
            df2_index = index
            while curr != expected:
                line = pd.DataFrame({'Close': [prev['Close']],
                                     'Date': [expected],
                                     'High': [prev['High']],
                                     'Last': [prev['Last']],
                                     'Low': [prev['Low']],
                                     'Open': [prev['Open']],
                                     'Volume (BTC)': [prev['Volume (BTC)']],
                                     'Volume (Currency)': [prev['Volume (Currency)']],
                                     'Weighted Price': [prev['Weighted Price']]})
                df2 = pd.concat([df.iloc[:df2_index],
                                 line,
                                 df.iloc[df2_index:]]).reset_index(drop=True)
                df = df2
                df2_index += 1
                expected = expected - datetime.timedelta(days=1)
        expected = row['Date'] - datetime.timedelta(days=1)
    return df






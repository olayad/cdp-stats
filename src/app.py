#!/usr/bin/env python3

import argparse
import datetime
import sys

import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
from dash.dependencies import Input, Output
from config import set_test_mode, set_loans_input_file

import tools
from debt import Debt
from exceptions import InitializationDataNotFound, ThirdPartyApiUnavailable, InvalidData
from loan import Loan, get_loans, update_loans_with_current_price, get_cost_analysis, get_closed_loan_dates


loans = None
debt = None

parser = argparse.ArgumentParser(description='CDP stats server.')

parser.add_argument('-t', '--test', help='Specify the test suite (/tests/data/[loans-x].csv file to run')
parser.add_argument('-f', '--file', help='Specify the file path to run as follows: \'../data/[loans].csv\'')

args = parser.parse_args()
if args.test:
    set_test_mode(args.test)
if args.file:
    set_loans_input_file(args.file)

try:
    loans = get_loans()
except InitializationDataNotFound:
    print('[ERROR] Validate \'loan.csv\' and \'btcusd.csv\' files are available' +
          ' in \'/data/\' dir. Terminating execution.')
    sys.exit(1)
except ThirdPartyApiUnavailable:
    print('[ERROR] Third party API not responding, try again later. Terminating execution.')
    sys.exit(1)
except InvalidData:
    print('[ERROR] Invalid "loan.csv" file given. ')
    sys.exit(1)
debt = Debt()
debt.build_dataframe()


app = dash.Dash()
app.layout = html.Div([
    dcc.Interval(id='interval_price', interval=100000, n_intervals=0),
    dcc.Interval(id='interval_ltv', interval=500000, n_intervals=0),
    dcc.Interval(id='interval_cost_analysis', interval=500000, n_intervals=0),
    dcc.Interval(id='interval_debt', interval=500000, n_intervals=0),

    html.H1(id='btc_price', children=''),

    html.Div([
       dcc.Graph(id='graph_cost_analysis')
    ]),

    html.Div([
        dcc.Graph(id='graph_ltv')
    ]),

    html.Div([
        html.Div([
            dcc.Graph(id='graph_debt_btc')
        ], style={'width': '50%', 'display': 'inline-block'}),

        html.Div([
            dcc.Graph(id='graph_debt_cad')
        ], style={'width': '50%', 'display': 'inline-block'})
    ])
])

############################
#### Terminal summary ######
############################
total_coll_in_custody = 0
for loan in Loan.actives:
    total_coll_in_custody += loan.current_collateral
print(f'#################################################################')
print(f'Total collateral held by third parties: {total_coll_in_custody}')
############################


@app.callback(Output('btc_price', 'children'),
              [Input('interval_price', 'n_intervals')])
def on_price_interval(n_intervals):
    price = update_price_label()
    return price


def update_price_label():
    price_usd = float(tools.get_usd_price())
    curr_fx_cadusd = float(tools.get_fx_cadusd_rates(datetime.datetime.now().strftime('%Y-%m-%d'))[0])
    price_cad = int(price_usd / curr_fx_cadusd)
    return 'BTC: '+str(price_usd)+' USD / '+str(price_cad)+' CAD'


@app.callback(Output('graph_ltv', 'figure'),
              [Input('interval_ltv', 'n_intervals')])
def on_ltv_interval(n_intervals):
    figure = update_graph_ltv()
    return figure


def update_graph_ltv():
    update_loans_with_current_price()
    figure = build_graph_ltv()
    return figure


def build_graph_ltv():
    data = []
    oldest_start_date = datetime.date.today()
    for cdp in Loan.actives:
        if cdp.start_date < oldest_start_date : oldest_start_date = cdp.start_date
        trace = go.Scatter(x=cdp.stats['date'],
                           y=cdp.stats['ltv'],
                           mode='lines',
                           name='$'+str(cdp.current_debt_cad))
        data.append(trace)
    layout = go.Layout(title='Loan to Value (LTV)',
                       shapes=[{'type': 'line',
                                'y0': 0.5, 'x0': oldest_start_date,
                                'y1': 0.5, 'x1': datetime.date.today(),
                                'line': {'color': 'red', 'width': 2.0, 'dash': 'dot'}}],
                       legend_orientation='h',
                       showlegend=True,
                       yaxis_title="Ratio",
                       xaxis={
                           'rangeselector': {'buttons':[
                               {
                                   "count": 1,
                                   "label": "1 mo",
                                   "step": "month",
                                   "stepmode": "backward"
                               },
                               {
                                   "count": 3,
                                   "label": "3 mo",
                                   "step": "month",
                                   "stepmode": "backward"
                               },
                               {
                                   "count": 6,
                                   "label": "6 mo",
                                   "step": "month",
                                   "stepmode": "backward"
                               },
                               {
                                   "count": 1,
                                   "label": "YTD",
                                   "step": "year",
                                   "stepmode": "todate"
                               },
                               {"step": "all"}
                           ]},
                           'rangeslider': {'visible': True},
                           'type': 'date',
                           "autorange": True
                       })
    return {'data': data, 'layout': layout}


@app.callback(Output('graph_cost_analysis', 'figure'),
              [Input('interval_cost_analysis', 'n_intervals')])
def on_cost_analysis_interval(n_intervals):
    figure = update_graph_cost_analysis()
    return figure


def update_graph_cost_analysis():
    cost_data = get_cost_analysis()
    figure = build_graph_cost_analysis(cost_data)
    return figure


def build_graph_cost_analysis(cost_data):
    annotation = ['Percent change: {}%'.format(p) for p in cost_data['delta_percent']]
    trace1 = go.Bar(x=cost_data['loan_id'],
                    y=cost_data['start_cost'],
                    hovertext=annotation,
                    name='Start cost (BTC)',
                    marker_color='lightgrey')
    trace2 = go.Bar(x=cost_data['loan_id'],
                    y=cost_data['curr_cost'],
                    hovertext=annotation,
                    name='Curr cost (BTC)',
                    marker_color='lightskyblue')

    data = [trace1, trace2]
    layout = go.Layout(title='Cost Analysis - USD Loan',
                       xaxis={'type': 'category'},
                       yaxis_title='BTC')
    return {'data': data, 'layout': layout}


@app.callback([Output('graph_debt_btc', 'figure'),
               Output('graph_debt_cad', 'figure')],
              [Input('interval_debt', 'n_intervals')])
def interval_debt_triggered(n_intervals):
    debt.update_df_with_current_price()
    figure_btc = update_graph_debt_btc()
    figure_cad = update_graph_debt_cad()
    return figure_btc, figure_cad


def update_graph_debt_btc():
    df = debt.df_debt
    trace1 = go.Scatter(x=df['date'],
                        y=df['debt_btc'],
                        mode='lines',
                        name='Debt')
    trace2 = go.Scatter(x=df['date'],
                        y=df['interest_btc'],
                        mode='lines',
                        name='Interest')
    trace3 = go.Scatter(x=df['date'],
                        y=df['total_liab_btc'],
                        mode='lines',
                        name='Total Liabilities')
    data = [trace1, trace2, trace3]
    closing_dates_makers = get_closing_dates_markers(df, 'BTC')
    layout = go.Layout(title='Liabilities (BTC)',
                       legend_orientation='h',
                       showlegend=True,
                       yaxis_title="BTC",
                       xaxis={
                           'rangeselector': {'buttons': [
                               {
                                   "count": 1,
                                   "label": "1 mo",
                                   "step": "month",
                                   "stepmode": "backward"
                               },
                               {
                                   "count": 3,
                                   "label": "3 mo",
                                   "step": "month",
                                   "stepmode": "backward"
                               },
                               {
                                   "count": 6,
                                   "label": "6 mo",
                                   "step": "month",
                                   "stepmode": "backward"
                               },
                               {
                                   "count": 1,
                                   "label": "YTD",
                                   "step": "year",
                                   "stepmode": "todate"
                               },
                               {"step": "all"}
                           ]},
                           'rangeslider': {'visible': True},
                           'type': 'date',
                           "autorange": True
                       },
                       shapes=closing_dates_makers)
    figure = {'data': data, 'layout': layout}
    return figure


def update_graph_debt_cad():
    df = debt.df_debt
    trace1 = go.Scatter(x=df['date'],
                        y=df['debt_cad'],
                        mode='lines',
                        name='Debt')
    trace2 = go.Scatter(x=df['date'],
                        y=df['interest_cad'],
                        mode='lines',
                        name='Interest')
    trace3 = go.Scatter(x=df['date'],
                        y=df['total_liab_cad'],
                        mode='lines',
                        name='Total Liabilities')
    data = [trace1, trace2, trace3]
    closing_dates_makers = get_closing_dates_markers(df, 'CAD')
    layout = go.Layout(title='Liabilities (CAD)',
                       legend_orientation='h',
                       showlegend=True,
                       yaxis_title="CAD",
                       xaxis={
                           'rangeselector': {'buttons': [
                               {
                                   "count": 1,
                                   "label": "1 mo",
                                   "step": "month",
                                   "stepmode": "backward"
                               },
                               {
                                   "count": 3,
                                   "label": "3 mo",
                                   "step": "month",
                                   "stepmode": "backward"
                               },
                               {
                                   "count": 6,
                                   "label": "6 mo",
                                   "step": "year",
                                   "stepmode": "backward"
                               },
                               {
                                   "count": 1,
                                   "label": "YTD",
                                   "step": "year",
                                   "stepmode": "todate"
                               },
                               {"step": "all"}
                           ]},
                           'rangeslider': {'visible': True},
                           'type': 'date',
                           "autorange": True
                       },
                       shapes=closing_dates_makers)

    figure = {'data': data, 'layout': layout}
    return figure


def get_closing_dates_markers(df, currency):
    closing_dates = get_closed_loan_dates()
    closed_dates_markers = []
    for date in closing_dates:
        closed_dates_markers.append(
            {
                'type': 'line',
                'x0': date,
                'y0': 0,
                'x1': date,
                'y1': df['total_liab_btc'].max() if currency == 'BTC' else df['total_liab_cad'].max(),
                'line': {
                    'color': 'rgb(133,20,75)',
                    'width': 1,
                    'dash': 'dashdot',
                }
            }
        )
    return closed_dates_markers


def loans_overview():
    total_coll = 0
    print(f'\n################################################################################')
    print(f'##############################      OVERVIEW      ##############################')
    print(f'################################################################################')
    for loan in loans:
        print(f'{loan}')
        total_coll += loan.current_collateral
    print("- Total collateral: ", total_coll)
    # liquidate = (loan/price)
    # print("If I want to rebalance with current price: ", liquidate * 2)
    # withdraw = total_coll - (liquidate * 2)
    # print(f"Could withdraw: {withdraw} - ${withdraw * price}")
    # print(f"cost to rebalance (2%): {loan*(0.02)}")
    print(f'################################################################################\n')


loans_overview()

if __name__ == '__main__':
    app.run_server()


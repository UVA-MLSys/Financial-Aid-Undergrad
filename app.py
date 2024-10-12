# https://dash.plotly.com/tutorial
# https://dash.plotly.com/basic-callbacks

# Import packages
import pandas as pd
import dash_bootstrap_components as dbc
import dash_auth
from util.utils import *
from util.plotter import *
from config import *
import argparse, json
import warnings, logging
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)
logging.basicConfig(
    filename=data_root + 'myapp.log', 
    level=logging.INFO
)
logger.info('Started')

# data input
df = pd.read_csv(data_root + 'Merged.csv')

# Initialize the app
VALID_USERNAME_PASSWORD_PAIRS = json.load(open(data_root + 'login.json'))
external_stylesheets = [dbc.themes.BOOTSTRAP]
app = Dash(__name__, external_stylesheets=external_stylesheets, description='Financial Aid')
server = app.server
auth = dash_auth.BasicAuth(
    app,
    VALID_USERNAME_PASSWORD_PAIRS
)

# remove ' Undergraduate' from ACADEMIC_PROGRAM_DESC
for value in [' Undergraduate', ' Undergrad']:
    df['ACADEMIC_PROGRAM_DESC'] = df['ACADEMIC_PROGRAM_DESC'].apply(lambda x: x.replace(value, ''))
    
def get_categories(df, col, default_value):
    unique_values = list(sorted(df[col].unique()))
    # default value will work as Total
    unique_values = [x for x in unique_values if x != 'Total']
    
    return [default_value] + unique_values

program_ids = get_categories(df, 'ACADEMIC_PROGRAM_DESC', default_values['ACADEMIC_PROGRAM_DESC'])
academic_plans = get_categories(df, 'ACADEMIC_PLAN', default_values['ACADEMIC_PLAN'])
report_categories = get_categories(df, 'UVA_ACCESS', default_values['UVA_ACCESS'])
report_codes = get_categories(df, 'REPORT_CODE', default_values['REPORT_CODE'])
need_based = get_categories(df, 'Need based', default_values['Need based'])
residency = get_categories(df, 'FIN_AID_FED_RES', default_values['FIN_AID_FED_RES'])

# get_categories(df, 'ACADEMIC_LEVEL_TERM_START', default_values['ACADEMIC_LEVEL_TERM_START'])
academic_levels = [default_values['ACADEMIC_LEVEL_TERM_START']] + [
    'Level One', 'Level Two', 'Level Three', 'Level Four'
]

summed = pd.DataFrame(columns=[
   'AID_YEAR', 'OFFER_BALANCE','PREDICTED_MEAN',
    f'{confidence}% CI - LOWER', 
    f'{confidence}% CI - UPPER', 
    'FUNDED_PARTY', 'TOTAL_PARTY'
])

app.layout = get_layout(
    factors=[
        program_ids, academic_levels, academic_plans, 
        report_categories, report_codes, need_based, residency
    ], factor_labels=[
        'program-desc', 'academic-level', 'academic-plan', 
        'report-category', 'report-code', 'need-based', 'residency'
    ], summed=summed
)

callbacks = [
    Output("time-series-chart", "figure"), 
    Output("count-chart", "figure"), 
    Output('table', 'data')
] + [Input(f"dropdown-{value}", "value") for value in [
        'academic-level', 'program-desc', 'academic-plan', 
        'report-category', 'report-code', 'need-based', 'residency']
] + [Input('radio-time-series', 'value'), Input('radio-count-series', 'value')]
@app.callback(callbacks)
def update_data(
    level, program_desc, academic_plan, 
    report_category, report_code, need_based, residency,
    radio_time, radio_count
):
    dis = filter_disbursement(
        df, level, program_desc, academic_plan, 
        report_category, report_code, need_based,
        residency, logger
    )
    summed = dis.groupby(time_column)[target].sum().reset_index()
    years = summed[time_column].values
    
    count_df = dis.groupby(
        time_column
    )['FUNDED_PARTY'].sum().reset_index()
    
    count_df['TOTAL_PARTY'] = dis.groupby(
        time_column
    )['TOTAL_PARTY'].sum().values
    party_fig = draw_party_fig(years, count_df, radio_count)
    
    predictions = {
        'PREDICTED_MEAN': [], time_column:[],
        f'{confidence}% CI - LOWER':[], 
        f'{confidence}% CI - UPPER':[]
    }
    
    predictions = predict(summed, predictions)
    predictions = autoregressive(summed, predictions) 
    
    predictions = pd.DataFrame(predictions)   
    fig = draw_main_fig(summed, predictions, radio_time)
    
    summed = summed.merge(count_df, on=time_column)
    summed = summed.merge(predictions, on=time_column, how='outer')
    summed.sort_values(by=time_column, ascending=False, inplace=True)
    
    for col in summed.columns:
        if col in ['AID_YEAR']: continue
        index = ~summed[col].isna()
        # summed.loc[index, col] = summed.loc[index, col].apply(numerize, args=(1,))
        summed.loc[index, col] = summed.loc[index, col].apply('{:,.2f}'.format)
    
    return fig, party_fig, summed.round(0).to_dict('records')

    
# Run the app
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Financial Aid Forecasting App', 
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--host', type=str, default='127.0.0.1', 
        help='Host address. Should be 0.0.0.0 if running on AWS, 127.0.0.1 if running locally.'
    )
    parser.add_argument('--port', type=int, default=8050)
    args = parser.parse_args()
    
    app.run(host=args.host, port=args.port, debug=True)

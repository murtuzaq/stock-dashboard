"""Revenue and earnings per share (EPS), quarterly and annual, with growth rates.

Yahoo only returns the latest ~5 quarters and ~4 years. Everything downloaded is kept in the local database,
so the history (and the growth figures that need a year-earlier period) builds up over time.
"""
import time
import warnings

import pandas as pd
import yfinance as yf

from . import store

warnings.filterwarnings('ignore', module='yfinance')

MAX_AGE_SECONDS = 7 * 24 * 3600  # companies report quarterly, so a weekly check is plenty
PERIODS = ('quarterly', 'annual')
YAHOO_ROWS = {'revenue': 'Total Revenue', 'eps': 'Diluted EPS'}


def _download(symbol: str) -> dict[str, pd.DataFrame]:
    ticker = yf.Ticker(symbol.replace('.', '-'))
    statements = {'quarterly': ticker.quarterly_income_stmt, 'annual': ticker.income_stmt}
    figures = {}
    for period, statement in statements.items():
        columns = {name: statement.loc[row] if row in statement.index else None for name, row in YAHOO_ROWS.items()}
        frame = pd.DataFrame(columns, index=pd.DatetimeIndex(statement.columns, name='end_date'))
        figures[period] = frame.dropna(how='all').sort_index()
    return figures


def _growth(values: pd.Series, dates: pd.DatetimeIndex, years: int = 0, previous_row: bool = False) -> pd.Series:
    """Percent change versus the period one row earlier, or versus the period `years` earlier (within 3 weeks).

    Not meaningful when the earlier value is zero or negative (e.g. a loss), so that gives NaN.
    """
    if previous_row:
        earlier = values.shift()
    else:
        lookup = pd.DataFrame({'date': dates, 'value': values.to_numpy()})
        wanted = pd.DataFrame({'date': dates - pd.DateOffset(years=years)})
        earlier = pd.merge_asof(wanted, lookup, on='date', direction='nearest',
                                tolerance=pd.Timedelta(days=21))['value'].set_axis(values.index)
    growth = (values / earlier - 1) * 100
    return growth.where(earlier > 0)


def with_growth(figures: pd.DataFrame, period: str) -> pd.DataFrame:
    """Adds year-over-year growth columns (and quarter-over-quarter for quarterly figures)."""
    result = figures.copy()
    for column in ('revenue', 'eps'):
        result[f'{column}_yoy'] = _growth(figures[column], figures.index, years=1)
        if period == 'quarterly':
            result[f'{column}_qoq'] = _growth(figures[column], figures.index, previous_row=True)
    return result


def load_financials(symbol: str) -> dict[str, pd.DataFrame]:
    """{'quarterly': ..., 'annual': ...}, each indexed by period end date with revenue, eps and growth columns."""
    last_checked = store.checked_at(symbol, 'financials_checked')
    if last_checked is None or time.time() - last_checked > MAX_AGE_SECONDS:
        try:
            for period, figures in _download(symbol).items():
                store.save_financials(symbol, period, figures)
            store.mark_checked(symbol, 'financials_checked')
        except Exception as error:
            print(f'Could not update financials for {symbol} ({error}); using stored figures')
    return {period: with_growth(store.read_financials(symbol, period), period) for period in PERIODS}

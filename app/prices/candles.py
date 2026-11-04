"""Turns daily prices into candles of any size, and works out where each history range starts."""
import pandas as pd

# Candle size -> pandas resample rule. Weeks end on Friday (the last trading day).
CANDLE_RULES = {'1D': None, '1W': 'W-FRI', '2W': '2W-FRI', '1M': 'ME', '3M': 'QE'}
# Trading days in one candle, to convert indicator lengths given in days (e.g. 50-day SMA = 10 weekly candles).
CANDLE_DAYS = {'1D': 1, '1W': 5, '2W': 10, '1M': 21, '3M': 63}

# History length shown on the chart.
RANGES = ['1M', '3M', '6M', 'YTD', '1Y', '5Y', '10Y', 'Max']
DEFAULT_RANGE = '1Y'
RANGE_NAMES = {
    '1M': 'past month', '3M': 'past 3 months', '6M': 'past 6 months', 'YTD': 'year to date',
    '1Y': 'past year', '5Y': 'past 5 years', '10Y': 'past 10 years', 'Max': 'all time',
}
RANGE_OFFSETS = {
    '1M': pd.DateOffset(months=1), '3M': pd.DateOffset(months=3), '6M': pd.DateOffset(months=6),
    '1Y': pd.DateOffset(years=1), '5Y': pd.DateOffset(years=5), '10Y': pd.DateOffset(years=10),
}


def to_candles(daily: pd.DataFrame, candle_size: str) -> pd.DataFrame:
    """Combine daily rows into bigger candles: first open, highest high, lowest low, last close, total volume.

    Each candle is dated by its first trading day. The size is recorded in candles.attrs['candle_size'].
    """
    rule = CANDLE_RULES[candle_size]
    if rule is None or daily.empty:
        candles = daily.copy()
    else:
        rows = daily.assign(first_day=daily.index)
        candles = rows.resample(rule).agg({
            'first_day': 'first', 'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum',
        }).dropna().set_index('first_day').rename_axis('date')
    candles.attrs['candle_size'] = candle_size
    return candles


def range_start(last_day: pd.Timestamp, first_day: pd.Timestamp, range_label: str) -> pd.Timestamp:
    if range_label == 'Max':
        return first_day
    if range_label == 'YTD':
        return pd.Timestamp(year=last_day.year, month=1, day=1)
    return max(first_day, last_day - RANGE_OFFSETS[range_label])


def range_change(daily: pd.DataFrame, start: pd.Timestamp) -> tuple[float, float]:
    """Change from the first close in the range to the latest close, as (amount, percent).

    This matches Google Finance, e.g. YTD compares with the close of the year's first trading day.
    """
    first = min(int(daily.index.searchsorted(start)), len(daily) - 1)
    base = daily['close'].iloc[first]
    last = daily['close'].iloc[-1]
    return last - base, (last / base - 1) * 100

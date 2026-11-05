"""Volatility indicators: how much price typically moves."""
import pandas as pd


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Average True Range: the typical size of one candle's move, in price units.

    True range is the largest of: high - low, |high - previous close|, |low - previous close|
    (so overnight gaps count). Averaged with Wilder's smoothing, like TradingView.
    """
    previous_close = close.shift()
    true_range = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()],
                           axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def bollinger(close: pd.Series, length: int = 20, deviations: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands: a `length`-candle average (middle) with bands `deviations` standard deviations above and
    below it. Uses the population standard deviation, as John Bollinger and TradingView do."""
    middle = close.rolling(length).mean()
    spread = close.rolling(length).std(ddof=0) * deviations
    return pd.DataFrame({'upper': middle + spread, 'middle': middle, 'lower': middle - spread})

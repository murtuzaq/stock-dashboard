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

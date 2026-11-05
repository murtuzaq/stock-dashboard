"""Trend indicators: which way price is heading, and how it compares with the market."""
import pandas as pd


def sma(close: pd.Series, length: int) -> pd.Series:
    """Simple moving average: the average close of the last `length` candles."""
    return close.rolling(length).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD: the gap between a fast and a slow exponential average of the close.

    Returns macd (fast EMA minus slow EMA), signal (EMA of macd) and histogram (macd minus signal).
    Defaults match TradingView's: 12, 26, 9.
    """
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({'macd': line, 'signal': signal_line, 'histogram': line - signal_line})


def relative_strength(close: pd.Series, benchmark_close: pd.Series) -> pd.Series:
    """Ratio of the stock's close to the benchmark's on the same dates. Rising = beating the benchmark."""
    benchmark = benchmark_close.reindex(close.index, method='ffill')
    return close / benchmark


def donchian(high: pd.Series, low: pd.Series, length: int) -> pd.DataFrame:
    """Donchian channel: the highest high and lowest low of the PREVIOUS `length` candles (not counting this one).

    Excluding the current candle is what makes "close crosses above the upper line" mean a breakout to a new
    `length`-candle high, as in the Turtle rules.
    """
    return pd.DataFrame({'upper': high.rolling(length).max().shift(1), 'lower': low.rolling(length).min().shift(1)})

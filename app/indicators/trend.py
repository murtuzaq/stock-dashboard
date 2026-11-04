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

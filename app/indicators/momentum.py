"""Momentum indicators: how strong and how stretched recent price moves are."""
import numpy as np
import pandas as pd


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Relative Strength Index (0-100): average gain vs. average loss over `length` candles.

    Uses Wilder's smoothing, like TradingView and most platforms.
    """
    change = close.diff()
    average_gain = change.clip(lower=0).ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    average_loss = (-change.clip(upper=0)).ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    return 100 - 100 / (1 + average_gain / average_loss)


def stoch_rsi(close: pd.Series, rsi_length: int = 14, stoch_length: int = 14,
              k_smoothing: int = 3, d_smoothing: int = 3) -> pd.DataFrame:
    """Stochastic RSI (0-100): where RSI sits within its own high-low range over `stoch_length` candles.

    Returns two lines: k (the fast line, smoothed) and d (a moving average of k).
    Defaults match TradingView's: 14, 14, 3, 3.
    """
    strength = rsi(close, rsi_length)
    lowest = strength.rolling(stoch_length).min()
    highest = strength.rolling(stoch_length).max()
    position = ((strength - lowest) / (highest - lowest) * 100).replace([np.inf, -np.inf], np.nan)
    k = position.rolling(k_smoothing).mean()
    d = k.rolling(d_smoothing).mean()
    return pd.DataFrame({'k': k, 'd': d})

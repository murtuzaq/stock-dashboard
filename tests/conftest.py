"""Shared test helpers. Run the suite from the project folder with: pytest"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from strategy import Condition, Exits, Operand, RuleGroup, Strategy  # noqa: E402


def make_candles(closes, candle_size: str = '1D', start: str = '2024-01-01') -> pd.DataFrame:
    """Candles from a list of closes: open = close, high/low = close ± 1, one per business day."""
    closes = np.asarray(closes, dtype=float)
    index = pd.bdate_range(start, periods=len(closes), name='date')
    candles = pd.DataFrame({'open': closes, 'high': closes + 1, 'low': closes - 1, 'close': closes,
                            'volume': np.full(len(closes), 1000.0)}, index=index)
    candles.attrs['candle_size'] = candle_size
    return candles


def random_walk(length: int, seed: int, start_price: float = 100.0) -> pd.DataFrame:
    """Realistic-looking daily candles for property tests."""
    rng = np.random.default_rng(seed)
    close = start_price * np.exp(np.cumsum(rng.normal(0, 0.015, length)))
    open_ = close * np.exp(rng.normal(0, 0.005, length))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, length))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, length))
    index = pd.bdate_range('2020-01-01', periods=length, name='date')
    candles = pd.DataFrame({'open': open_, 'high': high, 'low': low, 'close': close,
                            'volume': rng.integers(1_000, 10_000, length).astype(float)}, index=index)
    candles.attrs['candle_size'] = '1D'
    return candles


def indicator(key: str, output: str | None = None, **params) -> Operand:
    return Operand(indicator=key, output=output, params=params)


def number(value: float) -> Operand:
    return Operand(value=value)


@pytest.fixture
def spec_example() -> Strategy:
    """The example from the feature request: trend + MACD cross + Stoch RSI dip; exit on MACD cross down or trend loss."""
    return Strategy(
        name='MACD + Stoch RSI', symbol='IBM',
        buy=RuleGroup('all', [
            Condition(indicator('close'), 'above', indicator('sma', days=200)),
            Condition(indicator('macd', 'macd'), 'crosses_above', indicator('macd', 'signal')),
            Condition(indicator('stoch_rsi', 'k'), 'below', number(20)),
        ]),
        sell=RuleGroup('any', [
            Condition(indicator('macd', 'macd'), 'crosses_below', indicator('macd', 'signal')),
            Condition(indicator('close'), 'below', indicator('sma', days=200)),
        ]),
        exits=Exits(stop_loss_pct=8),
    )

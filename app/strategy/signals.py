"""Turns a strategy's rules into BUY/SELL signals: one True/False per candle.

No look-ahead: the value on candle t uses only candles up to and including t, because every indicator
is causal (rolling or exponential averages) and crosses compare with the previous candle (shift(1)).
Indicators that are not ready yet (e.g. the first 199 candles of SMA 200) give False, never True.
"""
import pandas as pd

from . import catalog
from .model import Condition, Operand, RuleGroup, Strategy


class SeriesCache:
    """Computes each indicator once per evaluation, even if several conditions use it."""

    def __init__(self, candles: pd.DataFrame, benchmark: pd.DataFrame | None) -> None:
        self.candles, self.benchmark = candles, benchmark
        self.frames: dict[tuple, pd.DataFrame] = {}

    def series(self, operand: Operand) -> pd.Series:
        if operand.is_number:
            return pd.Series(operand.value, index=self.candles.index, dtype=float)
        indicator = catalog.get(operand.indicator)
        settings = indicator.settings(operand.params)
        key = (indicator.key, tuple(sorted(settings.items())))
        if key not in self.frames:
            self.frames[key] = indicator.compute(self.candles, self.benchmark, settings)
        output = operand.output or indicator.main_output
        if output not in indicator.outputs:
            raise ValueError(f'{indicator.label} has no output {output!r}; choose from {list(indicator.outputs)}')
        return self.frames[key][output].astype(float)


def condition_signal(condition: Condition, cache: SeriesCache) -> pd.Series:
    left, right = cache.series(condition.left), cache.series(condition.right)
    if condition.op == 'above':
        result = left > right
    elif condition.op == 'below':
        result = left < right
    elif condition.op == 'crosses_above':
        result = (left > right) & (left.shift(1) <= right.shift(1))
    else:  # crosses_below
        result = (left < right) & (left.shift(1) >= right.shift(1))
    # Comparisons with a missing value (indicator still warming up) are already False.
    if condition.is_event and condition.within > 1:
        result = result.astype(int).rolling(condition.within, min_periods=1).max().astype(bool)
    return result.astype(bool)


def group_signal(group: RuleGroup, cache: SeriesCache) -> pd.Series:
    if not group.conditions:
        return pd.Series(False, index=cache.candles.index)  # no rules: never signals
    parts = pd.concat([group_signal(item, cache) if isinstance(item, RuleGroup) else condition_signal(item, cache)
                       for item in group.conditions], axis=1)
    return parts.all(axis=1) if group.match == 'all' else parts.any(axis=1)


def evaluate(strategy: Strategy, candles: pd.DataFrame, benchmark: pd.DataFrame | None = None) -> pd.DataFrame:
    """buy_signal and sell_signal for every candle (signals are known at the candle's close)."""
    cache = SeriesCache(candles, benchmark)
    return pd.DataFrame({'buy_signal': group_signal(strategy.buy, cache),
                         'sell_signal': group_signal(strategy.sell, cache)}, index=candles.index)

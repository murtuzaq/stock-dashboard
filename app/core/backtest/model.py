"""The Backtest chart as data: each selected strategy's account value over time, against buy & hold."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.common import theme
from core.common.formatting import Line, Span, money, plain
from core.strategies.results import equity_curves
from strategy import Strategy
from strategy.backtest import BacktestResult


@dataclass(frozen=True)
class BacktestSeries:
    """One line on the chart."""
    label: str
    color: str
    values: np.ndarray  # account value per candle, NaN before the range starts
    end_value: float
    return_pct: float
    is_hold: bool = False


@dataclass(frozen=True)
class BacktestChart:
    dates: pd.DatetimeIndex
    start: pd.Timestamp
    series: list[BacktestSeries]  # the strategies in selection order, then buy & hold last
    legend: Line  # one entry per line: name, final value, return
    note: str  # e.g. a warning that the strategies did not start with the same cash, else ''


def strategy_color(index: int) -> str:
    return theme.STRATEGY_COLORS[index % len(theme.STRATEGY_COLORS)]


def _legend_entry(series: BacktestSeries) -> Line:
    result = f'{money(series.end_value)} ({series.return_pct:+.2f}%)'
    return [Span('━ ', series.color, bold=True), plain(f'{series.label}  '),
            Span(result, theme.change_color(series.return_pct))]


def backtest_chart(runs: list[tuple[Strategy, BacktestResult]]) -> BacktestChart | None:
    """Lines for every (strategy, result) of the same stock and candles. None when there is nothing to draw."""
    if not runs:
        return None
    first = runs[0][1]
    series = []
    for index, (strategy, result) in enumerate(runs):
        equity, _ = equity_curves(result)
        series.append(BacktestSeries(strategy.name, strategy_color(index), equity, result.metrics['end_capital'],
                                     result.metrics['return_pct']))
    _, hold = equity_curves(first)
    capital = first.metrics['start_capital']
    series.append(BacktestSeries(f'Buy & hold ({money(capital)} start)', theme.HOLD_COLOR, hold,
                                 float(first.buy_hold.iloc[-1]), first.metrics['buy_hold_return_pct'], is_hold=True))

    capitals = {result.metrics['start_capital'] for _, result in runs}
    note = ''
    if len(capitals) > 1:
        note = 'These strategies start with different cash: compare the % returns, not the dollar lines.'

    legend: Line = []
    for entry in series:
        if legend:
            legend.append(plain('   ·   '))
        legend.extend(_legend_entry(entry))
    return BacktestChart(first.dates, first.start, series, legend, note)

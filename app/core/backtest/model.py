"""The Backtest chart as data: each selected strategy's account value over time, against buy & hold."""
from dataclasses import dataclass, field

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
    start_value: float = 0.0  # the cash it started with
    summary: Line = field(default_factory=list)  # the whole-range figures, shown when hovering its line


@dataclass(frozen=True)
class BacktestChart:
    dates: pd.DatetimeIndex
    start: pd.Timestamp
    series: list[BacktestSeries]  # the strategies in selection order, then buy & hold last
    legend: Line  # one entry per line: name, final value, return
    note: str  # e.g. a warning that the strategies did not start with the same cash, else ''


def strategy_color(index: int) -> str:
    return theme.STRATEGY_COLORS[index % len(theme.STRATEGY_COLORS)]


def _strategy_summary(result: BacktestResult) -> Line:
    """Return, comparison with holding, trades, win rate and drawdown: what the single-strategy panel's cards say."""
    m = result.metrics
    versus = m['return_pct'] - m['buy_hold_return_pct']
    win_rate = '—' if m['win_rate_pct'] is None else f'{m["win_rate_pct"]:.0f}%'
    return [plain('Whole range: '), Span(f'{m["return_pct"]:+.2f}%', theme.change_color(m['return_pct'])),
            plain(' ('), Span(f'{versus:+.1f} pts', theme.change_color(versus)), plain(' vs buy & hold)\n'),
            plain(f'Trades {m["trades"]} ({m["wins"]} won, {m["losses"]} lost, win rate {win_rate})\n'),
            plain(f'Max drawdown {m["max_drawdown_pct"]:.1f}% · in market {m["time_in_market_pct"]:.0f}%')]


def _hold_summary(result: BacktestResult) -> Line:
    m = result.metrics
    hold = m['buy_hold_return_pct']
    return [plain('Whole range: '), Span(f'{hold:+.2f}%', theme.change_color(hold)),
            plain(f'\nMax drawdown {m["buy_hold_max_drawdown_pct"]:.1f}%')]


def hover_line(chart: BacktestChart, index: int, slot: int) -> Line | None:
    """What to show when the mouse is over line `index` at candle `slot`: its name, the date, the account value and
    return so far, then its whole-range figures. None where the line has not started (before the range)."""
    series = chart.series[index]
    if not 0 <= slot < len(series.values) or np.isnan(series.values[slot]):
        return None
    value = float(series.values[slot])
    so_far = (value / series.start_value - 1) * 100 if series.start_value else 0.0
    return [Span(series.label, series.color, bold=True), plain(f'\n{chart.dates[slot]:%b %d, %Y}  '),
            plain(f'{money(value)} '), Span(f'({so_far:+.2f}% so far)', theme.change_color(so_far)), plain('\n'),
            *series.summary]


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
                                     result.metrics['return_pct'], start_value=result.metrics['start_capital'],
                                     summary=_strategy_summary(result)))
    _, hold = equity_curves(first)
    capital = first.metrics['start_capital']
    series.append(BacktestSeries(f'Buy & hold ({money(capital)} start)', theme.HOLD_COLOR, hold,
                                 float(first.buy_hold.iloc[-1]), first.metrics['buy_hold_return_pct'], is_hold=True,
                                 start_value=capital, summary=_hold_summary(first)))

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

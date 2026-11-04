"""Where a backtest's trades are drawn on a chart, as plain geometry: the renderer only has to paint it.

On price charts (Price, Candles, SMA):
  ▲ green BUY below the signal candle, ▼ red SELL above it, a dot where each order filled,
  the entry price as a line from entry to exit, a dashed line from entry to exit price,
  green (profit) or red (loss) shading over the trade, and the stop / target levels.
On indicator charts: green / red vertical lines at the signals and the same shading.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core import theme
from strategy.backtest import BacktestResult

OPEN_COLOR = '#2962ff'  # a trade still open at the end of the backtest
MARKER_GAP = 0.015  # markers sit this fraction of the price below the low / above the high
SHADE_ALPHA = 28
LEVEL_ALPHA = 160
SIGNAL_ALPHA = 170

SOLID, DASH, DOT = 'solid', 'dash', 'dot'


@dataclass(frozen=True)
class Region:
    """Vertical band over a trade (slots start..end)."""
    start: float
    end: float
    color: str
    alpha: int


@dataclass(frozen=True)
class Segment:
    """A straight line between two points (slot, price)."""
    x: tuple[float, float]
    y: tuple[float, float]
    color: str
    width: int
    style: str
    alpha: int | None = None


@dataclass(frozen=True)
class VerticalLine:
    slot: int
    color: str
    alpha: int


@dataclass
class TradeMarks:
    regions: list[Region] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    vlines: list[VerticalLine] = field(default_factory=list)
    buys: tuple[list[int], np.ndarray] = field(default_factory=lambda: ([], np.array([])))  # slots, marker prices
    sells: tuple[list[int], np.ndarray] = field(default_factory=lambda: ([], np.array([])))
    fills: tuple[np.ndarray, np.ndarray] = field(default_factory=lambda: (np.array([]), np.array([])))


def trade_color(trade) -> str:
    if trade.is_open:
        return OPEN_COLOR
    return theme.UP if trade.pnl > 0 else theme.DOWN


def trade_marks(result: BacktestResult, candles: pd.DataFrame, on_price_chart: bool) -> TradeMarks:
    marks = TradeMarks()
    for trade in result.trades:
        color = trade_color(trade)
        marks.regions.append(Region(trade.entry_slot - 0.5, trade.exit_slot + 0.5, color, SHADE_ALPHA))
        if on_price_chart:
            _price_marks(marks, trade, color)
        else:
            _signal_lines(marks, trade)
    if on_price_chart:
        _markers(marks, result, candles)
    return marks


def _price_marks(marks: TradeMarks, trade, color: str) -> None:
    span = (trade.entry_slot, trade.exit_slot)
    marks.segments.append(Segment(span, (trade.entry_price, trade.entry_price), color, 2, SOLID))
    marks.segments.append(Segment(span, (trade.entry_price, trade.exit_price), color, 1, DASH))
    for level, level_color in ((trade.stop_price, theme.DOWN), (trade.target_price, theme.UP)):
        if level is not None:
            marks.segments.append(Segment(span, (level, level), level_color, 1, DOT, LEVEL_ALPHA))


def _signal_lines(marks: TradeMarks, trade) -> None:
    marks.vlines.append(VerticalLine(trade.signal_slot, theme.UP, SIGNAL_ALPHA))
    if trade.exit_signal_slot is not None:
        marks.vlines.append(VerticalLine(trade.exit_signal_slot, theme.DOWN, SIGNAL_ALPHA))


def _markers(marks: TradeMarks, result: BacktestResult, candles: pd.DataFrame) -> None:
    lows, highs = candles['low'].to_numpy(), candles['high'].to_numpy()
    buys = [t.signal_slot for t in result.trades]
    sells = [t.exit_signal_slot for t in result.trades if t.exit_signal_slot is not None]
    marks.buys = (buys, lows[buys] * (1 - MARKER_GAP))
    marks.sells = (sells, highs[sells] * (1 + MARKER_GAP))
    fills = [(t.entry_slot, t.entry_price) for t in result.trades] + \
            [(t.exit_slot, t.exit_price) for t in result.trades if not t.is_open]
    if fills:
        x, y = np.array(fills).T
        marks.fills = (x, y)

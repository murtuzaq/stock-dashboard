"""Draws a backtest's trades on any chart, so every stacked chart shows the same trades in the same places.

On price charts (Price, Candles, SMA):
  ▲ green BUY below the signal candle, ▼ red SELL above it, a dot where each order filled,
  the entry price as a line from entry to exit, a dashed line from entry to exit price,
  green (profit) or red (loss) shading over the trade, and the stop / target levels.
On indicator charts: green / red vertical lines at the signals and the same shading.
Nothing here affects auto-scaling, so overlays never change a chart's zoom.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt

from chart_view import DOWN, UP, TimePlot

OPEN_COLOR = '#2962ff'  # a trade still open at the end of the backtest
MARKER_GAP = 0.015  # markers sit this fraction of the price below the low / above the high


def _with_alpha(color: str, alpha: int):
    qcolor = pg.mkColor(color)
    qcolor.setAlpha(alpha)
    return qcolor


class TradeOverlay:
    def __init__(self, plot: TimePlot, on_price_chart: bool) -> None:
        self.plot = plot
        self.on_price_chart = on_price_chart
        self.items: list = []

    def clear(self) -> None:
        for item in self.items:
            self.plot.removeItem(item)
        self.items = []

    def _add(self, item, z: float = 5) -> None:
        item.setZValue(z)
        self.plot.addItem(item, ignoreBounds=True)
        self.items.append(item)

    def show(self, result, candles) -> None:
        """Draw `result`'s trades (BacktestResult) over the chart's candles."""
        self.clear()
        if result is None:
            return
        for trade in result.trades:
            color = OPEN_COLOR if trade.is_open else UP if trade.pnl > 0 else DOWN
            self._add(pg.LinearRegionItem((trade.entry_slot - 0.5, trade.exit_slot + 0.5), movable=False,
                                          brush=pg.mkBrush(_with_alpha(color, 28)), pen=pg.mkPen(None)), z=-10)
            if self.on_price_chart:
                self._draw_price_marks(trade, color)
            else:
                self._draw_signal_lines(trade)
        if self.on_price_chart:
            self._draw_markers(result, candles)

    def _draw_price_marks(self, trade, color: str) -> None:
        span = [trade.entry_slot, trade.exit_slot]
        self._add(pg.PlotCurveItem(span, [trade.entry_price] * 2, pen=pg.mkPen(color, width=2)))
        self._add(pg.PlotCurveItem(span, [trade.entry_price, trade.exit_price],
                                   pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)))
        for level, level_color in ((trade.stop_price, DOWN), (trade.target_price, UP)):
            if level is not None:
                self._add(pg.PlotCurveItem(span, [level] * 2,
                                           pen=pg.mkPen(_with_alpha(level_color, 160), width=1,
                                                        style=Qt.PenStyle.DotLine)))

    def _draw_signal_lines(self, trade) -> None:
        self._add(pg.InfiniteLine(trade.signal_slot, angle=90,
                                  pen=pg.mkPen(_with_alpha(UP, 170), style=Qt.PenStyle.DashLine)))
        if trade.exit_signal_slot is not None:
            self._add(pg.InfiniteLine(trade.exit_signal_slot, angle=90,
                                      pen=pg.mkPen(_with_alpha(DOWN, 170), style=Qt.PenStyle.DashLine)))

    def _draw_markers(self, result, candles) -> None:
        lows, highs = candles['low'].to_numpy(), candles['high'].to_numpy()
        buys = [t.signal_slot for t in result.trades]
        sells = [t.exit_signal_slot for t in result.trades if t.exit_signal_slot is not None]
        if buys:
            self._add(pg.ScatterPlotItem(buys, lows[buys] * (1 - MARKER_GAP), symbol='t1', size=13,
                                         brush=pg.mkBrush(UP), pen=pg.mkPen(None)), z=20)
        if sells:
            self._add(pg.ScatterPlotItem(sells, highs[sells] * (1 + MARKER_GAP), symbol='t', size=13,
                                         brush=pg.mkBrush(DOWN), pen=pg.mkPen(None)), z=20)
        fills = [(t.entry_slot, t.entry_price) for t in result.trades] + \
                [(t.exit_slot, t.exit_price) for t in result.trades if not t.is_open]
        if fills:
            x, y = np.array(fills).T
            self._add(pg.ScatterPlotItem(x, y, symbol='o', size=6, brush=pg.mkBrush('#d1d4dc'),
                                         pen=pg.mkPen('#131722')), z=20)

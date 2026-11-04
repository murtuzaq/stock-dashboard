"""Draws a backtest's trades on any chart, so every stacked chart shows the same trades in the same places.

What to draw and where (the geometry) comes from core.dashboard.trade_marks; this only paints it with pyqtgraph.
Nothing here affects auto-scaling, so overlays never change a chart's zoom.
"""
import pyqtgraph as pg
from PySide6.QtCore import Qt

from core.dashboard import trade_marks as marks_module
from core.common.theme import BACKGROUND, DOWN, GRID_TEXT, UP
from core.dashboard.trade_marks import trade_marks
from qtrender.dashboard.chart_view import TimePlot

PEN_STYLES = {marks_module.SOLID: Qt.PenStyle.SolidLine, marks_module.DASH: Qt.PenStyle.DashLine,
              marks_module.DOT: Qt.PenStyle.DotLine}
SHADE_Z, LINE_Z, MARKER_Z = -10, 5, 20


def _color(color: str, alpha: int | None):
    qcolor = pg.mkColor(color)
    if alpha is not None:
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

    def _add(self, item, z: float = LINE_Z) -> None:
        item.setZValue(z)
        self.plot.addItem(item, ignoreBounds=True)
        self.items.append(item)

    def show(self, result, candles) -> None:
        """Draw `result`'s trades (BacktestResult) over the chart's candles."""
        self.clear()
        if result is None:
            return
        marks = trade_marks(result, candles, self.on_price_chart)
        for region in marks.regions:
            self._add(pg.LinearRegionItem((region.start, region.end), movable=False,
                                          brush=pg.mkBrush(_color(region.color, region.alpha)),
                                          pen=pg.mkPen(None)), SHADE_Z)
        for segment in marks.segments:
            pen = pg.mkPen(_color(segment.color, segment.alpha), width=segment.width,
                           style=PEN_STYLES[segment.style])
            self._add(pg.PlotCurveItem(list(segment.x), list(segment.y), pen=pen))
        for line in marks.vlines:
            self._add(pg.InfiniteLine(line.slot, angle=90,
                                      pen=pg.mkPen(_color(line.color, line.alpha), style=Qt.PenStyle.DashLine)))
        self._draw_markers(marks)

    def _draw_markers(self, marks) -> None:
        buy_slots, buy_prices = marks.buys
        sell_slots, sell_prices = marks.sells
        if len(buy_slots):
            self._add(pg.ScatterPlotItem(buy_slots, buy_prices, symbol='t1', size=13, brush=pg.mkBrush(UP),
                                         pen=pg.mkPen(None)), MARKER_Z)
        if len(sell_slots):
            self._add(pg.ScatterPlotItem(sell_slots, sell_prices, symbol='t', size=13, brush=pg.mkBrush(DOWN),
                                         pen=pg.mkPen(None)), MARKER_Z)
        fill_x, fill_y = marks.fills
        if len(fill_x):
            self._add(pg.ScatterPlotItem(fill_x, fill_y, symbol='o', size=6, brush=pg.mkBrush(GRID_TEXT),
                                         pen=pg.mkPen(BACKGROUND)), MARKER_Z)

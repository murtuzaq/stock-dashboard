"""Backtest view: the account value of the selected strategies over time, against buy & hold, on one chart.

Shown when two or more strategies are selected. A colour legend names the lines; hover over a line to see that
strategy's date, value and figures.
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QPointF, Qt

from core.backtest.model import BacktestChart, hover_line
from core.common.formatting import Span, plain
from core.common.theme import BACKGROUND, GRID_TEXT, MUTED
from qtrender.dashboard.chart_view import PanelView, TimePlot
from qtrender.richtext import line_html

HINT = 'Ctrl+click two or more strategies under Strategies to compare how much each would have grown.'
NEAR_PIXELS = 14  # how close the mouse must be to a line to pick it
LINE_WIDTH, HOLD_WIDTH, HOVER_EXTRA = 2, 1.5, 2


class BacktestPlot(TimePlot):
    """One line per strategy, in dollars. Shares the time axis with the other charts."""

    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.chart: BacktestChart | None = None
        self.lines: list[pg.PlotDataItem] = []
        self.hovered: int | None = None  # index of the line the mouse is on

        self.hover_dot = pg.ScatterPlotItem(size=10, pen=pg.mkPen(BACKGROUND, width=2))
        self.hover_text = pg.TextItem(color=GRID_TEXT, fill=pg.mkBrush('#1e222d'), border=pg.mkPen(MUTED))
        for item in (self.hover_dot, self.hover_text):
            self.addItem(item, ignoreBounds=True)
        self._hide_hover()
        self.mouse_proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)

    def show_chart(self, chart: BacktestChart | None) -> None:
        self._hide_hover()
        for line in self.lines:
            self.removeItem(line)
        self.lines = []
        self.chart = chart
        if chart is None:
            return
        self.set_dates(chart.dates)
        slots = np.arange(len(chart.dates))
        for series in chart.series:
            style = Qt.PenStyle.DashLine if series.is_hold else Qt.PenStyle.SolidLine
            line = self.plot(slots, series.values, pen=pg.mkPen(series.color, width=self._width(series.is_hold),
                                                                style=style), connect='finite')
            self.lines.append(line)
        self.set_range(chart.start)

    @staticmethod
    def _width(is_hold: bool, thick: bool = False) -> float:
        return (HOLD_WIDTH if is_hold else LINE_WIDTH) + (HOVER_EXTRA if thick else 0)

    # --- hover ---

    def nearest_line(self, scene_position: QPointF) -> tuple[int, int] | None:
        """(line index, candle slot) of the line closest to the mouse, if one is within NEAR_PIXELS."""
        if self.chart is None:
            return None
        view_box = self.getViewBox()
        slot = int(round(view_box.mapSceneToView(scene_position).x()))
        best: tuple[float, int] | None = None
        for index, series in enumerate(self.chart.series):
            if not 0 <= slot < len(series.values) or np.isnan(series.values[slot]):
                continue
            line_y = view_box.mapViewToScene(QPointF(slot, series.values[slot])).y()
            distance = abs(line_y - scene_position.y())
            if distance <= NEAR_PIXELS and (best is None or distance < best[0]):
                best = (distance, index)
        return None if best is None else (best[1], slot)

    def _on_mouse_moved(self, event) -> None:
        position = event[0]
        view_box = self.getViewBox()
        if self.chart is None or not view_box.sceneBoundingRect().contains(position):
            self._hide_hover()
            return
        found = self.nearest_line(position)
        if found is None:
            self._hide_hover()
            return
        self.show_hover(*found)

    def show_hover(self, index: int, slot: int) -> None:
        """Thicken line `index`, put a dot on it at `slot` and show its details beside the dot."""
        line = hover_line(self.chart, index, slot)
        if line is None:
            self._hide_hover()
            return
        self._set_hovered(index)
        series = self.chart.series[index]
        value = float(series.values[slot])
        (x_low, x_high), (y_low, y_high) = self.getViewBox().viewRange()
        self.hover_dot.setData([slot], [value], brush=pg.mkBrush(series.color))
        self.hover_text.setHtml(line_html(line))
        self.hover_text.setAnchor((0 if slot < (x_low + x_high) / 2 else 1, 0 if value > (y_low + y_high) / 2 else 1))
        self.hover_text.setPos(slot, value)
        self.hover_dot.show()
        self.hover_text.show()

    def _set_hovered(self, index: int | None) -> None:
        if index == self.hovered or self.chart is None:
            return
        for position, series in enumerate(self.chart.series):
            if position == self.hovered or position == index:
                line = self.lines[position]
                line.setPen(pg.mkPen(series.color, width=self._width(series.is_hold, thick=position == index),
                                     style=Qt.PenStyle.DashLine if series.is_hold else Qt.PenStyle.SolidLine))
        self.hovered = index

    def _hide_hover(self) -> None:
        self._set_hovered(None)
        self.hover_dot.hide()
        self.hover_text.hide()

    def leaveEvent(self, event) -> None:
        self._hide_hover()
        super().leaveEvent(event)


class BacktestView(PanelView):
    def __init__(self) -> None:
        super().__init__(BacktestPlot(), 'Account value over time for each selected strategy, starting from its '
                                         'starting cash, against simply buying and holding. Hover over a line for '
                                         'that strategy\'s details. The higher line grew your money more.')
        self.set_legend([Span(HINT, MUTED)])

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        pass  # results arrive through show_chart()

    def show_chart(self, chart: BacktestChart | None) -> None:
        self.plot_widget.show_chart(chart)
        if chart is None:
            self.set_legend([Span(HINT, MUTED)])
            return
        legend = list(chart.legend)
        if chart.note:
            legend += [plain('\n'), Span(chart.note, MUTED)]
        self.set_legend(legend)

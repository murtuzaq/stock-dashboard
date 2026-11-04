"""Price view: closing prices as an area chart, green or red by the change over the selected range."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient

from core.panels import PriceModel, price_model
from core.theme import BACKGROUND, GRID_TEXT, MUTED, UP
from qtrender.chart_view import TimePlot


class PriceView(TimePlot):
    """One point per candle: the closing price. On daily candles this is the familiar Google Finance chart."""

    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=False, y=True, alpha=0.15)
        view_box = self.getViewBox()
        view_box.setAutoVisible(y=True)
        view_box.enableAutoRange(axis='y')

        self.model: PriceModel | None = None
        self.color = UP

        # The shaded area is a separate curve that is left out of auto-ranging, so it can always
        # reach the bottom of the view without stretching the price axis down to it.
        self.fill = pg.PlotCurveItem(pen=pg.mkPen(None))
        self.addItem(self.fill, ignoreBounds=True)
        self.line = pg.PlotDataItem()
        self.line.setDownsampling(auto=True, method='peak')
        self.line.setClipToView(True)
        self.addItem(self.line)
        view_box.sigYRangeChanged.connect(lambda _, y_range: self._fit_fill(*y_range))

        # Crosshair: a dashed line, a dot on the price, and the date and close at the top.
        self.cursor_line = pg.InfiniteLine(angle=90, pen=pg.mkPen(MUTED, style=Qt.PenStyle.DashLine))
        self.cursor_dot = pg.ScatterPlotItem(size=9, pen=pg.mkPen(BACKGROUND, width=2))
        self.cursor_text = pg.TextItem(color=GRID_TEXT, fill=pg.mkBrush('#1e222d'))
        for item in (self.cursor_line, self.cursor_dot, self.cursor_text):
            self.addItem(item, ignoreBounds=True)
        self._hide_cursor()
        self.mouse_proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        self.model = price_model(daily, candles)
        self.set_dates(self.model.dates)
        slots = np.arange(len(self.model.closes))
        self.line.setData(slots, self.model.closes)
        self.fill.setData(slots, self.model.closes)

    def set_range(self, start: pd.Timestamp) -> None:
        self._hide_cursor()
        self.color = self.model.color(start)
        self.line.setPen(pg.mkPen(self.color, width=2))
        super().set_range(start)
        self._fit_fill(*self.getViewBox().viewRange()[1])

    def _fit_fill(self, y_bottom: float, y_top: float) -> None:
        """Shade from the line down to the bottom of the view, fading out towards the bottom."""
        self.fill.setFillLevel(y_bottom)
        gradient = QLinearGradient(0, y_bottom, 0, y_top)  # in price units, so it spans the visible chart
        faded, strong = QColor(self.color), QColor(self.color)
        faded.setAlpha(0)
        strong.setAlpha(70)
        gradient.setColorAt(0, faded)
        gradient.setColorAt(1, strong)
        self.fill.setBrush(QBrush(gradient))

    def _on_mouse_moved(self, event) -> None:
        position = event[0]
        view_box = self.getViewBox()
        if self.model is None or not len(self.model.closes) or not view_box.sceneBoundingRect().contains(position):
            self._hide_cursor()
            return
        slot = int(round(view_box.mapSceneToView(position).x()))
        if not 0 <= slot < len(self.model.closes):
            self._hide_cursor()
            return
        (x_low, x_high), (_, y_high) = view_box.viewRange()
        self.cursor_line.setPos(slot)
        self.cursor_dot.setData([slot], [self.model.closes[slot]], brush=pg.mkBrush(self.color))
        self.cursor_text.setText(self.model.cursor_text(slot))
        self.cursor_text.setAnchor((0, 0) if slot < (x_low + x_high) / 2 else (1, 0))
        self.cursor_text.setPos(slot, y_high)
        for item in (self.cursor_line, self.cursor_dot, self.cursor_text):
            item.show()

    def _hide_cursor(self) -> None:
        for item in (self.cursor_line, self.cursor_dot, self.cursor_text):
            item.hide()

    def leaveEvent(self, event) -> None:
        self._hide_cursor()
        super().leaveEvent(event)

"""Candles view: a candlestick chart drawn with pyqtgraph, plus the building blocks every chart shares."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPicture
from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.common.formatting import Line
from core.common.theme import BACKGROUND, DOWN, GRID_TEXT, UP
from core.dashboard.time_axis import tick_labels
from qtrender.learn.info_label import InfoLabel

CANDLE_WIDTH = 0.7  # fraction of the space between candles


class TradingDayAxis(pg.AxisItem):
    """Time axis for candles placed one per slot (0, 1, 2, ...), labelled with each candle's date.

    Which dates get labels is decided by core.dashboard.time_axis.tick_labels; this only hands them to pyqtgraph.
    """

    def __init__(self) -> None:
        super().__init__(orientation='bottom')
        self.dates = pd.DatetimeIndex([])
        self.labels: dict[int, str] = {}

    def tickValues(self, min_value, max_value, size):
        labels = tick_labels(self.dates, min_value, max_value, size)
        if not labels:
            return []
        self.labels = labels
        return [(1, list(labels))]

    def tickStrings(self, values, scale, spacing):
        return [self.labels.get(int(round(value)), '') for value in values]


class CandlestickItem(pg.GraphicsObject):
    """Draws candles from a DataFrame with open/high/low/close columns. Candle i is drawn at x = i."""

    def __init__(self) -> None:
        super().__init__()
        self.picture = QPicture()
        self.lows = self.highs = np.array([])

    def set_data(self, candles: pd.DataFrame) -> None:
        self.lows, self.highs = candles['low'].to_numpy(), candles['high'].to_numpy()

        self.picture = QPicture()
        painter = QPainter(self.picture)
        for slot, (open_, high, low, close) in enumerate(zip(candles['open'], self.highs, self.lows, candles['close'])):
            color = pg.mkColor(UP if close >= open_ else DOWN)
            painter.setPen(pg.mkPen(color))
            painter.drawLine(QPointF(slot, low), QPointF(slot, high))
            painter.setBrush(pg.mkBrush(color))
            painter.drawRect(QRectF(slot - CANDLE_WIDTH / 2, open_, CANDLE_WIDTH, close - open_))
        painter.end()
        self.prepareGeometryChange()
        self.informViewBoundsChanged()
        self.update()

    def dataBounds(self, axis, frac=1.0, orthoRange=None):
        """Lets the price axis fit only the candles currently in view."""
        count = len(self.lows)
        if not count:
            return None, None
        if axis == 0:
            return -1, count
        slots = np.arange(count)
        visible = np.ones(count, bool) if orthoRange is None else \
            (slots >= orthoRange[0]) & (slots <= orthoRange[1])
        if not visible.any():
            return None, None
        return self.lows[visible].min(), self.highs[visible].max()

    def paint(self, painter, *args) -> None:
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self) -> QRectF:
        return QRectF(self.picture.boundingRect())


class VisibleBars(pg.BarGraphItem):
    """Bars (one per slot) whose value range covers only the bars in view, so zooming rescales the axis."""

    def dataBounds(self, ax, frac=1.0, orthoRange=None):
        heights = self.opts.get('height')
        if ax == 0 or heights is None or not len(heights):
            return super().dataBounds(ax, frac, orthoRange)
        slots = np.arange(len(heights))
        visible = np.ones(len(heights), bool) if orthoRange is None else \
            (slots >= orthoRange[0]) & (slots <= orthoRange[1])
        shown = heights[visible]
        shown = shown[np.isfinite(shown)]
        return (min(0.0, float(shown.min())), max(0.0, float(shown.max()))) if len(shown) else (None, None)


def value_axis_width() -> int:
    """Room for the labels on the right-hand axis, sized from the font so display scaling can't cut them off."""
    return QFontMetrics(QFont()).horizontalAdvance('00000.00') + 16


class TimePlot(pg.PlotWidget):
    """Base for every chart: one slot per candle, values on the right, dates below, drag/scroll through time.

    All charts share this layout so they line up exactly when stacked.
    """

    def __init__(self, value_axis: pg.AxisItem | None = None) -> None:
        self.time_axis = TradingDayAxis()
        axes = {'bottom': self.time_axis} | ({'right': value_axis} if value_axis else {})
        super().__init__(axisItems=axes, background=BACKGROUND)
        self.hideButtons()  # pyqtgraph's small auto-zoom "A" button
        self.hideAxis('left')
        self.showAxis('right')  # values on the right, like trading platforms
        for axis in ('right', 'bottom'):
            self.getAxis(axis).setTextPen(GRID_TEXT)
        self.getAxis('right').setWidth(value_axis_width())
        self.setMouseEnabled(x=True, y=False)

    def set_dates(self, dates: pd.DatetimeIndex) -> None:
        self.time_axis.dates = dates

    def show_dates(self, visible: bool) -> None:
        """When charts are stacked, only the bottom one shows the dates."""
        self.showAxis('bottom', visible)

    def set_range(self, start: pd.Timestamp) -> None:
        dates = self.time_axis.dates
        first_slot = int(dates.searchsorted(start))
        self.setXRange(first_slot - 0.5, len(dates) - 0.5, padding=0)


class CandleChart(TimePlot):
    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=True, y=True, alpha=0.15)
        # The price axis always fits the candles in view.
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.candle_item = CandlestickItem()
        self.addItem(self.candle_item)

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        self.set_dates(candles.index)
        self.candle_item.set_data(candles)


class PanelView(QWidget):
    """An indicator chart with a one-line legend above it. Subclasses fill in set_data()."""

    def __init__(self, plot: TimePlot, tooltip: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.legend = InfoLabel('indicator legend')
        self.legend.setObjectName('indicatorLegend')
        self.legend.setToolTip(tooltip)
        layout.addWidget(self.legend)
        self.plot_widget = plot
        layout.addWidget(plot)

    def set_legend(self, line: Line) -> None:
        self.legend.set_line(line)

    def set_range(self, start: pd.Timestamp) -> None:
        self.plot_widget.set_range(start)

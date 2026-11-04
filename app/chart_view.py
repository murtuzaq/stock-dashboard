"""Candles view: a candlestick chart drawn with pyqtgraph, plus the building blocks every chart shares."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPicture
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

BACKGROUND = '#131722'
GRID_TEXT = '#d1d4dc'
UP = '#26a69a'
DOWN = '#ef5350'

CANDLE_WIDTH = 0.7  # fraction of the space between candles


def short_number(value: float) -> str:
    """5_583_900 -> '5.58M'."""
    for limit, suffix in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if abs(value) >= limit:
            return f'{value / limit:.3g}{suffix}'
    return f'{value:.0f}'


class TradingDayAxis(pg.AxisItem):
    """Time axis for candles placed one per slot (0, 1, 2, ...), labelled with each candle's date.

    Like trading platforms, this skips weekends and holidays instead of leaving gaps for them, and puts
    labels where a new year, month or week starts (so a label never repeats).
    """

    PIXELS_PER_LABEL = 90
    YEAR = staticmethod(lambda d: d.year)
    MONTH = staticmethod(lambda d: d.year * 12 + d.month)
    WEEK = staticmethod(lambda d: (d - pd.to_timedelta(d.dayofweek, unit='D')).normalize().asi8)
    DAY = staticmethod(lambda d: d.normalize().asi8)
    # Coarsest to finest: (group dates by, label format, marker group, label format when the marker changes).
    # E.g. month labels read "Oct", "Nov", but "2026" where a new year begins.
    LEVELS = [
        (YEAR, '%Y', None, '%Y'),
        (MONTH, '%b', YEAR, '%Y'),
        (WEEK, '%d', MONTH, '%b'),
        (DAY, '%d', MONTH, '%b'),
    ]

    def __init__(self) -> None:
        super().__init__(orientation='bottom')
        self.dates = pd.DatetimeIndex([])
        self.labels: dict[int, str] = {}

    def tickValues(self, min_value, max_value, size):
        first, last = max(int(np.ceil(min_value)), 0), min(int(max_value), len(self.dates) - 1)
        if last <= first:
            return []
        max_labels = max(2, int(size / self.PIXELS_PER_LABEL))
        shown = self.dates[first:last + 1]
        # Use the finest unit (day, week, month, year) that needs at most every other start labelled.
        level, starts = 0, self._group_starts(shown, self.LEVELS[0][0])
        for candidate in range(len(self.LEVELS) - 1, -1, -1):
            candidate_starts = self._group_starts(shown, self.LEVELS[candidate][0])
            if len(candidate_starts) <= 2 * max_labels:
                level, starts = candidate, candidate_starts
                break
        starts = starts[::int(np.ceil(len(starts) / max_labels)) or 1]

        _, plain_format, marker, marker_format = self.LEVELS[level]
        marker_keys = np.asarray(marker(shown)) if marker else None
        self.labels = {}
        previous = None
        for i in starts:
            # Marker label if the year (or month) changed since the previous label, or at this very date.
            reference = previous if previous is not None else i - 1
            marked = marker_keys is not None and marker_keys[i] != marker_keys[reference]
            self.labels[first + i] = f'{shown[i]:{marker_format if marked else plain_format}}'
            previous = i
        return [(1, list(self.labels))]

    @staticmethod
    def _group_starts(dates: pd.DatetimeIndex, group) -> list[int]:
        """Positions where a new year/month/week/day begins (vectorised: fast even for 60 years of days)."""
        keys = np.asarray(group(dates))
        return (np.flatnonzero(keys[1:] != keys[:-1]) + 1).tolist()

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
        self.legend = QLabel()
        self.legend.setObjectName('indicatorLegend')
        self.legend.setToolTip(tooltip)
        layout.addWidget(self.legend)
        self.plot_widget = plot
        layout.addWidget(plot)

    def set_range(self, start: pd.Timestamp) -> None:
        self.plot_widget.set_range(start)

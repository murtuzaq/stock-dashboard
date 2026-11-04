"""SMA view: the 50, 150 and 200-day simple moving averages, the classic long-term trend lines.

Shown alone, they are drawn over a faint closing-price line. Selected together with Price or Candles,
they are drawn on top of that chart instead (an overlay), which is how traders normally read them.
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg

from chart_view import GRID_TEXT, TimePlot
from indicators import sma
from prices import CANDLE_DAYS

SMA_DAYS = (50, 150, 200)
SMA_COLORS = ('#2962ff', '#f7c948', '#e040fb')


def sma_length(days: int, candle_size: str) -> int:
    """A length in trading days expressed in candles, e.g. 50 days on weekly candles = 10 candles."""
    return max(1, round(days / CANDLE_DAYS[candle_size]))


class SmaLines:
    """The three moving-average lines and their legend, drawn on any chart."""

    def __init__(self, plot: TimePlot) -> None:
        self.lines = [plot.plot(pen=pg.mkPen(color, width=1.5), connect='finite') for color in SMA_COLORS]
        self.legend = pg.LegendItem(offset=(10, 6), labelTextColor=GRID_TEXT, brush=pg.mkBrush(19, 23, 34, 200),
                                     colCount=len(SMA_DAYS))  # one row, to cover as little of the chart as possible
        self.legend.setParentItem(plot.getPlotItem())

    def set_data(self, candles: pd.DataFrame) -> None:
        candle_size = candles.attrs.get('candle_size', '1D')
        slots = np.arange(len(candles))
        self.legend.clear()
        for line, days in zip(self.lines, SMA_DAYS):
            length = sma_length(days, candle_size)
            line.setData(slots, sma(candles['close'], length).to_numpy())
            note = '' if candle_size == '1D' else f' ({length} × {candle_size} candles)'
            self.legend.addItem(line, f'SMA {days}d{note}')

    def set_visible(self, visible: bool) -> None:
        # Hidden lines are left out of auto-ranging, so they don't stretch the price axis.
        for line in self.lines:
            line.setVisible(visible)
        self.legend.setVisible(visible)


class SmaView(TimePlot):
    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=True, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.setToolTip('Price above a rising average = uptrend. Below a falling one = downtrend.\n'
                        'Many swing traders only buy when price > 50 > 150 > 200-day averages.')
        self.close_line = self.plot(pen=pg.mkPen('#787b86', width=1))
        self.lines = SmaLines(self)

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        self.set_dates(candles.index)
        self.close_line.setData(np.arange(len(candles)), candles['close'].to_numpy())
        self.lines.set_data(candles)

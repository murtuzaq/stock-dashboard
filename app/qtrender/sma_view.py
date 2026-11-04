"""SMA view: the 50, 150 and 200-day simple moving averages, the classic long-term trend lines.

Shown alone, they are drawn over a faint closing-price line. Selected together with Price or Candles,
they are drawn on top of that chart instead (an overlay), which is how traders normally read them.
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg

from core.panels import SMA_DAYS, sma_model
from core.theme import GRID_TEXT, MUTED, SMA_COLORS
from qtrender.chart_view import TimePlot


class SmaLines:
    """The three moving-average lines and their legend, drawn on any chart."""

    def __init__(self, plot: TimePlot) -> None:
        self.lines = [plot.plot(pen=pg.mkPen(color, width=1.5), connect='finite') for color in SMA_COLORS]
        self.legend = pg.LegendItem(offset=(10, 6), labelTextColor=GRID_TEXT, brush=pg.mkBrush(19, 23, 34, 200),
                                    colCount=len(SMA_DAYS))  # one row, to cover as little of the chart as possible
        self.legend.setParentItem(plot.getPlotItem())

    def set_data(self, candles: pd.DataFrame) -> None:
        model = sma_model(candles)
        slots = np.arange(len(candles))
        self.legend.clear()
        for line, model_line in zip(self.lines, model.lines):
            line.setData(slots, model_line.values)
            self.legend.addItem(line, model_line.label)

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
        self.close_line = self.plot(pen=pg.mkPen(MUTED, width=1))
        self.lines = SmaLines(self)

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        self.set_dates(candles.index)
        self.close_line.setData(np.arange(len(candles)), candles['close'].to_numpy())
        self.lines.set_data(candles)

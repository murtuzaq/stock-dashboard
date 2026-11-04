"""MACD view: the MACD line, its signal line, and the histogram of the gap between them."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt

from core.dashboard.panels import MacdModel, macd_model
from core.common.theme import MACD_COLOR, MUTED, SIGNAL_COLOR
from qtrender.dashboard.chart_view import CANDLE_WIDTH, PanelView, TimePlot, VisibleBars


class MacdPlot(TimePlot):
    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.addItem(pg.InfiniteLine(0, angle=0, pen=pg.mkPen(MUTED, style=Qt.PenStyle.DotLine)))
        self.bars = VisibleBars(x=[], height=[], width=CANDLE_WIDTH)
        self.addItem(self.bars)
        self.macd_line = self.plot(pen=pg.mkPen(MACD_COLOR, width=1.5), connect='finite')
        self.signal_line = self.plot(pen=pg.mkPen(SIGNAL_COLOR, width=1.5), connect='finite')

    def show_model(self, model: MacdModel) -> None:
        self.set_dates(model.dates)
        slots = np.arange(len(model.histogram))
        self.bars.setOpts(x=slots, height=model.histogram, width=CANDLE_WIDTH, pen=pg.mkPen(None),
                          brushes=[pg.mkBrush(color) for color in model.bar_colors])
        self.macd_line.setData(slots, model.macd)
        self.signal_line.setData(slots, model.signal)


class MacdView(PanelView):
    def __init__(self) -> None:
        super().__init__(MacdPlot(), 'MACD line above the signal line (bars above zero): momentum is rising.\n'
                                     'Below it: momentum is falling. Crossovers are common buy/sell confirmations.')

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        model = macd_model(candles)
        self.plot_widget.show_model(model)
        self.set_legend(model.legend)

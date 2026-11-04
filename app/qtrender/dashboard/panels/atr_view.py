"""ATR view: Average True Range, the typical size of one candle's move. Used to size stops and positions."""
import numpy as np
import pandas as pd
import pyqtgraph as pg

from core.dashboard.panels import AtrModel, atr_model
from core.common.theme import ATR_COLOR
from qtrender.dashboard.chart_view import PanelView, TimePlot


class AtrPlot(TimePlot):
    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.line = self.plot(pen=pg.mkPen(ATR_COLOR, width=1.5), connect='finite')

    def show_model(self, model: AtrModel) -> None:
        self.set_dates(model.dates)
        self.line.setData(np.arange(len(model.values)), model.values)


class AtrView(PanelView):
    def __init__(self) -> None:
        super().__init__(AtrPlot(), 'How far price typically moves in one candle, in dollars.\n'
                                    'Rising ATR = more volatile. A stop-loss is often placed 1.5-2 × ATR '
                                    'away so normal swings don\'t trigger it.')

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        model = atr_model(candles)
        self.plot_widget.show_model(model)
        self.set_legend(model.legend)

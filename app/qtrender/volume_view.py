"""Volume view: shares traded per candle as bars, with a 20-candle average line.

Bars are green when the candle closed up and red when it closed down, like trading platforms.
High volume on a move suggests conviction behind it; a move on low volume is easier to reverse.
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg

from core.formatting import short_number
from core.panels import VOLUME_AVERAGE_LENGTH, VolumeModel, volume_model
from core.theme import AVERAGE_COLOR
from qtrender.chart_view import CANDLE_WIDTH, PanelView, TimePlot, VisibleBars


class VolumeAxis(pg.AxisItem):
    """Value axis that writes 5,000,000 as 5M."""

    def tickStrings(self, values, scale, spacing):
        return [short_number(value) for value in values]


class VolumePlot(TimePlot):
    def __init__(self) -> None:
        super().__init__(value_axis=VolumeAxis(orientation='right'))
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.bars = VisibleBars(x=[], height=[], width=CANDLE_WIDTH)
        self.addItem(self.bars)
        self.average = self.plot(pen=pg.mkPen(AVERAGE_COLOR, width=1.5), connect='finite')

    def show_model(self, model: VolumeModel) -> None:
        self.set_dates(model.dates)
        slots = np.arange(len(model.volume))
        self.bars.setOpts(x=slots, height=model.volume, width=CANDLE_WIDTH,
                          brushes=[pg.mkBrush(color) for color in model.bar_colors], pen=pg.mkPen(None))
        self.average.setData(slots, model.average)


class VolumeView(PanelView):
    def __init__(self) -> None:
        super().__init__(VolumePlot(), 'Shares traded per candle. Green: closed up. Red: closed down.\n'
                                       f'The yellow line is the average of the last {VOLUME_AVERAGE_LENGTH} candles; '
                                       'bars well above it show unusual interest.')

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        model = volume_model(candles)
        self.plot_widget.show_model(model)
        self.set_legend(model.legend)

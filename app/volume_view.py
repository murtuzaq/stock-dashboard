"""Volume view: shares traded per candle as bars, with a 20-candle average line.

Bars are green when the candle closed up and red when it closed down, like trading platforms.
High volume on a move suggests conviction behind it; a move on low volume is easier to reverse.
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg

from chart_view import CANDLE_WIDTH, DOWN, UP, PanelView, TimePlot, VisibleBars, short_number

AVERAGE_LENGTH = 20
AVERAGE_COLOR = '#f7c948'


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

    def set_values(self, candles: pd.DataFrame, average: pd.Series) -> None:
        self.set_dates(candles.index)
        up = (candles['close'] >= candles['open']).to_numpy()
        slots = np.arange(len(candles))
        self.bars.setOpts(x=slots, height=candles['volume'].to_numpy(dtype=float), width=CANDLE_WIDTH,
                          brushes=[pg.mkBrush(UP if rising else DOWN) for rising in up], pen=pg.mkPen(None))
        self.average.setData(slots, average.to_numpy(dtype=float))


class VolumeView(PanelView):
    def __init__(self) -> None:
        super().__init__(VolumePlot(), 'Shares traded per candle. Green: closed up. Red: closed down.\n'
                                       f'The yellow line is the average of the last {AVERAGE_LENGTH} candles; '
                                       'bars well above it show unusual interest.')

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        average = candles['volume'].rolling(AVERAGE_LENGTH).mean()
        self.plot_widget.set_values(candles, average)
        self._show_legend(candles['volume'], average)

    def _show_legend(self, volume: pd.Series, average: pd.Series) -> None:
        if volume.empty or pd.isna(average.iloc[-1]):
            self.legend.setText('Volume')
            return
        ratio = volume.iloc[-1] / average.iloc[-1]
        self.legend.setText(
            f'Volume {short_number(volume.iloc[-1])}   '
            f'<span style="color:{AVERAGE_COLOR}">avg({AVERAGE_LENGTH}) {short_number(average.iloc[-1])}</span>   '
            f'<span style="color:#787b86">{ratio:.2f}× average</span>')

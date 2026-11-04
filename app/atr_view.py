"""ATR view: Average True Range, the typical size of one candle's move. Used to size stops and positions."""
import numpy as np
import pandas as pd
import pyqtgraph as pg

from chart_view import PanelView, TimePlot
from indicators import atr

ATR_COLOR = '#e040fb'
ATR_LENGTH = 14


class AtrPlot(TimePlot):
    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.line = self.plot(pen=pg.mkPen(ATR_COLOR, width=1.5), connect='finite')

    def set_values(self, dates: pd.DatetimeIndex, values: pd.Series) -> None:
        self.set_dates(dates)
        self.line.setData(np.arange(len(values)), values.to_numpy())


class AtrView(PanelView):
    def __init__(self) -> None:
        super().__init__(AtrPlot(), 'How far price typically moves in one candle, in dollars.\n'
                                    'Rising ATR = more volatile. A stop-loss is often placed 1.5-2 × ATR '
                                    'away so normal swings don\'t trigger it.')

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        values = atr(candles['high'], candles['low'], candles['close'], ATR_LENGTH)
        self.plot_widget.set_values(candles.index, values)
        latest, close = values.iloc[-1], candles['close'].iloc[-1]
        if pd.isna(latest):
            self.legend.setText(f'ATR ({ATR_LENGTH}) · not enough history yet')
            return
        self.legend.setText(
            f'<span style="color:{ATR_COLOR}">ATR ({ATR_LENGTH}) {latest:.2f}</span>   '
            f'<span style="color:#787b86">{latest / close * 100:.1f}% of price per candle · '
            f'2 × ATR stop = {2 * latest:.2f} below entry</span>')

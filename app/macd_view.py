"""MACD view: the MACD line, its signal line, and the histogram of the gap between them."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt

from chart_view import CANDLE_WIDTH, PanelView, TimePlot, VisibleBars
from indicators import macd

MACD_COLOR = '#2962ff'
SIGNAL_COLOR = '#ff6d00'
# Histogram colours, as on TradingView: strong when the bar grows, pale when it shrinks.
ABOVE_GROWING, ABOVE_SHRINKING = '#26a69a', '#b2dfdb'
BELOW_GROWING, BELOW_SHRINKING = '#ff5252', '#ffcdd2'


def histogram_colors(histogram: np.ndarray) -> list[str]:
    previous = np.concatenate([[np.nan], histogram[:-1]])
    colors = []
    for value, before in zip(histogram, previous):
        growing = np.isnan(before) or abs(value) >= abs(before)
        if value >= 0:
            colors.append(ABOVE_GROWING if growing else ABOVE_SHRINKING)
        else:
            colors.append(BELOW_GROWING if growing else BELOW_SHRINKING)
    return colors


class MacdPlot(TimePlot):
    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.addItem(pg.InfiniteLine(0, angle=0, pen=pg.mkPen('#787b86', style=Qt.PenStyle.DotLine)))
        self.bars = VisibleBars(x=[], height=[], width=CANDLE_WIDTH)
        self.addItem(self.bars)
        self.macd_line = self.plot(pen=pg.mkPen(MACD_COLOR, width=1.5), connect='finite')
        self.signal_line = self.plot(pen=pg.mkPen(SIGNAL_COLOR, width=1.5), connect='finite')

    def set_values(self, dates: pd.DatetimeIndex, values: pd.DataFrame) -> None:
        self.set_dates(dates)
        slots = np.arange(len(values))
        histogram = values['histogram'].to_numpy()
        self.bars.setOpts(x=slots, height=histogram, width=CANDLE_WIDTH, pen=pg.mkPen(None),
                          brushes=[pg.mkBrush(color) for color in histogram_colors(histogram)])
        self.macd_line.setData(slots, values['macd'].to_numpy())
        self.signal_line.setData(slots, values['signal'].to_numpy())


class MacdView(PanelView):
    def __init__(self) -> None:
        super().__init__(MacdPlot(), 'MACD line above the signal line (bars above zero): momentum is rising.\n'
                                     'Below it: momentum is falling. Crossovers are common buy/sell confirmations.')

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        values = macd(candles['close'])
        self.plot_widget.set_values(candles.index, values)
        line, signal, histogram = values.iloc[-1]
        mood = 'MACD above signal: momentum rising' if histogram >= 0 else 'MACD below signal: momentum falling'
        self.legend.setText(
            f'MACD (12, 26, 9)   <span style="color:{MACD_COLOR}">MACD {line:.2f}</span>   '
            f'<span style="color:{SIGNAL_COLOR}">Signal {signal:.2f}</span>   Histogram {histogram:+.2f}   '
            f'<span style="color:#787b86">{mood}</span>')

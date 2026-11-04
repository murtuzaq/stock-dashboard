"""Stoch RSI view: the Stochastic RSI indicator on its own 0-100 panel."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt

from chart_view import PanelView, TimePlot
from indicators import stoch_rsi

K_COLOR = '#2962ff'
D_COLOR = '#ff6d00'
OVERBOUGHT = 80
OVERSOLD = 20


class OscillatorPlot(TimePlot):
    """A 0-100 panel with the zone between oversold and overbought shaded, like trading platforms."""

    def __init__(self) -> None:
        super().__init__()
        self.getAxis('right').setTicks([[(v, str(v)) for v in (0, OVERSOLD, 50, OVERBOUGHT, 100)]])
        self.enableAutoRange(axis='y', enable=False)
        self.setYRange(0, 100, padding=0.05)

        self.addItem(pg.LinearRegionItem((OVERSOLD, OVERBOUGHT), orientation='horizontal', movable=False,
                                         brush=pg.mkBrush(126, 87, 194, 25), pen=pg.mkPen(None)))
        for level, style in ((OVERBOUGHT, Qt.PenStyle.DashLine), (50, Qt.PenStyle.DotLine),
                             (OVERSOLD, Qt.PenStyle.DashLine)):
            self.addItem(pg.InfiniteLine(level, angle=0, pen=pg.mkPen('#787b86', style=style)))
        self.k_line = self.plot(pen=pg.mkPen(K_COLOR, width=1.5), connect='finite')
        self.d_line = self.plot(pen=pg.mkPen(D_COLOR, width=1.5), connect='finite')

    def set_values(self, dates: pd.DatetimeIndex, values: pd.DataFrame) -> None:
        self.set_dates(dates)
        slots = np.arange(len(values))
        self.k_line.setData(slots, values['k'].to_numpy())
        self.d_line.setData(slots, values['d'].to_numpy())


class StochRsiView(PanelView):
    def __init__(self) -> None:
        super().__init__(OscillatorPlot(), 'Above 80: overbought (stretched up). Below 20: oversold (stretched down).\n'
                                           'K is the fast line, D is its average. K crossing D can signal a turn.')

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        values = stoch_rsi(candles['close'])
        self.plot_widget.set_values(candles.index, values)
        self._show_legend(values)

    def _show_legend(self, values: pd.DataFrame) -> None:
        latest = values.dropna()
        if latest.empty:
            self.legend.setText('Stoch RSI (14, 14, 3, 3) · not enough history yet')
            return
        k, d = latest.iloc[-1]
        zone = 'overbought' if k > OVERBOUGHT else 'oversold' if k < OVERSOLD else 'neutral'
        self.legend.setText(
            f'Stoch RSI (14, 14, 3, 3)   <span style="color:{K_COLOR}">K {k:.1f}</span>   '
            f'<span style="color:{D_COLOR}">D {d:.1f}</span>   <span style="color:#787b86">{zone}</span>')

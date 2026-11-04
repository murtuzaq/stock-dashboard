"""Stoch RSI view: the Stochastic RSI indicator on its own 0-100 panel."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt

from core.dashboard.panels import OVERBOUGHT, OVERSOLD, StochRsiModel, stoch_rsi_model
from core.common.theme import D_COLOR, K_COLOR, MUTED
from qtrender.dashboard.chart_view import PanelView, TimePlot


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
            self.addItem(pg.InfiniteLine(level, angle=0, pen=pg.mkPen(MUTED, style=style)))
        self.k_line = self.plot(pen=pg.mkPen(K_COLOR, width=1.5), connect='finite')
        self.d_line = self.plot(pen=pg.mkPen(D_COLOR, width=1.5), connect='finite')

    def show_model(self, model: StochRsiModel) -> None:
        self.set_dates(model.dates)
        slots = np.arange(len(model.k))
        self.k_line.setData(slots, model.k)
        self.d_line.setData(slots, model.d)


class StochRsiView(PanelView):
    def __init__(self) -> None:
        super().__init__(OscillatorPlot(), 'Above 80: overbought (stretched up). Below 20: oversold (stretched down).\n'
                                           'K is the fast line, D is its average. K crossing D can signal a turn.')

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        model = stoch_rsi_model(candles)
        self.plot_widget.show_model(model)
        self.set_legend(model.legend)

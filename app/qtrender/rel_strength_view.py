"""Relative Strength view: the stock compared with the S&P 500.

The line is the stock's price divided by the S&P 500's, set to 100 at the start of the selected range.
Above 100 = the stock has done better than the market since then; rising = it is pulling ahead.
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt

from core.panels import BENCHMARK_NAME, RelStrengthModel, rel_strength_model
from core.theme import MUTED, RS_COLOR
from qtrender.chart_view import PanelView, TimePlot


class RelStrengthPlot(TimePlot):
    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.addItem(pg.InfiniteLine(100, angle=0, pen=pg.mkPen(MUTED, style=Qt.PenStyle.DashLine)))
        self.line = self.plot(pen=pg.mkPen(RS_COLOR, width=1.5), connect='finite')
        self.model: RelStrengthModel | None = None

    def show_model(self, model: RelStrengthModel) -> None:
        self.model = model
        self.set_dates(model.dates)

    def set_range(self, start: pd.Timestamp) -> None:
        self.line.setData(np.arange(len(self.model.ratio)), self.model.rebased(start))
        super().set_range(start)


class RelStrengthView(PanelView):
    def __init__(self) -> None:
        super().__init__(RelStrengthPlot(), f'Stock price ÷ {BENCHMARK_NAME}, set to 100 at the start of the range.\n'
                                            'Above 100: beating the market. A rising line: pulling ahead.')
        self.model: RelStrengthModel | None = None
        self.benchmark = pd.DataFrame()

    def set_benchmark(self, benchmark_daily: pd.DataFrame) -> None:
        self.benchmark = benchmark_daily

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        self.model = rel_strength_model(daily, candles, self.benchmark)
        self.plot_widget.show_model(self.model)

    def set_range(self, start: pd.Timestamp) -> None:
        super().set_range(start)
        self.set_legend(self.model.legend(start))

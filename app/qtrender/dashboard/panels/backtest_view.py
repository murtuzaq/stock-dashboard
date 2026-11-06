"""Backtest view: the account value of every selected strategy over time, against buy & hold, on one chart."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt

from core.backtest.model import BacktestChart
from core.common.formatting import Span, plain
from core.common.theme import MUTED
from qtrender.dashboard.chart_view import PanelView, TimePlot

HINT = 'Select one or more strategies (Ctrl+click) under Strategies to compare how much each would have grown.'


class BacktestPlot(TimePlot):
    """One line per strategy, in dollars. Shares the time axis with the other charts."""

    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.lines: list[pg.PlotDataItem] = []

    def show_chart(self, chart: BacktestChart | None) -> None:
        for line in self.lines:
            self.removeItem(line)
        self.lines = []
        if chart is None:
            return
        self.set_dates(chart.dates)
        slots = np.arange(len(chart.dates))
        for series in chart.series:
            style = Qt.PenStyle.DashLine if series.is_hold else Qt.PenStyle.SolidLine
            line = self.plot(slots, series.values, pen=pg.mkPen(series.color, width=1.5 if series.is_hold else 2,
                                                                style=style), connect='finite')
            self.lines.append(line)
        self.set_range(chart.start)


class BacktestView(PanelView):
    def __init__(self) -> None:
        super().__init__(BacktestPlot(), 'Account value over time for each selected strategy, starting from its '
                                         'starting cash, against simply buying and holding. The higher line grew '
                                         'your money more.')
        self.set_legend([Span(HINT, MUTED)])

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        pass  # results arrive through show_chart()

    def show_chart(self, chart: BacktestChart | None) -> None:
        self.plot_widget.show_chart(chart)
        if chart is None:
            self.set_legend([Span(HINT, MUTED)])
            return
        legend = list(chart.legend)
        if chart.note:
            legend += [plain('\n'), Span(chart.note, MUTED)]
        self.set_legend(legend)

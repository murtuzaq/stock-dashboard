"""Relative Strength view: the stock compared with the S&P 500.

The line is the stock's price divided by the S&P 500's, set to 100 at the start of the selected range.
Above 100 = the stock has done better than the market since then; rising = it is pulling ahead.
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt

from chart_view import DOWN, UP, PanelView, TimePlot
from indicators import relative_strength
from prices import range_change, to_candles

BENCHMARK = '^GSPC'  # Yahoo's symbol for the S&P 500 index
BENCHMARK_NAME = 'S&P 500'
RS_COLOR = '#2962ff'


class RelStrengthPlot(TimePlot):
    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.addItem(pg.InfiniteLine(100, angle=0, pen=pg.mkPen('#787b86', style=Qt.PenStyle.DashLine)))
        self.line = self.plot(pen=pg.mkPen(RS_COLOR, width=1.5), connect='finite')
        self.ratio = np.array([])

    def set_values(self, dates: pd.DatetimeIndex, ratio: pd.Series) -> None:
        self.set_dates(dates)
        self.ratio = ratio.to_numpy()

    def set_range(self, start: pd.Timestamp) -> None:
        """Rebase so the first candle of the range is 100."""
        first_slot = min(int(self.time_axis.dates.searchsorted(start)), len(self.ratio) - 1)
        finite = np.flatnonzero(np.isfinite(self.ratio[first_slot:]))
        base = self.ratio[first_slot + finite[0]] if len(finite) else np.nan
        self.line.setData(np.arange(len(self.ratio)), self.ratio / base * 100)
        super().set_range(start)


class RelStrengthView(PanelView):
    def __init__(self) -> None:
        super().__init__(RelStrengthPlot(), f'Stock price ÷ {BENCHMARK_NAME}, set to 100 at the start of the range.\n'
                                            'Above 100: beating the market. A rising line: pulling ahead.')
        self.daily = pd.DataFrame()
        self.benchmark = pd.DataFrame()

    def set_benchmark(self, benchmark_daily: pd.DataFrame) -> None:
        self.benchmark = benchmark_daily

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        self.daily = daily
        if self.benchmark.empty:
            self.plot_widget.set_values(candles.index, pd.Series(np.nan, index=candles.index))
            return
        benchmark_candles = to_candles(self.benchmark, candles.attrs.get('candle_size', '1D'))
        self.plot_widget.set_values(candles.index, relative_strength(candles['close'], benchmark_candles['close']))

    def set_range(self, start: pd.Timestamp) -> None:
        super().set_range(start)
        if self.benchmark.empty:
            self.legend.setText(f'Relative strength · {BENCHMARK_NAME} data unavailable')
            return
        _, stock = range_change(self.daily, start)
        _, market = range_change(self.benchmark, start)
        gap = stock - market
        verdict = f'beating the market by {gap:.1f} pts' if gap >= 0 else f'lagging the market by {-gap:.1f} pts'
        self.legend.setText(
            f'Relative strength vs {BENCHMARK_NAME} since {max(start, self.daily.index[0]):%b %d, %Y}   '
            f'stock {stock:+.2f}%   {BENCHMARK_NAME} {market:+.2f}%   '
            f'<span style="color:{UP if gap >= 0 else DOWN}">{verdict}</span>')

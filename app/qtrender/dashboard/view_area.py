"""Main area (renderer): the stacked views, the title and header lines, and the range buttons.

All decisions (what to load, which range, which strategy results) are made by core.dashboard.controller.DashboardController,
which drives this widget through the DashboardView protocol. This widget draws what it is told and reports clicks.

Every view gets the same data (daily prices, plus candles for the chosen candle size) and the same range.
Stacked charts share one time axis: they scroll and zoom together, and only the bottom one shows dates.
"""
from collections.abc import Callable

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QSplitter, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

from core.common.background import BackgroundLoader
from core.dashboard.controller import HeaderModel
from core.common.formatting import plain, Span
from core.common.theme import MUTED
from core.dashboard.layout import PRICE_CHARTS, SMA_HOSTS, PanelLayout
from prices import DEFAULT_RANGE, RANGES
from qtrender.dashboard.panels.atr_view import AtrView
from qtrender.dashboard.chart_view import CandleChart, TimePlot
from qtrender.dashboard.panels.growth_view import GrowthView
from qtrender.dashboard.panels.history_view import HistoryView
from qtrender.dashboard.panels.macd_view import MacdView
from qtrender.dashboard.panels.price_view import PriceView
from qtrender.dashboard.panels.rel_strength_view import RelStrengthView
from qtrender.richtext import line_html
from qtrender.dashboard.panels.sma_view import SmaLines, SmaView
from qtrender.dashboard.panels.stoch_rsi_view import StochRsiView
from qtrender.dashboard.panels.strategy_view import StrategyView
from qtrender.dashboard.trade_overlay import TradeOverlay
from qtrender.dashboard.panels.volume_view import VolumeView
from strategy import Strategy
from strategy.backtest import BacktestResult


def chart_of(widget: QWidget) -> TimePlot | None:
    """The chart inside a view, if it has one (the Growth and History tables do not)."""
    return widget if isinstance(widget, TimePlot) else getattr(widget, 'plot_widget', None)


class ViewArea(QStackedWidget):
    range_selected = Signal(str)  # a range button was clicked
    costs_changed = Signal(object)  # Costs, from the results panel
    edit_strategy = Signal(str)  # strategy id (from the results panel's "Edit rules…" button)

    def __init__(self, loader: BackgroundLoader, financials_source: Callable[[str], dict]) -> None:
        super().__init__()
        self.shown: list[str] = []  # views that currently have their own panel

        placeholder = QLabel('Search a symbol to begin')
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName('placeholder')
        self.addWidget(placeholder)

        page = QWidget()
        layout = QVBoxLayout(page)
        title_row = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName('chartTitle')
        self.last_price = QLabel()
        self.last_price.setObjectName('lastPrice')
        title_row.addWidget(self.title)
        title_row.addWidget(self.last_price)
        title_row.addStretch()
        layout.addLayout(title_row)

        self.status = QLabel()
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setObjectName('placeholder')
        layout.addWidget(self.status, stretch=1)

        # One widget per view; each has set_data(daily, candles) and set_range(start_date).
        # Optional hooks: set_symbol(symbol) and set_benchmark(sp500_daily).
        self.views = {'price': PriceView(), 'candles': CandleChart(), 'sma': SmaView(), 'volume': VolumeView(),
                      'macd': MacdView(), 'stoch_rsi': StochRsiView(), 'atr': AtrView(),
                      'rel_strength': RelStrengthView(), 'growth': GrowthView(loader, financials_source),
                      'strategy': StrategyView(), 'history': HistoryView()}
        self.sma_overlays = {key: SmaLines(self.views[key]) for key in SMA_HOSTS}
        self.trade_overlays = {key: TradeOverlay(chart_of(widget), key in PRICE_CHARTS)
                               for key, widget in self.views.items() if chart_of(widget) and key != 'strategy'}
        self.views['strategy'].costs_changed.connect(self.costs_changed)
        self.views['strategy'].edit_requested.connect(self.edit_strategy)
        self.panels = QSplitter(Qt.Orientation.Vertical)
        self.panels.setChildrenCollapsible(False)
        for widget in self.views.values():
            self.panels.addWidget(widget)
        layout.addWidget(self.panels, stretch=1)

        layout.addLayout(self._build_range_bar())
        self.addWidget(page)

    def _build_range_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        label = QLabel('Range')
        label.setObjectName('barLabel')
        label.setToolTip('How much history to show')
        bar.addWidget(label)
        self.range_buttons = QButtonGroup(self)
        for range_label in RANGES:
            button = QToolButton()
            button.setText(range_label)
            button.setCheckable(True)
            button.setChecked(range_label == DEFAULT_RANGE)
            self.range_buttons.addButton(button)
            bar.addWidget(button)
        self.range_buttons.buttonClicked.connect(lambda button: self.range_selected.emit(button.text()))
        bar.addStretch()
        return bar

    # --- DashboardView: what the controller asks for ---

    def show_selection(self, title: str, layout: PanelLayout) -> None:
        """Show only the selected views, link their time axes, and put the dates under the bottom chart."""
        self.title.setText(title)
        self.shown = layout.shown
        self.setCurrentIndex(1)
        for key, overlay in self.sma_overlays.items():
            overlay.set_visible(key == layout.sma_host)
        for key, widget in self.views.items():
            widget.setVisible(key in layout.shown)
            chart = chart_of(widget)
            if chart:
                chart.setXLink(None)
        charts = [chart_of(self.views[key]) for key in layout.shown if chart_of(self.views[key])]
        for chart in charts[1:]:
            chart.setXLink(charts[0])
        for chart in charts:
            chart.show_dates(chart is charts[-1])
        self.panels.setSizes([layout.height_of(key) * 1000 for key in self.views])

    def set_symbol(self, symbol: str) -> None:
        for widget in self.views.values():
            if hasattr(widget, 'set_symbol'):
                widget.set_symbol(symbol)

    def show_status(self, text: str) -> None:
        self.panels.hide()
        self.status.setText(text)
        self.status.show()

    def show_data(self, daily: pd.DataFrame, candles: pd.DataFrame, benchmark: pd.DataFrame) -> None:
        self.status.hide()
        self.panels.show()
        for widget in self.views.values():
            if hasattr(widget, 'set_benchmark'):
                widget.set_benchmark(benchmark)
            widget.set_data(daily, candles)
        for overlay in self.sma_overlays.values():
            overlay.set_data(candles)

    def show_range(self, start: pd.Timestamp | None, header: HeaderModel | None) -> None:
        if start is None or header is None:
            self.last_price.clear()
            return
        for widget in self.views.values():
            widget.set_range(start)
        self.last_price.setText(line_html([plain(f'{header.last}  '), Span(header.change, header.change_color),
                                           plain('  '), Span(header.detail, MUTED)]))

    def show_strategy(self, strategy: Strategy, result: BacktestResult, candles: pd.DataFrame) -> None:
        self.views['strategy'].show_result(strategy, result)
        for key, overlay in self.trade_overlays.items():
            if key in self.shown:
                overlay.show(result, candles)
            else:
                overlay.clear()

    def clear_strategy(self) -> None:
        for overlay in self.trade_overlays.values():
            overlay.clear()

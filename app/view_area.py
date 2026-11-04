"""Main area: loads a symbol's price history and shows the views selected in the Explorer, stacked top to bottom.

Every view gets the same data (daily prices, plus candles for the chosen candle size) and the same range.
Stacked charts share one time axis: they scroll and zoom together, and only the bottom one shows dates.
"""
import threading

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QSplitter, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

from chart_view import DOWN, UP, CandleChart, TimePlot
from explorer import VIEWS
from history_view import HistoryView
from price_view import PriceView
from stoch_rsi_view import StochRsiView
from prices import DEFAULT_RANGE, RANGE_NAMES, RANGES, load_daily, range_change, range_start, to_candles

# Share of the height each view gets when stacked (price charts get more room than indicators).
HEIGHT_WEIGHTS = {'price': 3, 'candles': 3, 'stoch_rsi': 2, 'history': 3}


def chart_of(widget: QWidget) -> TimePlot | None:
    """The chart inside a view, if it has one (the History table does not)."""
    return widget if isinstance(widget, TimePlot) else getattr(widget, 'plot_widget', None)


class ViewArea(QStackedWidget):
    _history_loaded = Signal(str, object)  # symbol, daily DataFrame

    def __init__(self) -> None:
        super().__init__()
        self.symbol: str | None = None
        self.selected: list[str] = []
        self.candle_size = '1D'
        self.range = DEFAULT_RANGE
        self.daily: dict[str, pd.DataFrame] = {}  # downloaded history, kept for this session
        self.candles = pd.DataFrame()
        self._history_loaded.connect(self._on_history_loaded)

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

        # One widget per Explorer view; each has set_data(daily, candles) and set_range(start_date).
        self.views = {'price': PriceView(), 'candles': CandleChart(), 'stoch_rsi': StochRsiView(),
                      'history': HistoryView()}
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
            button.setChecked(range_label == self.range)
            self.range_buttons.addButton(button)
            bar.addWidget(button)
        self.range_buttons.buttonClicked.connect(lambda button: self.set_range(button.text()))
        bar.addStretch()
        return bar

    # --- what to show ---

    def show_views(self, symbol: str, views: list[str], candle_size: str) -> None:
        labels = dict(VIEWS)
        self.title.setText(f'{symbol} · {" + ".join(labels[v] for v in views)} · {candle_size}')
        self.selected = views
        self._arrange_panels()
        self.setCurrentIndex(1)
        if symbol == self.symbol and candle_size == self.candle_size and not self.candles.empty:
            return  # same data, only the selection changed
        self.symbol, self.candle_size = symbol, candle_size
        if symbol in self.daily:
            self._render()
            return
        self.candles = pd.DataFrame()
        self._show_status(f'Loading {symbol} price history…')
        threading.Thread(target=lambda: self._history_loaded.emit(symbol, load_daily(symbol)), daemon=True).start()

    def set_range(self, range_label: str) -> None:
        self.range = range_label
        self._apply_range()

    def _on_history_loaded(self, symbol: str, daily: pd.DataFrame) -> None:
        self.daily[symbol] = daily
        if symbol == self.symbol:  # ignore downloads for a symbol the user already left
            self._render()

    def _render(self) -> None:
        daily = self.daily[self.symbol]
        if daily.empty:
            self.candles = pd.DataFrame()
            self.last_price.clear()
            self._show_status(f'No price history found for {self.symbol}.\nCheck the symbol, or it may be delisted.')
            return
        self.status.hide()
        self.panels.show()
        self.candles = to_candles(daily, self.candle_size)
        for widget in self.views.values():
            widget.set_data(daily, self.candles)
        self._apply_range()

    def _arrange_panels(self) -> None:
        """Show only the selected views, link their time axes, and put the dates under the bottom chart."""
        for key, widget in self.views.items():
            widget.setVisible(key in self.selected)
            chart = chart_of(widget)
            if chart:
                chart.setXLink(None)
        charts = [chart_of(self.views[key]) for key in self.selected if chart_of(self.views[key])]
        for chart in charts[1:]:
            chart.setXLink(charts[0])
        for chart in charts:
            chart.show_dates(chart is charts[-1])
        self.panels.setSizes([HEIGHT_WEIGHTS[key] * 1000 if key in self.selected else 0 for key in self.views])

    def _apply_range(self) -> None:
        if self.candles.empty:
            return
        daily = self.daily[self.symbol]
        start = range_start(daily.index[-1], daily.index[0], self.range)
        for widget in self.views.values():
            widget.set_range(start)
        self._show_header(daily, start)

    def _show_header(self, daily: pd.DataFrame, start: pd.Timestamp) -> None:
        """Latest close, the change over the selected range (like finance sites), then today's change."""
        last = daily['close'].iloc[-1]
        amount, percent = range_change(daily, start)
        today = (last / daily['close'].iloc[-2] - 1) * 100 if len(daily) > 1 else 0.0
        color = UP if percent >= 0 else DOWN
        self.last_price.setText(
            f'{last:,.2f}  <span style="color:{color}">{percent:+.2f}% ({amount:+,.2f}) {RANGE_NAMES[self.range]}'
            f'</span>  <span style="color:#787b86">· today {today:+.2f}% · close {daily.index[-1]:%b %d, %Y}</span>')

    def _show_status(self, text: str) -> None:
        self.panels.hide()
        self.status.setText(text)
        self.status.show()

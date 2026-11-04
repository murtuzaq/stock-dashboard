"""The dashboard's session: which symbol, views, candle size and range are showing, and everything derived from them.

This is the application logic that used to live inside the view-area widget. It loads price history, builds
candles, works out the range, runs and caches backtests, and tells a `DashboardView` (the renderer) what to show.
It never touches a widget.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from core import theme
from core.background import BackgroundLoader
from core.panels import BENCHMARK
from core.strategy_service import StrategyService
from core.views import STRATEGY_VIEW, VIEWS, PanelLayout, arrange, is_strategy_key, strategy_id_of
from prices import DEFAULT_RANGE, RANGE_NAMES, load_daily, range_change, range_start, to_candles
from strategy import Costs, Strategy
from strategy.backtest import BacktestResult, run as run_backtest, strategy_hash


@dataclass(frozen=True)
class HeaderModel:
    """The line under the title: latest close, change over the range (coloured), then today's change."""
    last: str
    change: str
    change_color: str
    detail: str


class DashboardView(Protocol):
    """What the controller needs from the renderer."""

    def show_selection(self, title: str, layout: PanelLayout) -> None: ...
    def set_symbol(self, symbol: str) -> None: ...
    def show_status(self, text: str) -> None: ...
    def show_data(self, daily: pd.DataFrame, candles: pd.DataFrame, benchmark: pd.DataFrame) -> None: ...
    def show_range(self, start: pd.Timestamp | None, header: HeaderModel | None) -> None: ...
    def show_strategy(self, strategy: Strategy, result: BacktestResult, candles: pd.DataFrame) -> None: ...
    def clear_strategy(self) -> None: ...


def header_model(daily: pd.DataFrame, start: pd.Timestamp, range_label: str) -> HeaderModel:
    """Latest close, the change over the selected range (like finance sites), then today's change."""
    last = daily['close'].iloc[-1]
    amount, percent = range_change(daily, start)
    today = (last / daily['close'].iloc[-2] - 1) * 100 if len(daily) > 1 else 0.0
    return HeaderModel(last=f'{last:,.2f}',
                       change=f'{percent:+.2f}% ({amount:+,.2f}) {RANGE_NAMES[range_label]}',
                       change_color=theme.change_color(percent),
                       detail=f'· today {today:+.2f}% · close {daily.index[-1]:%b %d, %Y}')


class DashboardController:
    def __init__(self, view: DashboardView, loader: BackgroundLoader, strategies: StrategyService | None = None,
                 history_source: Callable[[str], pd.DataFrame] = load_daily) -> None:
        self.view = view
        self.loader = loader
        self.strategies = strategies or StrategyService()
        self.history_source = history_source
        self.symbol: str | None = None
        self.view_keys: list[str] = []  # as selected in the Explorer, e.g. ['price', 'strategy:<id>']
        self.shown: list[str] = []  # selected views that get their own panel
        self.candle_size = '1D'
        self.range = DEFAULT_RANGE
        self.daily: dict[str, pd.DataFrame] = {}  # downloaded history, kept for this session
        self.benchmark = pd.DataFrame()
        self.candles = pd.DataFrame()
        self.start: pd.Timestamp | None = None  # first day of the selected range
        self.strategy_id: str | None = None  # the strategy selected in the Explorer, if any
        self._results: dict[tuple, BacktestResult] = {}  # by (symbol, rules hash, candle size, start)

    # --- what to show ---

    def show_views(self, symbol: str, view_keys: list[str], candle_size: str) -> None:
        """Show the selected views; a selected strategy ('strategy:<id>') shows its results panel and trades."""
        self.view_keys = view_keys
        strategy_keys = [key for key in view_keys if is_strategy_key(key)]
        self.strategy_id = strategy_id_of(strategy_keys[0]) if strategy_keys else None
        strategy = self.strategies.get(self.strategy_id) if self.strategy_id else None

        labels = dict(VIEWS)
        if strategy:
            labels[strategy_keys[0]] = f'Strategy "{strategy.name}"'
        title = f'{symbol} · {" + ".join(labels.get(key, key) for key in view_keys)} · {candle_size}'
        selected = [STRATEGY_VIEW if is_strategy_key(key) else key for key in view_keys]
        layout = arrange(selected)
        self.shown = layout.shown
        self.view.show_selection(title, layout)
        self.view.set_symbol(symbol)

        if symbol == self.symbol and candle_size == self.candle_size and not self.candles.empty:
            self.refresh_strategy()  # same data, only the selection changed
            return
        self.symbol, self.candle_size = symbol, candle_size
        if symbol in self.daily:
            self._render()
            return
        self.candles = pd.DataFrame()
        self.view.show_status(f'Loading {symbol} price history…')
        self.loader.run(lambda: (self.history_source(symbol), self.history_source(BENCHMARK)),
                        lambda loaded: self._on_history_loaded(symbol, *loaded),
                        lambda error: self._on_history_failed(symbol, error))

    def set_candle_size(self, candle_size: str) -> None:
        if self.symbol:
            self.show_views(self.symbol, self.view_keys, candle_size)
        else:
            self.candle_size = candle_size

    def set_range(self, range_label: str) -> None:
        self.range = range_label
        self._apply_range()

    # --- loading ---

    def _on_history_loaded(self, symbol: str, daily: pd.DataFrame, benchmark: pd.DataFrame) -> None:
        self.daily[symbol] = daily
        if not benchmark.empty:
            self.benchmark = benchmark
        if symbol == self.symbol:  # ignore downloads for a symbol the user already left
            self._render()

    def _on_history_failed(self, symbol: str, error: Exception) -> None:
        if symbol == self.symbol:
            self.view.show_status(f'Could not load price history for {symbol}.\n{error}')

    def _render(self) -> None:
        daily = self.daily[self.symbol]
        if daily.empty:
            self.candles = pd.DataFrame()
            self.view.show_range(None, None)
            self.view.show_status(f'No price history found for {self.symbol}.\n'
                                  'Check the symbol, or it may be delisted.')
            return
        self.candles = to_candles(daily, self.candle_size)
        self.view.show_data(daily, self.candles, self.benchmark)
        self._apply_range()

    def _apply_range(self) -> None:
        if self.candles.empty:
            return
        daily = self.daily[self.symbol]
        self.start = start = range_start(daily.index[-1], daily.index[0], self.range)
        self.view.show_range(start, header_model(daily, start, self.range))
        self.refresh_strategy()

    # --- strategy backtest ---

    def refresh_strategy(self) -> None:
        """Backtest the selected strategy (cached) and show its results and trades on the visible charts."""
        strategy = self.strategies.get(self.strategy_id) if self.strategy_id else None
        if strategy is None or self.candles.empty or self.start is None:
            self.view.clear_strategy()
            return
        key = (self.symbol, strategy_hash(strategy), self.candle_size, self.start)
        if key not in self._results:
            self._results[key] = run_backtest(strategy, self.candles, self.benchmark, self.start, self.symbol)
        self.view.show_strategy(strategy, self._results[key], self.candles)

    def update_costs(self, costs: Costs) -> None:
        """The user edited capital / commission / slippage on the results panel."""
        self.strategies.update_costs(self.strategy_id, costs)
        self.refresh_strategy()

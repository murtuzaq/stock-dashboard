"""The dashboard's session: which symbol, views, candle size and range are showing, and everything derived from them.

This is the application logic that used to live inside the view-area widget. It loads price history, builds
candles, works out the range, runs and caches backtests, and tells a `DashboardView` (the renderer) what to show.
It never touches a widget.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from company import CompanyProfile, load_profile
from core.common import theme
from core.common.background import BackgroundLoader
from core.backtest.model import BacktestChart, backtest_chart
from core.dashboard.panels import BENCHMARK
from core.overview.model import OverviewModel, overview_model, rank_strategies
from core.strategies.service import StrategyService
from core.dashboard.layout import (BACKTEST, OVERVIEW, OVERVIEW_LABEL, STRATEGY_VIEW, VIEWS, PanelLayout, arrange,
                                   is_strategy_key, strategy_id_of)
from prices import DEFAULT_RANGE, RANGE_NAMES, load_daily, range_change, range_start, to_candles
from strategy import Costs, Strategy
from strategy.backtest import BacktestResult, run as run_backtest, strategy_hash
from strategy.ranking import Ranked


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
    def show_empty(self) -> None: ...
    def set_symbol(self, symbol: str) -> None: ...
    def show_status(self, text: str) -> None: ...
    def show_data(self, daily: pd.DataFrame, candles: pd.DataFrame, benchmark: pd.DataFrame) -> None: ...
    def show_range(self, start: pd.Timestamp | None, header: HeaderModel | None) -> None: ...
    def show_strategy(self, strategy: Strategy, result: BacktestResult, candles: pd.DataFrame) -> None: ...
    def clear_strategy(self) -> None: ...
    def show_backtest(self, chart: BacktestChart | None) -> None:
        """The comparison of every selected strategy, or (None) a hint to select some."""
    def show_overview(self, model: OverviewModel | None, status: str = '') -> None:
        """The company overview, or (model None) a status line such as 'Loading…'."""


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
                 history_source: Callable[[str], pd.DataFrame] = load_daily,
                 profile_source: Callable[[str], CompanyProfile] = load_profile) -> None:
        self.view = view
        self.loader = loader
        self.strategies = strategies or StrategyService()
        self.history_source = history_source
        self.profile_source = profile_source
        self.profiles: dict[str, CompanyProfile] = {}  # company profiles, kept for this session
        self._rankings: dict[tuple, list[Ranked]] = {}  # by (symbol, last date, the strategies' rule hashes)
        self.symbol: str | None = None
        self.view_keys: list[str] = []  # as selected in the Explorer, e.g. ['price', 'strategy:<id>']
        self.shown: list[str] = []  # selected views that get their own panel
        self.candle_size = '1D'
        self.range = DEFAULT_RANGE
        self.daily: dict[str, pd.DataFrame] = {}  # downloaded history, kept for this session
        self.benchmark = pd.DataFrame()
        self.candles = pd.DataFrame()
        self.start: pd.Timestamp | None = None  # first day of the selected range
        self.strategy_id: str | None = None  # the strategy selected in the Explorer, if exactly one is
        self.strategy_ids: list[str] = []  # every strategy selected (several only while Backtest is selected)
        self._results: dict[tuple, BacktestResult] = {}  # by (symbol, rules hash, candle size, start)

    # --- what to show ---

    def show_views(self, symbol: str, view_keys: list[str], candle_size: str) -> None:
        """Show the selected views; a selected strategy ('strategy:<id>') shows its results panel and trades."""
        self.view_keys = view_keys
        strategy_keys = [key for key in view_keys if is_strategy_key(key)]
        self.strategy_ids = [strategy_id_of(key) for key in strategy_keys]
        # The results panel and trade arrows belong to a single strategy; with several, only the Backtest chart shows.
        self.strategy_id = self.strategy_ids[0] if len(self.strategy_ids) == 1 else None

        labels = dict(VIEWS) | {OVERVIEW: OVERVIEW_LABEL}
        for key in strategy_keys:
            strategy = self.strategies.get(strategy_id_of(key))
            if strategy:
                labels[key] = f'Strategy "{strategy.name}"'
        title = f'{symbol} · {" + ".join(labels.get(key, key) for key in view_keys)}'
        if view_keys != [OVERVIEW]:  # the overview doesn't depend on the candle size
            title += f' · {candle_size}'
        selected = []
        for key in view_keys:
            if not is_strategy_key(key):
                selected.append(key)
            elif self.strategy_id:
                selected.append(STRATEGY_VIEW)
        layout = arrange(selected)
        self.shown = layout.shown
        self.view.show_selection(title, layout)
        self.view.set_symbol(symbol)

        if symbol == self.symbol and candle_size == self.candle_size and not self.candles.empty:
            self.refresh_strategy()  # same data, only the selection changed
            self.refresh_overview()
            return
        self.symbol, self.candle_size = symbol, candle_size
        self.refresh_overview()  # the profile loads alongside the prices
        if symbol in self.daily:
            self._render()
            return
        self.candles = pd.DataFrame()
        self.view.show_status(f'Loading {symbol} price history…')
        self.loader.run(lambda: (self.history_source(symbol), self.history_source(BENCHMARK)),
                        lambda loaded: self._on_history_loaded(symbol, *loaded),
                        lambda error: self._on_history_failed(symbol, error))

    def clear(self) -> None:
        """Nothing is selected any more (e.g. the stock being shown was removed): show the empty chart area."""
        self.symbol, self.view_keys, self.shown, self.strategy_id, self.strategy_ids = None, [], [], None, []
        self.candles, self.start = pd.DataFrame(), None
        self.view.show_empty()

    def select(self, symbol: str, view_keys: list[str]) -> None:
        """The Explorer selection changed: show these views, in the current candle size."""
        self.show_views(symbol, view_keys, self.candle_size)

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
        self.refresh_overview()  # the strategy comparison needs the prices

    def _apply_range(self) -> None:
        if self.candles.empty:
            return
        daily = self.daily[self.symbol]
        self.start = start = range_start(daily.index[-1], daily.index[0], self.range)
        self.view.show_range(start, header_model(daily, start, self.range))
        self.refresh_strategy()

    # --- company overview ---

    def refresh_overview(self) -> None:
        """Show the company overview if it is selected. The profile loads once per session; the strategy comparison
        is worked out once the prices are in (and again only if the prices or the strategies change)."""
        if OVERVIEW not in self.shown or self.symbol is None:
            return
        symbol = self.symbol
        profile = self.profiles.get(symbol)
        if profile is None:
            self.view.show_overview(None, f'Loading {symbol} company profile…')
            self.loader.run(lambda: self.profile_source(symbol), lambda loaded: self._on_profile_loaded(symbol, loaded),
                            lambda error: self._on_profile_loaded(symbol, CompanyProfile(symbol)))
            return
        daily = self.daily.get(symbol)
        ranked = self._ranking(symbol, daily) if daily is not None else None
        self.view.show_overview(overview_model(symbol, profile, daily, self.benchmark, ranked))

    def _on_profile_loaded(self, symbol: str, profile: CompanyProfile) -> None:
        self.profiles[symbol] = profile
        if symbol == self.symbol:  # ignore profiles for a stock the user already left
            self.refresh_overview()

    def _ranking(self, symbol: str, daily: pd.DataFrame) -> list[Ranked]:
        strategies = self.strategies.for_symbol(symbol)
        last_day = daily.index[-1] if not daily.empty else None
        key = (symbol, last_day, tuple(strategy_hash(strategy) for strategy in strategies))
        if key not in self._rankings:
            self._rankings[key] = rank_strategies(strategies, daily, self.benchmark, symbol)
        return self._rankings[key]

    # --- strategy backtest ---

    def _backtest_of(self, strategy: Strategy) -> BacktestResult:
        """The strategy's backtest on the candles showing, run once and then cached."""
        key = (self.symbol, strategy_hash(strategy), self.candle_size, self.start)
        if key not in self._results:
            self._results[key] = run_backtest(strategy, self.candles, self.benchmark, self.start, self.symbol)
        return self._results[key]

    def refresh_strategy(self) -> None:
        """Backtest the selected strategy (cached) and show its results and trades on the visible charts; then update
        the Backtest chart, which compares every selected strategy."""
        strategy = self.strategies.get(self.strategy_id) if self.strategy_id else None
        if strategy is None or self.candles.empty or self.start is None:
            self.view.clear_strategy()
        else:
            self.view.show_strategy(strategy, self._backtest_of(strategy), self.candles)
        self.refresh_backtest()

    def refresh_backtest(self) -> None:
        """Show every selected strategy's account value on the Backtest chart, if that view is selected."""
        if BACKTEST not in self.shown:
            return
        if self.candles.empty or self.start is None:
            self.view.show_backtest(None)
            return
        strategies = [self.strategies.get(strategy_id) for strategy_id in self.strategy_ids]
        runs = [(strategy, self._backtest_of(strategy)) for strategy in strategies if strategy]
        self.view.show_backtest(backtest_chart(runs))

    def update_costs(self, costs: Costs) -> None:
        """The user edited capital / commission / slippage on the results panel."""
        self.strategies.update_costs(self.strategy_id, costs)
        self.refresh_strategy()

"""Tools > Portfolio Test: pick the stocks, how many winners to hold and the first year, and see the yearly rotation
against buy & hold of the same stocks.

Uses only prices already in the database. The universe is every stored stock, or the stocks of a saved portfolio.
The test itself is strategy.rotation.run_rotation; this controller gathers the prices, runs it off the GUI thread and
tells the page what to show.
"""
from collections.abc import Callable
from datetime import date
from typing import Protocol

import pandas as pd

from core.common.background import BackgroundLoader
from core.dashboard.panels import BENCHMARK
from core.portfolio_test.model import WARNING, PortfolioResult, portfolio_result
from prices import load_stored, store
from strategy import Costs
from strategy.rotation import RotationSettings, earliest_first_year, run_rotation

ALL_STOCKS = 'All stocks in my database'
DEFAULT_N = 10
YEARS_BACK = 10  # the first year defaults to this many years ago


class PortfolioTestView(Protocol):
    def show_universes(self, names: list[str], current: str) -> None: ...
    def show_settings(self, n: int, first_year: int, last_year: int) -> None: ...
    def show_warning(self, text: str) -> None: ...
    def show_result(self, result: PortfolioResult | None) -> None: ...
    def show_notice(self, text: str) -> None: ...
    def set_running(self, running: bool) -> None: ...


class PortfolioTestController:
    def __init__(self, view: PortfolioTestView, loader: BackgroundLoader,
                 portfolios_source: Callable[[], dict[str, list[str]]],
                 stocks_source: Callable[[], pd.DataFrame] = store.stored_stocks,
                 series_source: Callable[[str], pd.DataFrame] = load_stored,
                 today: Callable[[], date] = date.today, costs: Costs | None = None) -> None:
        self.view = view
        self.loader = loader
        self.portfolios_source = portfolios_source  # saved portfolios: name -> its symbols
        self.stocks_source = stocks_source  # prices.store.stored_stocks
        self.series_source = series_source  # a stock's daily prices from the database: never downloads
        self.today = today
        self.costs = costs or Costs()  # the $10,000 seed and the app's usual slippage and commission
        self.universe = ALL_STOCKS
        self.running = False
        self._portfolios: dict[str, list[str]] = {}
        self._stored: list[str] = []

    # --- opening ---

    def start_panel(self) -> None:
        """The page was opened: list the universes (all stored stocks, then each saved portfolio) and set defaults."""
        self._portfolios = self.portfolios_source()
        stocks = self.stocks_source()
        self._stored = [] if stocks.empty else sorted(stocks['symbol'])
        names = [ALL_STOCKS, *self._portfolios]
        if self.universe not in names:
            self.universe = ALL_STOCKS
        self.view.show_universes(names, self.universe)
        year = self.today().year
        self.view.show_settings(DEFAULT_N, year - YEARS_BACK, year)
        self.view.show_warning(WARNING)
        self.view.show_notice('')
        self.view.set_running(self.running)

    def choose_universe(self, name: str) -> None:
        if not self.running and (name == ALL_STOCKS or name in self._portfolios):
            self.universe = name

    def symbols(self) -> tuple[list[str], list[str]]:
        """(the chosen universe's stocks that have stored prices, the ones that do not)."""
        wanted = self._stored if self.universe == ALL_STOCKS else self._portfolios.get(self.universe, [])
        stored = set(self._stored)
        return [s for s in wanted if s in stored], [s for s in wanted if s not in stored]

    # --- running ---

    def run(self, n: int, first_year: int) -> None:
        if self.running:
            return
        symbols, missing = self.symbols()
        if len(symbols) < 2:
            self.view.show_notice('Choose at least 2 stocks that have stored prices (see Tools > Stocks > Download / '
                                  'update to add more).')
            return
        notes = []
        if missing:
            notes.append(f'{len(missing)} stock{"s" if len(missing) != 1 else ""} in this portfolio '
                         f'({", ".join(missing[:5])}{"…" if len(missing) > 5 else ""}) have no stored prices and are '
                         'left out: download them in Tools > Stocks.')
        if n > len(symbols):
            notes.append(f'Only {len(symbols)} stocks to choose from, so it holds all of them.')
            n = len(symbols)
        self.running = True
        self.view.set_running(True)
        self.view.show_notice(' '.join(notes) + (' ' if notes else '') + 'Working…')
        self.loader.run(lambda: self._work(symbols, n, first_year), lambda outcome: self._done(outcome, notes),
                        self._crashed)

    def _work(self, symbols: list[str], n: int, first_year: int) -> tuple[PortfolioResult | None, str]:
        """Worker thread: load the stored prices and run the rotation. Returns (result, '') or (None, the reason)."""
        prices = {symbol: self.series_source(symbol) for symbol in symbols}
        prices = {symbol: frame for symbol, frame in prices.items() if not frame.empty}
        benchmark = self.series_source(BENCHMARK)
        try:
            return portfolio_result(run_rotation(prices, benchmark, RotationSettings(n=n, first_year=first_year, costs=self.costs))), ''
        except ValueError as error:
            earliest = earliest_first_year(prices, min(n, len(prices))) if prices else None
            hint = f' The earliest year that can work with these stocks is {earliest}.' if earliest else ''
            return None, f'{error}{hint}'

    def _done(self, outcome: tuple[PortfolioResult | None, str], notes: list[str]) -> None:
        self.running = False
        self.view.set_running(False)
        result, reason = outcome
        self.view.show_result(result)
        self.view.show_notice(' '.join(notes + ([reason] if reason else [])))

    def _crashed(self, error: Exception) -> None:
        self.running = False
        self.view.set_running(False)
        self.view.show_notice(f'The test stopped unexpectedly: {error}')

"""Tools > Strategy Scoreboard: every saved strategy on every stored stock, with the out-of-sample check.

Uses the candle size and range selected in the main window when Run was pressed, $10,000 per test, and only prices
already in the database. The work is one stock at a time in the background, with progress and Stop; the page only runs
while it is showing. The engine is strategy.scoreboard; this controller gathers prices, caches and reports.
"""
import dataclasses
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from core.common.background import BackgroundLoader
from core.dashboard.panels import BENCHMARK
from core.library.stocks import SEED
from core.scoreboard.model import ScoreboardResult, scoreboard_result
from prices import RANGE_NAMES, load_stored, range_start, store, to_candles
from strategy import Strategy
from strategy.backtest import run as run_backtest, strategy_hash
from strategy.scoreboard import StockScore, score_stock, summarise


@dataclass(frozen=True)
class Progress:
    done: int
    total: int
    symbol: str


@dataclass(frozen=True)
class Outcome:
    scores: list[StockScore]
    total: int  # stocks in the database
    stopped: bool


class ScoreboardView(Protocol):
    def show_header(self, text: str) -> None: ...
    def show_result(self, result: ScoreboardResult | None) -> None: ...
    def show_progress(self, done: int, total: int, text: str) -> None: ...
    def show_notice(self, text: str) -> None: ...
    def set_running(self, running: bool) -> None: ...


class ScoreboardExplorer(Protocol):
    def add_symbol(self, symbol: str) -> None: ...
    def select_strategy(self, symbol: str, strategy_id: str) -> None: ...


class ScoreboardController:
    def __init__(self, view: ScoreboardView, loader: BackgroundLoader, strategies_source: Callable[[], list[Strategy]],
                 explorer: ScoreboardExplorer, settings_source: Callable[[], tuple[str, str]],
                 stocks_source: Callable[[], pd.DataFrame] = store.stored_stocks,
                 series_source: Callable[[str], pd.DataFrame] = load_stored,
                 backtest: Callable = run_backtest) -> None:
        self.view = view
        self.loader = loader
        self.strategies_source = strategies_source  # every saved strategy (library templates and each stock's own)
        self.explorer = explorer
        self.settings_source = settings_source  # () -> (candle size, range label) selected in the main window
        self.stocks_source = stocks_source
        self.series_source = series_source  # a stock's daily prices from the database: never downloads
        self.backtest = backtest
        self.running = False
        self._stop = threading.Event()
        self._cache: dict[tuple, StockScore] = {}
        self._best: dict[str, str | None] = {}  # symbol -> its best strategy's id, for opening the stock

    # --- running ---

    def start(self) -> None:
        """Test every strategy on every stored stock with the candle size and range selected right now."""
        if self.running:
            return
        strategies = [dataclasses.replace(s, costs=dataclasses.replace(s.costs, capital=SEED))
                      for s in self.strategies_source()]
        if not strategies:
            self.view.show_notice('There are no strategies yet. Create one or use the Strategy Library.')
            return
        candle_size, range_label = self.settings_source()
        self.view.show_header(f'{len(strategies)} strategies · {candle_size} candles · {RANGE_NAMES[range_label]} · '
                              f'${SEED:,} per test')
        self.view.show_result(None)
        self.view.show_notice('')
        self.view.show_progress(0, 1, 'Starting…')
        self._stop.clear()
        self.running = True
        self.view.set_running(True)
        self.loader.run_with_progress(lambda report: self._work(strategies, candle_size, range_label, report),
                                      lambda outcome: self._ended(outcome, strategies), self._crashed,
                                      self._on_progress)

    def stop(self) -> None:
        """Halt after the stock being worked on (also when the page is hidden). What finished is still shown."""
        self._stop.set()

    def _work(self, strategies: list[Strategy], candle_size: str, range_label: str, report: Callable) -> Outcome:
        """Worker thread: score one stock at a time. Nothing here touches the screen."""
        stocks = self.stocks_source()
        benchmark = self.series_source(BENCHMARK)
        rules = '|'.join(sorted(strategy_hash(s) + s.id for s in strategies))
        scores = []
        rows = list(stocks.itertuples())
        for position, stock in enumerate(rows):
            if self._stop.is_set():
                return Outcome(scores, len(rows), stopped=True)
            report(Progress(position, len(rows), stock.symbol))
            start = range_start(stock.last_date, stock.first_date, range_label)
            key = (stock.symbol, rules, candle_size, start)
            if key not in self._cache:
                score = self._score(strategies, stock.symbol, candle_size, start, benchmark)
                if score is None:
                    continue
                self._cache[key] = score
            scores.append(self._cache[key])
        return Outcome(scores, len(rows), stopped=False)

    def _score(self, strategies: list[Strategy], symbol: str, candle_size: str, start: pd.Timestamp,
               benchmark: pd.DataFrame) -> StockScore | None:
        daily = self.series_source(symbol)
        if daily.empty:
            return None
        applicable = [s for s in strategies if s.symbol is None or s.symbol == symbol]
        return score_stock(applicable, to_candles(daily, candle_size), benchmark, start, symbol, self.backtest)

    # --- the worker's reports, on the GUI thread ---

    def _on_progress(self, progress: Progress) -> None:
        self.view.show_progress(progress.done, progress.total,
                                f'Testing {progress.symbol} ({progress.done + 1} of {progress.total})')

    def _ended(self, outcome: Outcome, strategies: list[Strategy]) -> None:
        self.running = False
        self.view.set_running(False)
        self.view.show_progress(0, 1, '')
        scoreboard = summarise(outcome.scores, strategies)
        self._best = {row.symbol: row.best_id for row in scoreboard.best}
        self.view.show_result(scoreboard_result(scoreboard, strategies))
        if outcome.stopped:
            self.view.show_notice(f'Stopped: {len(outcome.scores):,} of {outcome.total:,} stocks were tested. '
                                  'Press Run to test them all (finished stocks are remembered).')
        elif outcome.total == 0:
            self.view.show_notice('There are no stocks in the database yet. Add some with Tools > Stocks.')

    def _crashed(self, error: Exception) -> None:
        self.running = False
        self.view.set_running(False)
        self.view.show_notice(f'The scoreboard stopped unexpectedly: {error}')

    # --- using a result ---

    def open_stock(self, symbol: str) -> None:
        """A row was double-clicked: open that stock, with its best strategy selected when it has one."""
        best_id = self._best.get(symbol)
        if best_id is None:
            self.explorer.add_symbol(symbol)
        else:
            self.explorer.select_strategy(symbol, best_id)

"""Tools > Strategies > Compare on all stocks: one strategy against every stock in the local database.

Each stored stock is backtested with $10,000 over the candle size and range that were selected in the main window when
the button was pressed, using only the prices already in the database (nothing is downloaded). The results are listed
so they can be sorted from the best performer to the worst, next to what simply buying and holding would have made.
The backtests run one stock at a time in the background, with progress and Stop.
"""
import dataclasses
import statistics
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from core.common import theme
from core.common.background import BackgroundLoader
from core.common.formatting import Cell, money
from core.dashboard.panels import BENCHMARK
from core.library.stocks import NO_VALUE, SEED
from prices import RANGE_NAMES, load_stored, range_start, to_candles
from prices import store
from search import company_names
from strategy import Strategy
from strategy.backtest import run as run_backtest, strategy_hash

COLUMNS = ['Symbol', 'Name', 'Strategy $10K', 'Return', 'Buy & hold', 'vs hold', 'Trades', 'Win rate', 'Max drawdown']
RETURN_COLUMN = 3  # the table opens sorted by this one, best first
_KEPT = ('end_capital', 'return_pct', 'buy_hold_return_pct', 'trades', 'wins', 'losses', 'win_rate_pct',
         'max_drawdown_pct', 'time_in_market_pct')


@dataclass(frozen=True)
class StockResult:
    """How the strategy did on one stock. `metrics` is None when it could not be run (`reason` says why)."""
    symbol: str
    name: str
    metrics: dict | None
    reason: str = ''


@dataclass(frozen=True)
class CompareRow:
    symbol: str
    cells: list[Cell]


@dataclass(frozen=True)
class Progress:
    done: int
    total: int
    symbol: str


@dataclass(frozen=True)
class Outcome:
    results: list[StockResult]
    total: int  # stocks in the database
    stopped: bool


class CompareView(Protocol):
    def show_header(self, text: str) -> None: ...
    def show_rows(self, rows: list[CompareRow], summary: str) -> None: ...
    def show_progress(self, done: int, total: int, text: str) -> None: ...
    def show_notice(self, text: str) -> None: ...
    def set_running(self, running: bool) -> None: ...


class CompareExplorer(Protocol):
    def add_symbol(self, symbol: str) -> None: ...
    def select_strategy(self, symbol: str, strategy_id: str) -> None: ...


class StrategySource(Protocol):
    def get(self, strategy_id: str) -> Strategy | None: ...


def _cells(result: StockResult) -> list[Cell]:
    """The nine table cells for one stock: numbers coloured green/red and sortable by value."""
    name = Cell(result.name)
    if result.metrics is None:
        none = [Cell('n/a', tooltip=result.reason, align_right=True, sort_value=NO_VALUE) for _ in COLUMNS[2:]]
        return [Cell(result.symbol), name, *none]
    m = result.metrics
    versus = m['return_pct'] - m['buy_hold_return_pct']
    win_rate = 'n/a' if m['win_rate_pct'] is None else f'{m["win_rate_pct"]:.0f}%'
    trades = f'{m["trades"]} trades: {m["wins"]} won, {m["losses"]} lost; in the market {m["time_in_market_pct"]:.0f}% of the time'
    hold_tip = f'Buying and holding {result.symbol} over the same range, with the same costs'
    return [Cell(result.symbol), name,
            Cell(money(m['end_capital']), theme.change_color(m['return_pct']), align_right=True,
                 sort_value=m['end_capital'], tooltip=trades),
            Cell(f'{m["return_pct"]:+.1f}%', theme.change_color(m['return_pct']), align_right=True,
                 sort_value=m['return_pct'], tooltip=trades),
            Cell(f'{m["buy_hold_return_pct"]:+.1f}%', theme.change_color(m['buy_hold_return_pct']), align_right=True,
                 sort_value=m['buy_hold_return_pct'], tooltip=hold_tip),
            Cell(f'{versus:+.1f} pts', theme.change_color(versus), align_right=True, sort_value=versus,
                 tooltip='Strategy return minus buy & hold return, in percentage points'),
            Cell(str(m['trades']), align_right=True, sort_value=float(m['trades'])),
            Cell(win_rate, align_right=True, sort_value=NO_VALUE if m['win_rate_pct'] is None else m['win_rate_pct']),
            Cell(f'{m["max_drawdown_pct"]:.1f}%', align_right=True, sort_value=m['max_drawdown_pct'])]


def compare_rows(results: list[StockResult]) -> list[CompareRow]:
    """Rows best return first; stocks the strategy could not run on go last."""
    ordered = sorted(results, key=lambda r: (r.metrics is None, -(r.metrics['return_pct'] if r.metrics else 0), r.symbol))
    return [CompareRow(result.symbol, _cells(result)) for result in ordered]


def summary_line(results: list[StockResult]) -> str:
    """'Beat buy & hold on 38 of 105 stocks · median return +4.2% · best NVDA +212.0%'."""
    ran = [r for r in results if r.metrics is not None]
    if not ran:
        return 'The strategy could not be run on any stock.'
    beat = sum(1 for r in ran if r.metrics['return_pct'] > r.metrics['buy_hold_return_pct'])
    best = max(ran, key=lambda r: r.metrics['return_pct'])
    median = statistics.median(r.metrics['return_pct'] for r in ran)
    text = (f'Beat buy & hold on {beat} of {len(ran)} stocks · median return {median:+.1f}% · '
            f'best {best.symbol} {best.metrics["return_pct"]:+.1f}%')
    if len(ran) < len(results):
        text += f' · {len(results) - len(ran)} could not be run'
    return text


class CompareController:
    def __init__(self, view: CompareView, loader: BackgroundLoader, strategies: StrategySource,
                 explorer: CompareExplorer, settings_source: Callable[[], tuple[str, str]],
                 stocks_source: Callable[[], pd.DataFrame] = store.stored_stocks,
                 names_source: Callable[[], dict[str, str]] = company_names,
                 series_source: Callable[[str], pd.DataFrame] = load_stored,
                 backtest: Callable = run_backtest) -> None:
        self.view = view
        self.loader = loader
        self.strategies = strategies
        self.explorer = explorer
        self.settings_source = settings_source  # () -> (candle size, range label) selected in the main window
        self.stocks_source = stocks_source  # prices.store.stored_stocks: one row per stored stock
        self.names_source = names_source
        self.series_source = series_source  # a stock's daily prices from the database: never downloads
        self.backtest = backtest
        self.strategy: Strategy | None = None
        self.running = False
        self._stop = threading.Event()
        self._cache: dict[tuple, dict | None] = {}  # one stock's metrics by (symbol, rules hash, candle size, start)
        self._reasons: dict[tuple, str] = {}

    # --- running ---

    def start(self, strategy_id: str) -> None:
        """Compare this strategy on every stored stock, using the candle size and range selected right now."""
        if self.running:
            return
        strategy = self.strategies.get(strategy_id)
        if strategy is None:
            self.view.show_notice('That strategy no longer exists.')
            return
        self.strategy = strategy
        candle_size, range_label = self.settings_source()
        self.view.show_header(f'{strategy.name} · {candle_size} candles · {RANGE_NAMES[range_label]} · '
                              f'${SEED:,} per stock')
        self.view.show_rows([], '')
        self.view.show_notice('')
        self.view.show_progress(0, 1, 'Starting…')
        self._stop.clear()
        self.running = True
        self.view.set_running(True)
        self.loader.run_with_progress(lambda report: self._compare(strategy, candle_size, range_label, report),
                                      self._ended, self._crashed, self._on_progress)

    def rerun(self) -> None:
        """Run it again with whatever candle size and range are selected now."""
        if self.strategy is not None:
            self.start(self.strategy.id)

    def stop(self) -> None:
        """Halt after the stock being worked on (also when the page is hidden). What finished is still shown."""
        self._stop.set()

    def _compare(self, strategy: Strategy, candle_size: str, range_label: str, report: Callable) -> Outcome:
        """Worker thread: one backtest per stored stock. Nothing here touches the screen."""
        stocks = self.stocks_source()
        names = self.names_source()
        benchmark = self.series_source(BENCHMARK)
        seeded = dataclasses.replace(strategy, costs=dataclasses.replace(strategy.costs, capital=SEED))
        rules = strategy_hash(seeded)
        results = []
        rows = list(stocks.itertuples())
        for position, stock in enumerate(rows):
            if self._stop.is_set():
                return Outcome(results, len(rows), stopped=True)
            report(Progress(position, len(rows), stock.symbol))
            start = range_start(stock.last_date, stock.first_date, range_label)
            key = (stock.symbol, rules, candle_size, start)
            if key not in self._cache:
                self._cache[key], self._reasons[key] = self._one(seeded, stock.symbol, candle_size, start, benchmark)
            results.append(StockResult(stock.symbol, names.get(stock.symbol, ''), self._cache[key],
                                       self._reasons.get(key, '')))
        return Outcome(results, len(rows), stopped=False)

    def _one(self, strategy: Strategy, symbol: str, candle_size: str, start: pd.Timestamp,
             benchmark: pd.DataFrame) -> tuple[dict | None, str]:
        daily = self.series_source(symbol)
        if daily.empty:
            return None, 'No prices stored for this stock'
        try:
            result = self.backtest(strategy, to_candles(daily, candle_size), benchmark, start, symbol)
        except ValueError as error:  # e.g. it needs the S&P 500 and that is not in the database
            return None, str(error)
        return {name: result.metrics[name] for name in _KEPT}, ''

    # --- the worker's reports, on the GUI thread ---

    def _on_progress(self, progress: Progress) -> None:
        self.view.show_progress(progress.done, progress.total,
                                f'Testing {progress.symbol} ({progress.done + 1} of {progress.total})')

    def _ended(self, outcome: Outcome) -> None:
        self.running = False
        self.view.set_running(False)
        self.view.show_progress(0, 1, '')
        self.view.show_rows(compare_rows(outcome.results), summary_line(outcome.results))
        if outcome.stopped:
            self.view.show_notice(f'Stopped: {len(outcome.results):,} of {outcome.total:,} stocks were tested. '
                                  'Press Re-run to test them all.')
        elif outcome.total == 0:
            self.view.show_notice('There are no stocks in the database yet. Add some with Tools > Stocks.')

    def _crashed(self, error: Exception) -> None:
        self.running = False
        self.view.set_running(False)
        self.view.show_notice(f'The comparison stopped unexpectedly: {error}')

    # --- using a result ---

    def open_stock(self, symbol: str) -> None:
        """A row was double-clicked: open that stock, with the strategy selected if it applies to it."""
        if self.strategy is None:
            return
        if self.strategy.symbol is None or self.strategy.symbol == symbol:
            self.explorer.select_strategy(symbol, self.strategy.id)
        else:
            self.explorer.add_symbol(symbol)

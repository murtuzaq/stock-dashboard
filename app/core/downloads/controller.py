"""Tools > Stocks > Download / update: fills the local price database slowly and politely, only while open.

The panel lists every stock of a chosen set (an index, an exchange, the user's portfolios, the stocks already stored,
or ones picked by hand), coloured by state. Start fetches whatever is not up to date, one stock at a time with a random
pause between them so Yahoo is never hit like a bot; if Yahoo says "too many requests" it waits, retries once, and
then gives up for a while. Closing the Stock Library (or Stop) halts the download at once; every finished stock is already
saved, so starting again continues where it left off.
"""
import json
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import pandas as pd

from core.common.background import BackgroundLoader
from core.downloads import model
from core.downloads.awake import keep_awake
from core.downloads.model import DownloadRow, StockStatus
from prices import RateLimited, refresh
from prices import store
from prices.history import NO_DATA
from search import Catalog

COOLDOWN_DOCUMENT = ('download', '_cooldown')  # where "Yahoo limited us until ..." is remembered


@dataclass(frozen=True)
class PacingProfile:
    """How gently to ask Yahoo. Yahoo publishes no limit, so these look like a patient person, not a bot."""
    pause_min: float = 15.0  # seconds between two stocks (random, so the rhythm is not mechanical)
    pause_max: float = 25.0
    rate_limit_wait: float = 30 * 60  # after "too many requests": wait this long, then retry that stock once
    cooldown: float = 2 * 3600  # after a second one in a row: refuse to start again for this long
    max_consecutive_failures: int = 5  # in a row: probably offline, stop
    max_per_run: int = 1500  # most stocks in one run (about 8 hours at the default pace)


@dataclass(frozen=True)
class RunSummary:
    reason: str  # 'finished', 'stopped', 'rate_limited' or 'failures'
    fetched: int
    failed: int
    remaining: int


class DownloadView(Protocol):
    """What the controller needs from the panel."""

    def show_universes(self, names: list[str], current: str) -> None: ...
    def show_rows(self, rows: list[DownloadRow]) -> None: ...
    def update_row(self, row: DownloadRow) -> None: ...
    def show_totals(self, text: str) -> None: ...
    def show_progress(self, done: int, total: int, text: str) -> None: ...
    def show_notice(self, text: str) -> None: ...
    def set_running(self, running: bool) -> None: ...
    def alert(self) -> None:
        """Draw the user's attention (a run ended while they were elsewhere)."""


# What the worker thread reports (delivered on the GUI thread).
@dataclass(frozen=True)
class Started:
    symbol: str
    done: int
    total: int


@dataclass(frozen=True)
class Finished:
    symbol: str
    outcome: str  # prices.history NEW / UPDATED / NO_DATA
    done: int


@dataclass(frozen=True)
class Failed:
    symbol: str
    reason: str
    done: int


@dataclass(frozen=True)
class Waiting:
    text: str


def _read_cooldown() -> float | None:
    saved = store.read_document(*COOLDOWN_DOCUMENT)
    return json.loads(saved[1]).get('until') if saved else None


def _write_cooldown(until: float) -> None:
    store.save_document(*COOLDOWN_DOCUMENT, json.dumps({'until': until}))


class DownloadController:
    def __init__(self, view: DownloadView, loader: BackgroundLoader, catalog_source: Callable[[], Catalog],
                 stocks_source: Callable[[], pd.DataFrame], portfolio_symbols: Callable[[], list[str]],
                 pacing: PacingProfile | None = None, refresh_stock: Callable[[str], str] = refresh,
                 clock: Callable[[], float] = time.time, pause: Callable[[float, float], float] = random.uniform,
                 wait: Callable[[float], bool] | None = None, awake: Callable[[bool], None] = keep_awake,
                 read_cooldown: Callable[[], float | None] = _read_cooldown,
                 write_cooldown: Callable[[float], None] = _write_cooldown) -> None:
        self.view = view
        self.loader = loader
        self.catalog_source = catalog_source
        self.stocks_source = stocks_source  # prices.store.stored_stocks
        self.portfolio_symbols = portfolio_symbols
        self.pacing = pacing or PacingProfile()
        self.refresh_stock = refresh_stock
        self.clock = clock
        self.pause = pause  # (low, high) -> seconds, random between two stocks
        self._stop = threading.Event()
        self.wait = wait or self._stop.wait  # wait(seconds) -> True if stopped meanwhile; replaceable in tests
        self.awake = awake
        self.read_cooldown = read_cooldown
        self.write_cooldown = write_cooldown

        self.on_ended: Callable[[], None] | None = None  # called when a run ends (the Stock Library refreshes its list)
        self.catalog: Catalog | None = None
        self.groups: dict[str, list[str]] = {}
        self.names: dict[str, str] = {}
        self.picked: list[str] = []
        self._portfolio_symbols: list[str] = []
        self.universe = ''
        self.only_pending = False
        self.running = False
        self.stored = pd.DataFrame()
        self.session: dict[str, tuple[StockStatus, str]] = {}  # what happened to each stock in this session
        self.rows: list[DownloadRow] = []

    # --- opening and choosing what to show ---

    def start_panel(self) -> None:
        """The panel was opened: load the lists of stocks (in the background), then show the first one."""
        self.view.show_notice('')
        self.view.set_running(self.running)
        if self.running:
            return
        self.session.clear()  # a fresh look: what the database says now, not what happened last time

        def work():
            catalog = self.catalog_source()
            return catalog, self.stocks_source(), self.portfolio_symbols()
        self.loader.run(work, lambda loaded: self._loaded(*loaded),
                        lambda error: self.view.show_notice(f'Could not read the stock lists: {error}'))

    def _loaded(self, catalog: Catalog, stored: pd.DataFrame, portfolio_symbols: list[str]) -> None:
        self.catalog, self.stored = catalog, stored
        self.names = {symbol: security.name for symbol, security in catalog.securities.items()}
        self.groups = {group.label: sorted(group.symbols) for group in catalog.groups}
        self._portfolio_symbols = portfolio_symbols
        self._show_universe(self.universe if self.universe in self._options() else next(iter(self._options())))

    def _options(self) -> dict[str, list[str]]:
        stored = [] if self.stored.empty else self.stored['symbol'].tolist()
        return model.universe_options(self.groups, self._portfolio_symbols, stored, self.picked)

    def choose_universe(self, name: str) -> None:
        if not self.running and name in self._options():
            self._show_universe(name)

    def _show_universe(self, name: str) -> None:
        self.universe = name
        self.view.show_universes(list(self._options()), name)
        self._render()

    def set_only_pending(self, only_pending: bool) -> None:
        self.only_pending = only_pending
        self._render()

    def pick(self, symbol: str) -> None:
        """A stock was chosen in the panel's search box: add it to 'Stocks I picked' and show that list."""
        if self.running:
            self.view.show_notice('Stop the download before picking more stocks.')
            return
        if symbol not in self.picked:
            self.picked.append(symbol)
        if self.catalog and symbol in self.catalog.securities:
            self.names[symbol] = self.catalog.securities[symbol].name
        self._show_universe(model.PICKED)

    def _symbols(self) -> list[str]:
        return self._options().get(self.universe, [])

    def _render(self) -> None:
        self.rows = model.build_rows(self._symbols(), self.names, self.stored, self.session,
                                     datetime.fromtimestamp(self.clock()))
        self.view.show_rows(model.visible_rows(self.rows, self.only_pending))
        self.view.show_totals(model.totals_line(self.rows))

    # --- running ---

    def start(self) -> None:
        if self.running:
            return
        until = self.read_cooldown()
        if until and until > self.clock():
            self.view.show_notice(f'Yahoo recently asked us to slow down. Please wait until '
                                  f'{datetime.fromtimestamp(until):%H:%M} before downloading again.')
            return
        queue = model.queue_of(self.rows, self.pacing.max_per_run)
        if not queue:
            self.view.show_notice('Nothing to download: everything listed is up to date.')
            return
        self._stop.clear()
        self.running = True
        self.view.set_running(True)
        self.view.show_notice('')
        self.view.show_progress(0, len(queue), 'Starting…')
        self.loader.run_with_progress(lambda report: self._run(queue, report), self._ended, self._crashed,
                                      self._on_report)

    def stop(self) -> None:
        """Halt at once (the panel closed, or the user pressed Stop). Anything already saved stays."""
        self._stop.set()

    def _run(self, queue: list[str], report: Callable) -> RunSummary:
        """Worker thread. Nothing here touches the GUI: it reports events, which arrive on the GUI thread."""
        self.awake(True)
        try:
            return self._fetch_all(queue, report)
        finally:
            self.awake(False)

    def _fetch_all(self, queue: list[str], report: Callable) -> RunSummary:
        fetched = failed = failures_in_a_row = rate_limits_in_a_row = 0
        position = 0
        while position < len(queue):
            if self._stop.is_set():
                return RunSummary('stopped', fetched, failed, len(queue) - position)
            symbol = queue[position]
            report(Started(symbol, position, len(queue)))
            try:
                outcome = self.refresh_stock(symbol)
            except RateLimited:
                rate_limits_in_a_row += 1
                if rate_limits_in_a_row >= 2:
                    self.write_cooldown(self.clock() + self.pacing.cooldown)
                    return RunSummary('rate_limited', fetched, failed, len(queue) - position)
                report(Waiting(f'Yahoo asked us to slow down: waiting {self.pacing.rate_limit_wait / 60:.0f} minutes, '
                               'then trying again…'))
                if self.wait(self.pacing.rate_limit_wait):
                    return RunSummary('stopped', fetched, failed, len(queue) - position)
                continue  # the same stock again
            except Exception as error:  # noqa: BLE001 - a network or data problem with this one stock
                rate_limits_in_a_row = 0
                failed += 1
                failures_in_a_row += 1
                position += 1
                report(Failed(symbol, str(error) or type(error).__name__, position))
                if failures_in_a_row >= self.pacing.max_consecutive_failures:
                    return RunSummary('failures', fetched, failed, len(queue) - position)
            else:
                rate_limits_in_a_row = failures_in_a_row = 0
                fetched += outcome != NO_DATA
                position += 1
                report(Finished(symbol, outcome, position))
            if position < len(queue) and self._pause_stopped():
                return RunSummary('stopped', fetched, failed, len(queue) - position)
        return RunSummary('finished', fetched, failed, 0)

    def _pause_stopped(self) -> bool:
        """The polite gap between two stocks. True if the download was stopped during it."""
        return self.wait(self.pause(self.pacing.pause_min, self.pacing.pause_max))

    # --- the worker's reports, on the GUI thread ---

    def _on_report(self, event) -> None:
        if isinstance(event, Started):
            self.session[event.symbol] = (StockStatus.DOWNLOADING, '')
            self.view.show_progress(event.done, event.total, f'Downloading {event.symbol} ({event.done + 1} of '
                                                             f'{event.total})')
            self._row_changed(event.symbol)
        elif isinstance(event, Finished):
            if event.outcome == NO_DATA:
                self.session[event.symbol] = (StockStatus.NO_DATA, 'Yahoo has no prices for this symbol')
            else:
                self.session[event.symbol] = (StockStatus.UP_TO_DATE, 'just downloaded')
            self._row_changed(event.symbol)
        elif isinstance(event, Failed):
            self.session[event.symbol] = (StockStatus.FAILED, event.reason)
            self._row_changed(event.symbol)
        elif isinstance(event, Waiting):
            self.view.show_notice(event.text)

    def _row_changed(self, symbol: str) -> None:
        """Redraw one stock's row (or the whole list when the filter would now hide it), and the totals."""
        row = next((r for r in self.rows if r.symbol == symbol), None)
        if row is None:
            return
        fresh = model.build_rows([symbol], self.names, self.stored, self.session,
                                 datetime.fromtimestamp(self.clock()))[0]
        self.rows[self.rows.index(row)] = fresh
        if self.only_pending and fresh.status in (StockStatus.UP_TO_DATE, StockStatus.NO_DATA):
            self.view.show_rows(model.visible_rows(self.rows, True))
        else:
            self.view.update_row(fresh)
        self.view.show_totals(model.totals_line(self.rows))

    def _ended(self, summary: RunSummary) -> None:
        self.running = False
        self.view.set_running(False)
        messages = {
            'finished': f'Finished: {summary.fetched:,} downloaded' + (f', {summary.failed:,} failed' if summary.failed
                                                                     else '') + '.',
            'stopped': f'Stopped. {summary.fetched:,} downloaded; {summary.remaining:,} still to do '
                       '(press Start to continue).',
            'rate_limited': 'Yahoo asked us to slow down twice, so the download stopped. Try again in a couple of '
                            f'hours. {summary.fetched:,} downloaded; {summary.remaining:,} still to do.',
            'failures': f'Stopped after {self.pacing.max_consecutive_failures} failures in a row (are you online?). '
                        f'{summary.fetched:,} downloaded; {summary.remaining:,} still to do.',
        }
        self.view.show_notice(messages[summary.reason])
        self.view.show_progress(0, 1, '')
        for symbol, (status, _) in list(self.session.items()):  # a stock caught mid-download goes back to its state
            if status == StockStatus.DOWNLOADING:
                del self.session[symbol]
        self._render()
        if self.on_ended:
            self.on_ended()
        if summary.reason != 'stopped':
            self.view.alert()

    def _crashed(self, error: Exception) -> None:
        self.running = False
        self.view.set_running(False)
        self.view.show_notice(f'The download stopped unexpectedly: {error}')

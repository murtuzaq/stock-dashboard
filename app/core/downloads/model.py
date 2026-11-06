"""Tools > Stocks > Download / update as data: which stocks are listed, what state each is in, and what is left to fetch."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

import pandas as pd

from core.common import theme

FRESH_SECONDS = 20 * 3600  # a stock Yahoo was asked about this recently is not asked again


class StockStatus(Enum):
    NOT_DOWNLOADED = 'Not downloaded'
    DOWNLOADING = 'Downloading…'
    UP_TO_DATE = 'Up to date'
    STALE = 'Out of date'
    FAILED = 'Failed'
    NO_DATA = 'No data at Yahoo'


STATUS_COLORS = {StockStatus.NOT_DOWNLOADED: None, StockStatus.DOWNLOADING: theme.DOWNLOADING,
                 StockStatus.UP_TO_DATE: theme.UP, StockStatus.STALE: theme.WARNING, StockStatus.FAILED: theme.DOWN,
                 StockStatus.NO_DATA: theme.MUTED}

# Order in which a run fetches: never-downloaded (and failed) stocks first, then out-of-date ones.
_NEEDS_DOWNLOAD = {StockStatus.NOT_DOWNLOADED: 0, StockStatus.FAILED: 0, StockStatus.STALE: 1}


@dataclass(frozen=True)
class DownloadRow:
    symbol: str
    name: str
    status: StockStatus
    reason: str = ''  # why it failed, or the last price date for stored stocks
    checked_at: float = 0.0  # when Yahoo was last asked (0 = never), used to fetch the oldest first

    @property
    def needs_download(self) -> bool:
        return self.status in _NEEDS_DOWNLOAD


def previous_weekday(today: date) -> date:
    """The most recent Monday-Friday strictly before today: the newest day prices can be expected for."""
    day = today - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def status_of(last_date: pd.Timestamp | None, checked_at: float | None, now: datetime) -> StockStatus:
    """Stored stock state. Out of date means the newest price is older than the last weekday AND Yahoo has not been
    asked in the last 20 hours (so a weekend or a holiday does not turn the whole database yellow)."""
    if last_date is None or pd.isna(last_date):
        return StockStatus.NOT_DOWNLOADED
    if last_date.date() >= previous_weekday(now.date()):
        return StockStatus.UP_TO_DATE
    if checked_at is not None and not pd.isna(checked_at) and now.timestamp() - checked_at < FRESH_SECONDS:
        return StockStatus.UP_TO_DATE
    return StockStatus.STALE


def build_rows(symbols: list[str], names: dict[str, str], stored: pd.DataFrame,
               session: dict[str, tuple[StockStatus, str]], now: datetime) -> list[DownloadRow]:
    """One row per symbol, alphabetical. What happened in this session (downloading, failed, finished) wins over
    what the database says."""
    known = {row.symbol: row for row in stored.itertuples()} if not stored.empty else {}
    rows = []
    for symbol in sorted(set(symbols)):
        stock = known.get(symbol)
        checked = 0.0 if stock is None or pd.isna(stock.checked_at) else float(stock.checked_at)
        if symbol in session:
            status, reason = session[symbol]
        elif stock is None:
            status, reason = StockStatus.NOT_DOWNLOADED, ''
        else:
            status = status_of(stock.last_date, stock.checked_at, now)
            reason = f'prices to {stock.last_date:%Y-%m-%d}'
        rows.append(DownloadRow(symbol, names.get(symbol, ''), status, reason, checked))
    return rows


def visible_rows(rows: list[DownloadRow], only_pending: bool) -> list[DownloadRow]:
    """With the filter on, everything not already up to date (not downloaded, out of date, failed, no data)."""
    if not only_pending:
        return rows
    return [row for row in rows if row.status != StockStatus.UP_TO_DATE]


def queue_of(rows: list[DownloadRow], limit: int) -> list[str]:
    """Symbols to fetch in this run: never-downloaded first, then out-of-date ones, the least recently checked first."""
    todo = [row for row in rows if row.needs_download]
    todo.sort(key=lambda row: (_NEEDS_DOWNLOAD[row.status], row.checked_at, row.symbol))
    return [row.symbol for row in todo[:limit]]


def totals_line(rows: list[DownloadRow]) -> str:
    """'2,140 up to date · 310 out of date · 1,560 not downloaded · 12 failed'."""
    count = {status: sum(1 for row in rows if row.status == status) for status in StockStatus}
    parts = [f'{count[StockStatus.UP_TO_DATE]:,} up to date', f'{count[StockStatus.STALE]:,} out of date',
             f'{count[StockStatus.NOT_DOWNLOADED]:,} not downloaded']
    if count[StockStatus.FAILED]:
        parts.append(f'{count[StockStatus.FAILED]:,} failed')
    if count[StockStatus.NO_DATA]:
        parts.append(f'{count[StockStatus.NO_DATA]:,} with no data at Yahoo')
    return ' · '.join(parts)


def universe_options(groups: dict[str, list[str]], portfolio_symbols: list[str], stored_symbols: list[str],
                     picked: list[str]) -> dict[str, list[str]]:
    """The dropdown: every index/exchange group, then the user's own sets. Order is the order shown."""
    options = dict(groups)
    options[PORTFOLIOS] = portfolio_symbols
    options[STORED] = stored_symbols
    options[PICKED] = picked
    return options


PORTFOLIOS = 'Stocks in my portfolios'
STORED = 'Update stocks already in my database'
PICKED = 'Stocks I picked'

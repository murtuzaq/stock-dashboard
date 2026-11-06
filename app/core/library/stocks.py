"""Tools > Stocks: every stock whose prices are stored locally, and growing that list.

A stock joins the library the first time its prices are downloaded (by searching it, or with the panel's own
search box). Right-click a stock to open it or add it to any saved portfolio. The renderer implements
`StockLibraryView` and reports picks and menu choices here.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import pandas as pd

from core.common import theme
from core.common.background import BackgroundLoader
from core.common.formatting import Cell
from core.portfolios.service import PortfolioError, PortfolioService
from core.strategies.service import Menu, MenuEntry
from portfolio import Portfolio

OPEN, ADD_TO, ADD_TO_NEW = 'library_open', 'library_add_to', 'library_add_to_new'  # menu actions
COLUMNS = ['Symbol', 'Name', 'Last close', 'Day', 'Prices since', 'Updated']


@dataclass(frozen=True)
class StockRow:
    symbol: str
    cells: list[Cell]


class StockLibraryView(Protocol):
    def show_title(self, text: str) -> None: ...
    def show_stocks(self, rows: list[StockRow]) -> None: ...
    def show_notice(self, text: str) -> None: ...
    def close(self) -> None: ...


class LibraryExplorer(Protocol):
    """The part of the Explorer controller this one drives."""

    def add_symbol(self, symbol: str) -> None: ...
    def open_portfolio(self, portfolio: Portfolio) -> None: ...
    def refresh_portfolio(self, portfolio: Portfolio) -> None: ...
    def begin_rename(self, portfolio_id: str) -> None: ...


def stock_rows(stocks: pd.DataFrame, names: dict[str, str]) -> list[StockRow]:
    """Table rows from prices.store.stored_stocks() and a symbol -> company name lookup."""
    rows = []
    for stock in stocks.itertuples():
        change = None
        if pd.notna(stock.previous_close) and stock.previous_close:
            change = (stock.last_close / stock.previous_close - 1) * 100
        updated = '—' if pd.isna(stock.checked_at) else f'{datetime.fromtimestamp(stock.checked_at):%Y-%m-%d}'
        rows.append(StockRow(stock.symbol, [
            Cell(stock.symbol), Cell(names.get(stock.symbol, '')),
            Cell(f'{stock.last_close:,.2f}', align_right=True),
            Cell('—' if change is None else f'{change:+.2f}%', theme.change_color(change or 0) if change is not None
                 else None, align_right=True),
            Cell(f'{stock.first_date:%Y}', tooltip=f'{stock.days:,} trading days stored, '
                 f'{stock.first_date:%b %d, %Y} to {stock.last_date:%b %d, %Y}', align_right=True),
            Cell(updated, tooltip='When Yahoo was last asked for new prices', align_right=True)]))
    return rows


class StockLibraryController:
    def __init__(self, view: StockLibraryView, loader: BackgroundLoader, portfolios: PortfolioService,
                 explorer: LibraryExplorer, stocks_source: Callable[[], pd.DataFrame],
                 names_source: Callable[[], dict[str, str]], history_source: Callable[[str], pd.DataFrame]) -> None:
        self.view = view
        self.loader = loader
        self.portfolios = portfolios
        self.explorer = explorer
        self.stocks_source = stocks_source  # stored stocks (see prices.store.stored_stocks)
        self.names_source = names_source  # symbol -> company name
        self.history_source = history_source  # downloads and stores a stock's prices
        self.symbols: list[str] = []
        self._names: dict[str, str] | None = None

    def start(self) -> None:
        self.view.show_title('Stock Library')
        self.view.show_notice('')
        self.refresh()

    def refresh(self) -> None:
        def work():
            if self._names is None:
                self._names = self.names_source()
            return self.stocks_source()
        self.loader.run(work, self._show, lambda error: self.view.show_notice(f'Could not read the library: {error}'))

    def _show(self, stocks: pd.DataFrame) -> None:
        rows = stock_rows(stocks, self._names or {})
        self.symbols = [row.symbol for row in rows]
        self.view.show_stocks(rows)

    # --- growing the library ---

    def add(self, symbol: str) -> None:
        """The user picked a stock in the panel's search box: download and store its prices."""
        if symbol in self.symbols:
            self.view.show_notice(f'{symbol} is already in the library.')
            return
        self.view.show_notice(f'Downloading {symbol} price history…')
        self.loader.run(lambda: self.history_source(symbol), lambda daily: self._added(symbol, daily),
                        lambda error: self.view.show_notice(f'Could not download {symbol}: {error}'))

    def _added(self, symbol: str, daily: pd.DataFrame) -> None:
        if daily.empty:
            self.view.show_notice(f'No price history found for {symbol}, so it was not added.')
            return
        self.view.show_notice(f'Added {symbol}: {len(daily):,} trading days since {daily.index[0]:%Y}.')
        self.refresh()

    # --- right-click menu ---

    def menu_for(self, symbol: str) -> Menu:
        saved = self.portfolios.saved()
        targets = [MenuEntry(summary.name, ADD_TO, summary.id) for summary in saved]
        children = targets + ([None] if targets else []) + [MenuEntry('New portfolio…', ADD_TO_NEW)]
        return [MenuEntry(f'Open {symbol}', OPEN), None, MenuEntry('Add to portfolio', children=tuple(children))]

    def menu_action(self, action: str, symbol: str, argument: str | None = None) -> None:
        try:
            if action == OPEN:
                self.explorer.add_symbol(symbol)
            elif action == ADD_TO:
                self._add_to(symbol, argument)
            elif action == ADD_TO_NEW:
                portfolio = self.portfolios.create_default()
                self.portfolios.add_symbols(portfolio.id, [symbol])
                self.explorer.open_portfolio(self.portfolios.get(portfolio.id))
                self.explorer.begin_rename(portfolio.id)
                self.view.show_notice(f'Added {symbol} to a new portfolio; type its name in the Explorer.')
            else:
                raise ValueError(f'Unknown stock library action {action!r}')
        except PortfolioError as error:
            self.view.show_notice(str(error))

    def _add_to(self, symbol: str, portfolio_id: str) -> None:
        added, _ = self.portfolios.add_symbols(portfolio_id, [symbol])
        portfolio = self.portfolios.get(portfolio_id)
        if portfolio is None:
            raise PortfolioError('That portfolio no longer exists (its file was removed).')
        self.explorer.refresh_portfolio(portfolio)  # updates the tree if the portfolio is open
        self.view.show_notice(f'Added {symbol} to "{portfolio.name}".' if added
                              else f'{symbol} is already in "{portfolio.name}".')

    def done(self) -> None:
        self.view.close()

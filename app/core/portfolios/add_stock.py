"""The Add Stock wizard: pick any number of stocks for a portfolio, then press Done.

Each pick is saved at once (auto-save), so closing the panel never loses anything. The renderer implements
`AddStockView` and forwards the search bar's pick and the Done button here.
"""
from typing import Protocol

from core.portfolios.controller import PortfolioExplorer
from core.portfolios.service import PortfolioError, PortfolioService
from portfolio import Portfolio


class AddStockView(Protocol):
    def show_title(self, text: str) -> None: ...
    def show_members(self, symbols: list[str]) -> None:
        """List the portfolio's stocks (what is in it right now)."""
    def show_notice(self, text: str) -> None: ...
    def close(self) -> None: ...


class AddStockController:
    def __init__(self, view: AddStockView, service: PortfolioService, explorer: PortfolioExplorer) -> None:
        self.view = view
        self.service = service
        self.explorer = explorer
        self.portfolio_id: str | None = None

    def start(self, portfolio: Portfolio) -> None:
        self.portfolio_id = portfolio.id
        self.view.show_title(f'Add stocks to "{portfolio.name}"')
        self.view.show_members(portfolio.symbols)
        self.view.show_notice('')

    def add(self, symbol: str) -> None:
        """The user picked a stock in the search bar."""
        try:
            added, already = self.service.add_symbols(self.portfolio_id, [symbol])
            portfolio = self.service.get(self.portfolio_id)
        except PortfolioError as error:  # the portfolio's file was removed while the panel was open
            self.view.show_notice(str(error))
            return
        self.explorer.refresh_portfolio(portfolio)
        self.view.show_members(portfolio.symbols)
        if added:
            self.view.show_notice(f'Added {added[0]}.')
        elif already:
            self.view.show_notice(f'{already[0]} is already in this portfolio.')

    def done(self) -> None:
        self.view.close()

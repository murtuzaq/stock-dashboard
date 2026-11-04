"""The rules for saved portfolios: naming, renaming, adding and removing stocks. Every change is saved at once."""
from dataclasses import dataclass

from portfolio import Portfolio, normalize_symbol, repository

DEFAULT_NAME = 'Portfolio'


class PortfolioError(ValueError):
    """A change the user asked for that is not allowed; the message says why, in plain words."""


@dataclass(frozen=True)
class PortfolioSummary:
    id: str
    name: str
    stock_count: int


class PortfolioService:
    def get(self, portfolio_id: str) -> Portfolio | None:
        return repository.get(portfolio_id)

    def saved(self) -> list[PortfolioSummary]:
        return [PortfolioSummary(p.id, p.name, len(p.symbols)) for p in repository.all_portfolios()]

    def create_default(self) -> Portfolio:
        """A new empty portfolio called 'Portfolio 1' (the lowest number not used by any saved portfolio)."""
        taken = {p.name.lower() for p in repository.all_portfolios()}
        number = 1
        while f'{DEFAULT_NAME} {number}'.lower() in taken:
            number += 1
        portfolio = Portfolio(f'{DEFAULT_NAME} {number}')
        repository.save(portfolio)
        return portfolio

    def rename(self, portfolio_id: str, name: str) -> Portfolio:
        name = name.strip()
        if not name:
            raise PortfolioError('A portfolio needs a name.')
        portfolio = self._require(portfolio_id)
        for other in repository.all_portfolios():
            if other.id != portfolio_id and other.name.lower() == name.lower():
                raise PortfolioError(f'A portfolio called "{other.name}" already exists.')
        portfolio.name = name
        repository.save(portfolio)
        return portfolio

    def add_symbols(self, portfolio_id: str, symbols: list[str]) -> tuple[list[str], list[str]]:
        """Add stocks; returns (added, already_in_the_portfolio). Order is kept, repeats are ignored."""
        portfolio = self._require(portfolio_id)
        added, present = [], []
        for symbol in map(normalize_symbol, symbols):
            if not symbol:
                continue
            if portfolio.has(symbol) or symbol in added:
                present.append(symbol)
            else:
                added.append(symbol)
        if added:
            portfolio.symbols.extend(added)
            repository.save(portfolio)
        return added, present

    def remove_symbol(self, portfolio_id: str, symbol: str) -> Portfolio:
        portfolio = self._require(portfolio_id)
        symbol = normalize_symbol(symbol)
        if symbol in portfolio.symbols:
            portfolio.symbols.remove(symbol)
            repository.save(portfolio)
        return portfolio

    def delete(self, portfolio_id: str) -> None:
        repository.delete(portfolio_id)

    def _require(self, portfolio_id: str) -> Portfolio:
        portfolio = repository.get(portfolio_id)
        if portfolio is None:
            raise PortfolioError('That portfolio no longer exists (its file was removed).')
        return portfolio

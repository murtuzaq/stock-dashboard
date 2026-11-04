"""What the user can do with portfolios: File > New / Load, rename in place, and the right-click actions.

Widgets are reached only through the protocols below. The rules (naming, duplicates) are in PortfolioService; the
Explorer controller keeps the tree in step with what is saved.
"""
from collections.abc import Callable
from typing import Protocol

from core.portfolios import actions
from core.portfolios.service import PortfolioError, PortfolioService, PortfolioSummary
from portfolio import Portfolio


class PortfolioExplorer(Protocol):
    """The part of the Explorer controller this one drives."""

    def open_portfolio(self, portfolio: Portfolio) -> None: ...
    def refresh_portfolio(self, portfolio: Portfolio) -> None: ...
    def close_portfolio(self, portfolio_id: str) -> None: ...
    def begin_rename(self, portfolio_id: str) -> None: ...
    def open_portfolio_ids(self) -> set[str]: ...


class PortfolioDialogs(Protocol):
    def confirm(self, text: str) -> bool: ...
    def notify(self, text: str) -> None: ...
    def choose_portfolio(self, options: list[PortfolioSummary]) -> str | None:
        """Let the user pick one of these saved portfolios (its id), or cancel (None)."""


class _Node(Protocol):  # what an Explorer node offers (core.explorer.controller.Node, which is read-only)
    @property
    def symbol(self) -> str: ...

    @property
    def portfolio(self) -> str | None: ...


class PortfolioController:
    def __init__(self, service: PortfolioService, explorer: PortfolioExplorer, dialogs: PortfolioDialogs,
                 open_add_stock: Callable[[Portfolio], None]) -> None:
        self.service = service
        self.explorer = explorer
        self.dialogs = dialogs
        self.open_add_stock = open_add_stock  # opens the Add Stock wizard panel for a portfolio

    # --- File menu ---

    def new_portfolio(self) -> None:
        """A new empty portfolio with a default name, ready for the user to type a better one."""
        portfolio = self.service.create_default()
        self.explorer.open_portfolio(portfolio)
        self.explorer.begin_rename(portfolio.id)

    def load_portfolio(self) -> None:
        """Open a saved portfolio that is not already showing."""
        saved = self.service.saved()
        open_ids = self.explorer.open_portfolio_ids()
        options = [summary for summary in saved if summary.id not in open_ids]
        if not options:
            self.dialogs.notify('All saved portfolios are already open.' if saved else 'No saved portfolios yet. '
                                'Use File > New Portfolio to create one.')
            return
        chosen = self.dialogs.choose_portfolio(options)
        if not chosen:
            return
        try:
            self.explorer.open_portfolio(self._get(chosen))
        except PortfolioError as error:  # its file was removed while the list was open
            self.dialogs.notify(str(error))

    # --- Explorer right-click menu and in-place rename ---

    def handle(self, action: str, node: _Node, argument: str | None = None) -> None:
        """Run an action from core.portfolios.actions. `node` is where the user clicked."""
        if action not in actions.ALL:
            raise ValueError(f'Unknown portfolio action {action!r}')
        try:
            getattr(self, f'_{action}')(node, argument)
        except PortfolioError as error:
            self.dialogs.notify(str(error))
            self._resync(node)

    def _add_stock(self, node, argument) -> None:
        self.open_add_stock(self._get(node.portfolio))

    def _rename_portfolio(self, node, argument) -> None:
        """`argument` is the typed name; from the menu (no name yet) the user is asked in place."""
        if argument is None:
            self.explorer.begin_rename(node.portfolio)
            return
        self.explorer.refresh_portfolio(self.service.rename(node.portfolio, argument))

    def _close_portfolio(self, node, argument) -> None:
        self.explorer.close_portfolio(node.portfolio)

    def _delete_portfolio(self, node, argument) -> None:
        portfolio = self._get(node.portfolio)
        if self.dialogs.confirm(f'Delete portfolio "{portfolio.name}"?\n\nThis removes its file. '
                                'The stocks themselves and their strategies are not affected.'):
            self.service.delete(portfolio.id)
            self.explorer.close_portfolio(portfolio.id)

    def _add_to_portfolio(self, node, argument) -> None:
        """Add the stock to another portfolio (it stays where it is)."""
        portfolio = self._get(argument)
        _, already = self.service.add_symbols(portfolio.id, [node.symbol])
        self.explorer.refresh_portfolio(self._get(portfolio.id))
        if already:
            self.dialogs.notify(f'{node.symbol} is already in "{portfolio.name}".')

    def _add_to_new_portfolio(self, node, argument) -> None:
        portfolio = self.service.create_default()
        self.service.add_symbols(portfolio.id, [node.symbol])
        self.explorer.open_portfolio(self._get(portfolio.id))
        self.explorer.begin_rename(portfolio.id)

    def _remove_from_portfolio(self, node, argument) -> None:
        self.explorer.refresh_portfolio(self.service.remove_symbol(node.portfolio, node.symbol))

    # --- helpers ---

    def _get(self, portfolio_id: str | None) -> Portfolio:
        portfolio = self.service.get(portfolio_id) if portfolio_id else None
        if portfolio is None:
            raise PortfolioError('That portfolio no longer exists (its file was removed).')
        return portfolio

    def _resync(self, node) -> None:
        """After a refused change, put the tree back to what is saved (e.g. the old name after a bad rename)."""
        portfolio = self.service.get(node.portfolio) if node.portfolio else None
        if portfolio:
            self.explorer.refresh_portfolio(portfolio)
        elif node.portfolio:
            self.explorer.close_portfolio(node.portfolio)  # its file is gone: drop the stale row


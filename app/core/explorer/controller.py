"""The Explorer's behaviour: which stocks and portfolios are open, what is selected, what a right-click offers.

The tree widget implements `ExplorerTreeView` and reports what the user clicked; this controller decides what that
means (selection rules, what to show next) and tells the rest of the app. It also implements the views that the
strategy and portfolio controllers drive (add a stock, refresh strategies, open a portfolio ...).

A stock can appear more than once (on its own, and inside portfolios), so a tree position is a `Scope`:
(portfolio id or None, symbol). Strategies belong to the symbol and are shared by every scope showing it.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple, Protocol

from core.dashboard.layout import STRATEGIES_BEFORE, VIEWS, strategy_id_of, strategy_key
from core.explorer.entries import StrategyEntry, strategy_entries
from core.explorer.selection import Entry, resolve_selection
from core.portfolios import actions as portfolio_actions
from core.strategies.service import MenuEntry, menu_for
from portfolio import Portfolio

SYMBOL, VIEW, FOLDER, STRATEGY, PORTFOLIO = 'symbol', 'view', 'folder', 'strategy', 'portfolio'  # node kinds
FIRST_VIEW = VIEWS[0][0]


class Scope(NamedTuple):
    """One open stock in the tree: on its own (portfolio None) or inside a portfolio."""
    portfolio: str | None
    symbol: str


@dataclass(frozen=True)
class Node:
    """A tree node as the widget reports it. A portfolio node has an empty symbol and its id in `portfolio`."""
    symbol: str
    key: str | None  # view key, or 'strategy:<id>'; None for a stock, folder or portfolio
    kind: str
    is_library: bool = False
    portfolio: str | None = None  # the portfolio the node is or sits in, if any

    @property
    def scope(self) -> Scope:
        return Scope(self.portfolio, self.symbol)


@dataclass(frozen=True)
class TreeRow:
    """One child row under a stock, top to bottom."""
    kind: str  # VIEW or FOLDER
    key: str | None
    label: str


class ExplorerTreeView(Protocol):
    def add_portfolio(self, portfolio_id: str, name: str) -> None: ...
    def rename_portfolio(self, portfolio_id: str, name: str) -> None:
        """Show this name on the portfolio's row (silently: it is not a user edit)."""
    def begin_rename(self, portfolio_id: str) -> None:
        """Select the portfolio's row and let the user type a new name in place."""
    def remove_portfolio(self, portfolio_id: str) -> None:
        """Remove the portfolio's row and the stocks inside it."""
    def add_symbol(self, scope: Scope, rows: list[TreeRow], strategies: list[StrategyEntry]) -> None:
        """Add the stock's row (inside its portfolio's row if the scope has one)."""
    def remove_symbol(self, scope: Scope) -> None: ...
    def set_strategies(self, symbol: str, strategies: list[StrategyEntry]) -> None:
        """Replace the strategy rows of every copy of this symbol in the tree."""
    def select_only(self, scope: Scope, keys: list[str]) -> None:
        """Open the stock and make exactly these rows the selection (the first becomes current)."""
    def restore_selection(self, scope: Scope, keys: list[str], current_key: str | None) -> None:
        """Silently re-select these rows (no selection-changed report)."""
    def apply_selection(self, scope: Scope, keep: list[str]) -> None:
        """Silently deselect every row that is not one of this stock's `keep` rows."""
    def read_selection(self) -> tuple[Node | None, list[Node]]:
        """The current node and every selected node."""


class ExplorerController:
    def __init__(self, view: ExplorerTreeView,
                 on_views_selected: Callable[[str, list[str]], None] | None = None,
                 on_strategy_action: Callable[[str, str, str], None] | None = None,
                 on_portfolio_action: Callable[[str, Node, str | None], None] | None = None,
                 on_selection_cleared: Callable[[], None] | None = None,
                 entries_source: Callable[[str], list[StrategyEntry]] = strategy_entries) -> None:
        self.view = view
        self.on_views_selected = on_views_selected  # (symbol, view keys in stacking order)
        self.on_strategy_action = on_strategy_action  # (action, symbol, strategy id or '')
        self.on_portfolio_action = on_portfolio_action  # (action, node, the menu entry's argument)
        self.on_selection_cleared = on_selection_cleared  # the stock being shown left the tree: nothing is selected
        self._entries_source = entries_source
        self.scopes: list[Scope] = []  # every open stock, in the order opened
        self.portfolios: dict[str, str] = {}  # open portfolios: id -> name, in the order opened
        self.strategies: dict[str, list[StrategyEntry]] = {}  # per symbol (shared by all its scopes)
        self.current_scope: Scope | None = None
        self.current_key: str | None = None
        self.selected: list[str] = []  # the current stock's selected keys, in stacking order

    @property
    def symbols(self) -> list[str]:
        """Symbols of the stocks open on their own (not inside a portfolio), in the order opened."""
        return [scope.symbol for scope in self.scopes if scope.portfolio is None]

    @property
    def current_symbol(self) -> str | None:
        return self.current_scope.symbol if self.current_scope else None

    # --- ExplorerView (used by the strategy controller and the search bar) ---

    def add_symbol(self, symbol: str) -> None:
        """Open a stock on its own (unless already open) and select its first view."""
        self._open(Scope(None, symbol))
        self.view.select_only(Scope(None, symbol), [FIRST_VIEW])

    def refresh_strategies(self) -> None:
        """Re-read the strategy files (after creating, editing or deleting), keeping the selection if possible."""
        for symbol in self.strategies:
            self.strategies[symbol] = self._entries_source(symbol)
            self.view.set_strategies(symbol, self.strategies[symbol])
        scope = self.current_scope
        if scope is None:
            return
        keys = self.ordered_keys(scope.symbol)
        still_selected = [key for key in keys if key in self.selected]
        if self.current_key not in keys or not still_selected:
            self.view.select_only(scope, [FIRST_VIEW])  # e.g. the selected strategy was deleted
            return
        self.view.restore_selection(scope, still_selected, self.current_key)
        self.on_selection_changed(*self.view.read_selection())

    def select_strategy(self, symbol: str, strategy_id: str) -> None:
        """Select a strategy under the stock being viewed (if it is this symbol), else under the stock on its own."""
        scope = self.current_scope if self.current_symbol == symbol else Scope(None, symbol)
        newly_opened = scope not in self.scopes
        self._open(scope)
        key = strategy_key(strategy_id)
        if key in self.ordered_keys(symbol):
            self.view.select_only(scope, [key])
        elif newly_opened:
            self.view.select_only(scope, [FIRST_VIEW])  # a stock opened just for this: show something

    # --- portfolios (used by the portfolio controller) ---

    def open_portfolio(self, portfolio: Portfolio) -> None:
        """Show a portfolio and its stocks (or bring its row up to date if it is already open)."""
        if portfolio.id not in self.portfolios:
            self.portfolios[portfolio.id] = portfolio.name
            self.view.add_portfolio(portfolio.id, portfolio.name)
        self.refresh_portfolio(portfolio)

    def refresh_portfolio(self, portfolio: Portfolio) -> None:
        """Make the tree match the saved portfolio: its name, and which stocks it holds."""
        if portfolio.id not in self.portfolios:
            return
        self.portfolios[portfolio.id] = portfolio.name
        self.view.rename_portfolio(portfolio.id, portfolio.name)
        for symbol in portfolio.symbols:
            self._open(Scope(portfolio.id, symbol))
        for scope in [s for s in self.scopes if s.portfolio == portfolio.id and s.symbol not in portfolio.symbols]:
            self._drop(scope)

    def close_portfolio(self, portfolio_id: str) -> None:
        """Take a portfolio and its stocks out of the tree (nothing is deleted)."""
        if portfolio_id not in self.portfolios:
            return
        for scope in [s for s in self.scopes if s.portfolio == portfolio_id]:
            self._drop(scope, from_tree=False)
        del self.portfolios[portfolio_id]
        self.view.remove_portfolio(portfolio_id)

    def begin_rename(self, portfolio_id: str) -> None:
        self.view.begin_rename(portfolio_id)

    def open_portfolio_ids(self) -> set[str]:
        return set(self.portfolios)

    # --- the tree reports clicks ---

    def on_selection_changed(self, current: Node | None, selected: list[Node]) -> None:
        if current is None or current.kind == PORTFOLIO:  # a portfolio has no views: keep showing what was showing
            return
        if current.kind == SYMBOL:  # a stock was clicked: open its first view
            self.view.select_only(current.scope, [FIRST_VIEW])
            return
        scope = current.scope
        chosen = {node.key for node in selected if node.scope == scope and node.kind in (VIEW, STRATEGY)}
        strategy_keys = {entry.key for entry in self.strategies[scope.symbol]}
        rows = [Entry(key, key in strategy_keys, key in chosen) for key in self.ordered_keys(scope.symbol)]
        keep = resolve_selection(rows, current.key)
        # Only one stock's views at a time, and only one strategy at a time.
        self.view.apply_selection(scope, keep)
        self.current_scope, self.current_key, self.selected = scope, current.key, keep
        if keep and self.on_views_selected:  # Ctrl+clicking away the last view keeps showing it
            self.on_views_selected(scope.symbol, keep)

    def rename_requested(self, portfolio_id: str, text: str) -> None:
        """The user typed a new name into a portfolio's row."""
        if self.on_portfolio_action:
            self.on_portfolio_action(portfolio_actions.RENAME, Node('', None, PORTFOLIO, portfolio=portfolio_id), text)

    def menu_for(self, node: Node) -> list[MenuEntry | None]:
        """The right-click menu for a node."""
        if node.kind == PORTFOLIO:
            return [MenuEntry('Add Stock…', portfolio_actions.ADD_STOCK),
                    MenuEntry('Rename…', portfolio_actions.RENAME), None,
                    MenuEntry('Close Portfolio', portfolio_actions.CLOSE),
                    MenuEntry('Delete Portfolio…', portfolio_actions.DELETE)]
        entries = menu_for(node.kind, node.symbol, node.is_library)
        if node.kind == SYMBOL:
            entries = entries + [None, self._add_to_portfolio_entry(node)]
            if node.portfolio:
                entries.append(MenuEntry('Remove from portfolio', portfolio_actions.REMOVE_FROM))
        return entries

    def menu_action(self, action: str, node: Node, argument: str | None = None) -> None:
        if action in portfolio_actions.ALL:
            if self.on_portfolio_action:
                self.on_portfolio_action(action, node, argument)
            return
        strategy_id = strategy_id_of(node.key) if node.kind == STRATEGY else ''
        if self.on_strategy_action:
            self.on_strategy_action(action, node.symbol, strategy_id)

    def _add_to_portfolio_entry(self, node: Node) -> MenuEntry:
        """'Add to portfolio >' listing every other open portfolio, then 'New portfolio…'."""
        targets = [MenuEntry(name, portfolio_actions.ADD_TO, portfolio_id)
                   for portfolio_id, name in self.portfolios.items() if portfolio_id != node.portfolio]
        children = targets + ([None] if targets else []) + [MenuEntry('New portfolio…', portfolio_actions.ADD_TO_NEW)]
        return MenuEntry('Add to portfolio', children=tuple(children))

    # --- the layout of one stock's rows ---

    def ordered_keys(self, symbol: str) -> list[str]:
        """The stock's selectable rows, top to bottom: views, with its strategies just before STRATEGIES_BEFORE."""
        keys = []
        for key, _ in VIEWS:
            if key == STRATEGIES_BEFORE:
                keys.extend(entry.key for entry in self.strategies[symbol])
            keys.append(key)
        return keys

    def _open(self, scope: Scope) -> None:
        """Make sure the stock is in the tree (building its rows the first time)."""
        if scope.symbol not in self.strategies:
            self.strategies[scope.symbol] = self._entries_source(scope.symbol)
        if scope not in self.scopes:
            self.scopes.append(scope)
            self.view.add_symbol(scope, self._rows(), self.strategies[scope.symbol])

    def _drop(self, scope: Scope, from_tree: bool = True) -> None:
        self.scopes.remove(scope)
        if from_tree:
            self.view.remove_symbol(scope)
        if self.current_scope == scope:
            self.current_scope, self.current_key, self.selected = None, None, []
            if self.on_selection_cleared:
                self.on_selection_cleared()

    @staticmethod
    def _rows() -> list[TreeRow]:
        rows = []
        for key, label in VIEWS:
            if key == STRATEGIES_BEFORE:
                rows.append(TreeRow(FOLDER, None, 'Strategies'))
            rows.append(TreeRow(VIEW, key, label))
        return rows

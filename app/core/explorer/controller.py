"""The Explorer's behaviour: which stocks are open, what is selected, what a right-click offers.

The tree widget implements `ExplorerTreeView` and reports what the user clicked; this controller decides what that
means (selection rules, what to show next) and tells the rest of the app. It also implements the `ExplorerView`
that core.strategies.controller drives (add a stock, refresh strategies, select a strategy).
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from core.dashboard.layout import STRATEGIES_BEFORE, VIEWS, strategy_id_of, strategy_key
from core.explorer.entries import StrategyEntry, strategy_entries
from core.explorer.selection import Entry, resolve_selection
from core.strategies.service import MenuEntry, menu_for

SYMBOL, VIEW, FOLDER, STRATEGY = 'symbol', 'view', 'folder', 'strategy'  # kinds of tree node
FIRST_VIEW = VIEWS[0][0]


@dataclass(frozen=True)
class Node:
    """A tree node as the widget reports it."""
    symbol: str
    key: str | None  # view key, or 'strategy:<id>'; None for a symbol or folder
    kind: str
    is_library: bool = False


@dataclass(frozen=True)
class TreeRow:
    """One child row under a symbol, top to bottom."""
    kind: str  # VIEW or FOLDER
    key: str | None
    label: str


class ExplorerTreeView(Protocol):
    def add_symbol(self, symbol: str, rows: list[TreeRow], strategies: list[StrategyEntry]) -> None: ...
    def set_strategies(self, symbol: str, strategies: list[StrategyEntry]) -> None: ...
    def select_only(self, symbol: str, keys: list[str]) -> None:
        """Open the symbol and make exactly these rows the selection (the first becomes current)."""
    def restore_selection(self, symbol: str, keys: list[str], current_key: str | None) -> None:
        """Silently re-select these rows (no selection-changed report)."""
    def apply_selection(self, symbol: str, keep: list[str]) -> None:
        """Silently deselect every row that is not one of this symbol's `keep` rows."""
    def read_selection(self) -> tuple[Node | None, list[Node]]:
        """The current node and every selected node."""


class ExplorerController:
    def __init__(self, view: ExplorerTreeView,
                 on_views_selected: Callable[[str, list[str]], None] | None = None,
                 on_strategy_action: Callable[[str, str, str], None] | None = None,
                 entries_source: Callable[[str], list[StrategyEntry]] = strategy_entries) -> None:
        self.view = view
        self.on_views_selected = on_views_selected  # (symbol, view keys in stacking order)
        self.on_strategy_action = on_strategy_action  # (action, symbol, strategy id or '')
        self._entries_source = entries_source
        self.strategies: dict[str, list[StrategyEntry]] = {}  # per open symbol, in the order opened
        self.current_symbol: str | None = None
        self.current_key: str | None = None
        self.selected: list[str] = []  # the current symbol's selected keys, in stacking order

    @property
    def symbols(self) -> list[str]:
        return list(self.strategies)

    # --- ExplorerView (used by the strategy controller and the search bar) ---

    def add_symbol(self, symbol: str) -> None:
        """Add a symbol (unless already present) and select its first view."""
        if symbol not in self.strategies:
            entries = self._entries_source(symbol)
            self.strategies[symbol] = entries
            self.view.add_symbol(symbol, self._rows(), entries)
        self.view.select_only(symbol, [FIRST_VIEW])

    def refresh_strategies(self) -> None:
        """Re-read the strategy files (after creating, editing or deleting), keeping the selection if possible."""
        for symbol in self.strategies:
            self.strategies[symbol] = self._entries_source(symbol)
            self.view.set_strategies(symbol, self.strategies[symbol])
        symbol = self.current_symbol
        if symbol is None:
            return
        keys = self.ordered_keys(symbol)
        still_selected = [key for key in keys if key in self.selected]
        if self.current_key not in keys or not still_selected:
            self.view.select_only(symbol, [FIRST_VIEW])  # e.g. the selected strategy was deleted
            return
        self.view.restore_selection(symbol, still_selected, self.current_key)
        self.on_selection_changed(*self.view.read_selection())

    def select_strategy(self, symbol: str, strategy_id: str) -> None:
        if symbol not in self.strategies:
            self.add_symbol(symbol)
        key = strategy_key(strategy_id)
        if key in self.ordered_keys(symbol):
            self.view.select_only(symbol, [key])

    # --- the tree reports clicks ---

    def on_selection_changed(self, current: Node | None, selected: list[Node]) -> None:
        if current is None:
            return
        if current.kind == SYMBOL:  # a symbol was clicked: open its first view
            self.view.select_only(current.symbol, [FIRST_VIEW])
            return
        symbol = current.symbol
        chosen = {node.key for node in selected if node.symbol == symbol and node.kind in (VIEW, STRATEGY)}
        strategy_keys = {entry.key for entry in self.strategies[symbol]}
        rows = [Entry(key, key in strategy_keys, key in chosen) for key in self.ordered_keys(symbol)]
        keep = resolve_selection(rows, current.key)
        # Only one symbol's views at a time, and only one strategy at a time.
        self.view.apply_selection(symbol, keep)
        self.current_symbol, self.current_key, self.selected = symbol, current.key, keep
        if keep and self.on_views_selected:  # Ctrl+clicking away the last view keeps showing it
            self.on_views_selected(symbol, keep)

    def menu_for(self, node: Node) -> list[MenuEntry | None]:
        """The right-click menu for a node."""
        return menu_for(node.kind, node.symbol, node.is_library)

    def menu_action(self, action: str, node: Node) -> None:
        strategy_id = strategy_id_of(node.key) if node.kind == STRATEGY else ''
        if self.on_strategy_action:
            self.on_strategy_action(action, node.symbol, strategy_id)

    # --- the layout of one symbol's rows ---

    def ordered_keys(self, symbol: str) -> list[str]:
        """The symbol's selectable rows, top to bottom: views, with its strategies just before STRATEGIES_BEFORE."""
        keys = []
        for key, _ in VIEWS:
            if key == STRATEGIES_BEFORE:
                keys.extend(entry.key for entry in self.strategies[symbol])
            keys.append(key)
        return keys

    @staticmethod
    def _rows() -> list[TreeRow]:
        rows = []
        for key, label in VIEWS:
            if key == STRATEGIES_BEFORE:
                rows.append(TreeRow(FOLDER, None, 'Strategies'))
            rows.append(TreeRow(VIEW, key, label))
        return rows

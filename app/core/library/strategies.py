"""Tools > Strategies: every saved strategy in one place, to browse, try on a stock, copy, edit or create.

Library templates come first (they work on any stock), then each stock's own strategies. The actions themselves
(wizard, copy, delete) are the same ones the Explorer menu uses (core.strategies.controller); this controller
decides which apply and keeps the list in step after each change.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from core.strategies.service import Menu, MenuEntry, StrategyService
from strategy import About, Strategy, describe

LIBRARY_GROUP = 'Library templates'
# Actions on the selected strategy (also the right-click menu).
TRY, COPY_TO, SAVE_TO_LIBRARY, EDIT, DELETE, NEW_TEMPLATE = (
    'try', 'copy_to', 'save_to_library', 'edit', 'delete', 'new_template')


@dataclass(frozen=True)
class StrategyItem:
    id: str
    name: str
    symbol: str | None  # None for a library template
    description: str  # the rules in plain English
    about: About = field(default_factory=About)  # summary, reasoning, caveats and references (may be empty)

    @property
    def is_library(self) -> bool:
        return self.symbol is None


class StrategyLibraryView(Protocol):
    def show_title(self, text: str) -> None: ...
    def show_strategies(self, groups: list[tuple[str, list[StrategyItem]]]) -> None: ...
    def show_detail(self, item: StrategyItem | None, actions: list[MenuEntry]) -> None:
        """The selected strategy's rules and the buttons that apply to it (none selected: item None)."""
    def show_notice(self, text: str) -> None: ...
    def close(self) -> None: ...


class StrategyActions(Protocol):
    """core.strategies.controller.StrategyController: the actions shared with the Explorer menu."""

    def handle(self, action: str, symbol: str | None, strategy_id: str) -> None: ...


class LibraryExplorer(Protocol):
    def select_strategy(self, symbol: str, strategy_id: str) -> None: ...


class StrategyLibraryController:
    def __init__(self, view: StrategyLibraryView, service: StrategyService, actions: StrategyActions,
                 explorer: LibraryExplorer, current_symbol: Callable[[], str | None],
                 ask_symbol: Callable[[str], str | None]) -> None:
        self.view = view
        self.service = service
        self.actions = actions
        self.explorer = explorer
        self.current_symbol = current_symbol  # the stock on screen, if any
        self.ask_symbol = ask_symbol  # asks the user to pick a stock (None if they cancel)
        self.items: dict[str, StrategyItem] = {}
        self.selected: str | None = None

    def start(self) -> None:
        self.view.show_title('Strategy Library')
        self.view.show_notice('')
        self.refresh()

    def refresh(self) -> None:
        """Re-read the saved strategies (after any change), keeping the selection if it still exists."""
        strategies = self.service.all_strategies()
        self.items = {s.id: StrategyItem(s.id, s.name, s.symbol, describe(s), s.about) for s in strategies}
        groups: dict[str, list[StrategyItem]] = {LIBRARY_GROUP: []}
        for strategy in sorted(strategies, key=lambda s: (s.symbol is not None, s.symbol or '', s.name.lower())):
            groups.setdefault(strategy.symbol or LIBRARY_GROUP, []).append(self.items[strategy.id])
        self.view.show_strategies(list(groups.items()))
        self.select(self.selected if self.selected in self.items else None)

    def select(self, strategy_id: str | None) -> None:
        self.selected = strategy_id
        item = self.items.get(strategy_id) if strategy_id else None
        self.view.show_detail(item, self.actions_for(item) if item else [])

    # --- what can be done with a strategy ---

    def actions_for(self, item: StrategyItem) -> list[MenuEntry]:
        symbol = self.current_symbol()
        if item.is_library:
            target = f'Backtest on {symbol}' if symbol else 'Backtest on a stock…'
        elif symbol and symbol != item.symbol:
            target = f'Copy to {symbol} and backtest'
        else:
            target = f'Backtest on {item.symbol}'
        entries = [MenuEntry(target, TRY), MenuEntry('Copy to another stock…', COPY_TO)]
        if not item.is_library:
            entries.append(MenuEntry('Save to Library', SAVE_TO_LIBRARY))
        entries += [MenuEntry('Edit…', EDIT), MenuEntry('Delete…', DELETE)]
        return entries

    def menu_for(self, strategy_id: str) -> Menu:
        item = self.items.get(strategy_id)
        return [*self.actions_for(item), None, MenuEntry('New template…', NEW_TEMPLATE)] if item else \
            [MenuEntry('New template…', NEW_TEMPLATE)]

    def run(self, action: str, strategy_id: str | None = None) -> None:
        """A button or menu item was chosen (for the selected strategy unless another is given)."""
        if action == NEW_TEMPLATE:
            self.actions.handle('new', None, '')  # the wizard; the list refreshes when it saves
            return
        item = self.items.get(strategy_id or self.selected or '')
        if item is None:
            self.view.show_notice('Choose a strategy first.')
            return
        context = item.symbol or self.current_symbol()
        if action == TRY:
            self._try(item)
        elif action == COPY_TO:
            self.actions.handle('copy_to', context, item.id)
        elif action == SAVE_TO_LIBRARY:
            self.actions.handle('save_to_library', item.symbol, item.id)
            self.view.show_notice(f'"{item.name}" was copied to the library templates.')
        elif action in (EDIT, DELETE):
            self.actions.handle(action, context, item.id)
        else:
            raise ValueError(f'Unknown strategy library action {action!r}')
        self.refresh()

    def _try(self, item: StrategyItem) -> None:
        symbol = self.current_symbol()
        if item.is_library:
            symbol = symbol or self.ask_symbol(f'Backtest "{item.name}" on which stock?')
            if symbol:
                self.explorer.select_strategy(symbol, item.id)  # templates are listed under every stock
        elif symbol and symbol != item.symbol:
            copy = self.service.copy_to(item.id, symbol)
            self.explorer.select_strategy(symbol, copy.id)
            self.view.show_notice(f'Copied "{item.name}" to {symbol}.')
        else:
            self.explorer.select_strategy(item.symbol, item.id)

    def done(self) -> None:
        self.view.close()

"""What the strategy actions (Explorer right-click menu, results panel) do to the saved strategies.

No dialogs here: the renderer asks the user, then calls these. Each action returns what the renderer needs to
refresh and select.
"""
from dataclasses import dataclass

from strategy import Strategy, repository

# Action names, as emitted by the Explorer menu and dispatched by the renderer.
NEW, EDIT, COPY_HERE, DUPLICATE, COPY_TO, SAVE_TO_LIBRARY, DELETE = (
    'new', 'edit', 'copy_here', 'duplicate', 'copy_to', 'save_to_library', 'delete')


@dataclass(frozen=True)
class MenuEntry:
    text: str
    action: str


# None in a menu is a separator.
Menu = list[MenuEntry | None]


def menu_for(kind: str, symbol: str, is_library: bool) -> Menu:
    """The right-click menu for a tree node: kind is 'symbol', 'folder', 'view' or 'strategy'."""
    new = MenuEntry('New Strategy…', NEW)
    if kind in ('symbol', 'folder', 'view'):
        return [new]
    if kind != 'strategy':
        return []
    if is_library:
        return [MenuEntry(f'Copy to {symbol} and customise…', COPY_HERE), MenuEntry('Edit library template…', EDIT),
                MenuEntry('Copy to another stock…', COPY_TO), None, MenuEntry('Delete from library…', DELETE),
                None, new]
    return [MenuEntry('Edit…', EDIT), MenuEntry('Duplicate', DUPLICATE), MenuEntry('Copy to another stock…', COPY_TO),
            MenuEntry('Save to Library', SAVE_TO_LIBRARY), None, MenuEntry('Delete…', DELETE), None, new]


class StrategyService:
    def get(self, strategy_id: str) -> Strategy | None:
        return repository.get(strategy_id)

    def copy_here(self, strategy_id: str, symbol: str) -> Strategy:
        """Library template -> this stock's own copy."""
        return repository.copy(strategy_id, symbol)

    def duplicate(self, strategy_id: str) -> Strategy:
        original = repository.get(strategy_id)
        return repository.copy(strategy_id, original.symbol, f'{original.name} (copy)')

    def copy_to(self, strategy_id: str, symbol: str) -> Strategy:
        return repository.copy(strategy_id, symbol)

    def save_to_library(self, strategy_id: str) -> Strategy:
        return repository.copy(strategy_id, None)

    def delete_prompt(self, strategy_id: str) -> str:
        strategy = repository.get(strategy_id)
        where = 'the library' if strategy.symbol is None else strategy.symbol
        return f'Delete "{strategy.name}" from {where}?\n\nThis removes its file from the strategies folder.'

    def delete(self, strategy_id: str) -> None:
        repository.delete(strategy_id)

    def update_costs(self, strategy_id: str, costs) -> Strategy:
        strategy = repository.get(strategy_id)
        strategy.costs = costs
        repository.save(strategy)
        return strategy

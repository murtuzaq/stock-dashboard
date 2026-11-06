"""The Explorer's selection rules: several views of one stock may be stacked, but only one strategy at a time,
unless the Backtest view is selected: it compares any number of strategies."""
from dataclasses import dataclass

from core.dashboard.layout import BACKTEST


@dataclass(frozen=True)
class Entry:
    """One selectable row under the current stock (a view or a strategy), top to bottom."""
    key: str
    is_strategy: bool
    selected: bool


def resolve_selection(entries: list[Entry], current_key: str | None) -> list[str]:
    """The keys that stay selected, in stacking order.

    The strategy the user just clicked wins; otherwise the first selected one does. Any other selected
    strategy is dropped, except while the Backtest view is selected: then every selected strategy stays.
    """
    if any(e.key == BACKTEST and e.selected for e in entries):
        return [e.key for e in entries if e.selected]
    chosen = next((e.key for e in entries if e.is_strategy and e.selected and e.key == current_key), None)
    if chosen is None:
        chosen = next((e.key for e in entries if e.is_strategy and e.selected), None)
    return [e.key for e in entries if e.selected and (not e.is_strategy or e.key == chosen)]

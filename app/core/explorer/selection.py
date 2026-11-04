"""The Explorer's selection rules: several views of one stock may be stacked, but only one strategy at a time."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    """One selectable row under the current stock (a view or a strategy), top to bottom."""
    key: str
    is_strategy: bool
    selected: bool


def resolve_selection(entries: list[Entry], current_key: str | None) -> list[str]:
    """The keys that stay selected, in stacking order.

    The strategy the user just clicked wins; otherwise the first selected one does. Any other selected
    strategy is dropped.
    """
    chosen = next((e.key for e in entries if e.is_strategy and e.selected and e.key == current_key), None)
    if chosen is None:
        chosen = next((e.key for e in entries if e.is_strategy and e.selected), None)
    return [e.key for e in entries if e.selected and (not e.is_strategy or e.key == chosen)]

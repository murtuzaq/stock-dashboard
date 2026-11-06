"""The Explorer's selection rules: several views of one stock may be stacked, and any number of its strategies may be
selected together (one shows its results; two or more are compared on a chart)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    """One selectable row under the current stock (a view or a strategy), top to bottom."""
    key: str
    is_strategy: bool
    selected: bool


def resolve_selection(entries: list[Entry], current_key: str | None) -> list[str]:
    """The keys that stay selected, in stacking order: every selected view and every selected strategy."""
    return [e.key for e in entries if e.selected]

"""The search bar's behaviour: what typing, choosing, Enter, Escape and Backspace do.

The renderer implements `SearchView` and forwards user input here; the catalogue, filter and matching are in
core.searchbar.session.SearchSession.
"""
from collections.abc import Callable
from typing import Protocol

from core.searchbar.session import SearchResults, SearchSession
from search import Catalog, Group, Security


class SearchView(Protocol):
    def text(self) -> str: ...
    def clear_text(self) -> None: ...
    def set_placeholder(self, text: str) -> None: ...
    def show_scope(self, group: Group | None) -> None: ...
    def show_results(self, results: SearchResults) -> None: ...
    def hide_results(self) -> None: ...


class SearchController:
    def __init__(self, view: SearchView, on_symbol: Callable[[str], None],
                 session: SearchSession | None = None) -> None:
        self.view = view
        self.on_symbol = on_symbol  # called with the symbol the user picked
        self.session = session or SearchSession()
        self.view.set_placeholder(self.session.placeholder())

    def catalog_loaded(self, catalog: Catalog, input_has_focus: bool) -> None:
        self.session.catalog = catalog
        self.view.set_placeholder(self.session.placeholder())
        if input_has_focus:
            self.refresh()

    def refresh(self) -> None:
        """The text changed (or the input gained focus): list what matches."""
        results = self.session.results(self.view.text())
        if results is None:
            self.view.hide_results()
        else:
            self.view.show_results(results)

    # --- the group filter ---

    def set_scope(self, group: Group) -> None:
        self.session.scope = group
        self.view.show_scope(group)
        self.view.clear_text()
        self.view.set_placeholder(self.session.placeholder())
        self.refresh()

    def clear_scope(self) -> None:
        self.session.scope = None
        self.view.show_scope(None)
        self.view.set_placeholder(self.session.placeholder())
        self.refresh()

    # --- choosing ---

    def choose(self, result: Group | Security | None) -> None:
        """A row was clicked or confirmed: a group becomes the filter, a security is opened."""
        if isinstance(result, Group):
            self.set_scope(result)
        elif isinstance(result, Security):
            self._open(result.symbol)

    def enter(self, results_open: bool, current: Group | Security | None) -> None:
        """Enter: take the highlighted row, or open the typed text as a symbol if no list is showing."""
        if results_open and current is not None:
            self.choose(current)
            return
        typed = self.session.typed_symbol(self.view.text())
        if typed:
            self._open(typed)

    def escape(self, results_open: bool) -> None:
        if results_open:
            self.view.hide_results()
        elif self.session.scope:
            self.clear_scope()

    def backspace_in_empty_box(self) -> bool:
        """Backspace with nothing typed removes the filter. True if it did (so the key is consumed)."""
        if self.view.text() or not self.session.scope:
            return False
        self.clear_scope()
        return True

    def _open(self, symbol: str) -> None:
        self.view.clear_text()
        self.view.hide_results()
        self.on_symbol(symbol)

"""The search bar's state and rules: the catalogue, the group filter, and what a typed query finds."""
from dataclasses import dataclass, field

from search import MAX_RESULTS, Catalog, Group, Security, match_groups, match_securities

PLACEHOLDER = 'Search symbol, company or index (e.g. AAPL, Apple, Nasdaq)'
LOADING_PLACEHOLDER = 'Loading symbol list…'


@dataclass
class SearchResults:
    groups: list[Group] = field(default_factory=list)
    securities: list[Security] = field(default_factory=list)

    @property
    def capped(self) -> bool:
        return len(self.securities) == MAX_RESULTS

    @property
    def empty(self) -> bool:
        return not self.groups and not self.securities


class SearchSession:
    def __init__(self) -> None:
        self.catalog: Catalog | None = None
        self.scope: Group | None = None  # while set, searches only look inside this group

    def placeholder(self) -> str:
        if self.catalog is None:
            return LOADING_PLACEHOLDER
        if self.scope is not None:
            return f'Search within {self.scope.label} ({len(self.scope.symbols):,} symbols)'
        return PLACEHOLDER

    def results(self, text: str) -> SearchResults | None:
        """What to list for the typed text, or None when nothing should be listed."""
        if self.catalog is None or (not text.strip() and self.scope is None):
            return None
        groups = [] if self.scope else match_groups(self.catalog, text)
        return SearchResults(groups, match_securities(self.catalog, text, self.scope))

    @staticmethod
    def typed_symbol(text: str) -> str | None:
        """Enter on text that matched nothing opens it as a symbol anyway."""
        symbol = text.strip().upper()
        return symbol or None

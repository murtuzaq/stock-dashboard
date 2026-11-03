"""Ranks what the user typed against the catalog."""
import re

from .catalog import Catalog, Group, Security

MAX_RESULTS = 200


def _normalize(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text.lower())


def match_groups(catalog: Catalog, query: str) -> list[Group]:
    """Groups whose name or alias starts with the query, e.g. 'nas' -> Nasdaq-100, Nasdaq."""
    q = _normalize(query)
    if len(q) < 2:
        return []
    return [g for g in catalog.groups if any(_normalize(name).startswith(q) for name in (g.label, *g.aliases))]


def _rank(security: Security, symbol_query: str, name_query: str, tokens: list[str]) -> int | None:
    """Lower is better; None means no match."""
    if security.symbol == symbol_query:
        return 0
    if security.symbol.startswith(symbol_query):
        return 1
    if security.name.lower().startswith(name_query):
        return 2
    if all(any(word.startswith(token) for word in security.words) for token in tokens):
        return 3
    if len(name_query) >= 3 and name_query in security.name.lower():
        return 4
    return None


def match_securities(catalog: Catalog, query: str, scope: Group | None = None) -> list[Security]:
    """Securities matching by symbol, name, word in the name, or partial name.

    With an empty query inside a scope, lists the scope's members alphabetically (browsing).
    """
    pool = scope.symbols if scope else catalog.securities.keys()
    query = query.strip()
    if not query:
        return [catalog.securities[s] for s in sorted(pool)[:MAX_RESULTS]] if scope else []

    symbol_query, name_query, tokens = query.upper(), query.lower(), query.lower().split()
    ranked = []
    for symbol in pool:
        security = catalog.securities[symbol]
        rank = _rank(security, symbol_query, name_query, tokens)
        if rank is not None:
            ranked.append((rank, symbol not in catalog.popular, len(symbol), symbol, security))
    ranked.sort(key=lambda r: r[:4])
    return [r[-1] for r in ranked[:MAX_RESULTS]]

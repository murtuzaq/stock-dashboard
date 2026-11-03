"""Everything the search bar can find: individual securities, and groups of them (indexes, exchanges, ETFs)."""
import re
from dataclasses import dataclass, field

from . import sources


@dataclass(frozen=True)
class Security:
    symbol: str
    name: str
    exchange: str
    is_etf: bool
    words: tuple[str, ...] = field(repr=False)  # lowercase name words, for "starts with" matching


@dataclass(frozen=True)
class Group:
    label: str
    kind: str  # Index, Exchange or Type
    about: str  # one-line explanation, shown in the results list
    aliases: tuple[str, ...]
    symbols: frozenset[str]


@dataclass
class Catalog:
    securities: dict[str, Security]
    groups: list[Group]
    popular: frozenset[str]  # members of the major indexes; ranked first when matches tie


def _words(name: str) -> tuple[str, ...]:
    return tuple(re.findall(r'[a-z0-9&]+', name.lower()))


def load_catalog() -> Catalog:
    listed = sources.cached('listed', sources.fetch_listed) or []
    securities = {s: Security(s, name, exchange, etf, _words(name)) for s, name, exchange, etf in listed}

    def members(symbols) -> frozenset[str]:
        return frozenset(s for s in symbols or [] if s in securities)

    nasdaq_100 = members(sources.cached('nasdaq_100', sources.fetch_nasdaq_100))
    sp_500 = members(sources.cached('sp_500', sources.fetch_sp_500))

    groups = [
        Group('Nasdaq-100', 'Index', 'The 100 largest non-financial companies on the Nasdaq exchange',
              ('nasdaq 100', 'ndx', 'qqq'), nasdaq_100),
        Group('S&P 500', 'Index', 'About 500 of the largest US companies, across all sectors',
              ('sp500', 'sp 500', 'spx', 'spy', 'standard and poors'), sp_500),
    ]
    exchanges = {
        'Nasdaq': 'Exchange known for technology companies',
        'NYSE': 'New York Stock Exchange, the largest exchange in the world',
        'NYSE American': 'NYSE exchange for smaller companies',
        'NYSE Arca': 'NYSE exchange where most ETFs are listed',
        'Cboe BZX': 'Cboe exchange, mostly ETFs',
    }
    for exchange, about in exchanges.items():
        groups.append(Group(exchange, 'Exchange', about, (exchange.lower(),),
                            frozenset(s.symbol for s in securities.values() if s.exchange == exchange)))
    groups.append(Group('ETFs', 'Type', 'Funds that trade like a stock and hold a basket of stocks',
                        ('etf', 'fund', 'funds', 'exchange traded fund'),
                        frozenset(s.symbol for s in securities.values() if s.is_etf)))

    return Catalog(securities, [g for g in groups if g.symbols], nasdaq_100 | sp_500)

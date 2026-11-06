"""What the Explorer tree lists under a stock: its strategies, then the library templates."""
from dataclasses import dataclass

from core.dashboard.layout import strategy_key
from strategy import describe, repository


@dataclass(frozen=True)
class StrategyEntry:
    key: str  # view key, 'strategy:<id>'
    label: str
    tooltip: str
    is_library: bool  # drawn differently: these are templates, not the stock's own


def strategy_entries(symbol: str) -> list[StrategyEntry]:
    entries = []
    for strategy in repository.for_symbol(symbol) + repository.library():
        rules = '\n\n'.join(part for part in (strategy.about.summary, describe(strategy)) if part)
        if strategy.symbol is None:
            tooltip = (f'Library template (try it on {symbol}; right-click to copy and customise)\n\n{rules}\n\n'
                       'Tools > Strategies explains why it can work, with references.')
            entries.append(StrategyEntry(strategy_key(strategy.id), f'{strategy.name} · library', tooltip, True))
        else:
            entries.append(StrategyEntry(strategy_key(strategy.id), strategy.name, rules, False))
    return entries

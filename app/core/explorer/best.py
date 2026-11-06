"""Which of a stock's strategies did best over the range on screen, for the star in the Explorer's Strategies folder."""
from dataclasses import dataclass

from prices import RANGE_NAMES
from strategy.ranking import Ranked


@dataclass(frozen=True)
class BestStrategy:
    strategy_id: str
    tooltip: str  # what the row's tooltip says about it


def best_strategy(ranked: list[Ranked], range_label: str) -> BestStrategy | None:
    """The strategy with the highest return, but only if it also beat buy & hold. None when there is nothing clearly
    ahead: fewer than two strategies ran, the top two tie (for example a short range where none of them traded), or
    even the best did no better than simply holding the stock."""
    if len(ranked) < 2:
        return None
    ordered = sorted(ranked, key=lambda entry: entry.return_pct, reverse=True)
    best, second = ordered[0], ordered[1]
    if best.return_pct <= second.return_pct:
        return None
    if not best.beats_buy_and_hold:
        return None
    hold = best.result.metrics['buy_hold_return_pct']
    text = (f'Best of {len(ranked)} strategies, {RANGE_NAMES.get(range_label, range_label)}: '
            f'{best.return_pct:+.1f}% and beat buy & hold ({hold:+.1f}%).')
    return BestStrategy(best.strategy.id, text)

"""Which strategy gets the star: highest return among the stock's strategies, only when clearly ahead."""
from types import SimpleNamespace

from core.explorer.best import best_strategy
from strategy.ranking import Ranked


def ranked(strategy_id: str, return_pct: float, hold: float = 5.0) -> Ranked:
    result = SimpleNamespace(metrics={'return_pct': return_pct, 'buy_hold_return_pct': hold})
    return Ranked(SimpleNamespace(id=strategy_id), result)


def test_the_highest_return_wins_whatever_the_input_order():
    best = best_strategy([ranked('a', 3), ranked('c', 12), ranked('b', 7)], '1Y')
    assert best.strategy_id == 'c'
    assert best.tooltip == 'Best of 3 strategies, past year: +12.0% and beat buy & hold (+5.0%).'


def test_nothing_is_starred_with_fewer_than_two_strategies():
    assert best_strategy([], '1Y') is None
    assert best_strategy([ranked('a', 10)], '1Y') is None


def test_nothing_is_starred_when_the_top_two_tie():
    assert best_strategy([ranked('a', 0), ranked('b', 0)], '1M') is None  # e.g. nobody traded in a short range
    assert best_strategy([ranked('a', 8), ranked('b', 8), ranked('c', 1)], '1Y') is None


def test_nothing_is_starred_when_even_the_best_did_not_beat_buy_and_hold():
    assert best_strategy([ranked('a', 2, hold=20), ranked('b', -3, hold=20)], '5Y') is None
    assert best_strategy([ranked('a', 20, hold=20), ranked('b', 1, hold=20)], '5Y') is None  # equal is not better


def test_the_tooltip_names_the_range():
    winner = best_strategy([ranked('a', 30, hold=20), ranked('b', -3, hold=20)], 'YTD')
    assert winner.strategy_id == 'a' and 'year to date' in winner.tooltip

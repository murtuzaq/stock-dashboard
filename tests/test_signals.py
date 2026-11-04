import numpy as np
import pandas as pd
import pytest

from conftest import indicator, make_candles, number, random_walk
from strategy import Condition, RuleGroup, Strategy, evaluate
from strategy import catalog
from strategy.signals import SeriesCache, condition_signal, group_signal

CLOSES = [1, 2, 3, 2, 1, 2, 3, 3, 2]


def signal(op, closes=CLOSES, level=2.5, within=1):
    candles = make_candles(closes)
    return condition_signal(Condition(indicator('close'), op, number(level), within), SeriesCache(candles, None)).tolist()


def test_states_hold_on_every_candle():
    assert signal('above') == [False, False, True, False, False, False, True, True, False]
    assert signal('below') == [True, True, False, True, True, True, False, False, True]


def test_events_fire_only_on_the_crossing_candle():
    assert signal('crosses_above') == [False, False, True, False, False, False, True, False, False]
    assert signal('crosses_below') == [False, False, False, True, False, False, False, False, True]


def test_touching_the_level_is_not_a_cross():
    # 2 -> 2 -> 3 against level 2: only the move from 2 to 3 crosses above
    assert signal('crosses_above', closes=[1, 2, 2, 3], level=2) == [False, False, False, True]


def test_within_keeps_an_event_alive_for_n_candles():
    assert signal('crosses_above', within=3) == [False, False, True, True, True, False, True, True, True]


def test_indicators_still_warming_up_never_signal():
    candles = make_candles(range(1, 11))
    result = condition_signal(Condition(indicator('close'), 'above', indicator('sma', days=5)),
                              SeriesCache(candles, None))
    assert not result.iloc[:4].any() and result.iloc[4:].all()


def test_sma_days_are_converted_for_weekly_candles():
    weekly = make_candles(np.arange(100.0), candle_size='1W')
    values = SeriesCache(weekly, None).series(indicator('sma', days=50))
    assert values.equals(weekly['close'].rolling(10).mean())


def test_all_any_and_nested_groups():
    cache = SeriesCache(make_candles(CLOSES), None)
    above_1, below_3 = (Condition(indicator('close'), 'above', number(1)),
                        Condition(indicator('close'), 'below', number(3)))
    assert group_signal(RuleGroup('all', [above_1, below_3]), cache).tolist() == \
        [False, True, False, True, False, True, False, False, True]
    assert group_signal(RuleGroup('any', [RuleGroup('all', [above_1, below_3]),
                                          Condition(indicator('close'), 'above', number(2.5))]), cache).tolist() == \
        [False, True, True, True, False, True, True, True, True]
    assert not group_signal(RuleGroup('all', []), cache).any()


@pytest.mark.parametrize('operand, message', [
    (indicator('bollinger'), 'Unknown indicator'),
    (indicator('macd', 'nope'), 'no output'),
    (indicator('rel_strength'), 'S&P 500'),
])
def test_bad_operands_explain_the_problem(operand, message):
    with pytest.raises(ValueError, match=message):
        SeriesCache(make_candles(CLOSES), None).series(operand)


def test_every_catalog_indicator_computes_all_its_lines():
    candles, benchmark = random_walk(300, seed=1), random_walk(300, seed=2)
    for key, item in catalog.INDICATORS.items():
        frame = item.compute(candles, benchmark, item.settings({}))
        assert list(frame.columns) == list(item.outputs), key
        assert frame.index.equals(candles.index), key
        assert frame.iloc[-1].notna().all(), key


def every_indicator_strategy() -> Strategy:
    """Uses every indicator in the catalogue, so the look-ahead test covers all of them."""
    buy = RuleGroup('any', [
        Condition(indicator('close'), 'crosses_above', indicator('sma', days=20)),
        Condition(indicator('macd', 'macd'), 'crosses_above', indicator('macd', 'signal'), within=2),
        Condition(indicator('stoch_rsi', 'k'), 'crosses_above', indicator('stoch_rsi', 'd')),
        Condition(indicator('rsi'), 'below', number(35)),
        Condition(indicator('volume'), 'above', indicator('volume_average')),
        Condition(indicator('rel_strength'), 'crosses_above', indicator('rel_strength', 'average', days=20)),
    ])
    sell = RuleGroup('any', [
        Condition(indicator('high'), 'crosses_below', indicator('sma', days=50)),
        Condition(indicator('atr'), 'above', number(3)),
        Condition(indicator('low'), 'below', indicator('open')),
    ])
    return Strategy('everything', buy, sell)


@pytest.mark.parametrize('candle_size', ['1D', '1W'])
def test_no_look_ahead_signals_never_change_when_future_candles_arrive(candle_size):
    from prices import to_candles
    daily, benchmark = random_walk(1200, seed=3), random_walk(1200, seed=4)
    candles = to_candles(daily, candle_size)
    strategy = every_indicator_strategy()
    full = evaluate(strategy, candles, benchmark)
    assert full['buy_signal'].any() and full['sell_signal'].any(), 'test strategy should produce signals'
    for t in np.linspace(60, len(candles) - 1, 8).astype(int):
        partial = evaluate(strategy, candles.iloc[:t + 1], benchmark)
        pd.testing.assert_frame_equal(partial, full.iloc[:t + 1])

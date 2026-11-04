import json

import pytest

from conftest import indicator, number
from strategy import Condition, Costs, RuleGroup, Strategy, describe


def test_json_round_trip_keeps_everything(spec_example):
    data = json.loads(json.dumps(spec_example.to_dict()))
    restored = Strategy.from_dict(data)
    assert restored.to_dict() == spec_example.to_dict()


def test_nested_groups_round_trip():
    group = RuleGroup('any', [Condition(indicator('close'), 'above', number(10)),
                              RuleGroup('all', [Condition(indicator('rsi'), 'below', number(30))])])
    assert RuleGroup.from_dict(group.to_dict()).to_dict() == group.to_dict()


def test_defaults_are_filled_in_when_missing():
    strategy = Strategy.from_dict({'name': 'Bare', 'buy': {'conditions': []}, 'sell': {'conditions': []}})
    assert strategy.costs == Costs() and strategy.buy.match == 'all' and strategy.symbol is None


def test_copy_for_another_stock_is_independent(spec_example):
    copy = spec_example.copy_for('NVDA')
    copy.buy.conditions[2].right.value = 30  # customise the copy's Stoch RSI threshold
    copy.exits.stop_loss_pct = 5
    assert spec_example.buy.conditions[2].right.value == 20 and spec_example.exits.stop_loss_pct == 8
    assert copy.symbol == 'NVDA' and copy.origin_id == spec_example.id and copy.id != spec_example.id


@pytest.mark.parametrize('build', [
    lambda: Condition(indicator('close'), 'touches', number(1)),   # unknown operator
    lambda: Condition(number(1), 'above', indicator('close')),      # number on the left
    lambda: Condition(indicator('close'), 'crosses_above', number(1), within=0),
    lambda: RuleGroup('some', []),
])
def test_invalid_definitions_are_rejected(build):
    with pytest.raises(ValueError):
        build()


def test_describe_reads_like_english(spec_example):
    assert describe(spec_example) == (
        'BUY when Close is above SMA 200d AND MACD line crosses above MACD signal AND Stoch RSI K is below 20\n'
        'SELL when MACD line crosses below MACD signal OR Close is below SMA 200d\n'
        '  or price falls 8% below the entry price (stop-loss)')


def test_describe_shows_changed_settings_and_event_windows():
    strategy = Strategy('x', RuleGroup('all', [
        Condition(indicator('rsi', length=10), 'crosses_above', number(30), within=3),
        Condition(indicator('rel_strength'), 'above', indicator('rel_strength', 'average', days=100))]),
        RuleGroup('any', []))
    assert describe(strategy).splitlines()[0] == (
        'BUY when RSI (10) crosses above 30 (within the last 3 candles) AND '
        'Rel. Strength is above Rel. Strength SMA 100d')
    assert describe(strategy).splitlines()[1] == 'SELL when never (no conditions)'

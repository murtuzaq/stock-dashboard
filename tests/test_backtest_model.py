"""The Backtest chart model: one coloured line per strategy, buy & hold last, aligned to the candles."""
import dataclasses

import numpy as np

from conftest import random_walk
from core.backtest.model import backtest_chart
from core.common import theme
from strategy import Costs
from strategy.backtest import run


def runs_for(*strategies):
    candles = random_walk(300, seed=3)
    benchmark = random_walk(300, seed=4)
    start = candles.index[100]
    return [(strategy, run(strategy, candles, benchmark, start, 'AAA')) for strategy in strategies]


def test_no_strategies_means_no_chart():
    assert backtest_chart([]) is None


def test_one_line_per_strategy_then_buy_and_hold(spec_example):
    other = dataclasses.replace(spec_example, id='other', name='Other')
    runs = runs_for(spec_example, other)
    chart = backtest_chart(runs)
    assert [s.label for s in chart.series[:2]] == ['MACD + Stoch RSI', 'Other']
    assert [s.color for s in chart.series[:2]] == list(theme.STRATEGY_COLORS[:2])
    hold = chart.series[-1]
    assert hold.is_hold and hold.color == theme.HOLD_COLOR and hold.label.startswith('Buy & hold')
    assert chart.series[0].end_value == runs[0][1].metrics['end_capital']
    assert chart.series[0].return_pct == runs[0][1].metrics['return_pct']
    assert chart.note == ''


def test_lines_are_nan_before_the_range_and_start_at_the_seed_money(spec_example):
    [(strategy, result)] = runs_for(spec_example)
    chart = backtest_chart([(strategy, result)])
    values = chart.series[0].values
    assert len(values) == len(chart.dates) and np.isnan(values[:result.first_slot]).all()
    assert abs(values[result.first_slot] - strategy.costs.capital) < strategy.costs.capital * 0.1
    assert chart.series[-1].end_value == float(result.buy_hold.iloc[-1])


def test_different_starting_cash_is_flagged(spec_example):
    rich = dataclasses.replace(spec_example, id='rich', name='Rich', costs=Costs(capital=50_000))
    chart = backtest_chart(runs_for(spec_example, rich))
    assert 'different cash' in chart.note

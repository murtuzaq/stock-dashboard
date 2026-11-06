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


def test_hover_text_names_the_strategy_the_date_the_value_so_far_and_its_whole_range_figures(spec_example):
    from core.backtest.model import hover_line
    from core.common.formatting import Span
    [(strategy, result)] = runs_for(spec_example)
    chart = backtest_chart([(strategy, result)])
    slot = len(chart.dates) - 1
    text = ''.join(span.text for span in hover_line(chart, 0, slot))
    assert text.startswith('MACD + Stoch RSI\n') and f'{chart.dates[slot]:%b %d, %Y}' in text
    assert f'({(chart.series[0].values[slot] / strategy.costs.capital - 1) * 100:+.2f}% so far)' in text
    assert 'Whole range:' in text and 'vs buy & hold' in text and 'Trades' in text and 'Max drawdown' in text
    assert isinstance(hover_line(chart, 0, slot)[0], Span) and hover_line(chart, 0, slot)[0].color == chart.series[0].color


def test_hovering_the_buy_and_hold_line_shows_its_own_figures(spec_example):
    from core.backtest.model import hover_line
    chart = backtest_chart(runs_for(spec_example))
    text = ''.join(span.text for span in hover_line(chart, len(chart.series) - 1, len(chart.dates) - 1))
    assert text.startswith('Buy & hold') and 'Whole range:' in text and 'Trades' not in text


def test_there_is_nothing_to_hover_before_the_range_starts_or_off_the_chart(spec_example):
    from core.backtest.model import hover_line
    [(strategy, result)] = runs_for(spec_example)
    chart = backtest_chart([(strategy, result)])
    assert hover_line(chart, 0, 0) is None  # warm-up candles before the range
    assert hover_line(chart, 0, len(chart.dates)) is None and hover_line(chart, 0, -1) is None

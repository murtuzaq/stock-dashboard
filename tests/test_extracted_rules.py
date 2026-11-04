"""Rules that used to sit inside widgets: axis labels, trade marks, condition-row operands, Explorer selection."""
import numpy as np
import pandas as pd

from conftest import make_candles, random_walk
from core.builder import rule_editor
from core.common import theme
from core.dashboard import trade_marks
from core.explorer.selection import Entry, resolve_selection
from core.dashboard.time_axis import tick_labels
from strategy import Condition, Costs, Exits, Operand, RuleGroup, Strategy, catalog
from strategy.backtest import run


# --- time axis -----------------------------------------------------------------------------------------------

def test_axis_uses_years_for_long_views_and_marks_the_new_year_when_months_are_shown():
    candles = random_walk(2500, seed=1)
    long_view = tick_labels(candles.index, 0, len(candles), 800)
    assert all(len(label) == 4 and label.isdigit() for label in long_view.values())  # '2021', '2022', ...

    months = tick_labels(candles.index, 1000, 1250, 800)
    assert any(label.isdigit() for label in months.values())  # a year marker where January begins
    assert any(not label.isdigit() for label in months.values())  # month names between them


def test_axis_labels_are_unique_and_inside_the_view():
    candles = random_walk(1000, seed=2)
    labels = tick_labels(candles.index, 500, 700, 600)
    assert labels and all(500 <= slot <= 700 for slot in labels)
    assert len(set(labels.values())) == len(labels)  # a label never repeats


def test_axis_has_no_labels_when_almost_nothing_is_in_view():
    candles = random_walk(100, seed=2)
    assert tick_labels(candles.index, 50, 50.5, 600) == {}
    assert tick_labels(pd.DatetimeIndex([]), 0, 10, 600) == {}


# --- trade marks ---------------------------------------------------------------------------------------------

def trend_strategy():
    """Buy above the 50-day average, sell below it, 8% stop: trades often on any random walk."""
    return Strategy('Trend', RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma', params={'days': 50}))]),
                    RuleGroup('any', [Condition(Operand('close'), 'below', Operand('sma', params={'days': 50}))]),
                    Exits(stop_loss_pct=8), Costs(10_000, 0, 0))


def a_result(_unused=None):
    candles = random_walk(500, seed=7)
    return candles, run(trend_strategy(), candles, None, candles.index[60])


def test_price_chart_marks_have_levels_markers_and_fills(spec_example):
    candles, result = a_result(spec_example)
    assert result.trades
    marks = trade_marks.trade_marks(result, candles, on_price_chart=True)
    assert len(marks.regions) == len(result.trades) and not marks.vlines
    first = result.trades[0]
    entry_line = marks.segments[0]
    assert entry_line.y == (first.entry_price, first.entry_price) and entry_line.style == trade_marks.SOLID
    assert any(s.style == trade_marks.DOT and s.color == theme.DOWN for s in marks.segments)  # the 8% stop
    buy_slots, buy_prices = marks.buys
    assert buy_slots == [t.signal_slot for t in result.trades]
    assert np.all(buy_prices < candles['low'].to_numpy()[buy_slots])  # arrows sit below the low
    assert len(marks.fills[0]) >= len(result.trades)


def test_indicator_chart_marks_use_signal_lines_instead(spec_example):
    candles, result = a_result(spec_example)
    marks = trade_marks.trade_marks(result, candles, on_price_chart=False)
    assert marks.vlines and not marks.segments and len(marks.buys[0]) == 0
    assert marks.vlines[0].slot == result.trades[0].signal_slot and marks.vlines[0].color == theme.UP


def test_trade_shading_colour_follows_the_outcome(spec_example):
    candles, result = a_result(spec_example)
    marks = trade_marks.trade_marks(result, candles, on_price_chart=True)
    for trade, region in zip(result.trades, marks.regions):
        expected = trade_marks.OPEN_COLOR if trade.is_open else (theme.UP if trade.pnl > 0 else theme.DOWN)
        assert region.color == expected
        assert (region.start, region.end) == (trade.entry_slot - 0.5, trade.exit_slot + 0.5)


# --- condition-row operands ----------------------------------------------------------------------------------

def test_choices_cover_every_indicator_output():
    choices = dict((key, label) for label, key in rule_editor.operand_choices())
    assert choices['macd:signal'] == 'MACD signal' and choices['close:value'] == 'Close'
    assert len(choices) == sum(len(i.outputs) for i in catalog.INDICATORS.values())


def test_build_operand_drops_settings_left_at_their_default():
    assert rule_editor.build_operand('sma:value', 0, {'days': 50}) == Operand('sma', None, {})
    assert rule_editor.build_operand('sma:value', 0, {'days': 200}) == Operand('sma', None, {'days': 200})
    macd_defaults = rule_editor.setting_values(Operand('macd'))
    assert rule_editor.build_operand('macd:signal', 0, macd_defaults) == Operand('macd', 'signal', {})
    assert rule_editor.build_operand(rule_editor.NUMBER, 20.5, {}) == Operand(value=20.5)


def test_choice_key_and_settings_round_trip():
    for operand in (Operand('sma', params={'days': 200}), Operand('macd', 'signal'), Operand('close'),
                    Operand('stoch_rsi', 'd')):
        key = rule_editor.choice_key(operand)
        settings = rule_editor.setting_values(operand)
        assert rule_editor.build_operand(key, 0, settings) == operand
    assert rule_editor.choice_key(Operand(value=3)) == rule_editor.NUMBER


def test_changing_the_left_side_suggests_a_matching_right_side():
    # Close (price) vs Number 20: wrong scale -> SMA 200
    assert rule_editor.suggest_right('close:value', rule_editor.NUMBER) == Operand('sma', params={'days': 200})
    # Stoch RSI K vs an SMA: -> the number 20
    assert rule_editor.suggest_right('stoch_rsi:k', 'sma:value') == Operand(value=20)
    # MACD line vs a number is a scale mismatch: the natural partner is its signal line
    assert rule_editor.suggest_right('macd:macd', 'sma:value') == Operand('macd', 'signal')
    # Same scale already: leave the right side alone
    assert rule_editor.suggest_right('close:value', 'sma:value') is None
    assert rule_editor.suggest_right('stoch_rsi:k', 'rsi:value') is None


# --- Explorer selection --------------------------------------------------------------------------------------

def entries(*spec):
    """('price', 'view', True) -> Entry; kind 'strategy' marks a strategy row."""
    return [Entry(key, kind == 'strategy', selected) for key, kind, selected in spec]


def test_views_stack_in_order_and_unselected_ones_are_left_out():
    rows = entries(('price', 'view', True), ('macd', 'view', False), ('atr', 'view', True))
    assert resolve_selection(rows, 'atr') == ['price', 'atr']


def test_the_strategy_just_clicked_wins_over_an_earlier_one():
    rows = entries(('price', 'view', True), ('strategy:a', 'strategy', True), ('strategy:b', 'strategy', True))
    assert resolve_selection(rows, 'strategy:b') == ['price', 'strategy:b']


def test_without_a_clicked_strategy_the_first_selected_one_stays():
    rows = entries(('price', 'view', True), ('strategy:a', 'strategy', True), ('strategy:b', 'strategy', True))
    assert resolve_selection(rows, 'price') == ['price', 'strategy:a']
    assert resolve_selection(rows, None) == ['price', 'strategy:a']


def test_nothing_selected_resolves_to_nothing():
    assert resolve_selection(entries(('price', 'view', False)), 'price') == []

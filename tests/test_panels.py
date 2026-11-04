"""The presentation models: what each view would show, checked without any widgets."""
import numpy as np
import pandas as pd

from conftest import make_candles, random_walk
from core.dashboard import panels
from core.strategies import results as strategy_results
from core.common import theme
from core.dashboard import layout as views
from core.common.formatting import money, short_number
from strategy import Costs
from strategy.backtest import run


def text_of(line) -> str:
    return ''.join(span.text for span in line)


def test_short_number_and_money():
    assert short_number(5_583_900) == '5.58M'
    assert short_number(999) == '999'
    assert money(-12.5) == '-$12.50' and money(1234.5) == '$1,234.50'


def test_macd_model_matches_the_legend_and_colours_every_bar():
    candles = random_walk(120, seed=1)
    model = panels.macd_model(candles)
    assert len(model.bar_colors) == len(model.histogram) == len(candles)
    assert text_of(model.legend).startswith('MACD (12, 26, 9)   MACD ')
    mood = model.legend[-1]
    assert mood.color == theme.MUTED and ('rising' in mood.text) == (model.histogram[-1] >= 0)


def test_histogram_colours_strong_when_growing_pale_when_shrinking():
    colors = panels.histogram_colors(np.array([1.0, 2.0, 1.0, -1.0, -2.0, -1.0]))
    assert colors == [theme.ABOVE_GROWING, theme.ABOVE_GROWING, theme.ABOVE_SHRINKING,
                      theme.BELOW_GROWING, theme.BELOW_GROWING, theme.BELOW_SHRINKING]


def test_volume_model_colours_bars_by_candle_direction():
    candles = make_candles([10, 11, 10, 12])
    candles['open'] = [10, 10, 11, 10]  # up, up, down, up
    model = panels.volume_model(candles)
    assert model.bar_colors == [theme.UP, theme.UP, theme.DOWN, theme.UP]
    assert text_of(model.legend) == 'Volume'  # fewer than 20 candles: no average yet


def test_atr_legend_says_when_history_is_too_short():
    model = panels.atr_model(make_candles([10, 11, 12]))
    assert 'not enough history' in text_of(model.legend)


def test_sma_model_labels_note_the_candle_size():
    daily = panels.sma_model(make_candles(range(1, 300), '1D'))
    weekly = panels.sma_model(make_candles(range(1, 300), '1W'))
    assert [line.label for line in daily.lines] == ['SMA 50d', 'SMA 150d', 'SMA 200d']
    assert weekly.lines[0].label == 'SMA 50d (10 × 1W candles)'


def test_relative_strength_rebases_to_100_at_the_range_start():
    candles = random_walk(200, seed=2)
    benchmark = random_walk(200, seed=5)
    model = panels.rel_strength_model(candles, candles, benchmark)
    start = candles.index[100]
    rebased = model.rebased(start)
    assert rebased[100] == 100.0
    assert 'since' in text_of(model.legend(start))


def test_relative_strength_without_a_benchmark_says_so():
    candles = random_walk(50, seed=2)
    model = panels.rel_strength_model(candles, candles, pd.DataFrame())
    assert not model.available
    assert 'data unavailable' in text_of(model.legend(candles.index[0]))


def test_price_model_colour_follows_the_range_change():
    rising = make_candles(np.linspace(10, 20, 50))
    falling = make_candles(np.linspace(20, 10, 50))
    assert panels.price_model(rising, rising).color(rising.index[0]) == theme.UP
    assert panels.price_model(falling, falling).color(falling.index[0]) == theme.DOWN


def test_history_rows_are_newest_first_and_use_the_previous_candle_for_change():
    candles = make_candles([10, 11, 12, 13])
    rows = panels.history_rows(candles, first_slot=1)
    assert list(rows['close']) == [13, 12, 11]
    assert panels.history_cell(rows, 2, 'Change').text == '+10.00%'  # 11 vs the candle before the range (10)
    assert panels.history_cell(rows, 0, 'Date').text == f'{candles.index[-1]:%Y-%m-%d}'
    assert 'rows' in panels.history_summary(rows)


def test_growth_cells():
    assert panels.growth_cell(float('nan'), 'revenue_yoy').text == '—'
    assert panels.growth_cell(float('nan'), 'revenue_yoy').tooltip
    assert panels.growth_cell(5.0, 'eps_yoy').color == theme.UP
    assert panels.growth_cell(-5.0, 'eps_yoy').text == '-5.0%'
    assert panels.growth_cell(2_500_000, 'revenue').text == '$2.5M'


def test_growth_summary_for_a_fund_with_no_financials():
    assert 'ETFs and indexes have none' in panels.growth_summary('SPY', pd.DataFrame())


def test_view_layout_hosts_sma_on_the_first_price_chart_and_dates_the_bottom_chart():
    layout = views.arrange(['volume', 'sma', 'price', 'growth'])
    assert layout.sma_host == 'price' and layout.shown == ['volume', 'price', 'growth']
    assert layout.dated == 'price'  # growth is a table: it has no time axis
    assert layout.height_of('sma') == 0 and layout.height_of('price') == 3


def test_sma_stands_alone_without_a_host():
    layout = views.arrange(['sma', 'macd'])
    assert layout.sma_host is None and layout.shown == ['sma', 'macd'] and layout.dated == 'macd'


def test_strategy_result_text_and_rows(spec_example):
    candles = random_walk(300, seed=7)
    spec_example.costs = Costs(10_000, 0, 0)
    result = run(spec_example, candles, None, candles.index[50])
    cards = text_of(strategy_results.result_cards(result))
    assert cards.startswith('Return ') and 'Max drawdown' in cards and 'In market' in cards
    rows = strategy_results.trade_rows(result)
    assert len(rows) == len(result.trades)
    equity, hold = strategy_results.equity_curves(result)
    assert len(equity) == len(hold) == len(candles) and np.isnan(equity[0])
    assert 'MACD + Stoch RSI' in text_of(strategy_results.rules_line(spec_example))

"""Tools > Strategies > Compare on all stocks: one strategy on every stored stock, with fake prices and backtests."""
import dataclasses
from types import SimpleNamespace

import pandas as pd
import pytest

from conftest import random_walk
from core.common import theme
from core.common.background import BackgroundLoader
from core.library import compare
from core.library.compare import CompareController, StockResult, compare_rows, summary_line
from strategy import Costs
from strategy.backtest import run as real_backtest

SYMBOLS = ['AAA', 'BBB', 'CCC']
STOCKS = pd.DataFrame({'symbol': SYMBOLS, 'first_date': pd.to_datetime(['2020-01-01'] * 3),
                       'last_date': pd.to_datetime(['2021-09-01'] * 3), 'last_close': [10.0, 20.0, 30.0]})
NAMES = {'AAA': 'Alpha Inc', 'BBB': 'Beta Inc'}


def metrics(ret: float, hold: float = 5.0, trades: int = 4) -> dict:
    return {'end_capital': 10_000 * (1 + ret / 100), 'return_pct': ret, 'buy_hold_return_pct': hold, 'trades': trades,
            'wins': trades // 2, 'losses': trades - trades // 2, 'win_rate_pct': 50.0 if trades else None,
            'max_drawdown_pct': -12.0, 'time_in_market_pct': 40.0}


class FakeView:
    def __init__(self) -> None:
        self.header, self.rows, self.summary, self.notices, self.running, self.progress = '', [], '', [], False, None

    def show_header(self, text): self.header = text
    def show_rows(self, rows, summary): self.rows, self.summary = rows, summary
    def show_progress(self, done, total, text): self.progress = (done, total, text)
    def show_notice(self, text): self.notices.append(text)
    def set_running(self, running): self.running = running


class FakeExplorer:
    def __init__(self) -> None:
        self.log = []

    def add_symbol(self, symbol): self.log.append(('add_symbol', symbol))
    def select_strategy(self, symbol, strategy_id): self.log.append(('select_strategy', symbol, strategy_id))


class FakeStrategies:
    def __init__(self, *strategies) -> None:
        self.by_id = {s.id: s for s in strategies}

    def get(self, strategy_id):
        return self.by_id.get(strategy_id)


class Rig:
    """A controller with fake prices; `calls` records every backtest as (symbol, capital, candle size, range start)."""

    def __init__(self, strategy, returns=None, settings=('1W', '1Y'), stocks=STOCKS, series=None) -> None:
        self.view, self.explorer, self.calls = FakeView(), FakeExplorer(), []
        self.returns, self.settings = dict(returns or {'AAA': 30.0, 'BBB': -5.0, 'CCC': 12.0}), list(settings)
        self.series = series or (lambda symbol: random_walk(400, seed=len(symbol) + ord(symbol[0])))
        self.controller = CompareController(
            self.view, BackgroundLoader.immediate(), FakeStrategies(strategy), self.explorer,
            lambda: tuple(self.settings), lambda: stocks, lambda: NAMES, self.series, self.backtest)

    def backtest(self, strategy, candles, benchmark, start, symbol):
        self.calls.append((symbol, strategy.costs.capital, candles.attrs['candle_size'], start))
        outcome = self.returns[symbol]
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            outcome()
            return SimpleNamespace(metrics=metrics(30.0))
        return SimpleNamespace(metrics=metrics(outcome))

    def texts(self, column):
        return [row.cells[column].text for row in self.view.rows]


def test_it_tests_every_stored_stock_with_10_thousand_whatever_the_strategys_own_capital(spec_example):
    strategy = dataclasses.replace(spec_example, costs=Costs(capital=50_000, commission=1.0, slippage_pct=0.2))
    rig = Rig(strategy)
    rig.controller.start(strategy.id)
    assert [call[0] for call in rig.calls] == SYMBOLS
    assert {call[1] for call in rig.calls} == {10_000}  # seeded, not 50,000
    assert {call[2] for call in rig.calls} == {'1W'}  # the candle size selected when the button was pressed
    assert not rig.controller.running and not rig.view.running


def test_the_range_is_worked_out_per_stock_from_its_own_last_day(spec_example):
    rig = Rig(spec_example, settings=('1D', '5Y'))
    rig.controller.start(spec_example.id)
    assert {call[3] for call in rig.calls} == {pd.Timestamp('2020-01-01')}  # 5Y reaches back past the first day


def test_the_header_names_the_strategy_candles_range_and_seed(spec_example):
    rig = Rig(spec_example, settings=('1W', '1Y'))
    rig.controller.start(spec_example.id)
    assert rig.view.header == f'{spec_example.name} · 1W candles · past year · $10,000 per stock'


def test_rows_are_best_first_with_numeric_sort_values_and_colours(spec_example):
    rig = Rig(spec_example)
    rig.controller.start(spec_example.id)
    assert [row.symbol for row in rig.view.rows] == ['AAA', 'CCC', 'BBB']
    assert rig.texts(3) == ['+30.0%', '+12.0%', '-5.0%'] and rig.texts(2)[0] == '$13,000.00'
    best, worst = rig.view.rows[0], rig.view.rows[2]
    assert best.cells[1].text == 'Alpha Inc' and rig.view.rows[1].cells[1].text == ''  # CCC has no name
    assert best.cells[3].color == theme.UP and worst.cells[3].color == theme.DOWN
    assert [cell.sort_value for cell in (best.cells[2], best.cells[3])] == [13_000.0, 30.0]
    assert best.cells[5].text == '+25.0 pts' and best.cells[5].sort_value == 25.0  # return minus buy & hold (5%)
    assert worst.cells[5].text == '-10.0 pts'


def test_the_summary_counts_stocks_that_beat_buy_and_hold(spec_example):
    rig = Rig(spec_example, returns={'AAA': 30.0, 'BBB': -5.0, 'CCC': 12.0})
    rig.controller.start(spec_example.id)
    assert rig.view.summary == 'Beat buy & hold on 2 of 3 stocks · median return +12.0% · best AAA +30.0%'


def test_a_stock_it_cannot_run_on_is_listed_last_as_not_available_with_the_reason(spec_example):
    rig = Rig(spec_example, returns={'AAA': 30.0, 'BBB': ValueError('needs the S&P 500'), 'CCC': 12.0})
    rig.controller.start(spec_example.id)
    assert [row.symbol for row in rig.view.rows] == ['AAA', 'CCC', 'BBB']
    last = rig.view.rows[-1]
    assert last.cells[3].text == 'n/a' and last.cells[3].tooltip == 'needs the S&P 500'
    assert last.cells[3].sort_value == compare.NO_VALUE  # sorts below every real number
    assert rig.view.summary.endswith('· 1 could not be run')


def test_a_stock_with_no_stored_prices_is_not_available(spec_example):
    rig = Rig(spec_example, series=lambda symbol: pd.DataFrame() if symbol == 'BBB' else random_walk(300, seed=1))
    rig.controller.start(spec_example.id)
    assert rig.view.rows[-1].symbol == 'BBB' and rig.view.rows[-1].cells[3].tooltip == 'No prices stored for this stock'


def test_running_again_with_the_same_settings_reuses_the_results_and_new_settings_run_again(spec_example):
    rig = Rig(spec_example)
    rig.controller.start(spec_example.id)
    first = len(rig.calls)
    rig.controller.rerun()
    assert len(rig.calls) == first  # all cached
    rig.settings[0] = '1D'  # the candle size selected in the main window changed
    rig.controller.rerun()
    assert len(rig.calls) == 2 * first and {call[2] for call in rig.calls[first:]} == {'1D'}


def test_changing_the_strategy_rules_is_not_served_from_the_cache(spec_example):
    rig = Rig(spec_example)
    rig.controller.start(spec_example.id)
    first = len(rig.calls)
    changed = dataclasses.replace(spec_example, exits=dataclasses.replace(spec_example.exits, stop_loss_pct=3))
    rig.controller.strategies = FakeStrategies(changed)
    rig.controller.start(changed.id)
    assert len(rig.calls) == 2 * first


def test_stop_halts_after_the_stock_in_progress_and_keeps_what_finished(spec_example):
    rig = Rig(spec_example)
    rig.returns['BBB'] = lambda: rig.controller.stop()  # the user presses Stop while BBB is being tested
    rig.controller.start(spec_example.id)
    assert [call[0] for call in rig.calls] == ['AAA', 'BBB']
    assert [row.symbol for row in rig.view.rows] == ['AAA', 'BBB']  # the two that finished (CCC was never tested)
    assert 'Stopped: 2 of 3 stocks were tested' in rig.view.notices[-1] and not rig.controller.running


def test_a_stock_can_be_opened_from_a_row(spec_example):
    template = dataclasses.replace(spec_example, id='tpl', symbol=None)
    rig = Rig(template)
    rig.controller.start('tpl')
    rig.controller.open_stock('BBB')
    assert rig.explorer.log == [('select_strategy', 'BBB', 'tpl')]  # a template is listed under every stock

    own = Rig(spec_example)  # belongs to IBM
    own.controller.start(spec_example.id)
    own.controller.open_stock('BBB')
    assert own.explorer.log == [('add_symbol', 'BBB')]  # not that stock's strategy: just open the stock


def test_an_unknown_strategy_and_an_empty_database_say_so(spec_example):
    rig = Rig(spec_example)
    rig.controller.start('missing')
    assert 'no longer exists' in rig.view.notices[-1] and rig.calls == []
    empty = Rig(spec_example, stocks=STOCKS.iloc[0:0])
    empty.controller.start(spec_example.id)
    assert 'no stocks in the database' in empty.view.notices[-1] and empty.view.rows == []


def test_rows_and_summary_helpers_handle_a_run_where_nothing_could_run():
    results = [StockResult('AAA', '', None, 'no prices')]
    assert summary_line(results) == 'The strategy could not be run on any stock.'
    assert compare_rows(results)[0].cells[3].text == 'n/a'


def test_the_real_backtest_is_used_by_default_and_gives_the_10k_end_value(spec_example):
    daily = random_walk(500, seed=7)
    stocks = pd.DataFrame({'symbol': ['AAA'], 'first_date': [daily.index[0]], 'last_date': [daily.index[-1]],
                           'last_close': [float(daily['close'].iloc[-1])]})
    rig = Rig(spec_example, stocks=stocks, series=lambda symbol: daily, settings=('1D', '1Y'))
    rig.controller.backtest = real_backtest
    rig.controller.start(spec_example.id)
    [row] = rig.view.rows
    seeded = dataclasses.replace(spec_example, costs=dataclasses.replace(spec_example.costs, capital=10_000))
    from prices import range_start, to_candles
    expected = real_backtest(seeded, to_candles(daily, '1D'), daily, range_start(daily.index[-1], daily.index[0], '1Y'),
                             'AAA').metrics
    assert row.cells[2].sort_value == pytest.approx(expected['end_capital'])

"""Tools > Strategy Scoreboard: the engine, the table model and the controller, with fake prices and fake backtests."""
from types import SimpleNamespace

import pandas as pd
import pytest

from conftest import random_walk
from core.common import theme
from core.common.background import BackgroundLoader
from core.scoreboard import model
from core.scoreboard.controller import ScoreboardController
from strategy import RuleGroup, Strategy
from strategy.scoreboard import MIN_PART, Run, best_of, pick_of, score_stock, summarise

LENGTH = 100  # candles per stock: 60 in the pick period, 40 in the test period


def strategy(name: str, symbol: str | None = None) -> Strategy:
    return Strategy(name, RuleGroup('all', []), RuleGroup('any', []), symbol=symbol)


S1, S2 = strategy('Alpha rule'), strategy('Beta rule')
STRATEGIES = [S1, S2]


def metrics(ret: float, hold: float, trades: int = 3, drawdown: float = -10.0) -> SimpleNamespace:
    return SimpleNamespace(metrics={'return_pct': ret, 'buy_hold_return_pct': hold, 'max_drawdown_pct': drawdown,
                                    'trades': trades})


def fake_backtest(table: dict):
    """table[(symbol, strategy name, 'whole' | 'pick' | 'test')] -> (return, buy & hold). A ValueError is raised as is."""
    def backtest(strategy, candles, benchmark, start, symbol):
        if len(candles) < LENGTH:
            phase = 'pick'
        elif start > candles.index[0]:
            phase = 'test'
        else:
            phase = 'whole'
        outcome = table[(symbol, strategy.name, phase)]
        if isinstance(outcome, Exception):
            raise outcome
        return metrics(*outcome)
    return backtest


def table_for(symbol: str, whole: dict, pick: dict, test: dict) -> dict:
    """Each dict: strategy name -> (return, hold)."""
    out = {}
    for phase, values in (('whole', whole), ('pick', pick), ('test', test)):
        for name, outcome in values.items():
            out[(symbol, name, phase)] = outcome
    return out


def candles() -> pd.DataFrame:
    return random_walk(LENGTH, seed=3)


def score(symbol='AAA', **phases):
    return score_stock(STRATEGIES, candles(), None, candles().index[0], symbol, fake_backtest(table_for(symbol, **phases)))


# --- the engine ---

def test_the_best_strategy_must_clearly_lead_and_beat_buy_and_hold():
    assert best_of({'a': Run(30, 10), 'b': Run(5, 10)}) == 'a'
    assert best_of({'a': Run(8, 10), 'b': Run(5, 10)}) is None  # the leader did not beat buy & hold
    assert best_of({'a': Run(0, 10), 'b': Run(0, 10)}) is None
    assert best_of({'a': Run(20, 10), 'b': Run(20, 10)}) is None  # tied at the top: nothing separated
    assert best_of({'a': Run(20, 10)}) is None  # one strategy is nothing to compare with


def test_the_pick_need_not_have_beaten_buy_and_hold_but_must_lead():
    assert pick_of({'a': Run(8, 10), 'b': Run(5, 10)}) == 'a'
    assert pick_of({'a': Run(5, 10), 'b': Run(5, 10)}) is None


def test_a_stock_is_scored_over_the_whole_range_the_first_part_and_the_rest():
    result = score(whole={'Alpha rule': (30, 10), 'Beta rule': (5, 10)},
                   pick={'Alpha rule': (40, 20), 'Beta rule': (1, 20)}, test={'Alpha rule': (-5, 8), 'Beta rule': (9, 8)})
    assert result.whole[S1.id].margin == 20 and result.whole[S2.id].beat_hold is False
    assert result.pick[S1.id].return_pct == 40 and result.test[S2.id].beat_hold is True
    assert result.split == candles().index[60]  # the test starts after the first 60%


def test_too_little_history_means_no_split_and_a_strategy_that_cannot_run_is_recorded_with_its_reason():
    short = random_walk(2 * MIN_PART - 1, seed=3)
    outcomes = {('AAA', 'Alpha rule', 'whole'): (10, 5), ('AAA', 'Beta rule', 'whole'): ValueError('needs the S&P 500')}

    def backtest(strategy, candles, benchmark, start, symbol):
        outcome = outcomes[(symbol, strategy.name, 'whole')]
        if isinstance(outcome, Exception):
            raise outcome
        return metrics(*outcome)
    result = score_stock(STRATEGIES, short, None, short.index[0], 'AAA', backtest)
    assert result.split is None and result.pick == {} and result.test == {}
    assert list(result.whole) == [S1.id] and result.skipped == {S2.id: 'needs the S&P 500'}


def two_stocks():
    first = score('AAA', whole={'Alpha rule': (30, 10), 'Beta rule': (5, 10)},
                  pick={'Alpha rule': (40, 20), 'Beta rule': (1, 20)}, test={'Alpha rule': (-5, 8), 'Beta rule': (9, 8)})
    second = score('BBB', whole={'Alpha rule': (4, 10), 'Beta rule': (50, 10)},
                   pick={'Alpha rule': (2, 20), 'Beta rule': (30, 20)}, test={'Alpha rule': (6, 8), 'Beta rule': (12, 8)})
    return [first, second]


def test_the_scoreboard_counts_who_beat_buy_and_hold_and_how_far_ahead_the_middle_stock_was():
    board = {row.name: row for row in summarise(two_stocks(), STRATEGIES).board}
    alpha, beta = board['Alpha rule'], board['Beta rule']
    assert (alpha.ran, alpha.beat, alpha.beat_pct) == (2, 1, 50.0)
    assert alpha.median_margin == pytest.approx((20 + -6) / 2) and alpha.stars == 1
    assert (beta.beat, beta.median_return, beta.avg_hold, beta.stars) == (1, pytest.approx(27.5), 10, 1)


def test_the_best_per_stock_has_its_margin_and_runner_up():
    best = {row.symbol: row for row in summarise(two_stocks(), STRATEGIES).best}
    assert best['AAA'].best_id == S1.id and best['AAA'].best.margin == 20 and best['AAA'].runner_up_id == S2.id
    assert best['BBB'].best_id == S2.id and best['BBB'].beating_hold == 1 and best['BBB'].ran == 2


def test_the_out_of_sample_check_scores_the_first_parts_pick_on_the_later_part_only():
    result = summarise(two_stocks(), STRATEGIES)
    rows = {row.symbol: row for row in result.out_of_sample}
    assert rows['AAA'].picked_id == S1.id and rows['AAA'].picked_pick.return_pct == 40
    assert rows['AAA'].picked_test.return_pct == -5  # the pick did badly afterwards
    assert rows['BBB'].picked_id == S2.id and rows['BBB'].picked_test.beat_hold
    assert result.pick_win_pct == 100 and result.test_win_pct == 50
    assert result.average_test_win_pct == 50  # only Beta rule beat hold in the later part, on each stock


def test_a_stock_where_nothing_ran_is_counted_and_has_no_best():
    nothing = score_stock(STRATEGIES, candles(), None, candles().index[0], 'ZZZ',
                          fake_backtest({('ZZZ', 'Alpha rule', 'whole'): ValueError('x'),
                                         ('ZZZ', 'Beta rule', 'whole'): ValueError('y')}))
    result = summarise([nothing], STRATEGIES)
    assert result.skipped_stocks == 1 and result.stocks == 0 and result.best[0].best is None
    assert all(row.ran == 0 and row.skipped == 1 for row in result.board)


# --- the table model ---

def test_the_model_formats_sortable_coloured_rows_and_plain_english_summaries():
    scoreboard = summarise(two_stocks(), STRATEGIES)
    result = model.scoreboard_result(scoreboard, STRATEGIES)
    assert [row.cells[0].text for row in result.board] == ['Alpha rule', 'Beta rule']  # tied at 50%: by name
    alpha = result.board[0].cells
    assert alpha[1].text == '1 of 2' and alpha[2].text == '50%' and alpha[3].text == '+7.0 pts'
    assert alpha[3].color == theme.UP and alpha[3].sort_value == 7.0
    best = {row.key: row for row in result.best}
    assert best['AAA'].cells[1].text == 'Alpha rule' and best['AAA'].cells[4].text == '+20.0 pts'
    assert best['AAA'].group == S1.id and best['AAA'].cells[5].text == 'Beta rule +5%'
    out = {row.key: row for row in result.out_of_sample}
    assert out['AAA'].cells[5].text == '-13.0 pts' and out['AAA'].cells[5].color == theme.DOWN
    assert 'only on 1 of 2 (50%)' in result.out_summary and 'picked at random beat it on 50%' in result.out_summary
    assert 'survivors' in result.summary and 'Some strategy beat buy & hold on 2 stocks' in result.summary


def test_with_no_split_the_out_of_sample_text_says_why():
    only_whole = StockScoreHelper.short()
    text = model.scoreboard_result(summarise([only_whole], STRATEGIES), STRATEGIES).out_summary
    assert 'not enough history' in text


class StockScoreHelper:
    @staticmethod
    def short():
        from strategy.scoreboard import StockScore
        return StockScore('AAA', {S1.id: Run(10, 5), S2.id: Run(1, 5)})


# --- the controller ---

STOCKS = pd.DataFrame({'symbol': ['AAA', 'BBB'], 'first_date': pd.to_datetime(['2020-01-01'] * 2),
                       'last_date': pd.to_datetime(['2020-05-20'] * 2), 'last_close': [10.0, 20.0]})


class FakeView:
    def __init__(self) -> None:
        self.header, self.result, self.notices, self.running, self.progress = '', 'unset', [], False, None

    def show_header(self, text): self.header = text
    def show_result(self, result): self.result = result
    def show_progress(self, done, total, text): self.progress = (done, total, text)
    def show_notice(self, text): self.notices.append(text)
    def set_running(self, running): self.running = running


class FakeExplorer:
    def __init__(self) -> None:
        self.log = []

    def add_symbol(self, symbol): self.log.append(('add_symbol', symbol))
    def select_strategy(self, symbol, strategy_id): self.log.append(('select_strategy', symbol, strategy_id))


class Rig:
    def __init__(self, strategies=None, settings=('1W', 'Max'), stocks=STOCKS) -> None:
        self.view, self.explorer, self.calls = FakeView(), FakeExplorer(), []
        self.settings, self.strategies = list(settings), STRATEGIES if strategies is None else strategies
        self.controller = ScoreboardController(
            self.view, BackgroundLoader.immediate(), lambda: list(self.strategies), self.explorer,
            lambda: tuple(self.settings), lambda: stocks, lambda symbol: candles(), self.backtest)

    def backtest(self, strategy, candles, benchmark, start, symbol):
        self.calls.append((symbol, strategy.name, strategy.costs.capital, candles.attrs['candle_size']))
        return metrics(30.0 if strategy.name == 'Alpha rule' else 5.0, 10.0)


def test_it_tests_every_strategy_on_every_stock_with_10_thousand_and_the_chosen_candles():
    rig = Rig()
    rig.controller.start()
    assert {call[2] for call in rig.calls} == {10_000} and {call[3] for call in rig.calls} == {'1W'}
    assert {(call[0], call[1]) for call in rig.calls} == {(s, n) for s in ('AAA', 'BBB') for n in ('Alpha rule', 'Beta rule')}
    assert '2 strategies' in rig.view.header and '1W candles' in rig.view.header and '$10,000' in rig.view.header
    assert rig.view.result.board[0].cells[0].text == 'Alpha rule' and not rig.controller.running and not rig.view.running


def test_running_again_with_the_same_settings_uses_the_remembered_results():
    rig = Rig()
    rig.controller.start()
    first = len(rig.calls)
    rig.controller.start()
    assert len(rig.calls) == first
    rig.settings = ['1D', 'Max']
    rig.controller.start()
    assert len(rig.calls) > first  # another candle size is a new test


def test_a_strategy_made_for_one_stock_is_only_tried_on_that_stock():
    own = strategy('Only BBB', symbol='BBB')
    rig = Rig([S1, own])
    rig.controller.start()
    assert {call[0] for call in rig.calls if call[1] == 'Only BBB'} == {'BBB'}


def test_stop_keeps_the_stocks_that_finished_and_says_so():
    rig = Rig()
    original = rig.backtest

    def stopping(strategy, candles, benchmark, start, symbol):
        rig.controller.stop()  # pressed while the first stock is being tested
        return original(strategy, candles, benchmark, start, symbol)
    rig.controller.backtest = stopping
    rig.controller.start()
    assert 'Stopped: 1 of 2 stocks were tested' in rig.view.notices[-1]
    assert {call[0] for call in rig.calls} == {'AAA'} and not rig.controller.running


def test_nothing_runs_without_strategies_or_while_already_running():
    rig = Rig([])
    rig.controller.start()
    assert 'no strategies' in rig.view.notices[-1] and rig.calls == []
    rig = Rig()
    rig.controller.running = True
    rig.controller.start()
    assert rig.calls == []


def test_opening_a_stock_selects_its_best_strategy_or_just_adds_the_stock():
    rig = Rig()
    rig.controller.start()
    rig.controller.open_stock('AAA')  # Alpha rule clearly beat hold and Beta rule on both stocks
    assert rig.explorer.log == [('select_strategy', 'AAA', S1.id)]
    rig.controller._best['BBB'] = None
    rig.controller.open_stock('BBB')
    assert rig.explorer.log[-1] == ('add_symbol', 'BBB')


def test_an_empty_database_says_how_to_add_stocks():
    rig = Rig(stocks=STOCKS.iloc[0:0])
    rig.controller.start()
    assert 'no stocks in the database' in rig.view.notices[-1]

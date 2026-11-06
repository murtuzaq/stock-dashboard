"""DashboardController: the session logic that used to live in the view-area widget, driven with a fake view."""
import pandas as pd

from conftest import random_walk
from core.common.background import BackgroundLoader
from core.dashboard.controller import DashboardController, header_model
from strategy import Costs, Strategy


class FakeView:
    """Records what the controller asked the renderer to do."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def show_selection(self, title, layout):
        self.calls.append(('selection', title, layout))

    def set_symbol(self, symbol):
        self.calls.append(('symbol', symbol))

    def show_empty(self):
        self.calls.append(('empty',))

    def show_status(self, text):
        self.calls.append(('status', text))

    def show_data(self, daily, candles, benchmark):
        self.calls.append(('data', len(daily), len(candles), len(benchmark)))

    def show_range(self, start, header):
        self.calls.append(('range', start, header))

    def show_strategy(self, strategy, result, candles):
        self.calls.append(('strategy', strategy.name, result))

    def clear_strategy(self):
        self.calls.append(('clear',))

    def show_backtest(self, chart):
        self.calls.append(('backtest', chart))

    def of(self, kind):
        return [call for call in self.calls if call[0] == kind]


class FakeStrategies:
    def __init__(self, strategy: Strategy | None = None) -> None:
        self.strategy = strategy
        self.saved_costs = None

    def get(self, strategy_id):
        return self.strategy

    def update_costs(self, strategy_id, costs):
        self.strategy.costs = costs
        self.saved_costs = costs
        return self.strategy


def make_controller(history=None, strategies=None, loader=None):
    view = FakeView()
    calls = []

    def source(symbol):
        calls.append(symbol)
        if history is None:
            return random_walk(400, seed=hash(symbol) % 1000)
        return history(symbol)

    controller = DashboardController(view, loader or BackgroundLoader.immediate(), strategies or FakeStrategies(),
                                     source)
    controller.source_calls = calls
    return controller, view


def test_showing_a_symbol_loads_history_and_renders_it():
    controller, view = make_controller()
    controller.show_views('AAA', ['price', 'macd'], '1D')
    assert view.of('selection')[0][1] == 'AAA · Price + MACD · 1D'
    assert view.of('selection')[0][2].shown == ['price', 'macd']
    assert view.of('data')[0][:3] == ('data', 400, 400)
    start, header = view.of('range')[0][1:]
    assert start is not None and header.last
    assert controller.symbol == 'AAA' and controller.range == '1Y'


def test_history_is_downloaded_once_per_symbol_per_session():
    controller, view = make_controller()
    controller.show_views('AAA', ['price'], '1D')
    controller.show_views('BBB', ['price'], '1D')
    controller.show_views('AAA', ['price'], '1D')
    assert controller.source_calls.count('AAA') == 1


def test_changing_only_the_selection_does_not_rerender_data():
    controller, view = make_controller()
    controller.show_views('AAA', ['price'], '1D')
    controller.show_views('AAA', ['price', 'volume'], '1D')
    assert len(view.of('data')) == 1


def test_candle_size_change_rebuilds_candles():
    controller, view = make_controller()
    controller.show_views('AAA', ['price'], '1D')
    controller.set_candle_size('1W')
    assert controller.candle_size == '1W'
    assert view.of('data')[-1][2] < 400  # fewer, bigger candles


def test_candle_size_before_any_symbol_is_remembered():
    controller, view = make_controller()
    controller.set_candle_size('1M')
    assert controller.candle_size == '1M' and view.calls == []


def test_range_change_updates_start_and_header():
    controller, view = make_controller()
    controller.show_views('AAA', ['price'], '1D')
    first_start = controller.start
    controller.set_range('1M')
    assert controller.start > first_start
    assert 'past month' in view.of('range')[-1][2].change


def test_empty_history_shows_a_message():
    controller, view = make_controller(history=lambda symbol: pd.DataFrame())
    controller.show_views('ZZZ', ['price'], '1D')
    assert 'No price history found for ZZZ' in view.of('status')[-1][1]
    assert view.of('range')[-1][1:] == (None, None)


def test_a_failed_download_is_reported_not_left_loading():
    def boom(symbol):
        raise OSError('offline')

    controller, view = make_controller(history=boom)
    controller.show_views('AAA', ['price'], '1D')
    assert 'Could not load price history for AAA' in view.of('status')[-1][1]


def test_a_download_for_a_symbol_the_user_left_is_ignored():
    pending = []

    class Deferred(BackgroundLoader):
        def run(self, work, done, failed=None):
            pending.append((work, done))

    controller, view = make_controller(loader=Deferred(post=lambda call: call()))
    controller.show_views('AAA', ['price'], '1D')
    controller.show_views('BBB', ['price'], '1D')
    for work, done in pending:  # AAA finishes after the user moved to BBB
        done(work())
    assert controller.daily.keys() == {'AAA', 'BBB'}
    assert len(view.of('data')) == 1  # only BBB (the current symbol) was rendered


def test_strategy_is_backtested_once_per_data_and_rules(spec_example):
    strategies = FakeStrategies(spec_example)
    controller, view = make_controller(strategies=strategies)
    controller.show_views('AAA', ['price', f'strategy:{spec_example.id}'], '1D')
    assert controller.strategy_id == spec_example.id
    assert view.of('selection')[0][2].shown == ['price', 'strategy']
    assert 'Strategy "MACD + Stoch RSI"' in view.of('selection')[0][1]
    results = view.of('strategy')
    assert results and results[-1][1] == spec_example.name
    controller.refresh_strategy()
    assert view.of('strategy')[-1][2] is results[-1][2]  # same cached result object


def test_changing_costs_saves_and_reruns(spec_example):
    strategies = FakeStrategies(spec_example)
    controller, view = make_controller(strategies=strategies)
    controller.show_views('AAA', [f'strategy:{spec_example.id}'], '1D')
    before = view.of('strategy')[-1][2]
    controller.update_costs(Costs(capital=50_000, commission=1, slippage_pct=0.1))
    assert strategies.saved_costs.capital == 50_000
    assert view.of('strategy')[-1][2] is not before  # rules/costs hash changed, so a fresh backtest


def test_no_strategy_selected_clears_overlays():
    controller, view = make_controller()
    controller.show_views('AAA', ['price'], '1D')
    assert view.of('clear')


def test_header_model_colours_by_the_range_change():
    candles = random_walk(300, seed=3)
    start = candles.index[0]
    model = header_model(candles, start, '1Y')
    assert model.change_color in ('#26a69a', '#ef5350')
    assert model.detail.startswith('· today')



def test_clear_returns_to_the_empty_state_and_the_same_stock_can_be_shown_again():
    controller, view = make_controller()
    controller.show_views('AAA', ['price', 'macd'], '1D')
    controller.clear()
    assert view.of('empty') and controller.symbol is None and controller.shown == [] and controller.candles.empty
    assert controller.start is None and controller.strategy_id is None

    controller.show_views('AAA', ['price'], '1D')  # same stock again: drawn from the cache, not downloaded again
    assert controller.source_calls.count('AAA') == 1 and view.of('data')[-1][1] == 400
    controller.range = '1M'
    controller.set_range('3M')  # works normally afterwards
    assert controller.start is not None


def test_clear_with_nothing_showing_is_harmless():
    controller, view = make_controller()
    controller.clear()
    controller.set_range('1M')
    assert view.of('empty') and view.of('range') == []


class StrategiesById(FakeStrategies):
    def __init__(self, *strategies: Strategy) -> None:
        super().__init__(strategies[0])
        self.by_id = {strategy.id: strategy for strategy in strategies}

    def get(self, strategy_id):
        return self.by_id.get(strategy_id)

    def for_symbol(self, symbol):
        return list(self.by_id.values())


def test_two_or_more_strategies_show_only_the_comparison_chart(spec_example):
    import dataclasses
    other = dataclasses.replace(spec_example, id='other-id', name='Other')
    controller, view = make_controller(strategies=StrategiesById(spec_example, other))
    keys = ['price', f'strategy:{spec_example.id}', f'strategy:{other.id}']
    controller.show_views('AAA', keys, '1D')
    assert view.of('selection')[0][2].shown == ['price', 'backtest']  # no single-strategy panel for several
    assert controller.strategy_id is None and len(controller.strategy_ids) == 2
    chart = view.of('backtest')[-1][1]
    assert [series.label for series in chart.series[:2]] == ['MACD + Stoch RSI', 'Other']
    assert chart.series[-1].is_hold and len({series.color for series in chart.series}) == 3
    assert view.of('clear') and not view.of('strategy')  # no trade arrows or results without exactly one strategy


def test_one_strategy_shows_the_full_results_panel_and_no_comparison_chart(spec_example):
    controller, view = make_controller(strategies=FakeStrategies(spec_example))
    controller.show_views('AAA', ['price', f'strategy:{spec_example.id}'], '1D')
    assert view.of('selection')[0][2].shown == ['price', 'strategy']
    assert view.of('strategy') and not view.of('backtest')


def test_no_strategy_selected_shows_no_comparison_chart():
    controller, view = make_controller()
    controller.show_views('AAA', ['price'], '1D')
    assert not view.of('backtest')


def test_comparison_results_are_cached_across_refreshes(spec_example):
    import dataclasses
    other = dataclasses.replace(spec_example, id='other-id', name='Other', costs=Costs(capital=5_000))
    controller, view = make_controller(strategies=StrategiesById(spec_example, other))
    controller.show_views('AAA', [f'strategy:{spec_example.id}', f'strategy:{other.id}'], '1D')
    first = len(controller._results)
    controller.refresh_strategy()
    assert len(controller._results) == first == 2  # one backtest per distinct strategy, run once


# --- the best strategy of the stock on screen (the star in the Explorer) ---

def fast_slow(spec_example):
    import dataclasses
    return spec_example, dataclasses.replace(spec_example, id='slow-id', name='Slow', costs=Costs(capital=5_000))


class FakeBacktests:
    """Stands in for run_backtest: 'MACD + Stoch RSI' wins over short, recent ranges and 'Slow' over long ones."""

    def __init__(self, monkeypatch) -> None:
        self.calls = []
        monkeypatch.setattr('core.dashboard.controller.run_backtest', self)

    def __call__(self, strategy, candles, benchmark, start, symbol):
        from types import SimpleNamespace
        self.calls.append((strategy.name, start))
        recent = start >= candles.index[200]
        wins = (strategy.name == 'MACD + Stoch RSI') == recent
        return SimpleNamespace(metrics={'return_pct': 10.0 if wins else 5.0, 'buy_hold_return_pct': 1.0})


def best_recorder(controller):
    announced = []
    controller.on_best_strategy = lambda symbol, best: announced.append((symbol, best and best.strategy_id))
    return announced


def test_the_best_strategy_follows_the_selected_range(spec_example, monkeypatch):
    fast, slow = fast_slow(spec_example)
    backtests = FakeBacktests(monkeypatch)
    controller, view = make_controller(strategies=StrategiesById(fast, slow))
    announced = best_recorder(controller)
    controller.show_views('AAA', ['price'], '1D')
    controller.set_range('1M')
    assert announced[-1] == ('AAA', fast.id)  # a short, recent range: the fast one
    controller.set_range('Max')
    assert announced[-1] == ('AAA', 'slow-id')  # the whole history: the other one wins
    runs = len(backtests.calls)
    controller.set_range('1M')
    assert announced[-1] == ('AAA', fast.id) and len(backtests.calls) == runs  # reused from the cache, not re-run


def test_selecting_a_strategy_afterwards_reuses_the_backtests_run_for_the_star(spec_example, monkeypatch):
    fast, slow = fast_slow(spec_example)
    backtests = FakeBacktests(monkeypatch)
    controller, view = make_controller(strategies=StrategiesById(fast, slow))
    best_recorder(controller)
    controller.show_views('AAA', ['price'], '1D')
    runs = len(backtests.calls)
    controller.show_views('AAA', ['price', f'strategy:{fast.id}'], '1D')
    assert len(backtests.calls) == runs and view.of('strategy')


def test_a_star_for_another_range_is_taken_off_other_stocks(spec_example, monkeypatch):
    fast, slow = fast_slow(spec_example)
    FakeBacktests(monkeypatch)
    controller, view = make_controller(strategies=StrategiesById(fast, slow))
    announced = best_recorder(controller)
    controller.show_views('AAA', ['price'], '1D')
    controller.show_views('BBB', ['price'], '1D')
    assert ('AAA', None) in announced and announced[-1][0] == 'BBB' and announced[-1][1] is not None


def test_a_result_for_a_range_the_user_already_left_is_not_announced(spec_example, monkeypatch):
    fast, slow = fast_slow(spec_example)
    FakeBacktests(monkeypatch)
    controller, view = make_controller(strategies=StrategiesById(fast, slow))
    announced = best_recorder(controller)
    controller.show_views('AAA', ['price'], '1D')
    waiting = []
    controller.loader = BackgroundLoader(post=waiting.append, threaded=False)  # deliveries wait until we flush them
    controller.set_range('1M')
    controller.set_range('Max')
    announced.clear()
    for deliver in waiting:
        deliver()
    assert announced == [('AAA', 'slow-id')]  # only the range on screen now; the 1M result was cached, not shown


def test_a_strategy_that_cannot_run_is_left_out_and_not_retried(spec_example, monkeypatch):
    fast, slow = fast_slow(spec_example)
    calls = []

    def run(strategy, candles, benchmark, start, symbol):
        from types import SimpleNamespace
        calls.append(strategy.name)
        if strategy.name == 'Slow':
            raise ValueError('needs the S&P 500')
        return SimpleNamespace(metrics={'return_pct': 4.0, 'buy_hold_return_pct': 1.0})
    monkeypatch.setattr('core.dashboard.controller.run_backtest', run)
    controller, view = make_controller(strategies=StrategiesById(fast, slow))
    announced = best_recorder(controller)
    controller.show_views('AAA', ['price'], '1D')
    assert announced[-1] == ('AAA', None)  # only one strategy ran: nothing to outperform
    first = len(calls)
    controller.refresh_best()
    assert len(calls) == first  # the failure was remembered

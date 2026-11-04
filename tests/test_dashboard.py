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


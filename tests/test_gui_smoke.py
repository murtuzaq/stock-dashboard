"""The real window, offscreen, driven end to end with canned data (no network, no event loop)."""
import os

import pytest

pytest.importorskip('PySide6')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pandas as pd  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from conftest import random_walk  # noqa: E402
from core.common.background import BackgroundLoader  # noqa: E402
from core.dashboard.layout import PANEL_ORDER, VIEWS  # noqa: E402
from strategy import Operand, repository  # noqa: E402


def financials(symbol):
    index = pd.to_datetime(['2025-03-31', '2025-06-30', '2025-09-30', '2025-12-31'])
    figures = pd.DataFrame({'revenue': [1e9, 1.1e9, 1.2e9, 1.3e9], 'eps': [1.0, 1.1, 1.2, 1.3],
                            'revenue_qoq': [float('nan'), 10, 9, 8], 'revenue_yoy': [float('nan')] * 3 + [20.0],
                            'eps_qoq': [float('nan'), 10, 9, 8], 'eps_yoy': [float('nan')] * 3 + [30.0]},
                           index=index)
    return {'quarterly': figures, 'annual': figures.iloc[[-1]]}


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(repository, 'ROOT', tmp_path / 'strategies')
    from main import MainWindow
    import qtrender.searchbar.bar as search_bar
    from search import Catalog
    monkeypatch.setattr(search_bar, 'load_catalog', lambda: Catalog({}, [], frozenset()))
    main_window = MainWindow(BackgroundLoader.immediate(), lambda symbol: random_walk(500, seed=len(symbol)),
                             financials)
    main_window.show()
    yield main_window
    main_window.close()


def test_every_view_renders_for_every_candle_size_and_range(window):
    window.explorer_controller.add_symbol('TEST')
    window.explorer.clearSelection()
    for key, _ in VIEWS:  # every non-strategy view at once
        window.explorer.items[('TEST', key)].setSelected(True)
    controller = window.controller
    # SMA is drawn on the Price chart, so it has no panel of its own.
    assert controller.shown == [key for key in PANEL_ORDER if key in dict(VIEWS) and key != 'sma']
    for candle_size in ('1D', '1W', '1M'):
        window.header.timeframe_changed.emit(candle_size)
        for range_label in ('1M', 'YTD', 'Max'):
            window.view_area.range_selected.emit(range_label)
    assert 'Latest quarter' in window.view_area.views['growth'].summary.text()
    assert window.view_area.last_price.text()


def test_strategy_results_and_wizard_flow(window):
    from strategy import Condition, Exits, Operand, RuleGroup, Strategy
    saved = Strategy('Trend', RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma', params={'days': 50}))]),
                     RuleGroup('any', [Condition(Operand('close'), 'below', Operand('sma', params={'days': 50}))]),
                     Exits(stop_loss_pct=8), symbol='TEST')
    repository.save(saved)
    window.explorer_controller.add_symbol('TEST')
    window.explorer_controller.refresh_strategies()
    window.explorer_controller.select_strategy('TEST', saved.id)
    strategy_view = window.view_area.views['strategy']
    assert strategy_view.strategy.id == saved.id and strategy_view.table.rowCount() > 0
    assert 'Return' in strategy_view.cards.text()

    # Edit it through the wizard and save: the results refresh under the same selection.
    window.strategy_controller.handle('edit', 'TEST', saved.id)
    wizard = window.wizard
    wizard.name.setText('Trend v2')
    for _ in range(4):
        wizard.next_button.click()
    assert repository.get(saved.id).name == 'Trend v2'
    assert not wizard.isVisible()
    assert 'Trend v2' in strategy_view.rules.text()


def test_new_strategy_wizard_reports_validation_errors(window):
    window.explorer_controller.add_symbol('TEST')
    window.strategy_controller.handle('new', 'TEST', '')
    wizard = window.wizard
    assert wizard.pages.currentIndex() == 0
    wizard.copy_radio.setChecked(True)
    wizard.next_button.click()
    assert 'Choose the strategy to copy' in wizard.error.text()
    wizard.new_radio.setChecked(True)
    wizard.next_button.click()
    wizard.name.setText('')
    wizard.next_button.click()
    assert wizard.error.text() == 'Give the strategy a name.'


def test_trades_are_drawn_on_price_and_indicator_charts(window):
    from strategy import Condition, Exits, Operand, RuleGroup, Strategy
    saved = Strategy('Trend', RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma', params={'days': 50}))]),
                     RuleGroup('any', [Condition(Operand('close'), 'below', Operand('sma', params={'days': 50}))]),
                     Exits(stop_loss_pct=8), symbol='TEST')
    repository.save(saved)
    window.explorer_controller.add_symbol('TEST')
    window.explorer_controller.refresh_strategies()
    window.explorer_controller.select_strategy('TEST', saved.id)
    for key in ('price', 'macd'):
        window.explorer.items[('TEST', key)].setSelected(True)  # like Ctrl+click: stack more views
    overlays = window.view_area.trade_overlays
    assert 'strategy' in window.controller.shown and {'price', 'macd'} <= set(window.controller.shown)
    assert overlays['price'].items and overlays['macd'].items
    assert not overlays['volume'].items  # not shown, so nothing drawn
    price_kinds = {type(item).__name__ for item in overlays['price'].items}
    macd_kinds = {type(item).__name__ for item in overlays['macd'].items}
    assert 'ScatterPlotItem' in price_kinds and 'ScatterPlotItem' not in macd_kinds
    assert 'InfiniteLine' in macd_kinds and 'InfiniteLine' not in price_kinds


def test_selecting_one_strategy_deselects_the_other(window):
    from strategy import Condition, Exits, RuleGroup, Strategy
    for name in ('Template A', 'Template B'):
        repository.save(Strategy(name, RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma'))]),
                                 RuleGroup('any', []), Exits(stop_loss_pct=5)))  # symbol None: library
    window.explorer_controller.add_symbol('TEST')
    library = [item for (symbol, key), item in window.explorer.items.items() if key.startswith('strategy:')]
    assert len(library) >= 2
    library[0].setSelected(True)
    library[1].setSelected(True)
    window.explorer.setCurrentItem(library[1])
    chosen = [i for i in window.explorer.selectedItems() if i.data(0, 257) == 'strategy']
    assert len(chosen) == 1


def test_changing_a_condition_row_suggests_a_matching_right_side(window):
    window.explorer_controller.add_symbol('TEST')
    window.strategy_controller.handle('new', 'TEST', '')
    row = window.wizard.buy.add_row()
    row.left.choice.setCurrentIndex(row.left.choice.findData('stoch_rsi:k'))
    assert row.condition().right == Operand(value=20)
    row.left.choice.setCurrentIndex(row.left.choice.findData('macd:macd'))
    assert row.condition().right == Operand('macd', 'signal')


def test_search_bar_widget_drives_the_controller(window):
    from PySide6.QtCore import Qt
    from search import Catalog, Group, Security
    apple = Security('AAPL', 'Apple Inc', 'NASDAQ', False, ('apple', 'inc'))
    group = Group('Nasdaq-100', 'Index', 'Largest Nasdaq stocks', ('nasdaq',), frozenset({'AAPL'}))
    bar = window.header.search
    bar.controller.catalog_loaded(Catalog({'AAPL': apple}, [group], frozenset()), input_has_focus=False)
    chosen = []
    bar.symbol_chosen.connect(chosen.append)

    bar.input.setText('app')
    bar.controller.refresh()
    assert bar.popup.isVisible() and bar.popup.topLevelItemCount() == 1
    assert bar._handle_key(Qt.Key.Key_Return) and chosen == ['AAPL']
    assert not bar.popup.isVisible() and bar.input.text() == ''

    bar.input.setText('nasdaq')
    bar.controller.refresh()
    bar.controller.choose(bar.popup.topLevelItem(0).data(0, 256))  # click the group row
    assert bar.scope_chip.isVisible() and 'Nasdaq-100' in bar.input.placeholderText()
    assert bar._handle_key(Qt.Key.Key_Backspace)  # empty box + filter: removes the filter
    assert not bar.scope_chip.isVisible()


def test_explorer_refresh_after_deleting_the_selected_strategy_falls_back_to_price(window):
    from strategy import Condition, Exits, RuleGroup, Strategy
    saved = Strategy('Temp', RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma'))]),
                     RuleGroup('any', []), Exits(stop_loss_pct=5), symbol='TEST')
    repository.save(saved)
    window.explorer_controller.add_symbol('TEST')
    window.explorer_controller.select_strategy('TEST', saved.id)
    assert window.controller.strategy_id == saved.id
    repository.delete(saved.id)
    window.explorer_controller.refresh_strategies()
    assert window.controller.strategy_id is None and window.controller.shown == ['price']
    assert [key for (symbol, key) in window.explorer.items if key.startswith('strategy:')] == []


def test_explorer_refresh_keeps_a_stack_of_views(window):
    window.explorer_controller.add_symbol('TEST')
    window.explorer.items[('TEST', 'macd')].setSelected(True)
    before = list(window.controller.shown)
    window.explorer_controller.refresh_strategies()
    assert window.controller.shown == before == ['price', 'macd']


def test_clicking_a_symbol_row_and_the_context_menu_are_wired(window):
    from core.explorer.controller import Node
    window.explorer_controller.add_symbol('TEST')
    window.explorer.items[('TEST', 'atr')].setSelected(True)
    window.explorer.setCurrentItem(window.explorer.symbol_items['TEST'])  # click the stock's own row
    assert window.controller.shown == ['price']

    menu = window.explorer.menu_source(Node('TEST', None, 'symbol'))
    assert [entry.action for entry in menu] == ['new']
    window.explorer.action_chosen.emit('new', Node('TEST', None, 'symbol'))
    assert window.wizard.isVisible() and 'New strategy for TEST' in window.wizard.title.text()

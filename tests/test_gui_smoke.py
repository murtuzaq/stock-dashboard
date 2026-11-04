"""The real window, offscreen, driven end to end with canned data (no network, no event loop)."""
import os

import pytest

pytest.importorskip('PySide6')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pandas as pd  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from conftest import random_walk  # noqa: E402
from core.background import BackgroundLoader  # noqa: E402
from core.views import PANEL_ORDER, VIEWS  # noqa: E402
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
    import qtrender.search_bar as search_bar
    monkeypatch.setattr(search_bar, 'load_catalog', lambda: search_bar.Catalog({}, [], frozenset()))
    main_window = MainWindow(BackgroundLoader.immediate(), lambda symbol: random_walk(500, seed=len(symbol)),
                             financials)
    main_window.show()
    yield main_window
    main_window.close()


def test_every_view_renders_for_every_candle_size_and_range(window):
    window.explorer.add_symbol('TEST')
    window.explorer.clearSelection()
    for item in window.explorer._view_items(window.explorer.symbols['TEST']):
        item.setSelected(item.data(0, 256) in [key for key, _ in VIEWS])  # every non-strategy view at once
    window.explorer._handle_selection()
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
    window.explorer.add_symbol('TEST')
    window.explorer.refresh_strategies()
    window.explorer.select_strategy('TEST', saved.id)
    strategy_view = window.view_area.views['strategy']
    assert strategy_view.strategy.id == saved.id and strategy_view.table.rowCount() > 0
    assert 'Return' in strategy_view.cards.text()

    # Edit it through the wizard and save: the results refresh under the same selection.
    window.strategy_actions.handle('edit', 'TEST', saved.id)
    wizard = window.wizard
    wizard.name.setText('Trend v2')
    for _ in range(4):
        wizard.next_button.click()
    assert repository.get(saved.id).name == 'Trend v2'
    assert not wizard.isVisible()
    assert 'Trend v2' in strategy_view.rules.text()


def test_new_strategy_wizard_reports_validation_errors(window):
    window.explorer.add_symbol('TEST')
    window.strategy_actions.handle('new', 'TEST', '')
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
    window.explorer.add_symbol('TEST')
    window.explorer.refresh_strategies()
    window.explorer.select_strategy('TEST', saved.id)
    for item in window.explorer._view_items(window.explorer.symbols['TEST']):
        if item.data(0, 256) in ('price', 'macd'):
            item.setSelected(True)  # like Ctrl+click: stack more views with the strategy
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
    window.explorer.add_symbol('TEST')
    library = [e for e in window.explorer._view_items(window.explorer.symbols['TEST'])
               if e.data(0, 257) == 'strategy']
    assert len(library) >= 2
    library[0].setSelected(True)
    library[1].setSelected(True)
    window.explorer.setCurrentItem(library[1])
    chosen = [i for i in window.explorer.selectedItems() if i.data(0, 257) == 'strategy']
    assert len(chosen) == 1


def test_changing_a_condition_row_suggests_a_matching_right_side(window):
    window.explorer.add_symbol('TEST')
    window.strategy_actions.handle('new', 'TEST', '')
    row = window.wizard.buy.add_row()
    row.left.choice.setCurrentIndex(row.left.choice.findData('stoch_rsi:k'))
    assert row.condition().right == Operand(value=20)
    row.left.choice.setCurrentIndex(row.left.choice.findData('macd:macd'))
    assert row.condition().right == Operand('macd', 'signal')

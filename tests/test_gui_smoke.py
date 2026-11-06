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
from core.explorer.controller import Node, Scope  # noqa: E402
from strategy import Operand, repository  # noqa: E402


def profile(symbol):
    from company import CompanyProfile
    return CompanyProfile(symbol, name=f'{symbol} Corporation', summary=f'{symbol} makes useful things.',
                          quote_type='EQUITY', sector='Technology', industry='Software', price=100.0,
                          market_cap=5e10, trailing_pe=40.0, revenue_growth=0.2, profit_margin=0.25,
                          debt_to_equity=200.0, analysts=10, recommendation='buy', recommendation_mean=2.0)


STORED_STOCKS = pd.DataFrame({
    'symbol': ['IBM', 'TEST'], 'days': [500, 500], 'first_date': pd.to_datetime(['2024-01-01'] * 2),
    'last_date': pd.to_datetime(['2025-12-01'] * 2), 'last_close': [250.0, 100.0], 'previous_close': [245.0, 101.0],
    'checked_at': [1.79e9, 1.79e9]})


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
    from PySide6.QtWidgets import QMessageBox
    from portfolio import repository as portfolio_repository
    monkeypatch.setattr(repository, 'ROOT', tmp_path / 'strategies')
    monkeypatch.setattr(portfolio_repository, 'ROOT', tmp_path / 'portfolios')
    messages, answers = [], {'confirm': True}
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda parent, title, text, *a: messages.append(text)))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(
        lambda parent, title, text, *a: messages.append(text) or (QMessageBox.StandardButton.Yes
                                                                  if answers['confirm'] else QMessageBox.StandardButton.No)))
    from main import MainWindow
    import qtrender.searchbar.bar as search_bar
    from search import Catalog
    monkeypatch.setattr(search_bar, 'load_catalog', lambda: Catalog({}, [], frozenset()))
    from core.learn.preferences import MemoryPreferences
    from learn import requests as info_requests
    monkeypatch.setattr(info_requests, 'FILE', tmp_path / 'info_requests.json')
    from core.downloads.controller import PacingProfile
    from search import Group, Security
    downloaded = []
    securities = {s: Security(s, f'{s} Inc', 'Nasdaq', False, ()) for s in ('AAA', 'BBB', 'IBM')}
    catalog = Catalog(securities, [Group('Test Index', 'Index', '', (), frozenset(securities))], frozenset())
    main_window = MainWindow(BackgroundLoader.immediate(), lambda symbol: random_walk(500, seed=len(symbol)),
                             financials, preferences=MemoryPreferences(), profile_source=profile,
                             stored_stocks_source=lambda: STORED_STOCKS.copy(),
                             names_source=lambda: {'TEST': 'Test Corporation', 'IBM': 'IBM Corp'},
                             catalog_source=lambda: catalog, download_pacing=PacingProfile(pause_min=0, pause_max=0),
                             download_refresh=lambda symbol: downloaded.append(symbol) or 'new')
    main_window.messages, main_window.answers, main_window.downloaded = messages, answers, downloaded
    main_window.show()
    yield main_window
    main_window.close()


def test_every_view_renders_for_every_candle_size_and_range(window):
    window.explorer_controller.add_symbol('TEST')
    window.explorer.clearSelection()
    for key, _ in VIEWS:  # every non-strategy view at once
        window.explorer.items[(Scope(None, 'TEST'), key)].setSelected(True)
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
        window.explorer.items[(Scope(None, 'TEST'), key)].setSelected(True)  # like Ctrl+click: stack more views
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
    library = [item for (scope, key), item in window.explorer.items.items() if key.startswith('strategy:')]
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
    assert [key for (scope, key) in window.explorer.items if key.startswith('strategy:')] == []


def test_explorer_refresh_keeps_a_stack_of_views(window):
    window.explorer_controller.add_symbol('TEST')
    window.explorer.items[(Scope(None, 'TEST'), 'macd')].setSelected(True)
    before = list(window.controller.shown)
    window.explorer_controller.refresh_strategies()
    assert window.controller.shown == before == ['price', 'macd']


def test_clicking_a_symbol_row_and_the_context_menu_are_wired(window):
    window.explorer_controller.add_symbol('TEST')
    window.explorer.items[(Scope(None, 'TEST'), 'atr')].setSelected(True)
    window.explorer.setCurrentItem(window.explorer.symbol_items[Scope(None, 'TEST')])  # click the stock's own row
    assert window.controller.shown == ['overview']
    assert [item.text(0) for item in window.explorer.selectedItems()] == ['TEST']  # the stock's row, nothing else

    menu = window.explorer.menu_source(Node('TEST', None, 'symbol'))
    assert menu[0].action == 'new' and menu[-1].text == 'Add to portfolio'
    window.explorer.action_chosen.emit('new', Node('TEST', None, 'symbol'), None)
    assert window.wizard.isVisible() and 'New strategy for TEST' in window.wizard.title.text()


# --- portfolios ------------------------------------------------------------------------------------------------

def portfolio_row(window, portfolio_id):
    return window.explorer.portfolio_items[portfolio_id]


def saved_portfolios():
    from core.portfolios.service import PortfolioService
    return PortfolioService().saved()


def test_file_menu_has_new_and_load_portfolio(window):
    file_menu = window.menu.actions()[0].menu()
    assert file_menu.title() == '&File'
    assert [a.text() for a in file_menu.actions() if not a.isSeparator()] == ['&New Portfolio', '&Load Portfolio…',
                                                                              'E&xit']


def test_new_portfolio_creates_a_node_in_rename_mode_and_saves_a_file(window, tmp_path):
    from PySide6.QtWidgets import QAbstractItemView
    window.menu.new_action.trigger()
    [summary] = saved_portfolios()
    assert summary.name == 'Portfolio 1' and (tmp_path / 'portfolios' / 'portfolio-1.json').exists()
    row = portfolio_row(window, summary.id)
    assert row.text(0) == 'Portfolio 1' and window.explorer.state() == QAbstractItemView.State.EditingState
    assert window.explorer_controller.portfolios == {summary.id: 'Portfolio 1'}


def test_typing_a_new_name_renames_and_a_refused_name_snaps_back(window):
    window.menu.new_action.trigger()
    window.menu.new_action.trigger()
    first, second = (s.id for s in saved_portfolios())
    portfolio_row(window, first).setText(0, '  Retirement ')
    assert [s.name for s in saved_portfolios()] == ['Portfolio 2', 'Retirement']
    assert portfolio_row(window, first).text(0) == 'Retirement'

    portfolio_row(window, second).setText(0, 'retirement')  # taken (case-insensitive)
    assert 'already exists' in window.messages[-1]
    assert portfolio_row(window, second).text(0) == 'Portfolio 2'
    portfolio_row(window, second).setText(0, '   ')
    assert 'needs a name' in window.messages[-1] and portfolio_row(window, second).text(0) == 'Portfolio 2'


def test_add_stock_panel_adds_many_stocks_then_done_dismisses_it(window):
    from search import Catalog, Security
    window.menu.new_action.trigger()
    [summary] = saved_portfolios()
    securities = {sym: Security(sym, f'{sym} Inc', 'NASDAQ', False, (sym.lower(),)) for sym in ('AAPL', 'MSFT')}
    panel = window.add_stock_panel
    panel.search.controller.catalog_loaded(Catalog(securities, [], frozenset()), input_has_focus=False)

    window.explorer_controller.menu_action('add_stock', Node('', None, 'portfolio', portfolio=summary.id))
    assert window.side_panel.isVisible() and panel.isVisible() and not window.wizard.isVisible()
    assert 'Add stocks to "Portfolio 1"' in panel.title.text()

    panel.search.controller.choose(securities['AAPL'])
    panel.search.controller.choose(securities['MSFT'])
    assert [panel.members.item(i).text() for i in range(panel.members.count())] == ['AAPL', 'MSFT']
    assert panel.notice.text() == 'Added MSFT.'
    panel.search.controller.choose(securities['AAPL'])
    assert 'already in this portfolio' in panel.notice.text()

    from portfolio import repository as portfolio_repository
    assert portfolio_repository.get(summary.id).symbols == ['AAPL', 'MSFT']
    children = [k for (scope, k) in window.explorer.items if scope.portfolio == summary.id and k == 'price']
    assert len(children) == 2  # both stocks appear under the portfolio

    panel.done_button.click()
    assert not window.side_panel.isVisible()


def test_stocks_inside_a_portfolio_show_their_views(window):
    from core.portfolios.service import PortfolioService
    service = PortfolioService()
    portfolio = service.create_default()
    service.add_symbols(portfolio.id, ['TEST'])
    window.explorer_controller.open_portfolio(service.get(portfolio.id))
    window.explorer.setCurrentItem(window.explorer.items[(Scope(portfolio.id, 'TEST'), 'macd')])  # a click
    assert window.controller.symbol == 'TEST' and window.controller.shown == ['macd']
    assert window.explorer_controller.current_scope == Scope(portfolio.id, 'TEST')


def test_load_portfolio_reopens_a_saved_one_with_its_stocks(window, monkeypatch):
    from core.portfolios.service import PortfolioService
    from qtrender.dialogs import QtDialogs
    service = PortfolioService()
    portfolio = service.create_default()
    service.add_symbols(portfolio.id, ['AAPL', 'MSFT'])
    offered = []
    monkeypatch.setattr(QtDialogs, 'choose_portfolio', lambda self, options: offered.append(options) or options[0].id)

    window.menu.load_action.trigger()
    assert [(o.name, o.stock_count) for o in offered[0]] == [('Portfolio 1', 2)]
    assert window.explorer_controller.portfolios == {portfolio.id: 'Portfolio 1'}
    assert [s for s in window.explorer_controller.scopes if s.portfolio == portfolio.id] == [
        Scope(portfolio.id, 'AAPL'), Scope(portfolio.id, 'MSFT')]
    window.menu.load_action.trigger()  # everything saved is open now
    assert 'already open' in window.messages[-1]


def test_a_standalone_stock_and_a_stock_from_another_portfolio_can_be_added_to_a_portfolio(window):
    from core.portfolios.service import PortfolioService
    service = PortfolioService()
    first, second = service.create_default(), service.create_default()
    service.add_symbols(first.id, ['IBM'])
    window.explorer_controller.open_portfolio(service.get(first.id))
    window.explorer_controller.open_portfolio(second)
    window.explorer_controller.add_symbol('AAPL')

    window.explorer.action_chosen.emit('add_to_portfolio', Node('AAPL', None, 'symbol'), second.id)
    window.explorer.action_chosen.emit('add_to_portfolio', Node('IBM', None, 'symbol', portfolio=first.id), second.id)
    assert service.get(second.id).symbols == ['AAPL', 'IBM'] and service.get(first.id).symbols == ['IBM']
    assert Scope(second.id, 'IBM') in window.explorer_controller.scopes
    assert Scope(None, 'AAPL') in window.explorer_controller.scopes  # still standalone too

    window.explorer.action_chosen.emit('remove_from_portfolio', Node('AAPL', None, 'symbol', portfolio=second.id), None)
    assert service.get(second.id).symbols == ['IBM']
    assert Scope(second.id, 'AAPL') not in window.explorer_controller.scopes
    assert (Scope(second.id, 'AAPL'), 'price') not in window.explorer.items


def test_add_to_a_new_portfolio_from_the_menu_creates_and_names_it(window):
    from PySide6.QtWidgets import QAbstractItemView
    window.explorer_controller.add_symbol('AAPL')
    window.explorer.action_chosen.emit('add_to_new_portfolio', Node('AAPL', None, 'symbol'), None)
    [summary] = saved_portfolios()
    assert summary.stock_count == 1 and window.explorer.state() == QAbstractItemView.State.EditingState


def test_close_keeps_the_file_and_delete_removes_it_when_confirmed(window):
    window.menu.new_action.trigger()
    [summary] = saved_portfolios()
    node = Node('', None, 'portfolio', portfolio=summary.id)
    window.explorer.action_chosen.emit('close_portfolio', node, None)
    assert summary.id not in window.explorer.portfolio_items and saved_portfolios() != []

    window.explorer_controller.open_portfolio(__import__('portfolio').repository.get(summary.id))
    window.answers['confirm'] = False
    window.explorer.action_chosen.emit('delete_portfolio', node, None)
    assert saved_portfolios() != [] and summary.id in window.explorer.portfolio_items
    window.answers['confirm'] = True
    window.explorer.action_chosen.emit('delete_portfolio', node, None)
    assert saved_portfolios() == [] and summary.id not in window.explorer.portfolio_items


def test_nested_context_menu_builds_a_real_submenu(window):
    from PySide6.QtWidgets import QMenu
    from core.portfolios.service import PortfolioService
    portfolio = PortfolioService().create_default()
    window.explorer_controller.open_portfolio(portfolio)
    node = Node('AAPL', None, 'symbol')
    menu = QMenu()
    window.explorer._fill_menu(menu, window.explorer.menu_source(node), node)
    add_to = next(a for a in menu.actions() if a.text() == 'Add to portfolio')
    assert [a.text() for a in add_to.menu().actions() if not a.isSeparator()] == ['Portfolio 1', 'New portfolio…']


def test_adding_stocks_replaces_the_strategy_builder_only_if_the_user_agrees(window):
    from core.portfolios.service import PortfolioService
    portfolio = PortfolioService().create_default()
    window.explorer_controller.open_portfolio(portfolio)
    window.explorer_controller.add_symbol('TEST')
    window.strategy_controller.handle('new', 'TEST', '')
    assert window.wizard.isVisible()

    node = Node('', None, 'portfolio', portfolio=portfolio.id)
    window.answers['confirm'] = False
    window.explorer.action_chosen.emit('add_stock', node, None)
    assert window.wizard.isVisible() and not window.add_stock_panel.isVisible()  # kept the strategy being edited
    window.answers['confirm'] = True
    window.explorer.action_chosen.emit('add_stock', node, None)
    assert window.add_stock_panel.isVisible() and not window.wizard.isVisible()
    window.strategy_controller.handle('new', 'TEST', '')  # the builder can take the panel back (nothing to lose)
    assert window.wizard.isVisible() and not window.add_stock_panel.isVisible()


def test_removing_the_shown_stock_or_closing_its_portfolio_empties_the_chart_area(window):
    from core.portfolios.service import PortfolioService
    service = PortfolioService()
    portfolio = service.create_default()
    service.add_symbols(portfolio.id, ['TEST'])
    window.explorer_controller.open_portfolio(service.get(portfolio.id))

    def show_it():
        window.explorer.setCurrentItem(window.explorer.items[(Scope(portfolio.id, 'TEST'), 'macd')])
        assert window.view_area.currentIndex() == 1 and window.controller.symbol == 'TEST'

    show_it()
    window.explorer.action_chosen.emit('remove_from_portfolio', Node('TEST', None, 'symbol', portfolio=portfolio.id),
                                       None)
    assert window.view_area.currentIndex() == 0 and window.controller.symbol is None  # "Search a symbol to begin"
    assert not window.explorer.selectedItems()

    service.add_symbols(portfolio.id, ['TEST'])  # put it back and show it again: works from the empty state
    window.explorer_controller.refresh_portfolio(service.get(portfolio.id))
    show_it()
    window.explorer.action_chosen.emit('close_portfolio', Node('', None, 'portfolio', portfolio=portfolio.id), None)
    assert window.view_area.currentIndex() == 0 and window.controller.symbol is None


# --- company overview ------------------------------------------------------------------------------------------

def test_clicking_a_stock_shows_its_company_overview_with_likes_dislikes_and_best_strategy(window):
    from strategy import Condition, Exits, Operand, RuleGroup, Strategy
    saved = Strategy('Trend', RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma', params={'days': 50}))]),
                     RuleGroup('any', [Condition(Operand('close'), 'below', Operand('sma', params={'days': 50}))]),
                     Exits(stop_loss_pct=8), symbol='TEST')
    repository.save(saved)
    window.explorer_controller.add_symbol('TEST')
    window.explorer.setCurrentItem(window.explorer.symbol_items[Scope(None, 'TEST')])
    overview = window.view_area.views['overview']
    assert window.view_area.title.text() == 'TEST · Company overview'
    assert 'TEST Corporation' in overview.heading.text() and 'useful things' in overview.summary.text()
    assert 'Sales are growing fast' in overview.likes.text() and 'Very profitable' in overview.likes.text()
    assert 'Priced richly' in overview.dislikes.text() and 'a lot of debt' in overview.dislikes.text()
    model = overview.model
    assert model.rank_rows[0].strategy_id is None and model.rank_rows[1].strategy_id == saved.id  # buy & hold first
    assert 'Trend' in overview.verdict.text()

    overview.table.cellClicked.emit(1, 0)  # click the strategy's row: its backtest opens
    assert window.controller.strategy_id == saved.id and window.controller.shown == ['strategy']


def test_overview_without_a_profile_still_shows_the_strategy_comparison(window, monkeypatch):
    from company import CompanyProfile
    monkeypatch.setattr(window.controller, 'profile_source', lambda symbol: CompanyProfile(symbol))
    window.explorer_controller.add_symbol('ETF')
    window.explorer.setCurrentItem(window.explorer.symbol_items[Scope(None, 'ETF')])
    overview = window.view_area.views['overview']
    assert 'No company description' in overview.summary.text()
    assert 'No strategies to compare' in overview.verdict.text()


# --- Tools menu ----------------------------------------------------------------------------------------------

def test_library_menu_has_stocks_and_strategies(window):
    library_menu = window.menu.actions()[2].menu()
    assert library_menu.title() == '&Tools'
    assert [a.text() for a in library_menu.actions()] == ['&Stocks…', 'S&trategies…']


def test_stock_library_lists_local_stocks_and_adds_one_to_a_portfolio(window):
    from core.portfolios.service import PortfolioService
    from PySide6.QtWidgets import QMenu
    from qtrender.library.stock_library_panel import fill_menu
    portfolio = PortfolioService().create_default()
    window.menu.stocks_action.trigger()
    panel = window.stock_library_panel
    assert window.side_panel.isVisible() and panel.isVisible() and window.side_panel.windowTitle() == 'Stock Library'
    assert [panel.table.item(r, 0).text() for r in range(panel.table.rowCount())] == ['IBM', 'TEST']
    assert panel.table.item(0, 1).text() == 'IBM Corp' and panel.count.text() == '2 stocks in the library'

    menu = QMenu()
    picked = []
    fill_menu(menu, panel.menu_source('IBM'), picked.append)
    add_to = next(a for a in menu.actions() if a.text() == 'Add to portfolio')
    assert [a.text() for a in add_to.menu().actions() if not a.isSeparator()] == ['Portfolio 1', 'New portfolio…']
    panel.action_chosen.emit('library_add_to', 'IBM', portfolio.id)
    assert PortfolioService().get(portfolio.id).symbols == ['IBM'] and 'Added IBM to "Portfolio 1"' in panel.notice.text()

    panel.table.cellDoubleClicked.emit(1, 0)  # double-click TEST: it opens in the Explorer
    assert Scope(None, 'TEST') in window.explorer_controller.scopes
    panel.done_button.click()
    assert not window.side_panel.isVisible()


def test_stock_library_search_box_downloads_and_adds_a_stock(window):
    from search import Catalog, Security
    window.menu.stocks_action.trigger()
    panel = window.stock_library_panel
    msft = Security('MSFT', 'Microsoft', 'NASDAQ', False, ('microsoft',))
    panel.search.controller.catalog_loaded(Catalog({'MSFT': msft}, [], frozenset()), input_has_focus=False)
    panel.search.controller.choose(msft)
    assert panel.notice.text().startswith('Added MSFT: 500 trading days')


def test_strategy_library_creates_a_template_and_returns_to_the_library(window):
    window.menu.strategies_action.trigger()
    panel = window.strategy_library_panel
    assert panel.isVisible() and window.side_panel.windowTitle() == 'Strategy Library'
    panel.new_button.click()
    wizard = window.wizard
    assert wizard.isVisible() and wizard.title.text() == 'New library template'
    wizard.next_button.click()  # Start: new
    wizard.name.setText('Breakout')
    for _ in range(4):
        wizard.next_button.click()
    [template] = repository.library()
    assert template.name == 'Breakout' and template.symbol is None
    assert panel.isVisible() and not wizard.isVisible()  # back in the library, which now lists it
    assert 'Breakout' in [panel.tree.topLevelItem(0).child(i).text(0) for i in range(panel.tree.topLevelItem(0).childCount())]


def test_strategy_library_backtests_a_template_on_the_stock_on_screen(window):
    from strategy import Condition, Exits, RuleGroup, Strategy
    template = Strategy('Template', RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma'))]),
                        RuleGroup('any', []), Exits(stop_loss_pct=5))
    repository.save(template)
    window.explorer_controller.add_symbol('TEST')
    window.menu.strategies_action.trigger()
    panel = window.strategy_library_panel
    panel.items[template.id].setSelected(True)
    buttons = [panel.buttons.itemAt(i).widget() for i in range(panel.buttons.count()) if panel.buttons.itemAt(i).widget()]
    assert [b.text() for b in buttons] == ['Backtest on TEST', 'Copy to another stock…', 'Edit…', 'Delete…']
    buttons[0].click()
    assert window.controller.strategy_id == template.id and window.controller.shown == ['strategy']


def test_opening_a_library_page_asks_before_discarding_the_strategy_being_edited(window):
    window.explorer_controller.add_symbol('TEST')
    window.strategy_controller.handle('new', 'TEST', '')
    window.answers['confirm'] = False
    window.menu.stocks_action.trigger()
    assert window.wizard.isVisible() and not window.stock_library_panel.isVisible()
    window.answers['confirm'] = True
    window.menu.stocks_action.trigger()
    assert window.stock_library_panel.isVisible() and not window.wizard.isVisible()


def test_switching_stocks_replaces_the_overview_facts_instead_of_stacking_them(window):
    overview = window.view_area.views['overview']
    for symbol in ('TEST', 'OTHER'):
        window.explorer_controller.add_symbol(symbol)
        window.explorer.setCurrentItem(window.explorer.symbol_items[Scope(None, symbol)])
    shown = [overview.facts.itemAt(i).widget() for i in range(overview.facts.count())]
    assert len(shown) == len(overview.model.facts)
    stale = [w for w in overview.widget().findChildren(type(shown[0])) if w.parent() is None or
             (w not in shown and w.isVisible() and w.layout() is not None and w.layout().count() == 2)]
    assert stale == []  # the first stock's fact boxes are gone, not hidden behind the second's


def test_strategy_library_buttons_are_rebuilt_cleanly_for_each_selection(window):
    from strategy import Condition, Exits, RuleGroup, Strategy
    for name, symbol in (('Template', None), ('Own', 'TEST')):
        repository.save(Strategy(name, RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma'))]),
                                 RuleGroup('any', []), Exits(stop_loss_pct=5), symbol=symbol))
    window.menu.strategies_action.trigger()
    panel = window.strategy_library_panel
    for item in list(panel.items.values()) * 2:  # select each twice: the old buttons (and the spacer) are cleared
        panel.tree.clearSelection()
        item.setSelected(True)
        texts = [panel.buttons.itemAt(i).widget().text() for i in range(panel.buttons.count())
                 if panel.buttons.itemAt(i).widget()]
        assert texts.count('Edit…') == 1 and texts[-1] == 'Delete…'


def test_strategy_library_shows_why_a_strategy_can_work_and_its_references(window):
    from strategy import About, Condition, Exits, RuleGroup, Strategy
    template = Strategy('Golden Cross', RuleGroup('all', [Condition(Operand('sma', params={'days': 50}), 'crosses_above',
                                                                    Operand('sma', params={'days': 200}))]),
                        RuleGroup('any', []), Exits(stop_loss_pct=5),
                        about=About('Buy when the 50-day crosses above the 200-day.', 'Trend following',
                                    'Classic trend signal.', 'Lags at turns.', ['Murphy, J. J. (1999). Technical Analysis.']))
    repository.save(template)
    window.menu.strategies_action.trigger()
    panel = window.strategy_library_panel
    panel.items[template.id].setSelected(True)
    text = panel.detail.text()
    for expected in ('Golden Cross', 'Trend following', 'Buy when the 50-day', 'Why it can work', 'Classic trend signal',
                     'Watch out for', 'Lags at turns', 'Rules', 'References', 'Murphy, J. J. (1999)'):
        assert expected in text, expected
    assert 'Buy when the 50-day' in panel.items[template.id].toolTip(0)


def test_the_wizard_saves_a_description_and_keeps_a_copied_strategys_references(window):
    from strategy import About, Condition, Exits, RuleGroup, Strategy
    source = Strategy('Classic', RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma'))]),
                      RuleGroup('any', []), Exits(stop_loss_pct=5),
                      about=About('Original idea.', why='Because.', references=['Book (2001).']))
    repository.save(source)
    window.explorer_controller.add_symbol('TEST')
    window.strategy_controller.handle('new', 'TEST', '')
    wizard = window.wizard
    item = next(wizard.existing.topLevelItem(i).child(0) for i in range(wizard.existing.topLevelItemCount())
                if wizard.existing.topLevelItem(i).text(0) == 'Library')
    wizard.existing.setCurrentItem(item)
    wizard.next_button.click()  # copy it
    assert wizard.description.toPlainText() == 'Original idea.'
    wizard.description.setPlainText('My take on it.')
    for _ in range(3):
        wizard.next_button.click()
    assert 'My take on it.' in wizard.review.text()
    wizard.next_button.click()
    [copy] = repository.for_symbol('TEST')
    assert copy.about.summary == 'My take on it.' and copy.about.references == ['Book (2001).']
    assert repository.get(source.id).about.summary == 'Original idea.'
    assert 'My take on it.' in window.view_area.views['strategy'].rules.text()


def test_ctrl_clicking_two_strategies_shows_the_comparison_chart_with_a_line_each_plus_buy_and_hold(window):
    from strategy import Condition, Exits, RuleGroup, Strategy
    for name, days in (('Fast', 20), ('Slow', 100)):
        repository.save(Strategy(name, RuleGroup('all', [Condition(Operand('close'), 'above',
                                                                    Operand('sma', params={'days': days}))]),
                                 RuleGroup('any', [Condition(Operand('close'), 'below',
                                                             Operand('sma', params={'days': days}))]),
                                 Exits(stop_loss_pct=8), symbol='TEST'))
    window.explorer_controller.add_symbol('TEST')
    window.explorer_controller.refresh_strategies()
    window.explorer.clearSelection()
    for (scope, key), item in window.explorer.items.items():
        if key.startswith('strategy:'):
            item.setSelected(True)
    assert 'backtest' in window.controller.shown and 'strategy' not in window.controller.shown
    plot = window.view_area.views['backtest'].plot_widget
    assert len(plot.lines) == len(window.controller.strategy_ids) + 1 >= 3
    assert 'Buy &amp; hold' in window.view_area.views['backtest'].legend.text()  # the label is rich text (HTML)


def test_stock_library_download_tab_lists_stocks_downloads_the_missing_ones_and_stops_when_hidden(window):
    window.menu.stocks_action.trigger()
    library = window.stock_library_panel
    panel = library.download_panel
    assert [library.tabs.tabText(i) for i in range(library.tabs.count())] == ['Stocks in the database',
                                                                               'Download / update']
    library.tabs.setCurrentWidget(panel)
    assert window.side_panel.isVisible() and panel.isVisible() and window.side_panel.windowTitle() == 'Stock Library'
    assert [panel.table.item(r, 0).text() for r in range(panel.table.rowCount())] == ['AAA', 'BBB', 'IBM']
    statuses = {panel.table.item(r, 0).text(): panel.table.item(r, 2).text() for r in range(panel.table.rowCount())}
    assert statuses['AAA'] == 'Not downloaded' and statuses['IBM'] in ('Up to date', 'Out of date')
    assert 'not downloaded' in panel.totals.text()

    panel.only_pending.setChecked(True)
    assert 'AAA' in [panel.table.item(r, 0).text() for r in range(panel.table.rowCount())]
    panel.only_pending.setChecked(False)

    panel.start_button.click()
    assert 'AAA' in window.downloaded and 'BBB' in window.downloaded
    assert panel.table.item(0, 2).text() == 'Up to date' and panel.start_button.isEnabled()
    assert 'Finished' in panel.notice.text()

    window.download_controller.choose_universe('Stocks I picked')
    assert panel.table.rowCount() == 0
    window.download_controller._stop.clear()
    library.tabs.setCurrentIndex(0)  # switching tabs is not leaving the library: a download keeps going
    assert not window.download_controller._stop.is_set()
    window.menu.strategies_action.trigger()  # another page replaces the Stock Library
    assert window.download_controller._stop.is_set()
    window.download_controller.running = False


def two_strategies_for_test():
    from strategy import Condition, Exits, RuleGroup, Strategy
    for name, days in (('Fast', 20), ('Slow', 100)):
        repository.save(Strategy(name, RuleGroup('all', [Condition(Operand('close'), 'above',
                                                                    Operand('sma', params={'days': days}))]),
                                 RuleGroup('any', [Condition(Operand('close'), 'below',
                                                             Operand('sma', params={'days': days}))]),
                                 Exits(stop_loss_pct=8), symbol='TEST'))


def strategy_rows(window):
    return {key: item for (scope, key), item in window.explorer.items.items() if key.startswith('strategy:')}


def test_the_best_strategy_row_is_starred_bold_and_explained_and_follows_the_range(window):
    two_strategies_for_test()
    window.explorer_controller.add_symbol('TEST')
    window.explorer_controller.refresh_strategies()
    rows = strategy_rows(window)
    starred = [item for item in rows.values() if item.text(0).startswith('★ ')]
    assert len(starred) == 1 and starred[0].font(0).bold()
    assert 'Best of 2 strategies, past year' in starred[0].toolTip(0)
    assert not any(item.font(0).bold() for item in rows.values() if item is not starred[0])

    def starred_rows():
        return [item for item in strategy_rows(window).values() if item.text(0).startswith('★ ')]

    window.view_area.range_selected.emit('1M')  # the star is worked out again for the new range, and names it
    assert len(starred_rows()) <= 1 and all('past month' in item.toolTip(0) for item in starred_rows())
    window.view_area.range_selected.emit('Max')
    assert len(starred_rows()) <= 1 and all('all time' in item.toolTip(0) for item in starred_rows())

    before = [item.text(0) for item in starred_rows()]
    window.explorer_controller.refresh_strategies()  # the rows are rebuilt: the star must survive that
    assert [item.text(0) for item in starred_rows()] == before


def test_one_strategy_shows_the_results_panel_and_two_show_only_the_chart_with_hover_details(window):
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication
    two_strategies_for_test()
    window.explorer_controller.add_symbol('TEST')
    window.explorer_controller.refresh_strategies()
    window.explorer.clearSelection()
    first, second = list(strategy_rows(window).values())[:2]
    first.setSelected(True)
    assert 'strategy' in window.controller.shown and 'backtest' not in window.controller.shown
    second.setSelected(True)  # Ctrl+click a second one
    assert 'backtest' in window.controller.shown and 'strategy' not in window.controller.shown

    view = window.view_area.views['backtest']
    plot = view.plot_widget
    plot.resize(900, 400)
    QApplication.processEvents()
    series = plot.chart.series[0]
    slot = len(plot.chart.dates) - 1
    point = plot.getViewBox().mapViewToScene(QPointF(slot, series.values[slot]))
    assert plot.nearest_line(point) is not None and plot.nearest_line(point)[1] == slot
    index, _ = plot.nearest_line(point)
    plot._on_mouse_moved((point,))
    assert plot.hover_text.isVisible() and plot.hovered == index
    shown = plot.hover_text.toPlainText()
    assert plot.chart.series[index].label in shown and 'Whole range:' in shown and 'so far' in shown
    assert plot.lines[index].opts['pen'].width() > 2 or plot.chart.series[index].is_hold

    far = plot.getViewBox().mapViewToScene(QPointF(slot, series.values[slot] * 50))  # nowhere near any line
    plot._on_mouse_moved((far,))
    assert not plot.hover_text.isVisible() and plot.hovered is None

    first.setSelected(False)  # back to one strategy: the full results panel returns
    assert 'strategy' in window.controller.shown and 'backtest' not in window.controller.shown

"""The Info Wizard with the real widgets (offscreen): View menu, underlining, double-click, docks, requests."""
import json

import pytest

pytest.importorskip('PySide6')

from PySide6.QtCore import QUrl, Qt  # noqa: E402
from PySide6.QtGui import QImage, QTextDocument  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QAbstractItemView, QMenu  # noqa: E402

from core.explorer.controller import Node, Scope  # noqa: E402
from core.learn.controller import RequestForm  # noqa: E402
from core.learn.preferences import MemoryPreferences  # noqa: E402
from test_gui_smoke import app, financials, window  # noqa: E402,F401  (the shared window fixture)

LEFT, NO_MODIFIER = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier


def turn_on(window):
    window.menu.info_action.setChecked(True)  # the user ticks View > Info Wizard
    window.info_dock.hide()  # skip the welcome page: most tests start from a clean "on" state
    window.info_controller.history, window.info_controller.position = [], -1


def row(window, key, symbol='TEST', portfolio=None):
    return window.explorer.items[(Scope(portfolio, symbol), key)]


def double_click(widget, item=None):
    """A real mouse double-click: on a tree row (which must be visible), or in the middle of a widget.

    On an item view the user's first click comes before the double-click, and Qt needs it (QTest's bare
    mouseDClick skips it), so it is sent first.
    """
    if item is not None:
        position = widget.visualItemRect(item).center()
        QTest.mouseClick(widget.viewport(), LEFT, NO_MODIFIER, position)
        QTest.mouseDClick(widget.viewport(), LEFT, NO_MODIFIER, position)
    else:
        QTest.mouseDClick(widget, LEFT)


# --- View menu -------------------------------------------------------------------------------------------------

def test_view_menu_has_a_checkable_info_wizard_that_starts_off(window):
    view_menu = window.menu.actions()[1].menu()
    assert view_menu.title() == '&View'
    action = window.menu.info_action
    assert action.text() == '&Info Wizard' and action.isCheckable() and not action.isChecked()
    assert not window.info_controller.enabled and not window.info_dock.isVisible()


def test_ticking_it_on_underlines_and_shows_the_welcome_topic_once(window):
    window.menu.info_action.setChecked(True)
    assert window.info_controller.enabled and window.info_mode.on
    assert window.info_dock.isVisible() and 'Using the Info Wizard' in window.info_panel.browser.toPlainText()
    assert window.info_panel.category.text() == 'HELP'

    window.menu.info_action.setChecked(False)
    assert not window.info_dock.isVisible() and not window.info_mode.on
    window.menu.info_action.setChecked(True)
    assert not window.info_dock.isVisible()  # the welcome page is only shown the first time


def test_the_remembered_setting_is_applied_at_start_without_opening_the_panel(app, tmp_path, monkeypatch):
    from main import MainWindow
    from core.common.background import BackgroundLoader
    from search import Catalog
    import qtrender.searchbar.bar as search_bar
    from learn import requests as info_requests
    monkeypatch.setattr(search_bar, 'load_catalog', lambda: Catalog({}, [], frozenset()))
    monkeypatch.setattr(info_requests, 'FILE', tmp_path / 'r.json')
    window = MainWindow(BackgroundLoader.immediate(), lambda s: None, financials,
                        preferences=MemoryPreferences(info_wizard_on=True, info_welcome_seen=True))
    window.show()
    assert window.info_mode.on and window.menu.info_action.isChecked() and not window.info_dock.isVisible()
    window.close()


# --- the Explorer ----------------------------------------------------------------------------------------------

def test_explorer_rows_with_an_explanation_are_underlined_only_while_info_is_on(window):
    window.explorer_controller.add_symbol('TEST')
    macd, price = row(window, 'macd'), row(window, 'price')
    assert not macd.font(0).underline()
    turn_on(window)
    assert macd.font(0).underline() and macd.foreground(0).color().name() == '#5b8def'
    assert not price.font(0).underline()  # no topic for the plain price view
    assert window.explorer.folders[Scope(None, 'TEST')].font(0).underline()  # Strategies -> backtest
    window.menu.info_action.setChecked(False)
    assert not macd.font(0).underline()


def test_double_clicking_a_term_opens_its_topic_in_the_info_dock(window):
    window.explorer_controller.add_symbol('TEST')
    turn_on(window)
    double_click(window.explorer, row(window, 'macd'))
    assert window.info_dock.isVisible()
    assert window.info_panel.browser.toPlainText().startswith('MACD')
    assert 'momentum' in window.info_panel.browser.toPlainText()
    assert window.info_controller.history == ['macd']


def test_double_click_does_nothing_new_while_info_is_off(window):
    window.explorer_controller.add_symbol('TEST')
    double_click(window.explorer, row(window, 'macd'))
    assert not window.info_dock.isVisible() and window.info_controller.history == []


def test_a_row_without_a_topic_keeps_its_usual_double_click(window):
    window.explorer_controller.add_symbol('TEST')
    window.explorer_controller.add_symbol('OTHER')
    turn_on(window)
    top = window.explorer.symbol_items[Scope(None, 'OTHER')]
    top.setExpanded(True)
    double_click(window.explorer, top)  # a stock row has no topic: it still expands/collapses
    assert not top.isExpanded() and not window.info_dock.isVisible()


def test_portfolio_double_click_explains_it_and_rename_stays_on_f2(window):
    window.menu.new_action.trigger()
    [portfolio_id] = window.explorer_controller.portfolios
    window.explorer.setState(QAbstractItemView.State.NoState)
    window.explorer.closePersistentEditor(window.explorer.portfolio_items[portfolio_id])
    turn_on(window)
    triggers = window.explorer.editTriggers()
    assert not triggers & QAbstractItemView.EditTrigger.DoubleClicked and triggers & QAbstractItemView.EditTrigger.EditKeyPressed
    assert not window.explorer.expandsOnDoubleClick()
    double_click(window.explorer, window.explorer.portfolio_items[portfolio_id])
    assert 'portfolio' in window.info_panel.browser.toPlainText().lower() and window.info_controller.history == ['portfolio']
    window.menu.info_action.setChecked(False)  # everything is back to normal when it is off
    assert window.explorer.editTriggers() & QAbstractItemView.EditTrigger.DoubleClicked
    assert window.explorer.expandsOnDoubleClick()


def test_right_click_menu_on_a_row_offers_what_is_and_request(window):
    window.explorer_controller.add_symbol('TEST')
    turn_on(window)
    menu = QMenu()
    window.info_mode.add_actions(menu, 'macd', 'MACD', 'explorer')
    assert [a.text() for a in menu.actions()] == ['What is “MACD”?', 'Request info on “MACD”…']
    plain = QMenu()
    window.info_mode.add_actions(plain, None, 'Price', 'explorer')
    assert [a.text() for a in plain.actions()] == ['Request info on “Price”…']


# --- generated text and labels ---------------------------------------------------------------------------------

def show_views(window, *views):
    window.explorer_controller.add_symbol('TEST')
    for view in views:
        row(window, view).setSelected(True)


def test_legend_terms_become_links_only_while_on_and_double_click_opens_them(window):
    show_views(window, 'macd')
    legend = window.view_area.views['macd'].legend
    assert 'href' not in legend.text()
    turn_on(window)
    assert 'href="info:macd"' in legend.text() and 'href="info:histogram"' in legend.text()
    legend._on_hover('info:histogram')  # the mouse is over the link
    assert 'histogram' in legend.toolTip().lower()
    QTest.mouseDClick(legend, LEFT)
    assert window.info_panel.browser.toPlainText().startswith('MACD histogram')
    window.menu.info_action.setChecked(False)
    assert 'href' not in legend.text()


def test_double_clicking_legend_text_that_is_not_a_link_does_nothing(window):
    show_views(window, 'macd')
    turn_on(window)
    legend = window.view_area.views['macd'].legend
    legend._on_hover('')
    QTest.mouseDClick(legend, LEFT)
    assert not window.info_dock.isVisible()


def test_the_range_and_candle_labels_explain_themselves(window):
    window.explorer_controller.add_symbol('TEST')
    turn_on(window)
    candle = window.header.candle_label
    assert candle.font().underline() and 'candle size' in candle.toolTip().lower()
    QTest.mouseDClick(candle, LEFT)
    assert window.info_controller.history == ['candle-size']
    window.menu.info_action.setChecked(False)
    assert not candle.font().underline()
    QTest.mouseDClick(candle, LEFT)
    assert window.info_controller.history == []  # off: nothing


def test_strategy_summary_words_are_links(window):
    from strategy import Condition, Exits, Operand, RuleGroup, Strategy, repository
    saved = Strategy('Trend', RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma', params={'days': 50}))]),
                     RuleGroup('any', []), Exits(stop_loss_pct=8), symbol='TEST')
    repository.save(saved)
    window.explorer_controller.add_symbol('TEST')
    window.explorer_controller.refresh_strategies()
    window.explorer_controller.select_strategy('TEST', saved.id)
    turn_on(window)
    strategy_view = window.view_area.views['strategy']
    window.controller.refresh_strategy()
    cards = strategy_view.cards.text()
    assert 'info:max-drawdown' in cards and 'info:buy-and-hold' in cards
    assert 'info:sma' in strategy_view.rules.text()


# --- tables ----------------------------------------------------------------------------------------------------

def test_history_column_titles_are_underlined_and_double_click_explains_them(window):
    show_views(window, 'history')
    table = window.view_area.views['history'].table
    close = table.model().headerData(4, Qt.Orientation.Horizontal, Qt.ItemDataRole.FontRole)
    assert close is None
    turn_on(window)
    font = table.model().headerData(4, Qt.Orientation.Horizontal, Qt.ItemDataRole.FontRole)
    assert font.underline() and table.model().headerData(4, Qt.Orientation.Horizontal,
                                                          Qt.ItemDataRole.ForegroundRole).name() == '#5b8def'
    assert table.model().headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.FontRole) is None  # 'Date'
    table.horizontalHeader().sectionDoubleClicked.emit(4)
    assert window.info_controller.history == ['candlestick']


def test_growth_table_titles_are_underlined_for_known_terms(window):
    show_views(window, 'growth')
    table = window.view_area.views['growth'].tables['quarterly']
    names = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
    turn_on(window)
    underlined = {name for i, name in enumerate(names) if table.horizontalHeaderItem(i).font().underline()}
    assert underlined == {'Revenue', 'QoQ', 'YoY', 'EPS'}
    table.horizontalHeader().sectionDoubleClicked.emit(names.index('EPS'))
    assert window.info_controller.history == ['eps']


# --- the panel and the docks -----------------------------------------------------------------------------------

def test_topics_show_images_related_links_and_navigation(window):
    turn_on(window)
    window.info_controller.open('candlestick')
    panel = window.info_panel
    data = panel.browser.loadResource(QTextDocument.ResourceType.ImageResource, QUrl('candle-anatomy.png'))
    image = QImage.fromData(data)  # found through the browser's search path (the assets folder)
    assert not image.isNull() and image.width() == 560
    assert 'Related topics' in panel.browser.toPlainText()

    panel.topic_requested.emit('volume')  # a related link was clicked
    assert panel.browser.toPlainText().startswith('Volume') and panel.back_button.isEnabled()
    panel.back_button.click()
    assert panel.browser.toPlainText().startswith('Candlestick') and panel.forward_button.isEnabled()
    panel.forward_button.click()
    assert panel.browser.toPlainText().startswith('Volume')


def test_an_unknown_term_shows_the_not_found_page_with_a_request_button(window, monkeypatch):
    from qtrender.learn.request_dialog import QtInfoDialogs
    turn_on(window)
    window.info_controller.open_text('Sharpe ratio')
    assert 'No explanation yet' in window.info_panel.browser.toPlainText()
    asked = []
    monkeypatch.setattr(QtInfoDialogs, 'ask_request', lambda self, text, where: asked.append((text, where)) or None)
    window.info_panel.request_button.click()
    assert asked == [('Sharpe ratio', 'Info panel')]


def test_both_docks_share_the_right_side_with_info_below_the_strategy_builder(window, app):
    window.explorer_controller.add_symbol('TEST')
    window.strategy_controller.handle('new', 'TEST', '')
    turn_on(window)
    window.info_controller.open('macd')
    app.processEvents()
    assert window.side_panel.isVisible() and window.info_dock.isVisible()
    assert window.info_dock.geometry().top() >= window.side_panel.geometry().bottom() - 4  # below it
    assert abs(window.info_dock.geometry().left() - window.side_panel.geometry().left()) <= 4  # same column
    assert window.wizard.isVisible()  # the strategy builder was not disturbed


def test_closing_a_dock_with_its_x_hides_it_and_the_next_double_click_brings_it_back(window):
    window.explorer_controller.add_symbol('TEST')
    turn_on(window)
    double_click(window.explorer, row(window, 'macd'))
    window.info_dock.close()
    assert not window.info_dock.isVisible() and window.menu.info_action.isChecked() and window.info_mode.on
    double_click(window.explorer, row(window, 'sma'))
    assert window.info_dock.isVisible() and window.info_panel.browser.toPlainText().startswith('SMA')


def test_the_builder_dock_title_follows_its_page_and_it_can_be_closed_and_reopened(window):
    window.explorer_controller.add_symbol('TEST')
    window.strategy_controller.handle('new', 'TEST', '')
    assert window.side_panel.windowTitle() == 'Strategy Builder'
    window.side_panel.close()
    assert not window.side_panel.isVisible()
    window.strategy_controller.handle('new', 'TEST', '')
    assert window.side_panel.isVisible()
    from core.portfolios.service import PortfolioService
    portfolio = PortfolioService().create_default()
    window.explorer_controller.open_portfolio(portfolio)
    window.explorer.action_chosen.emit('add_stock', Node('', None, 'portfolio', portfolio=portfolio.id), None)
    assert window.side_panel.windowTitle() == 'Add Stock'


# --- requests --------------------------------------------------------------------------------------------------

def test_requesting_info_writes_the_file_with_where_it_was_seen(window, monkeypatch, tmp_path):
    from qtrender.learn.request_dialog import QtInfoDialogs
    show_views(window, 'macd')
    turn_on(window)
    shown = []
    monkeypatch.setattr(QtInfoDialogs, 'ask_request', lambda self, text, where: RequestForm('Sharpe ratio', 'what is it?'))
    monkeypatch.setattr(QtInfoDialogs, 'notify', lambda self, text: shown.append(text))
    legend = window.view_area.views['macd'].legend
    menu = QMenu()
    window.info_mode.add_actions(menu, None, 'Sharpe', legend.where)
    next(a for a in menu.actions() if a.text().startswith('Request info')).trigger()
    data = json.loads((tmp_path / 'info_requests.json').read_text(encoding='utf-8'))
    [saved] = data['requests']
    assert saved['text'] == 'Sharpe ratio' and saved['note'] == 'what is it?' and saved['count'] == 1
    assert saved['contexts'] == [{'symbol': 'TEST', 'view': 'price,macd', 'where': 'indicator legend'}]
    assert 'added to your list' in shown[-1]


def test_the_request_dialog_needs_a_term_before_it_can_be_sent(app):
    from qtrender.learn.request_dialog import RequestDialog
    dialog = RequestDialog(None, '', 'legend')
    assert not dialog.ok_button.isEnabled()
    dialog.term.setText('  Sharpe ratio ')
    dialog.note.setText('please')
    assert dialog.ok_button.isEnabled() and dialog.form() == RequestForm('Sharpe ratio', 'please')

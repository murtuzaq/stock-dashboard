"""Tools > Stocks and Tools > Strategies controllers, through fake views (no Qt)."""
from datetime import datetime

import pandas as pd
import pytest

from conftest import random_walk
from core.common.background import BackgroundLoader
from core.library import stocks as stock_library
from core.library import strategies as strategy_library
from core.library.stocks import StockLibraryController, stock_rows
from core.library.strategies import LIBRARY_GROUP, StrategyLibraryController
from core.portfolios.service import PortfolioService
from core.strategies.service import StrategyService
from portfolio import repository as portfolio_repository
from strategy import Condition, Exits, Operand, RuleGroup, Strategy, repository


@pytest.fixture(autouse=True)
def temporary_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(repository, 'ROOT', tmp_path / 'strategies')
    monkeypatch.setattr(portfolio_repository, 'ROOT', tmp_path / 'portfolios')


STORED = pd.DataFrame({
    'symbol': ['IBM', 'NKE'], 'days': [16320, 11575],
    'first_date': pd.to_datetime(['1962-01-02', '1980-12-02']), 'last_date': pd.to_datetime(['2026-11-04'] * 2),
    'last_close': [254.32, 40.49], 'previous_close': [250.04, 38.48], 'checked_at': [1793848257.0, None]})


class FakeStockView:
    def __init__(self):
        self.title, self.rows, self.notices, self.closed = '', [], [], False

    def show_title(self, text): self.title = text
    def show_stocks(self, rows): self.rows = rows
    def show_notice(self, text): self.notices.append(text)
    def close(self): self.closed = True


class FakeExplorer:
    def __init__(self):
        self.log = []

    def add_symbol(self, symbol): self.log.append(('add_symbol', symbol))
    def open_portfolio(self, portfolio): self.log.append(('open_portfolio', portfolio.name, list(portfolio.symbols)))
    def refresh_portfolio(self, portfolio): self.log.append(('refresh_portfolio', portfolio.name, list(portfolio.symbols)))
    def begin_rename(self, portfolio_id): self.log.append(('begin_rename', portfolio_id))
    def select_strategy(self, symbol, strategy_id): self.log.append(('select_strategy', symbol, strategy_id))


def make_stocks(stored=STORED, history=lambda symbol: random_walk(300, seed=1)):
    view, explorer, service = FakeStockView(), FakeExplorer(), PortfolioService()
    controller = StockLibraryController(view, BackgroundLoader.immediate(), service, explorer, lambda: stored,
                                        lambda: {'IBM': 'International Business Machines'}, history)
    return controller, view, explorer, service


def test_stock_rows_show_name_price_day_change_and_history():
    ibm, nke = stock_rows(STORED, {'IBM': 'International Business Machines'})
    checked = f'{datetime.fromtimestamp(1793848257.0):%Y-%m-%d}'  # shown in local time
    assert [cell.text for cell in ibm.cells] == ['IBM', 'International Business Machines', '254.32', '+1.71%', '1962',
                                                 checked]
    assert nke.cells[1].text == '' and nke.cells[3].text == '+5.22%' and nke.cells[5].text == '—'
    assert '16,320 trading days stored' in ibm.cells[4].tooltip


def test_start_lists_the_stored_stocks():
    controller, view, *_ = make_stocks()
    controller.start()
    assert view.title == 'Stock Library' and [row.symbol for row in view.rows] == ['IBM', 'NKE']


def test_adding_a_stock_downloads_it_and_refreshes_the_list():
    stored = STORED.copy()
    controller, view, *_ = make_stocks(stored)
    controller.start()
    controller.add('IBM')
    assert view.notices[-1] == 'IBM is already in the library.'
    controller.add('MSFT')
    assert view.notices[-1].startswith('Added MSFT: 300 trading days')
    empty = make_stocks(history=lambda symbol: pd.DataFrame())
    empty[0].add('ZZZZ')
    assert 'No price history found for ZZZZ' in empty[1].notices[-1]


def test_right_click_lists_every_saved_portfolio_and_adds_the_stock():
    controller, view, explorer, service = make_stocks()
    retirement = service.create_default()
    service.rename(retirement.id, 'Retirement')
    menu = controller.menu_for('IBM')
    assert menu[0].text == 'Open IBM' and menu[2].text == 'Add to portfolio'
    assert [e.text if e else None for e in menu[2].children] == ['Retirement', None, 'New portfolio…']

    controller.menu_action(stock_library.ADD_TO, 'IBM', retirement.id)
    assert service.get(retirement.id).symbols == ['IBM'] and view.notices[-1] == 'Added IBM to "Retirement".'
    assert explorer.log[-1] == ('refresh_portfolio', 'Retirement', ['IBM'])
    controller.menu_action(stock_library.ADD_TO, 'IBM', retirement.id)
    assert view.notices[-1] == 'IBM is already in "Retirement".'

    controller.menu_action(stock_library.ADD_TO_NEW, 'NKE')
    assert explorer.log[-2][0] == 'open_portfolio' and explorer.log[-2][2] == ['NKE']
    assert explorer.log[-1][0] == 'begin_rename'
    controller.menu_action(stock_library.OPEN, 'NKE')
    assert explorer.log[-1] == ('add_symbol', 'NKE')
    controller.menu_action(stock_library.ADD_TO, 'IBM', 'deleted-portfolio')
    assert 'no longer exists' in view.notices[-1]


# --- Strategy Library ------------------------------------------------------------------------------------------

def strategy(name, symbol):
    return Strategy(name, RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma'))]),
                    RuleGroup('any', []), Exits(stop_loss_pct=5), symbol=symbol)


class FakeStrategyView:
    def __init__(self):
        self.groups, self.detail, self.actions, self.notices = [], None, [], []

    def show_title(self, text): self.title = text
    def show_strategies(self, groups): self.groups = groups
    def show_detail(self, item, actions): self.detail, self.actions = item, actions
    def show_notice(self, text): self.notices.append(text)
    def close(self): self.closed = True


class FakeActions:
    def __init__(self):
        self.calls = []

    def handle(self, action, symbol, strategy_id): self.calls.append((action, symbol, strategy_id))


def make_strategies(current=None, asked=None):
    view, actions, explorer = FakeStrategyView(), FakeActions(), FakeExplorer()
    controller = StrategyLibraryController(view, StrategyService(), actions, explorer, lambda: current,
                                           lambda title: asked)
    return controller, view, actions, explorer


def test_library_templates_come_first_then_each_stocks_strategies():
    for item in (strategy('Zeta', None), strategy('Alpha', None), strategy('Swing', 'NKE'), strategy('Trend', 'IBM')):
        repository.save(item)
    controller, view, *_ = make_strategies()
    controller.start()
    assert [(group, [i.name for i in items]) for group, items in view.groups] == [
        (LIBRARY_GROUP, ['Alpha', 'Zeta']), ('IBM', ['Trend']), ('NKE', ['Swing'])]
    assert view.detail is None


def test_buttons_depend_on_the_strategy_and_the_stock_on_screen():
    template, own = strategy('Template', None), strategy('Trend', 'IBM')
    repository.save(template), repository.save(own)
    controller, view, *_ = make_strategies(current='NKE')
    controller.start()
    controller.select(template.id)
    assert [a.text for a in view.actions] == ['Backtest on NKE', 'Copy to another stock…', 'Edit…', 'Delete…']
    assert 'BUY when Close is above SMA 50d' in view.detail.description
    controller.select(own.id)
    assert [a.text for a in view.actions] == ['Copy to NKE and backtest', 'Copy to another stock…', 'Save to Library',
                                              'Edit…', 'Delete…']
    nothing_on_screen = make_strategies(current=None)[0]
    nothing_on_screen.start()
    assert nothing_on_screen.actions_for(nothing_on_screen.items[own.id])[0].text == 'Backtest on IBM'
    assert nothing_on_screen.actions_for(nothing_on_screen.items[template.id])[0].text == 'Backtest on a stock…'


def test_trying_a_strategy_selects_or_copies_it():
    template, own = strategy('Template', None), strategy('Trend', 'IBM')
    repository.save(template), repository.save(own)
    controller, view, actions, explorer = make_strategies(current='NKE')
    controller.start()
    controller.run(strategy_library.TRY, template.id)
    assert explorer.log[-1] == ('select_strategy', 'NKE', template.id)  # templates are listed under every stock
    controller.run(strategy_library.TRY, own.id)  # another stock's strategy: copy it to NKE first
    [copy] = repository.for_symbol('NKE')
    assert copy.origin_id == own.id and explorer.log[-1] == ('select_strategy', 'NKE', copy.id)
    assert [i.name for i in dict(view.groups)['NKE']] == ['Trend']  # the list shows the new copy

    asks = make_strategies(current=None, asked='MSFT')
    asks[0].start()
    asks[0].run(strategy_library.TRY, template.id)
    assert asks[3].log[-1] == ('select_strategy', 'MSFT', template.id)


def test_other_actions_go_through_the_shared_strategy_actions():
    template, own = strategy('Template', None), strategy('Trend', 'IBM')
    repository.save(template), repository.save(own)
    controller, view, actions, _ = make_strategies(current='NKE')
    controller.start()
    controller.run(strategy_library.NEW_TEMPLATE)
    controller.run(strategy_library.EDIT, template.id)
    controller.run(strategy_library.EDIT, own.id)
    controller.run(strategy_library.DELETE, own.id)
    controller.run(strategy_library.COPY_TO, own.id)
    controller.run(strategy_library.SAVE_TO_LIBRARY, own.id)
    assert actions.calls == [('new', None, ''), ('edit', 'NKE', template.id), ('edit', 'IBM', own.id),
                             ('delete', 'IBM', own.id), ('copy_to', 'IBM', own.id), ('save_to_library', 'IBM', own.id)]
    controller.selected = None
    controller.run(strategy_library.EDIT)
    assert view.notices[-1] == 'Choose a strategy first.'

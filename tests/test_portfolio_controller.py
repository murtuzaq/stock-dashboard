"""PortfolioController: File menu actions, in-place rename and the right-click actions, with fake views."""
import pytest

from core.explorer.controller import PORTFOLIO, SYMBOL, Node
from core.portfolios import actions
from core.portfolios.controller import PortfolioController
from core.portfolios.service import PortfolioService
from portfolio import repository


@pytest.fixture(autouse=True)
def temporary_root(tmp_path, monkeypatch):
    monkeypatch.setattr(repository, 'ROOT', tmp_path / 'portfolios')


class FakeExplorer:
    def __init__(self):
        self.open, self.log, self.names = {}, [], {}

    def open_portfolio(self, portfolio):
        self.open[portfolio.id] = list(portfolio.symbols)
        self.names[portfolio.id] = portfolio.name
        self.log.append(('open', portfolio.id))

    def refresh_portfolio(self, portfolio):
        self.open[portfolio.id] = list(portfolio.symbols)
        self.names[portfolio.id] = portfolio.name
        self.log.append(('refresh', portfolio.id))

    def close_portfolio(self, portfolio_id):
        self.open.pop(portfolio_id, None)
        self.log.append(('close', portfolio_id))

    def begin_rename(self, portfolio_id):
        self.log.append(('begin_rename', portfolio_id))

    def open_portfolio_ids(self):
        return set(self.open)


class FakeDialogs:
    def __init__(self, yes=True, choice=None):
        self.yes, self.choice, self.notices, self.asked, self.offered = yes, choice, [], [], None

    def confirm(self, text):
        self.asked.append(text)
        return self.yes

    def notify(self, text):
        self.notices.append(text)

    def choose_portfolio(self, options):
        self.offered = options
        return self.choice(options) if callable(self.choice) else self.choice


def make(dialogs=None):
    service, explorer, opened = PortfolioService(), FakeExplorer(), []
    dialogs = dialogs or FakeDialogs()
    controller = PortfolioController(service, explorer, dialogs, opened.append)
    return controller, service, explorer, dialogs, opened


def stock(symbol, portfolio=None):
    return Node(symbol, None, SYMBOL, portfolio=portfolio)


def portfolio_node(portfolio_id):
    return Node('', None, PORTFOLIO, portfolio=portfolio_id)


# --- File menu -------------------------------------------------------------------------------------------------

def test_new_portfolio_is_created_opened_and_put_into_rename_mode():
    controller, service, explorer, *_ = make()
    controller.new_portfolio()
    saved = service.saved()
    assert [s.name for s in saved] == ['Portfolio 1']
    assert explorer.log == [('open', saved[0].id), ('begin_rename', saved[0].id)]


def test_load_offers_only_saved_portfolios_that_are_not_already_open():
    dialogs = FakeDialogs(choice=lambda options: options[0].id)
    controller, service, explorer, *_ = make(dialogs)
    first, second = service.create_default(), service.create_default()
    service.add_symbols(second.id, ['AAPL', 'MSFT'])
    explorer.open_portfolio(first)  # already showing
    controller.load_portfolio()
    assert [(o.name, o.stock_count) for o in dialogs.offered] == [('Portfolio 2', 2)]
    assert explorer.open[second.id] == ['AAPL', 'MSFT']


def test_load_with_nothing_to_load_says_why():
    controller, service, explorer, dialogs, _ = make()
    controller.load_portfolio()
    assert 'No saved portfolios yet' in dialogs.notices[-1]
    explorer.open_portfolio(service.create_default())
    controller.load_portfolio()
    assert 'already open' in dialogs.notices[-1]


def test_cancelling_the_load_dialog_opens_nothing():
    controller, service, explorer, dialogs, _ = make(FakeDialogs(choice=None))
    service.create_default()
    controller.load_portfolio()
    assert explorer.open == {}


def test_load_of_a_file_removed_meanwhile_is_reported_not_raised():
    dialogs = FakeDialogs(choice='gone')
    controller, service, explorer, dialogs, _ = make(dialogs)
    service.create_default()
    controller.load_portfolio()
    assert 'no longer exists' in dialogs.notices[-1] and explorer.open == {}


# --- rename ----------------------------------------------------------------------------------------------------

def test_a_typed_name_is_saved_and_shown():
    controller, service, explorer, *_ = make()
    portfolio = service.create_default()
    explorer.open_portfolio(portfolio)
    controller.handle(actions.RENAME, portfolio_node(portfolio.id), '  Retirement ')
    assert service.get(portfolio.id).name == 'Retirement' and explorer.names[portfolio.id] == 'Retirement'


def test_a_refused_name_is_explained_and_the_old_name_comes_back():
    controller, service, explorer, dialogs, _ = make()
    one, two = service.create_default(), service.create_default()
    explorer.open_portfolio(two)
    controller.handle(actions.RENAME, portfolio_node(two.id), 'portfolio 1')
    assert 'already exists' in dialogs.notices[-1]
    assert explorer.names[two.id] == 'Portfolio 2' and service.get(two.id).name == 'Portfolio 2'
    controller.handle(actions.RENAME, portfolio_node(two.id), '   ')
    assert 'needs a name' in dialogs.notices[-1] and explorer.names[two.id] == 'Portfolio 2'


def test_rename_from_the_menu_starts_editing_in_place():
    controller, service, explorer, *_ = make()
    portfolio = service.create_default()
    controller.handle(actions.RENAME, portfolio_node(portfolio.id), None)
    assert explorer.log == [('begin_rename', portfolio.id)]


# --- right-click actions ---------------------------------------------------------------------------------------

def test_add_stock_opens_the_wizard_for_that_portfolio():
    controller, service, explorer, dialogs, opened = make()
    portfolio = service.create_default()
    controller.handle(actions.ADD_STOCK, portfolio_node(portfolio.id))
    assert [p.id for p in opened] == [portfolio.id]


def test_close_keeps_the_file_and_delete_removes_it_after_confirmation():
    controller, service, explorer, dialogs, _ = make()
    portfolio = service.create_default()
    explorer.open_portfolio(portfolio)
    controller.handle(actions.CLOSE, portfolio_node(portfolio.id))
    assert portfolio.id not in explorer.open and service.get(portfolio.id) is not None

    dialogs.yes = False
    controller.handle(actions.DELETE, portfolio_node(portfolio.id))
    assert service.get(portfolio.id) is not None and 'Portfolio 1' in dialogs.asked[0]

    dialogs.yes = True
    explorer.open_portfolio(portfolio)
    controller.handle(actions.DELETE, portfolio_node(portfolio.id))
    assert service.get(portfolio.id) is None and portfolio.id not in explorer.open


def test_add_to_portfolio_copies_the_stock_and_reports_a_repeat():
    controller, service, explorer, dialogs, _ = make()
    target = service.create_default()
    explorer.open_portfolio(target)
    controller.handle(actions.ADD_TO, stock('aapl'), target.id)
    assert service.get(target.id).symbols == ['AAPL'] and explorer.open[target.id] == ['AAPL'] and not dialogs.notices
    controller.handle(actions.ADD_TO, stock('AAPL'), target.id)
    assert service.get(target.id).symbols == ['AAPL'] and 'already in "Portfolio 1"' in dialogs.notices[-1]


def test_a_stock_from_another_portfolio_can_be_added_and_stays_in_the_first():
    controller, service, explorer, *_ = make()
    first, second = service.create_default(), service.create_default()
    service.add_symbols(first.id, ['IBM'])
    explorer.open_portfolio(service.get(first.id))
    explorer.open_portfolio(second)
    controller.handle(actions.ADD_TO, stock('IBM', portfolio=first.id), second.id)
    assert service.get(first.id).symbols == ['IBM'] and service.get(second.id).symbols == ['IBM']


def test_add_to_new_portfolio_creates_it_with_the_stock_and_lets_the_user_name_it():
    controller, service, explorer, *_ = make()
    controller.handle(actions.ADD_TO_NEW, stock('MSFT'))
    [summary] = service.saved()
    assert summary.name == 'Portfolio 1' and service.get(summary.id).symbols == ['MSFT']
    assert explorer.open[summary.id] == ['MSFT'] and explorer.log[-1] == ('begin_rename', summary.id)


def test_remove_from_portfolio_only_changes_that_portfolio():
    controller, service, explorer, *_ = make()
    portfolio = service.create_default()
    service.add_symbols(portfolio.id, ['AAPL', 'MSFT'])
    explorer.open_portfolio(service.get(portfolio.id))
    controller.handle(actions.REMOVE_FROM, stock('AAPL', portfolio=portfolio.id))
    assert service.get(portfolio.id).symbols == ['MSFT'] and explorer.open[portfolio.id] == ['MSFT']


def test_acting_on_a_portfolio_whose_file_was_removed_drops_its_stale_row():
    controller, service, explorer, dialogs, _ = make()
    portfolio = service.create_default()
    explorer.open_portfolio(portfolio)
    service.delete(portfolio.id)  # removed behind the app's back
    controller.handle(actions.REMOVE_FROM, stock('AAPL', portfolio=portfolio.id))
    assert 'no longer exists' in dialogs.notices[-1] and portfolio.id not in explorer.open


def test_unknown_actions_are_rejected():
    controller, *_ = make()
    with pytest.raises(ValueError, match='Unknown portfolio action'):
        controller.handle('format_disk', stock('AAPL'))

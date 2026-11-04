"""Wizard, strategy-action and search controllers, driven through fake views (no Qt)."""
import pytest

from core.dashboard.controller import DashboardController
from core.searchbar.controller import SearchController
from core.strategies.controller import StrategyController
from core.strategies.service import StrategyService
from core.builder.session import BUY, NAME, REVIEW, SELL, START, WizardForm
from core.builder.controller import WizardController
from search import Catalog, Group, Security
from strategy import Condition, Exits, Operand, RuleGroup, Strategy, repository


@pytest.fixture(autouse=True)
def isolated_repository(tmp_path, monkeypatch):
    monkeypatch.setattr(repository, 'ROOT', tmp_path / 'strategies')


def condition():
    return Condition(Operand('close'), 'above', Operand('sma', params={'days': 50}))


# --- wizard ---------------------------------------------------------------------------------------------------

class FakeWizardView:
    def __init__(self):
        self.form = WizardForm()
        self.steps, self.errors, self.reviews, self.loaded, self.groups = [], [], [], [], None
        self.title = None
        self.closed = False
        self.new_chosen = False

    def show_title(self, text): self.title = text
    def show_step(self, index, step_text, back_enabled, next_text, for_text):
        self.steps.append((index, step_text, back_enabled, next_text, for_text))
    def show_error(self, text): self.errors.append(text)
    def show_review(self, line): self.reviews.append(''.join(s.text for s in line))
    def read_form(self): return self.form
    def load_strategy(self, strategy): self.loaded.append(strategy)
    def fill_existing(self, groups): self.groups = groups
    def choose_new(self): self.new_chosen = True
    def close(self): self.closed = True


def filled_form(**changes):
    values = dict(name='Mine', buy=RuleGroup('all', [condition()]), sell=RuleGroup('any', [condition()]),
                  exits=Exits(stop_loss_pct=5))
    values.update(changes)
    return WizardForm(**values)


def test_wizard_walks_all_five_steps_and_saves():
    view, saved = FakeWizardView(), []
    controller = WizardController(view, on_saved=saved.append)
    controller.start_new('IBM')
    assert view.title == 'New strategy for IBM' and view.new_chosen and view.groups == []
    assert view.steps[-1] == (START, 'Step 1 of 5: Start', False, 'Next', 'For IBM.')

    view.form = filled_form()
    for expected in (NAME, BUY, SELL, REVIEW):
        controller.next()
        assert controller.step == expected
    assert view.steps[-1][3] == 'Save && Backtest'
    assert view.reviews[-1].startswith('Mine — IBM')

    controller.next()  # Save & Backtest
    assert len(saved) == 1 and saved[0].name == 'Mine'
    assert repository.get(saved[0].id) is not None


def test_wizard_stays_on_a_step_and_explains_the_problem():
    view = FakeWizardView()
    controller = WizardController(view)
    controller.start_new('IBM')
    view.form = filled_form()
    controller.next()  # Start -> Name
    view.form = filled_form(name=' ')
    controller.next()
    assert controller.step == NAME and view.errors == ['Give the strategy a name.']


def test_wizard_back_and_cancel_and_the_start_page_is_not_reachable_when_editing():
    view = FakeWizardView()
    controller = WizardController(view)
    strategy = Strategy('Existing', RuleGroup('all', [condition()]), RuleGroup('any', []), Exits(stop_loss_pct=5),
                        symbol='IBM')
    controller.start_edit(strategy, 'IBM')
    assert controller.step == NAME and view.loaded == [strategy] and view.title == 'Edit "Existing"'
    assert view.steps[-1][2] is False  # no Back from the first step
    controller.back()
    assert controller.step == NAME  # clamped: editing skips the Start page
    view.form = filled_form()
    controller.next()
    controller.back()
    assert controller.step == NAME
    controller.cancel()
    assert view.closed


def test_wizard_copy_loads_the_chosen_strategy_into_the_form():
    source = Strategy('Source', RuleGroup('all', [condition()]), RuleGroup('any', []), Exits(stop_loss_pct=5),
                      symbol='AAPL')
    repository.save(source)
    view = FakeWizardView()
    controller = WizardController(view)
    controller.start_new('IBM')
    view.form = WizardForm(copy_requested=True, copy_source_id=source.id)
    controller.next()
    assert view.loaded[-1].name == 'Source' and view.loaded[-1].symbol == 'IBM' and view.loaded[-1].id != source.id


# --- strategy actions -------------------------------------------------------------------------------------------

class FakeExplorer:
    def __init__(self): self.calls = []
    def add_symbol(self, symbol): self.calls.append(('add', symbol))
    def refresh_strategies(self): self.calls.append(('refresh',))
    def select_strategy(self, symbol, strategy_id): self.calls.append(('select', symbol, strategy_id))


class FakeDialogs:
    def __init__(self, symbol=None, yes=True):
        self.symbol, self.yes, self.shown, self.asked = symbol, yes, 0, []
    def ask_symbol(self, title): return self.symbol
    def confirm(self, text): self.asked.append(text); return self.yes
    def show_wizard(self): self.shown += 1


class FakeDashboard:
    symbol = 'IBM'
    def __init__(self): self.refreshed = 0
    def refresh_strategy(self): self.refreshed += 1


def make_actions(dialogs=None):
    wizard_view = FakeWizardView()
    wizard = WizardController(wizard_view)
    explorer, dashboard = FakeExplorer(), FakeDashboard()
    dialogs = dialogs or FakeDialogs()
    controller = StrategyController(StrategyService(), explorer, wizard, dashboard, dialogs)
    return controller, explorer, wizard_view, dialogs, dashboard


def saved_strategy(symbol='IBM', name='Mine'):
    strategy = Strategy(name, RuleGroup('all', [condition()]), RuleGroup('any', []), Exits(stop_loss_pct=5),
                        symbol=symbol)
    repository.save(strategy)
    return strategy


def test_new_opens_the_wizard_for_the_stock():
    controller, explorer, wizard_view, dialogs, _ = make_actions()
    controller.handle('new', 'IBM', '')
    assert wizard_view.title == 'New strategy for IBM' and dialogs.shown == 1


def test_edit_opens_the_wizard_and_edit_current_uses_the_viewed_stock():
    controller, explorer, wizard_view, dialogs, _ = make_actions()
    strategy = saved_strategy()
    controller.edit_current(strategy.id)
    assert wizard_view.title == 'Edit "Mine"' and dialogs.shown == 1
    controller.edit('IBM', 'no-such-id')  # a strategy deleted meanwhile: nothing opens
    assert dialogs.shown == 1


def test_duplicate_copy_here_and_save_to_library_refresh_the_explorer():
    controller, explorer, wizard_view, dialogs, _ = make_actions()
    strategy = saved_strategy()
    controller.handle('duplicate', 'IBM', strategy.id)
    assert explorer.calls[0] == ('refresh',) and explorer.calls[1][:2] == ('select', 'IBM')
    assert repository.get(explorer.calls[1][2]).name == 'Mine (copy)'

    controller.handle('save_to_library', 'IBM', strategy.id)
    assert explorer.calls[-1] == ('refresh',) and [s.name for s in repository.library()] == ['Mine']

    template = repository.library()[0]
    explorer.calls.clear()
    controller.handle('copy_here', 'AAPL', template.id)
    assert ('select', 'AAPL') == explorer.calls[1][:2] and dialogs.shown == 1  # opened for customising


def test_copy_to_asks_for_a_stock_and_does_nothing_if_cancelled():
    strategy = saved_strategy()
    cancelled = make_actions(FakeDialogs(symbol=None))
    cancelled[0].handle('copy_to', 'IBM', strategy.id)
    assert cancelled[1].calls == []

    controller, explorer, *_ = make_actions(FakeDialogs(symbol='AAPL'))
    controller.handle('copy_to', 'IBM', strategy.id)
    assert explorer.calls[0] == ('add', 'AAPL') and explorer.calls[2][:2] == ('select', 'AAPL')
    assert [s.name for s in repository.for_symbol('AAPL')] == ['Mine']


def test_delete_only_after_confirmation():
    strategy = saved_strategy()
    no = make_actions(FakeDialogs(yes=False))
    no[0].handle('delete', 'IBM', strategy.id)
    assert repository.get(strategy.id) is not None and 'Delete "Mine" from IBM?' in no[3].asked[0]
    yes = make_actions(FakeDialogs(yes=True))
    yes[0].handle('delete', 'IBM', strategy.id)
    assert repository.get(strategy.id) is None and yes[1].calls == [('refresh',)]


def test_saving_in_the_wizard_closes_it_selects_the_strategy_and_reruns_the_backtest():
    controller, explorer, wizard_view, dialogs, dashboard = make_actions()
    controller.handle('new', 'IBM', '')
    wizard_view.form = filled_form()
    for _ in range(5):
        controller.wizard.next()
    assert wizard_view.closed and dashboard.refreshed == 1
    assert explorer.calls[0] == ('refresh',) and explorer.calls[1][:2] == ('select', 'IBM')


# --- search ---------------------------------------------------------------------------------------------------

APPLE = Security('AAPL', 'Apple Inc', 'NASDAQ', False, ('apple', 'inc'))
AMAZON = Security('AMZN', 'Amazon.com', 'NASDAQ', False, ('amazon.com',))
NASDAQ = Group('Nasdaq-100', 'Index', 'Largest Nasdaq stocks', ('nasdaq',), frozenset({'AAPL', 'AMZN'}))
CATALOG = Catalog({'AAPL': APPLE, 'AMZN': AMAZON}, [NASDAQ], frozenset())


class FakeSearchView:
    def __init__(self):
        self.typed, self.placeholder, self.scope, self.results, self.visible = '', None, 'unset', None, False
    def text(self): return self.typed
    def clear_text(self): self.typed = ''
    def set_placeholder(self, text): self.placeholder = text
    def show_scope(self, group): self.scope = group
    def show_results(self, results): self.results, self.visible = results, True
    def hide_results(self): self.visible = False


def make_search():
    view, opened = FakeSearchView(), []
    controller = SearchController(view, opened.append)
    return controller, view, opened


def test_search_shows_loading_then_the_normal_placeholder():
    controller, view, _ = make_search()
    assert view.placeholder == 'Loading symbol list…'
    controller.catalog_loaded(CATALOG, input_has_focus=False)
    assert view.placeholder.startswith('Search symbol, company') and not view.visible


def test_typing_lists_matches_and_nothing_before_the_catalog_arrives():
    controller, view, _ = make_search()
    view.typed = 'app'
    controller.refresh()
    assert not view.visible  # catalog not loaded yet
    controller.catalog_loaded(CATALOG, input_has_focus=True)  # focused: the pending text is searched now
    assert view.visible and [s.symbol for s in view.results.securities] == ['AAPL']


def test_choosing_a_group_filters_and_choosing_a_security_opens_it():
    controller, view, opened = make_search()
    controller.catalog_loaded(CATALOG, False)
    view.typed = 'nasdaq'
    controller.choose(NASDAQ)
    assert view.scope is NASDAQ and view.typed == '' and view.placeholder == 'Search within Nasdaq-100 (2 symbols)'
    assert view.results.groups == [] and {s.symbol for s in view.results.securities} == {'AAPL', 'AMZN'}

    controller.choose(AMAZON)
    assert opened == ['AMZN'] and view.typed == '' and not view.visible
    controller.choose(None)  # a note row: ignored
    assert opened == ['AMZN']


def test_enter_takes_the_highlighted_row_or_opens_the_typed_text():
    controller, view, opened = make_search()
    controller.catalog_loaded(CATALOG, False)
    controller.enter(results_open=True, current=APPLE)
    assert opened == ['AAPL']
    view.typed = ' zzzz '
    controller.enter(results_open=True, current=None)  # nothing highlighted: open what was typed
    view.typed = ' zzzz '  # opening a symbol clears the box
    controller.enter(results_open=False, current=None)
    assert opened == ['AAPL', 'ZZZZ', 'ZZZZ']
    view.typed = '  '
    controller.enter(False, None)
    assert len(opened) == 3  # blank text opens nothing


def test_escape_closes_the_list_first_then_removes_the_filter():
    controller, view, _ = make_search()
    controller.catalog_loaded(CATALOG, False)
    controller.set_scope(NASDAQ)
    controller.escape(results_open=True)
    assert not view.visible and view.scope is NASDAQ
    controller.escape(results_open=False)
    assert view.scope is None


def test_backspace_in_an_empty_box_removes_the_filter_only():
    controller, view, _ = make_search()
    controller.catalog_loaded(CATALOG, False)
    assert controller.backspace_in_empty_box() is False  # no filter: normal backspace
    controller.set_scope(NASDAQ)
    view.typed = 'a'
    assert controller.backspace_in_empty_box() is False  # text present: normal backspace
    view.typed = ''
    assert controller.backspace_in_empty_box() is True and view.scope is None

"""InfoController with fake views and dialogs, and the UI-to-topic mapping."""
import pytest

from core.learn import ui_terms
from core.learn.controller import PREF_ENABLED, PREF_WELCOME_SEEN, InfoController, RequestForm
from core.learn.preferences import MemoryPreferences
from learn import load_library
from learn import requests as info_requests


class FakeView:
    def __init__(self):
        self.pages, self.not_found, self.navigation, self.panel, self.highlighting = [], [], [], [], []

    def show_topic(self, page): self.pages.append(page)
    def show_not_found(self, text): self.not_found.append(text)
    def set_navigation(self, can_back, can_forward): self.navigation.append((can_back, can_forward))
    def show_panel(self): self.panel.append('show')
    def hide_panel(self): self.panel.append('hide')
    def set_highlighting(self, enabled): self.highlighting.append(enabled)


class FakeDialogs:
    def __init__(self, answer=None):
        self.answer, self.asked, self.notices = answer, [], []

    def ask_request(self, text, where):
        self.asked.append((text, where))
        return self.answer(text) if callable(self.answer) else self.answer

    def notify(self, text): self.notices.append(text)


@pytest.fixture(autouse=True)
def requests_file(tmp_path, monkeypatch):
    monkeypatch.setattr(info_requests, 'FILE', tmp_path / 'info_requests.json')


def make(enabled=False, answer=None, welcome_seen=False):
    view, dialogs = FakeView(), FakeDialogs(answer)
    preferences = MemoryPreferences(**{PREF_ENABLED: enabled, PREF_WELCOME_SEEN: welcome_seen})
    controller = InfoController(view, load_library(), dialogs, preferences,
                                context=lambda: {'symbol': 'IBM', 'view': 'macd'})
    return controller, view, dialogs, preferences


# --- on / off --------------------------------------------------------------------------------------------------

def test_restore_applies_the_remembered_setting_without_opening_the_panel():
    controller, view, *_ = make(enabled=True)
    controller.restore()
    assert controller.enabled and view.highlighting == [True] and view.panel == []
    off, off_view, *_ = make(enabled=False)
    off.restore()
    assert not off.enabled and off_view.highlighting == [False]


def test_turning_it_on_underlines_terms_remembers_it_and_shows_the_welcome_topic_once():
    controller, view, _, preferences = make()
    controller.set_enabled(True)
    assert view.highlighting == [True] and preferences.values[PREF_ENABLED] is True
    assert view.pages[-1].id == 'welcome-info' and view.panel == ['show'] and preferences.values[PREF_WELCOME_SEEN]

    controller.set_enabled(False)
    controller.set_enabled(True)
    assert [p.id for p in view.pages] == ['welcome-info']  # not shown a second time


def test_turning_it_off_hides_the_panel_clears_history_and_ignores_double_clicks():
    controller, view, _, preferences = make(welcome_seen=True)
    controller.set_enabled(True)
    controller.open('macd')
    controller.set_enabled(False)
    assert view.panel[-1] == 'hide' and view.highlighting == [True, False] and preferences.values[PREF_ENABLED] is False
    assert controller.history == []
    shown = len(view.pages)
    controller.open('sma')
    assert len(view.pages) == shown  # nothing happens while it is off


# --- opening topics --------------------------------------------------------------------------------------------

def opened(welcome_seen=True):
    controller, view, dialogs, preferences = make(welcome_seen=welcome_seen)
    controller.set_enabled(True)
    return controller, view, dialogs


def test_opening_a_topic_shows_its_page_with_related_topics_and_the_panel():
    controller, view, _ = opened()
    controller.open('macd')
    page = view.pages[-1]
    assert (page.id, page.title, page.category) == ('macd', 'MACD', 'Indicators')
    assert page.body.startswith('**MACD**') and page.summary
    assert ('signal-line', 'Signal line') in page.related and all(title for _, title in page.related)
    assert view.panel[-1] == 'show' and view.navigation[-1] == (False, False)


def test_back_and_forward_walk_the_history_and_a_new_topic_drops_the_old_forward():
    controller, view, _ = opened()
    for topic in ('macd', 'sma', 'atr'):
        controller.open(topic)
    assert view.navigation[-1] == (True, False)
    controller.back()
    controller.back()
    assert view.pages[-1].id == 'macd' and view.navigation[-1] == (False, True)
    controller.back()  # at the start: nothing happens
    assert view.pages[-1].id == 'macd'
    controller.forward()
    assert view.pages[-1].id == 'sma'
    controller.open('volume')  # branching off: atr is no longer ahead
    assert controller.history == ['macd', 'sma', 'volume'] and view.navigation[-1] == (True, False)
    controller.forward()
    assert view.pages[-1].id == 'volume'


def test_reopening_the_current_topic_does_not_add_a_history_entry():
    controller, view, _ = opened()
    controller.open('macd')
    controller.open('macd')
    assert controller.history == ['macd'] and view.navigation[-1] == (False, False)


def test_text_is_matched_by_title_or_alias_and_unknown_text_shows_the_not_found_page():
    controller, view, _ = opened()
    controller.open_text('moving average convergence divergence')
    assert view.pages[-1].id == 'macd'
    controller.open_text('Sharpe ratio')
    assert view.not_found == ['Sharpe ratio'] and view.navigation[-1] == (True, False)
    controller.back()
    assert view.pages[-1].id == 'macd'


def test_is_known_and_title_of():
    controller, *_ = make()
    assert controller.is_known('sma') and not controller.is_known('nope') and not controller.is_known(None)
    assert controller.title_of('sma') == 'SMA' and controller.title_of('nope') == 'nope'


# --- requests --------------------------------------------------------------------------------------------------

def test_a_request_is_saved_with_the_current_context_and_thanked():
    controller, view, dialogs = opened()
    dialogs.answer = RequestForm('Sharpe ratio', 'what is a good value?')
    controller.request('sharpe', 'summary card')
    assert dialogs.asked == [('sharpe', 'summary card')]
    [saved] = info_requests.all_requests()
    assert saved.text == 'Sharpe ratio' and saved.note == 'what is a good value?'
    assert saved.contexts == [{'symbol': 'IBM', 'view': 'macd', 'where': 'summary card'}]
    assert 'added to your list' in dialogs.notices[-1]


def test_asking_again_says_it_was_already_requested():
    controller, view, dialogs = opened()
    dialogs.answer = RequestForm('Sharpe ratio')
    controller.request('x', 'a')
    controller.request('x', 'b')
    assert 'already requested (2 times)' in dialogs.notices[-1]


def test_a_request_for_something_already_explained_opens_it_instead_of_saving():
    controller, view, dialogs = opened()
    dialogs.answer = RequestForm('stop loss')
    controller.request('stop loss', 'label')
    assert info_requests.all_requests() == []
    assert 'already explained' in dialogs.notices[-1] and view.pages[-1].id == 'stop-loss'


def test_cancelling_or_a_blank_request_saves_nothing():
    controller, view, dialogs = opened()
    controller.request('x', 'label')  # the dialog was cancelled (answer None)
    assert info_requests.all_requests() == [] and dialogs.notices == []
    dialogs.answer = RequestForm('   ')
    controller.request('x', 'label')
    assert info_requests.all_requests() == [] and 'Say which term' in dialogs.notices[-1]


# --- UI mapping ------------------------------------------------------------------------------------------------

def test_every_topic_the_ui_refers_to_exists_in_the_library():
    library = load_library()
    missing = sorted(topic for topic in ui_terms.all_topic_ids() if library.get(topic) is None)
    assert missing == []


def test_the_explorer_views_that_have_topics_are_real_views():
    from core.dashboard.layout import VIEWS
    keys = {key for key, _ in VIEWS}
    assert set(ui_terms.EXPLORER_VIEWS) <= keys

"""The Info Wizard: switching it on and off, opening topics, going back and forward, and requesting new ones.

The renderer implements `InfoView` (shows the page, underlines terms) and `InfoDialogs` (asks for a request), and
forwards double-clicks and menu choices here. Which topics exist comes from the learn.TopicLibrary.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from core.learn.preferences import Preferences
from core.learn.ui_terms import WELCOME
from learn import TopicLibrary
from learn import requests as info_requests

PREF_ENABLED = 'info_wizard_on'
PREF_WELCOME_SEEN = 'info_welcome_seen'


@dataclass(frozen=True)
class TopicPage:
    """What the panel shows for one topic."""
    id: str
    title: str
    category: str
    summary: str
    body: str  # Markdown
    related: tuple[tuple[str, str], ...]  # (id, title) of topics to offer next


@dataclass(frozen=True)
class RequestForm:
    text: str  # the term to explain (the user may have edited it)
    note: str = ''


class InfoView(Protocol):
    def show_topic(self, page: TopicPage) -> None: ...
    def show_not_found(self, text: str) -> None:
        """Tell the user there is no topic for this text yet and offer to request one."""
    def set_navigation(self, can_back: bool, can_forward: bool) -> None: ...
    def show_panel(self) -> None: ...
    def hide_panel(self) -> None: ...
    def set_highlighting(self, enabled: bool) -> None:
        """Underline (or stop underlining) every term that has an explanation."""


class InfoDialogs(Protocol):
    def ask_request(self, text: str, where: str) -> RequestForm | None:
        """Ask which term to request (pre-filled with `text`); None if the user cancels."""
    def notify(self, text: str) -> None: ...


class InfoController:
    def __init__(self, view: InfoView, library: TopicLibrary, dialogs: InfoDialogs, preferences: Preferences,
                 context: Callable[[], dict] | None = None,
                 add_request: Callable[[str, dict | None, str], info_requests.Request] = info_requests.add) -> None:
        self.view = view
        self.library = library
        self.dialogs = dialogs
        self.preferences = preferences
        self.context = context or (lambda: {})  # e.g. the stock and views showing, saved with each request
        self.add_request = add_request
        self.enabled = False
        self.history: list[str] = []  # topic ids (an unknown id is kept too, so Back works from "not found")
        self.position = -1

    # --- on / off ---

    def restore(self) -> None:
        """At start-up: apply the remembered setting. The panel stays closed until something is double-clicked."""
        self.enabled = self.preferences.get_bool(PREF_ENABLED, False)
        self.view.set_highlighting(self.enabled)

    def set_enabled(self, enabled: bool) -> None:
        """View > Info Wizard was ticked or unticked."""
        self.enabled = enabled
        self.preferences.set_bool(PREF_ENABLED, enabled)
        self.view.set_highlighting(enabled)
        if not enabled:
            self.history, self.position = [], -1
            self.view.hide_panel()
        elif not self.preferences.get_bool(PREF_WELCOME_SEEN, False):
            self.preferences.set_bool(PREF_WELCOME_SEEN, True)
            self.open(WELCOME)

    # --- looking things up ---

    def is_known(self, topic_id: str | None) -> bool:
        """Whether a term has an explanation (so the UI should mark it clickable)."""
        return topic_id is not None and self.library.get(topic_id) is not None

    def title_of(self, topic_id: str) -> str:
        topic = self.library.get(topic_id)
        return topic.title if topic else topic_id

    def open(self, topic_id: str) -> None:
        """Show a topic (a double-click on a term). Does nothing while the Info Wizard is off."""
        if not self.enabled:
            return
        if self.position < len(self.history) - 1:  # opening something new after going Back drops the old Forward
            del self.history[self.position + 1:]
        if not self.history or self.history[-1] != topic_id:
            self.history.append(topic_id)
        self.position = len(self.history) - 1
        self._show(topic_id)

    def open_text(self, text: str) -> None:
        """Show the topic a piece of text names, or the 'not found' page offering to request it."""
        topic = self.library.find(text)
        self.open(topic.id if topic else text)

    def back(self) -> None:
        if self.position > 0:
            self.position -= 1
            self._show(self.history[self.position])

    def forward(self) -> None:
        if self.position < len(self.history) - 1:
            self.position += 1
            self._show(self.history[self.position])

    def _show(self, topic_id_or_text: str) -> None:
        topic = self.library.get(topic_id_or_text)
        if topic is None:
            self.view.show_not_found(topic_id_or_text)
        else:
            related = tuple((other.id, other.title) for other in map(self.library.get, topic.related) if other)
            self.view.show_topic(TopicPage(topic.id, topic.title, topic.category, topic.summary, topic.body, related))
        self.view.set_navigation(self.position > 0, self.position < len(self.history) - 1)
        self.view.show_panel()

    # --- requests ---

    def request(self, text: str, where: str) -> None:
        """'Request info on...' (right-click, or the button on the not-found page)."""
        form = self.dialogs.ask_request(text, where)
        if form is None:
            return
        known = self.library.find(form.text)
        if known:  # it is already explained (the user may not have noticed): show it, do not record a request
            self.dialogs.notify(f'"{form.text}" is already explained: opening "{known.title}".')
            self.open(known.id)
            return
        context = {**self.context(), 'where': where}
        try:
            saved = self.add_request(form.text, context, form.note)
        except ValueError as error:
            self.dialogs.notify(str(error))
            return
        if saved.count > 1:
            self.dialogs.notify(f'"{saved.text}" was already requested ({saved.count} times). Thanks, that helps '
                                'prioritise it.')
        else:
            self.dialogs.notify(f'Thanks! "{saved.text}" was added to your list of requested topics.')

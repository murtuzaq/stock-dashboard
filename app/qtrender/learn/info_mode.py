"""Info mode: underlining the terms that have an explanation, and what double-click and right-click do on them.

One `InfoMode` exists per window. Widgets ask `current()` for it when they are built and stay plain if there is none.
It knows which topics exist (so only explained terms are marked) and forwards double-clicks and requests to the
core.learn InfoController, which it is bound to after construction.
"""
from weakref import WeakKeyDictionary

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtWidgets import QMenu, QWidget

from core.common.formatting import Line
from core.learn.controller import InfoController
from core.learn.linking import link_line
from learn import TopicLibrary

_current: 'InfoMode | None' = None


def current() -> 'InfoMode | None':
    return _current


def set_current(mode: 'InfoMode | None') -> None:
    global _current
    _current = mode


class InfoMode(QObject):
    changed = Signal(bool)  # the Info Wizard was switched on or off

    def __init__(self, library: TopicLibrary) -> None:
        super().__init__()
        self.library = library
        self.controller: InfoController | None = None
        self.on = False
        self._marked: WeakKeyDictionary[QWidget, tuple[str, str]] = WeakKeyDictionary()  # widget -> (topic, where)

    def bind(self, controller: InfoController) -> None:
        self.controller = controller

    def set_on(self, on: bool) -> None:
        self.on = on
        self.changed.emit(on)

    # --- asking questions ---

    def is_known(self, topic_id: str | None) -> bool:
        return topic_id is not None and self.library.get(topic_id) is not None

    def title_of(self, topic_id: str) -> str:
        topic = self.library.get(topic_id)
        return topic.title if topic else topic_id

    def link(self, line: Line) -> Line:
        """The line with its known terms tagged (only while Info mode is on)."""
        return link_line(line, self.library) if self.on else line

    def open(self, topic_id: str) -> None:
        if self.controller:
            self.controller.open(topic_id)

    def request(self, text: str, where: str) -> None:
        if self.controller:
            self.controller.request(text, where)

    def hint(self, topic_id: str) -> str:
        return f'Double-click to learn about {self.title_of(topic_id)}'

    # --- plain widgets with one term (a label, a button) ---

    def mark(self, widget: QWidget, topic_id: str, where: str) -> None:
        """Make a widget explain `topic_id` when double-clicked, and underline it while Info mode is on."""
        self._marked[widget] = (topic_id, where)
        widget.installEventFilter(self)
        self.changed.connect(lambda _on, w=widget: self._restyle(w))
        self._restyle(widget)

    def _restyle(self, widget: QWidget) -> None:
        topic_id, _ = self._marked[widget]
        underline = self.on and self.is_known(topic_id)
        font = widget.font()
        font.setUnderline(underline)
        widget.setFont(font)
        widget.setToolTip(self.hint(topic_id) if underline else '')

    def eventFilter(self, obj, event) -> bool:
        marked = self._marked.get(obj) if isinstance(obj, QWidget) else None
        if marked is None or not self.on:
            return False
        topic_id, where = marked
        if event.type() == QEvent.Type.MouseButtonDblClick and self.is_known(topic_id):
            self.open(topic_id)
            return True
        if event.type() == QEvent.Type.ContextMenu:
            menu = QMenu(obj)
            self.add_actions(menu, topic_id, _text_of(obj), where)
            menu.exec(event.globalPos())
            return True
        return False

    # --- the right-click entries (shared by every kind of widget) ---

    def add_actions(self, menu: QMenu, topic_id: str | None, text: str, where: str) -> None:
        """'What is X?' (if there is a topic) and 'Request info on X...' (always) on a menu."""
        if self.is_known(topic_id):
            menu.addAction(f'What is “{self.title_of(topic_id)}”?', lambda: self.open(topic_id))
        shown = text if len(text) <= 40 else text[:37] + '…'
        menu.addAction(f'Request info on “{shown}”…', lambda: self.request(text, where))


def _text_of(widget: QWidget) -> str:
    for name in ('text', 'title'):
        getter = getattr(widget, name, None)
        if callable(getter):
            return str(getter())
    return ''

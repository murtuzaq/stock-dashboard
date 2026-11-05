"""A label for generated text (legends, summaries). While Info mode is on, known terms in it are links."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMenu

from core.common.formatting import Line
from qtrender.learn import info_mode
from qtrender.richtext import LINK_PREFIX, line_html, plain_text


class InfoLabel(QLabel):
    def __init__(self, where: str) -> None:
        super().__init__()
        self.where = where  # what this text is, saved with a request ("legend", "summary card"...)
        self.mode = info_mode.current()
        self._line: Line = []
        self._hovered = ''
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                     Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self.linkHovered.connect(self._on_hover)
        if self.mode:
            self.mode.changed.connect(self._on_mode)  # a bound slot: Qt drops it when this label is destroyed

    def _on_mode(self, _on: bool) -> None:
        self._render()

    def set_line(self, line: Line) -> None:
        self._line = line
        self._render()

    def _render(self) -> None:
        on = bool(self.mode and self.mode.on)
        self.setText(line_html(self.mode.link(self._line) if on else self._line, links=on))

    def _on_hover(self, href: str) -> None:
        self._hovered = href
        self.setToolTip(self.mode.hint(href.removeprefix(LINK_PREFIX)) if href.startswith(LINK_PREFIX) and self.mode
                        else '')

    def _hovered_topic(self) -> str | None:
        return self._hovered.removeprefix(LINK_PREFIX) if self._hovered.startswith(LINK_PREFIX) else None

    def mouseDoubleClickEvent(self, event) -> None:
        topic_id = self._hovered_topic()
        if self.mode and self.mode.on and topic_id:
            self.mode.open(topic_id)
            return
        super().mouseDoubleClickEvent(event)

    def _show_menu(self, position) -> None:
        if not (self.mode and self.mode.on):
            return
        menu = QMenu(self)
        text = self.selectedText().strip() or plain_text(self._line).strip()
        self.mode.add_actions(menu, self._hovered_topic(), text, self.where)
        menu.exec(self.mapToGlobal(position))

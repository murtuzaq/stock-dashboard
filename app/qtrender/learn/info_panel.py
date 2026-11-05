"""The Info panel: shows one topic (Markdown, with images), Back / Forward, related topics and a Request button."""
from html import escape

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QToolButton,
                               QVBoxLayout, QWidget)

from core.learn.controller import TopicPage
from learn.library import ASSETS

MINIMUM_WIDTH = 360


class InfoPanel(QWidget):
    back_requested = Signal()
    forward_requested = Signal()
    topic_requested = Signal(str)  # a link to another topic was clicked
    request_requested = Signal(str)  # the Request button (the text is what was not found, or empty)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName('infoPanel')
        self._missing_text = ''
        layout = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.back_button = QToolButton()
        self.back_button.setText('◀')
        self.back_button.setToolTip('Back')
        self.back_button.clicked.connect(self.back_requested)
        self.forward_button = QToolButton()
        self.forward_button.setText('▶')
        self.forward_button.setToolTip('Forward')
        self.forward_button.clicked.connect(self.forward_requested)
        self.category = QLabel()
        self.category.setObjectName('barLabel')
        bar.addWidget(self.back_button)
        bar.addWidget(self.forward_button)
        bar.addWidget(self.category, stretch=1)
        layout.addLayout(bar)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setSearchPaths([str(ASSETS)])  # where a topic's images live
        self.browser.document().setDefaultStyleSheet('a { color: #5b8def; } h1 { font-size: 20px; } '
                                                     'h2 { font-size: 15px; } code { color: #f7c948; }')
        self.browser.anchorClicked.connect(self._clicked)
        layout.addWidget(self.browser, stretch=1)

        self.request_button = QPushButton('Request a topic…')
        self.request_button.setToolTip('Tell the developer about a term you would like explained')
        self.request_button.clicked.connect(lambda: self.request_requested.emit(self._missing_text))
        layout.addWidget(self.request_button)
        self.set_navigation(False, False)

    # --- InfoView: what the controller asks for ---

    def show_topic(self, page: TopicPage) -> None:
        self._missing_text = ''
        self.category.setText(page.category.upper())
        related = ''
        if page.related:
            related = '\n\n---\n\n**Related topics:** ' + ' · '.join(f'[{title}](topic:{topic_id})'
                                                                     for topic_id, title in page.related)
        self.browser.setMarkdown(f'# {page.title}\n\n{page.body}{related}')
        self.browser.verticalScrollBar().setValue(0)

    def show_not_found(self, text: str) -> None:
        self._missing_text = text
        self.category.setText('NOT EXPLAINED YET')
        shown = escape(text.replace('`', "'"))
        self.browser.setMarkdown(f'# No explanation yet\n\nThere is no topic for `{shown}` yet.\n\n'
                                 'Press **Request a topic…** below and it will be added to the list of terms to '
                                 'explain.')

    def set_navigation(self, can_back: bool, can_forward: bool) -> None:
        self.back_button.setEnabled(can_back)
        self.forward_button.setEnabled(can_forward)

    # --- links inside a topic ---

    def _clicked(self, url: QUrl) -> None:
        if url.scheme() == 'topic':
            self.topic_requested.emit(url.path())
        elif url.scheme() in ('http', 'https'):
            QDesktopServices.openUrl(url)


class InfoDock(QDockWidget):
    """The dock the panel lives in (below the strategy builder dock when both are showing)."""

    def __init__(self, panel: InfoPanel) -> None:
        super().__init__('Info')
        self.setObjectName('infoDock')
        self.panel = panel
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable |
                         QDockWidget.DockWidgetFeature.DockWidgetMovable |
                         QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        panel.setMinimumWidth(MINIMUM_WIDTH)
        self.setWidget(panel)
        self.hide()

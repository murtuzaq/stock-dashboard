"""Tools > Strategies (renderer): every strategy (library templates first, then each stock's), the selected
one's rules, and buttons for what can be done with it.

core.library.strategies.StrategyLibraryController decides what applies and what a click means
(StrategyLibraryView is what it needs from here).
"""
from collections.abc import Callable
from html import escape

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from core.common.theme import MUTED
from core.library.strategies import NEW_TEMPLATE, StrategyItem
from core.strategies.service import MenuEntry
from qtrender.layouts import clear_layout
from qtrender.library.stock_library_panel import fill_menu

ID_ROLE = Qt.ItemDataRole.UserRole
LIBRARY_COLOR = '#9598a1'


def _paragraph(heading: str, text: str) -> str:
    if not text:
        return ''
    body = escape(text).replace('\n', '<br>')
    return f'<p style="margin:8px 0 0 0"><b>{heading}</b><br>{body}</p>'


def detail_html(item: StrategyItem) -> str:
    """The selected strategy: what it is, why it can work, what to watch out for, its rules, and its references."""
    where = 'Library template (works on any stock)' if item.is_library else f'Belongs to {item.symbol}'
    about = item.about
    parts = [f'<b style="font-size:14px">{escape(item.name)}</b> <span style="color:{MUTED}">· {escape(where)}</span>']
    if about.style:
        parts.append(f'<br><span style="color:{MUTED}">{escape(about.style)}</span>')
    if about.summary:
        parts.append(f'<p style="margin:8px 0 0 0">{escape(about.summary)}</p>')
    parts += [_paragraph('Why it can work', about.why), _paragraph('Watch out for', about.caveats),
              _paragraph('Rules', item.description)]
    if about.references:
        listed = ''.join(f'<li>{escape(reference)}</li>' for reference in about.references)
        parts.append(f'<p style="margin:8px 0 0 0"><b>References</b></p><ul style="margin-top:2px">{listed}</ul>')
    return ''.join(parts)


class StrategyLibraryPanel(QWidget):
    strategy_selected = Signal(object)  # strategy id, or None
    action_chosen = Signal(str, object)  # action, strategy id (None: the selected one)
    done_requested = Signal()
    closed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName('wizard')
        self.menu_source: Callable[[str], list[MenuEntry | None]] = lambda strategy_id: []
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setObjectName('chartTitle')
        layout.addWidget(self.title)
        hint = QLabel('Library templates work on any stock. Each stock\'s own strategies are listed under it. '
                      'Pick one to see its rules and what you can do with it, or create a new template.')
        hint.setObjectName('summary')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.new_button = QPushButton('+ New template…')
        self.new_button.clicked.connect(lambda: self.action_chosen.emit(NEW_TEMPLATE, None))
        layout.addWidget(self.new_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel('Strategies')
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_menu)
        layout.addWidget(self.tree, stretch=2)

        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)  # references can be copied
        scroll = QScrollArea()  # the description, reasoning and references can be long
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.detail)
        layout.addWidget(scroll, stretch=3)
        self.buttons = QHBoxLayout()
        layout.addLayout(self.buttons)
        self.notice = QLabel()
        self.notice.setObjectName('summary')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        self.done_button = QPushButton('Done')
        self.done_button.clicked.connect(self.done_requested)
        layout.addWidget(self.done_button)
        self.items: dict[str, QTreeWidgetItem] = {}

    def _selection_changed(self) -> None:
        selected = self.tree.selectedItems()
        self.strategy_selected.emit(selected[0].data(0, ID_ROLE) if selected else None)

    def _show_menu(self, position: QPoint) -> None:
        item = self.tree.itemAt(position)
        strategy_id = item.data(0, ID_ROLE) if item else None
        menu = QMenu(self)
        entries = self.menu_source(strategy_id) if strategy_id else [MenuEntry('New template…', NEW_TEMPLATE)]
        fill_menu(menu, entries, lambda entry: self.action_chosen.emit(entry.action, strategy_id))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    # --- StrategyLibraryView: what the controller asks for ---

    def show_title(self, text: str) -> None:
        self.title.setText(text)

    def show_strategies(self, groups: list[tuple[str, list[StrategyItem]]]) -> None:
        selected = self.tree.selectedItems()
        keep = selected[0].data(0, ID_ROLE) if selected else None
        self.tree.blockSignals(True)  # rebuilding the list is not the user picking something
        self.tree.clear()
        self.items = {}
        for heading, items in groups:
            group = QTreeWidgetItem(self.tree, [f'{heading}  ({len(items)})'])
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = QFont(group.font(0))
            font.setBold(True)
            group.setFont(0, font)
            for item in items:
                row = QTreeWidgetItem(group, [item.name])
                row.setData(0, ID_ROLE, item.id)
                row.setToolTip(0, '\n\n'.join(part for part in (item.about.summary, item.description) if part))
                if item.is_library:
                    row.setForeground(0, QColor(LIBRARY_COLOR))
                self.items[item.id] = row
            group.setExpanded(True)
        if keep in self.items:
            self.items[keep].setSelected(True)
        self.tree.blockSignals(False)

    def show_detail(self, item: StrategyItem | None, actions: list[MenuEntry]) -> None:
        clear_layout(self.buttons)
        if item is None:
            self.detail.setText('<span style="color:#787b86">Choose a strategy to see its rules.</span>')
            return
        self.detail.setText(detail_html(item))
        for entry in actions:
            button = QPushButton(entry.text)
            button.clicked.connect(lambda checked=False, e=entry: self.action_chosen.emit(e.action, item.id))
            self.buttons.addWidget(button)
        self.buttons.addStretch()

    def show_notice(self, text: str) -> None:
        self.notice.setText(text)

    def close(self) -> None:
        self.closed.emit()

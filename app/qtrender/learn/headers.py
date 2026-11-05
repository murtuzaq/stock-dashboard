"""Table column titles that explain themselves: underlined while Info mode is on, double-click opens the topic."""
from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QHeaderView, QMenu, QTableWidget

from core.learn import ui_terms
from qtrender.learn import info_mode
from qtrender.richtext import LINK_COLOR


def topic_of_column(title: str) -> str | None:
    return ui_terms.COLUMNS.get(title)


def install_header_events(header: QHeaderView, title_at: Callable[[int], str], where: str) -> None:
    """Double-click a column title to learn about it; right-click for 'What is...' and 'Request info...'."""
    mode = info_mode.current()
    if mode is None:
        return

    def double_clicked(section: int) -> None:
        topic = topic_of_column(title_at(section))
        if mode.on and mode.is_known(topic):
            mode.open(topic)

    def context_menu(position: QPoint) -> None:
        if not mode.on:
            return
        title = title_at(header.logicalIndexAt(position))
        menu = QMenu(header)
        mode.add_actions(menu, topic_of_column(title), title, where)
        menu.exec(header.mapToGlobal(position))

    header.sectionDoubleClicked.connect(double_clicked)
    header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    header.customContextMenuRequested.connect(context_menu)


def mark_table_headers(table: QTableWidget, where: str) -> None:
    """For a QTableWidget whose header items already exist."""
    mode = info_mode.current()
    if mode is None:
        return

    def restyle(_on: bool = False) -> None:
        for column in range(table.columnCount()):
            item = table.horizontalHeaderItem(column)
            if item is None:
                continue
            underline = mode.on and mode.is_known(topic_of_column(item.text()))
            font = item.font()
            font.setUnderline(underline)
            item.setFont(font)
            item.setForeground(QBrush(QColor(LINK_COLOR)) if underline else QBrush())

    mode.changed.connect(restyle)
    restyle()
    install_header_events(table.horizontalHeader(), lambda column: _title(table, column), where)


def _title(table: QTableWidget, column: int) -> str:
    item = table.horizontalHeaderItem(column)
    return item.text() if item else ''

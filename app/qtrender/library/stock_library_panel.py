"""Tools > Stocks (renderer): every stock stored locally, a search box to add more, right-click to use one, and a
second tab to download or update many stocks at once.

core.library.stocks.StockLibraryController decides what everything means (StockLibraryView is what it needs here);
the second tab is qtrender.downloads.DownloadPanel, driven by core.downloads.DownloadController.
"""
from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QHideEvent
from PySide6.QtWidgets import (QHeaderView, QLabel, QMenu, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from core.common.background import BackgroundLoader
from core.library.stocks import COLUMNS, StockRow
from core.strategies.service import MenuEntry
from qtrender.downloads.download_panel import DownloadPanel
from qtrender.searchbar.bar import SearchBar

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
SYMBOL_ROLE = Qt.ItemDataRole.UserRole


def fill_menu(menu: QMenu, entries: list[MenuEntry | None], chosen: Callable[[MenuEntry], None]) -> None:
    """Build a (possibly nested) QMenu from core menu entries; `chosen` is called with the picked entry."""
    for entry in entries:
        if entry is None:
            menu.addSeparator()
        elif entry.children:
            fill_menu(menu.addMenu(entry.text), list(entry.children), chosen)
        else:
            menu.addAction(entry.text, lambda e=entry: chosen(e))


class StockLibraryPanel(QWidget):
    symbol_added = Signal(str)  # picked in the search box: add it to the library
    action_chosen = Signal(str, str, object)  # menu action, symbol, the entry's argument
    done_requested = Signal()
    closed = Signal()
    hidden = Signal()  # the whole page went away (dock closed, another page opened): stop any download

    def __init__(self, loader: BackgroundLoader) -> None:
        super().__init__()
        self.setObjectName('wizard')  # same look as the other side-panel pages
        self.menu_source: Callable[[str], list[MenuEntry | None]] = lambda symbol: []
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setObjectName('chartTitle')
        layout.addWidget(self.title)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, stretch=1)
        self.stocks_page = QWidget()
        self.download_panel = DownloadPanel(loader)  # download or update many stocks at once
        self.tabs.addTab(self.stocks_page, 'Stocks in the database')
        self.tabs.addTab(self.download_panel, 'Download / update')
        stocks = QVBoxLayout(self.stocks_page)
        stocks.setContentsMargins(0, 8, 0, 0)
        hint = QLabel('Every stock whose prices are stored on this computer. Searching a stock anywhere in the app '
                      'adds it; you can also add one here, or use the Download / update tab to fetch many at once. '
                      'Right-click a stock to open it or add it to a portfolio; double-click to open it.')
        hint.setObjectName('summary')
        hint.setWordWrap(True)
        stocks.addWidget(hint)

        self.search = SearchBar(loader)
        self.search.symbol_chosen.connect(self.symbol_added)
        stocks.addWidget(self.search)
        self.notice = QLabel()
        self.notice.setObjectName('summary')
        self.notice.setWordWrap(True)
        stocks.addWidget(self.notice)

        self.count = QLabel()
        self.count.setObjectName('barLabel')
        stocks.addWidget(self.count)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName('historyTable')
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)  # click a column title to sort by it
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)  # Qt would start descending (Z to A)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_menu)
        self.table.cellDoubleClicked.connect(lambda row, column: self._open(row))
        stocks.addWidget(self.table, stretch=1)

        self.done_button = QPushButton('Done')
        self.done_button.setDefault(True)
        self.done_button.clicked.connect(self.done_requested)
        layout.addWidget(self.done_button)

    def hideEvent(self, event: QHideEvent) -> None:
        """The page itself was hidden (not just a tab switched): that ends any download."""
        self.hidden.emit()
        super().hideEvent(event)

    def symbol_at(self, row: int) -> str | None:
        item = self.table.item(row, 0)
        return item.data(SYMBOL_ROLE) if item else None

    def _open(self, row: int) -> None:
        symbol = self.symbol_at(row)
        if symbol:
            self.action_chosen.emit('library_open', symbol, None)

    def _show_menu(self, position: QPoint) -> None:
        symbol = self.symbol_at(self.table.rowAt(position.y()))
        if symbol is None:
            return
        menu = QMenu(self)
        fill_menu(menu, self.menu_source(symbol), lambda entry: self.action_chosen.emit(entry.action, symbol,
                                                                                        entry.argument))
        menu.exec(self.table.viewport().mapToGlobal(position))

    # --- StockLibraryView: what the controller asks for ---

    def show_title(self, text: str) -> None:
        self.title.setText(text)

    def show_stocks(self, rows: list[StockRow]) -> None:
        self.table.setSortingEnabled(False)  # filling a sorted table moves rows under the loop
        self.table.setRowCount(len(rows))
        for row, stock in enumerate(rows):
            for column, cell in enumerate(stock.cells):
                item = QTableWidgetItem(cell.text)
                item.setData(SYMBOL_ROLE, stock.symbol)
                if cell.color:
                    item.setForeground(QColor(cell.color))
                if cell.tooltip:
                    item.setToolTip(cell.tooltip)
                if cell.align_right:
                    item.setTextAlignment(RIGHT)
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)
        noun = 'stock' if len(rows) == 1 else 'stocks'
        self.count.setText(f'{len(rows)} {noun} in the library')

    def show_notice(self, text: str) -> None:
        self.notice.setText(text)

    def close(self) -> None:
        self.closed.emit()

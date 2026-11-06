"""Tools > Stocks > "Download / update" tab (renderer): a list of stocks coloured by state, and Start / Stop.

core.downloads.controller.DownloadController decides everything (DownloadView is what it needs here). The Stock
Library page that contains this tab asks the controller to stop when the whole page is hidden.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QProgressBar,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.common.background import BackgroundLoader
from core.downloads.model import STATUS_COLORS, DownloadRow
from qtrender.searchbar.bar import SearchBar

COLUMNS = ['Symbol', 'Name', 'Status', 'Detail']
SYMBOL_ROLE = Qt.ItemDataRole.UserRole
HINT = ('Downloads stock prices into the local database, one stock at a time with a pause of 15-25 seconds between '
        'them, so Yahoo is never hit hard (the S&P 500 takes about 3 hours). It only runs while the Stock Library is open: '
        'closing it stops the download, and Start continues where it left off.  Green = up to date, yellow = out of '
        'date, red = failed, grey = Yahoo has no data.')


class DownloadPanel(QWidget):
    universe_chosen = Signal(str)
    only_pending_toggled = Signal(bool)
    symbol_picked = Signal(str)
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, loader: BackgroundLoader) -> None:
        super().__init__()
        self.row_of: dict[str, int] = {}
        layout = QVBoxLayout(self)
        hint = QLabel(HINT)
        hint.setObjectName('summary')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        chooser = QHBoxLayout()
        label = QLabel('Stocks')
        label.setObjectName('barLabel')
        chooser.addWidget(label)
        self.universe = QComboBox()
        self.universe.activated.connect(lambda index: self.universe_chosen.emit(self.universe.itemText(index)))
        chooser.addWidget(self.universe, stretch=1)
        layout.addLayout(chooser)

        self.search = SearchBar(loader)  # pick individual stocks to download
        self.search.symbol_chosen.connect(self.symbol_picked)
        layout.addWidget(self.search)

        self.only_pending = QCheckBox('Only show stocks not yet downloaded or out of date')
        self.only_pending.toggled.connect(self.only_pending_toggled)
        layout.addWidget(self.only_pending)
        self.totals = QLabel()
        self.totals.setObjectName('barLabel')
        layout.addWidget(self.totals)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName('historyTable')
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, stretch=1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.progress_text = QLabel()
        self.progress_text.setObjectName('barLabel')
        layout.addWidget(self.progress_text)
        self.notice = QLabel()
        self.notice.setObjectName('summary')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        buttons = QHBoxLayout()
        self.start_button = QPushButton('Start')
        self.start_button.clicked.connect(self.start_requested)
        buttons.addWidget(self.start_button)
        self.stop_button = QPushButton('Stop')
        self.stop_button.clicked.connect(self.stop_requested)
        self.stop_button.setEnabled(False)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        layout.addLayout(buttons)

    # --- DownloadView: what the controller asks for ---

    def show_universes(self, names: list[str], current: str) -> None:
        self.universe.blockSignals(True)
        self.universe.clear()
        self.universe.addItems(names)
        self.universe.setCurrentText(current)
        self.universe.blockSignals(False)

    def show_rows(self, rows: list[DownloadRow]) -> None:
        self.table.setUpdatesEnabled(False)
        scroll = self.table.verticalScrollBar().value()
        self.table.setRowCount(len(rows))
        self.row_of = {}
        for position, row in enumerate(rows):
            self.row_of[row.symbol] = position
            self._fill(position, row)
        self.table.verticalScrollBar().setValue(scroll)
        self.table.setUpdatesEnabled(True)

    def update_row(self, row: DownloadRow) -> None:
        position = self.row_of.get(row.symbol)
        if position is not None:
            self._fill(position, row)

    def _fill(self, position: int, row: DownloadRow) -> None:
        color = STATUS_COLORS[row.status]
        for column, text in enumerate((row.symbol, row.name, row.status.value, row.reason)):
            item = QTableWidgetItem(text)
            item.setData(SYMBOL_ROLE, row.symbol)
            if color:
                item.setForeground(QColor(color))
            if row.reason:
                item.setToolTip(row.reason)
            self.table.setItem(position, column, item)

    def show_totals(self, text: str) -> None:
        self.totals.setText(text)

    def show_progress(self, done: int, total: int, text: str) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        self.progress_text.setText(text)

    def show_notice(self, text: str) -> None:
        self.notice.setText(text)

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.universe.setEnabled(not running)
        self.search.setEnabled(not running)

    def alert(self) -> None:
        QApplication.alert(self.window())

"""Tools > Strategies > Compare on all stocks (renderer): one strategy's result on every stored stock, sortable.

core.library.compare.CompareController decides everything (CompareView is what it needs here). The run only lasts
while this page is showing: hiding it (Back, closing the dock, another page) asks the controller to stop.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QHideEvent
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core.library.compare import COLUMNS, RETURN_COLUMN, CompareRow
from qtrender.numeric_item import SORT_ROLE, NumberItem

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
SYMBOL_ROLE = Qt.ItemDataRole.UserRole
NOTE = ('Each stock is tested with $10,000, using the candle size and range selected at the top and under the chart '
        'when you pressed the button, and only the prices already stored (see Tools > Stocks > Download / update). '
        'Click a column title to sort; double-click a row to open that stock.')


class ComparePanel(QWidget):
    back_requested = Signal()
    rerun_requested = Signal()
    stop_requested = Signal()
    row_opened = Signal(str)  # symbol

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName('wizard')  # same look as the other side-panel pages
        layout = QVBoxLayout(self)
        self.title = QLabel('Strategy vs All Stocks')
        self.title.setObjectName('chartTitle')
        layout.addWidget(self.title)
        self.header = QLabel()
        self.header.setWordWrap(True)
        layout.addWidget(self.header)
        note = QLabel(NOTE)
        note.setObjectName('summary')
        note.setWordWrap(True)
        layout.addWidget(note)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.progress_text = QLabel()
        self.progress_text.setObjectName('barLabel')
        layout.addWidget(self.progress_text)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName('historyTable')
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)  # click a column title to sort by it
        self.table.cellDoubleClicked.connect(lambda row, column: self._open(row))
        layout.addWidget(self.table, stretch=1)

        self.notice = QLabel()
        self.notice.setObjectName('summary')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        buttons = QHBoxLayout()
        self.back_button = QPushButton('Back to strategies')
        self.back_button.clicked.connect(self.back_requested)
        buttons.addWidget(self.back_button)
        self.rerun_button = QPushButton('Re-run')
        self.rerun_button.setToolTip('Run it again with the candle size and range selected now')
        self.rerun_button.clicked.connect(self.rerun_requested)
        buttons.addWidget(self.rerun_button)
        self.stop_button = QPushButton('Stop')
        self.stop_button.clicked.connect(self.stop_requested)
        self.stop_button.setEnabled(False)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        layout.addLayout(buttons)

    def hideEvent(self, event: QHideEvent) -> None:
        """Going back, closing the dock or opening another page ends a run in progress."""
        self.stop_requested.emit()
        super().hideEvent(event)

    def _open(self, row: int) -> None:
        item = self.table.item(row, 0)
        if item:
            self.row_opened.emit(item.data(SYMBOL_ROLE))

    # --- CompareView: what the controller asks for ---

    def show_header(self, text: str) -> None:
        self.header.setText(text)

    def show_rows(self, rows: list[CompareRow], summary: str) -> None:
        self.table.setSortingEnabled(False)  # filling a sorted table moves rows under the loop
        self.table.setRowCount(len(rows))
        for position, row in enumerate(rows):
            for column, cell in enumerate(row.cells):
                item = NumberItem(cell.text) if cell.sort_value is not None else QTableWidgetItem(cell.text)
                if cell.sort_value is not None:
                    item.setData(SORT_ROLE, cell.sort_value)
                item.setData(SYMBOL_ROLE, row.symbol)
                if cell.color:
                    item.setForeground(QColor(cell.color))
                if cell.tooltip:
                    item.setToolTip(cell.tooltip)
                if cell.align_right:
                    item.setTextAlignment(RIGHT)
                self.table.setItem(position, column, item)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(RETURN_COLUMN, Qt.SortOrder.DescendingOrder)  # best performer first
        self.summary.setText(summary)

    def show_progress(self, done: int, total: int, text: str) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        self.progress_text.setText(text)

    def show_notice(self, text: str) -> None:
        self.notice.setText(text)

    def set_running(self, running: bool) -> None:
        self.rerun_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.back_button.setEnabled(True)

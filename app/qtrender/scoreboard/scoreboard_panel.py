"""Tools > Strategy Scoreboard (renderer): the strategies against each other, the best strategy per stock and the
out-of-sample check, in three sortable tables.

core.scoreboard.controller.ScoreboardController decides everything (ScoreboardView is what it needs here). The run only
lasts while this page is showing: hiding it (Done, closing the dock, another page) asks the controller to stop. The
content sits in a scroll area so that a short window never has to grow to fit it.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QHideEvent
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton, QScrollArea,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.scoreboard.model import (BEST_COLUMNS, BEST_SORT, BOARD_COLUMNS, BOARD_SORT, OUT_COLUMNS, OUT_SORT, Row,
                                   ScoreboardResult)
from qtrender.numeric_item import SORT_ROLE, NumberItem

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
KEY_ROLE = Qt.ItemDataRole.UserRole  # the row's strategy id or symbol
GROUP_ROLE = Qt.ItemDataRole.UserRole + 2  # the strategy a stock's row is about (+1 is numeric_item.SORT_ROLE)
INTRO = ('Every saved strategy on every stored stock, with $10,000 each, using the candle size and range selected at the '
         'top and under the chart when you pressed Run, and only the prices already stored. Click a column title to '
         'sort. Click a strategy to show only the stocks where it was best; double-click a stock to open it.')


def _label(text: str = '', object_name: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    if object_name:
        label.setObjectName(object_name)
    return label


def _table(columns: list[str], minimum_height: int, stretch_column: int | None = None) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setObjectName('historyTable')
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().hide()
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if stretch_column is not None:
        header.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    table.setMinimumHeight(minimum_height)
    return table


def _fill(table: QTableWidget, rows: list[Row], sort_column: int) -> None:
    table.setSortingEnabled(False)  # filling a sorted table moves rows under the loop
    table.setRowCount(len(rows))
    for position, row in enumerate(rows):
        for column, cell in enumerate(row.cells):
            item = NumberItem(cell.text) if cell.sort_value is not None else QTableWidgetItem(cell.text)
            if cell.sort_value is not None:
                item.setData(SORT_ROLE, cell.sort_value)
            item.setData(KEY_ROLE, row.key)
            item.setData(GROUP_ROLE, row.group)
            if cell.color:
                item.setForeground(QColor(cell.color))
            if cell.tooltip:
                item.setToolTip(cell.tooltip)
            if cell.align_right:
                item.setTextAlignment(RIGHT)
            table.setItem(position, column, item)
    table.setSortingEnabled(True)
    table.sortByColumn(sort_column, Qt.SortOrder.DescendingOrder)


class ScoreboardPanel(QWidget):
    run_requested = Signal()
    stop_requested = Signal()
    done_requested = Signal()
    row_opened = Signal(str)  # symbol

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName('wizard')  # same look as the other side-panel pages
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName('wizard')
        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 4, 0)

        title = QLabel('Strategy Scoreboard')
        title.setObjectName('chartTitle')
        layout.addWidget(title)
        self.header = _label()
        layout.addWidget(self.header)
        layout.addWidget(_label(INTRO, 'summary'))

        buttons = QHBoxLayout()
        self.run_button = QPushButton('Run')
        self.run_button.setDefault(True)
        self.run_button.setToolTip('Test every strategy on every stored stock with the candle size and range selected now')
        self.run_button.clicked.connect(self.run_requested)
        buttons.addWidget(self.run_button)
        self.stop_button = QPushButton('Stop')
        self.stop_button.clicked.connect(self.stop_requested)
        self.stop_button.setEnabled(False)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.progress_text = _label('', 'barLabel')
        layout.addWidget(self.progress_text)
        self.notice = _label('', 'summary')
        layout.addWidget(self.notice)

        self.summary = _label()
        layout.addWidget(self.summary)
        layout.addWidget(_label('Strategies', 'chartTitle'))
        self.board_table = _table(BOARD_COLUMNS, 200, 0)
        self.board_table.itemSelectionChanged.connect(self._filter_stocks)
        layout.addWidget(self.board_table)

        header = QHBoxLayout()
        header.addWidget(_label('Best strategy per stock', 'chartTitle'), stretch=1)
        self.show_all = QPushButton('Show all stocks')
        self.show_all.setToolTip('Remove the filter set by clicking a strategy')
        self.show_all.setEnabled(False)
        self.show_all.clicked.connect(self._clear_filter)
        header.addWidget(self.show_all)
        layout.addLayout(header)
        self.best_table = _table(BEST_COLUMNS, 260, 1)
        self.best_table.cellDoubleClicked.connect(lambda row, column: self._open(self.best_table, row))
        layout.addWidget(self.best_table)

        layout.addWidget(_label('Out-of-sample check', 'chartTitle'))
        self.out_summary = _label()
        layout.addWidget(self.out_summary)
        self.out_table = _table(OUT_COLUMNS, 220, 1)
        self.out_table.cellDoubleClicked.connect(lambda row, column: self._open(self.out_table, row))
        layout.addWidget(self.out_table)

        self.done_button = QPushButton('Done')
        self.done_button.clicked.connect(self.done_requested)
        outer.addWidget(self.done_button)

    def hideEvent(self, event: QHideEvent) -> None:
        """Closing the dock or opening another page ends a run in progress."""
        self.stop_requested.emit()
        super().hideEvent(event)

    # --- filtering the stock tables by the strategy clicked ---

    def _filter_stocks(self) -> None:
        selected = self.board_table.selectedItems()
        strategy_id = selected[0].data(KEY_ROLE) if selected else ''
        self.show_all.setEnabled(bool(strategy_id))
        for table in (self.best_table, self.out_table):
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                table.setRowHidden(row, bool(strategy_id) and item.data(GROUP_ROLE) != strategy_id)

    def _clear_filter(self) -> None:
        self.board_table.clearSelection()

    def _open(self, table: QTableWidget, row: int) -> None:
        item = table.item(row, 0)
        if item:
            self.row_opened.emit(item.data(KEY_ROLE))

    # --- ScoreboardView: what the controller asks for ---

    def show_header(self, text: str) -> None:
        self.header.setText(text)

    def show_result(self, result: ScoreboardResult | None) -> None:
        self.board_table.clearSelection()
        rows = result or ScoreboardResult([], [], [], '', '')
        _fill(self.board_table, rows.board, BOARD_SORT)
        _fill(self.best_table, rows.best, BEST_SORT)
        _fill(self.out_table, rows.out_of_sample, OUT_SORT)
        self.summary.setText(rows.summary)
        self.out_summary.setText(rows.out_summary)

    def show_progress(self, done: int, total: int, text: str) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        self.progress_text.setText(text)

    def show_notice(self, text: str) -> None:
        self.notice.setText(text)

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

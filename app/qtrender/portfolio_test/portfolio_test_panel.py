"""Tools > Portfolio Test (renderer): the form, the chart of the rotation against its baselines, and two tables.

core.portfolio_test.controller.PortfolioTestController decides everything (PortfolioTestView is what it needs
here). The page's content sits in a scroll area so that a short window never has to grow to fit it.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.common.formatting import Cell
from core.common.theme import MUTED, WARNING
from core.portfolio_test.model import LINE_COLUMNS, YEAR_COLUMNS, PortfolioResult
from qtrender.dashboard.panels.backtest_view import BacktestView

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
INTRO = ('Every January the money moves into last calendar year\'s biggest winners, and is compared with simply buying '
         'and holding the same stocks. $10,000 to start. Uses only the prices stored in the database.')
CHART_HINT = 'Press Run to see how the rotation compares with its baselines.'


def _fill(table: QTableWidget, rows: list[list[Cell]]) -> None:
    table.setRowCount(len(rows))
    for position, row in enumerate(rows):
        for column, cell in enumerate(row):
            item = QTableWidgetItem(cell.text)
            if cell.color:
                item.setForeground(QColor(cell.color))
            if cell.tooltip:
                item.setToolTip(cell.tooltip)
            if cell.align_right:
                item.setTextAlignment(RIGHT)
            table.setItem(position, column, item)


def _table(columns: list[str], minimum_height: int) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setObjectName('historyTable')
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().hide()
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setStretchLastSection(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    table.setMinimumHeight(minimum_height)
    return table


def _label(text: str = '', object_name: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    if object_name:
        label.setObjectName(object_name)
    return label


class PortfolioTestPanel(QWidget):
    universe_chosen = Signal(str)
    run_requested = Signal(int, int)  # how many winners to hold, the first year
    done_requested = Signal()

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

        title = QLabel('Portfolio Test')
        title.setObjectName('chartTitle')
        layout.addWidget(title)
        layout.addWidget(_label(INTRO, 'summary'))

        form = QHBoxLayout()
        self.universe = QComboBox()
        self.universe.setToolTip('The stocks to choose the winners from (and to buy and hold for comparison)')
        self.universe.activated.connect(lambda index: self.universe_chosen.emit(self.universe.itemText(index)))
        form.addWidget(self.universe, stretch=1)
        form.addWidget(_label('Hold the top', 'barLabel'))
        self.count = QSpinBox()
        self.count.setRange(1, 500)
        self.count.setToolTip('How many of last year\'s winners to hold, with equal money in each')
        form.addWidget(self.count)
        form.addWidget(_label('from', 'barLabel'))
        self.first_year = QSpinBox()
        self.first_year.setRange(1950, 2100)
        self.first_year.setToolTip('The first January to invest (it needs a full year of prices before it)')
        form.addWidget(self.first_year)
        self.run_button = QPushButton('Run')
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(lambda: self.run_requested.emit(self.count.value(), self.first_year.value()))
        form.addWidget(self.run_button)
        layout.addLayout(form)

        self.warning = _label()
        self.warning.setStyleSheet(f'color: {WARNING};')
        layout.addWidget(self.warning)
        self.notice = _label('', 'summary')
        layout.addWidget(self.notice)

        self.chart = BacktestView(CHART_HINT, 'Account value of the rotation and its baselines. Hover over a line '
                                              'for its figures.')
        self.chart.setMinimumHeight(260)
        layout.addWidget(self.chart)
        self.lines_table = _table(LINE_COLUMNS, 120)
        layout.addWidget(self.lines_table)
        self.summary = _label()
        layout.addWidget(self.summary)
        self.years_table = _table(YEAR_COLUMNS, 220)
        self.years_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.years_table)
        self.next_picks = _label('', 'summary')
        layout.addWidget(self.next_picks)

        self.done_button = QPushButton('Done')
        self.done_button.clicked.connect(self.done_requested)
        outer.addWidget(self.done_button)

    # --- PortfolioTestView: what the controller asks for ---

    def show_universes(self, names: list[str], current: str) -> None:
        self.universe.blockSignals(True)
        self.universe.clear()
        self.universe.addItems(names)
        self.universe.setCurrentText(current)
        self.universe.blockSignals(False)

    def show_settings(self, n: int, first_year: int, last_year: int) -> None:
        self.count.setValue(n)
        self.first_year.setRange(1950, last_year)
        self.first_year.setValue(first_year)

    def show_warning(self, text: str) -> None:
        self.warning.setText(text)

    def show_notice(self, text: str) -> None:
        self.notice.setText(text)

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.universe.setEnabled(not running)

    def show_result(self, result: PortfolioResult | None) -> None:
        if result is None:
            self.chart.show_chart(None)
            _fill(self.lines_table, [])
            _fill(self.years_table, [])
            self.summary.setText('')
            self.next_picks.setText('')
            return
        self.chart.show_chart(result.chart)
        _fill(self.lines_table, result.lines)
        _fill(self.years_table, result.years)
        self.summary.setText(result.summary)
        self.next_picks.setText(result.next_picks)

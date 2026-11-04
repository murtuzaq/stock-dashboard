"""Growth view: revenue and earnings per share (EPS), quarterly and annual, with growth rates.

Not a chart over time like the others, so it ignores the candle size and range.
"""
from collections.abc import Callable

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.background import BackgroundLoader
from core.formatting import Cell
from core.panels import GROWTH_COLUMNS, GROWTH_HEADER_TIPS, growth_rows, growth_summary

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def _item(cell: Cell) -> QTableWidgetItem:
    item = QTableWidgetItem(cell.text)
    if cell.tooltip:
        item.setToolTip(cell.tooltip)
    if cell.color:
        item.setForeground(QColor(cell.color))
    if cell.align_right:
        item.setTextAlignment(RIGHT)
    return item


class GrowthTable(QTableWidget):
    def __init__(self, period: str) -> None:
        self.period = period
        columns = GROWTH_COLUMNS[period]
        super().__init__(0, len(columns))
        self.setObjectName('historyTable')
        self.setHorizontalHeaderLabels([title for title, _ in columns])
        for index, (title, _) in enumerate(columns):
            self.horizontalHeaderItem(index).setToolTip(GROWTH_HEADER_TIPS.get(title, ''))
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)

    def show_figures(self, figures: pd.DataFrame) -> None:
        rows = growth_rows(self.period, figures)
        self.setRowCount(len(rows))
        for row, cells in enumerate(rows):
            for col, cell in enumerate(cells):
                self.setItem(row, col, _item(cell))


class GrowthView(QWidget):
    def __init__(self, loader: BackgroundLoader, source: Callable[[str], dict[str, pd.DataFrame]]) -> None:
        super().__init__()
        self.loader = loader
        self.source = source  # symbol -> {'quarterly': ..., 'annual': ...}
        self.symbol: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel()
        self.summary.setObjectName('indicatorLegend')
        layout.addWidget(self.summary)
        tables = QHBoxLayout()
        self.tables = {}
        for period, title in (('quarterly', 'Quarterly'), ('annual', 'Annual')):
            column = QVBoxLayout()
            heading = QLabel(title)
            heading.setObjectName('barLabel')
            column.addWidget(heading)
            self.tables[period] = GrowthTable(period)
            column.addWidget(self.tables[period])
            tables.addLayout(column, stretch=7 if period == 'quarterly' else 5)
        layout.addLayout(tables)

    def set_symbol(self, symbol: str) -> None:
        if symbol == self.symbol:
            return
        self.symbol = symbol
        self.summary.setText(f'Loading {symbol} financials…')
        for table in self.tables.values():
            table.setRowCount(0)
        self.loader.run(lambda: self.source(symbol), lambda figures: self._on_loaded(symbol, figures),
                        lambda error: self.summary.setText(f'Could not load {symbol} financials: {error}'))

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        pass  # financials don't depend on the price data or candle size

    def set_range(self, start: pd.Timestamp) -> None:
        pass

    def _on_loaded(self, symbol: str, financials: dict[str, pd.DataFrame]) -> None:
        if symbol != self.symbol:
            return
        for period, table in self.tables.items():
            table.show_figures(financials[period])
        self.summary.setText(growth_summary(symbol, financials['quarterly']))

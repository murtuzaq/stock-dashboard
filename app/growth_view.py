"""Growth view: revenue and earnings per share (EPS), quarterly and annual, with growth rates.

Not a chart over time like the others, so it ignores the candle size and range.
"""
import threading

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from chart_view import DOWN, UP, short_number
from prices import load_financials

NOT_AVAILABLE = 'Needs the same period a year earlier (or the earlier figure was a loss).\n' \
                'Yahoo only provides about 5 quarters; stored history grows as new quarters are reported.'
COLUMNS = {
    'quarterly': [('Quarter end', None), ('Revenue', 'revenue'), ('QoQ', 'revenue_qoq'), ('YoY', 'revenue_yoy'),
                  ('EPS', 'eps'), ('QoQ', 'eps_qoq'), ('YoY', 'eps_yoy')],
    'annual': [('Year end', None), ('Revenue', 'revenue'), ('YoY', 'revenue_yoy'), ('EPS', 'eps'),
               ('YoY', 'eps_yoy')],
}
HEADER_TIPS = {
    'Revenue': 'Total sales', 'EPS': 'Diluted earnings per share: profit divided by shares',
    'QoQ': 'Growth vs the previous quarter (seasonal businesses swing a lot here)',
    'YoY': 'Growth vs the same period a year earlier: the number most traders watch',
}


def _cell(value: float, column: str) -> QTableWidgetItem:
    if pd.isna(value):
        item = QTableWidgetItem('—')
        item.setToolTip(NOT_AVAILABLE)
    elif column.endswith(('_yoy', '_qoq')):
        item = QTableWidgetItem(f'{value:+.1f}%')
        item.setForeground(QColor(UP if value >= 0 else DOWN))
    elif column == 'revenue':
        item = QTableWidgetItem(f'${short_number(value)}')
    else:
        item = QTableWidgetItem(f'{value:.2f}')
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class GrowthTable(QTableWidget):
    def __init__(self, period: str) -> None:
        self.columns = COLUMNS[period]
        super().__init__(0, len(self.columns))
        self.setObjectName('historyTable')
        self.setHorizontalHeaderLabels([title for title, _ in self.columns])
        for index, (title, _) in enumerate(self.columns):
            self.horizontalHeaderItem(index).setToolTip(HEADER_TIPS.get(title, ''))
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)

    def show_figures(self, figures: pd.DataFrame) -> None:
        rows = figures.iloc[::-1]  # newest first
        self.setRowCount(len(rows))
        for row, (end_date, values) in enumerate(rows.iterrows()):
            for col, (_, column) in enumerate(self.columns):
                if column is None:
                    self.setItem(row, col, QTableWidgetItem(f'{end_date:%Y-%m-%d}'))
                else:
                    self.setItem(row, col, _cell(values[column], column))


class GrowthView(QWidget):
    _loaded = Signal(str, object)  # symbol, {'quarterly': ..., 'annual': ...}

    def __init__(self) -> None:
        super().__init__()
        self.symbol: str | None = None
        self._loaded.connect(self._on_loaded)
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
        threading.Thread(target=lambda: self._loaded.emit(symbol, load_financials(symbol)), daemon=True).start()

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        pass  # financials don't depend on the price data or candle size

    def set_range(self, start: pd.Timestamp) -> None:
        pass

    def _on_loaded(self, symbol: str, financials: dict[str, pd.DataFrame]) -> None:
        if symbol != self.symbol:
            return
        for period, table in self.tables.items():
            table.show_figures(financials[period])
        quarterly = financials['quarterly']
        if quarterly.empty:
            self.summary.setText(f'No revenue or earnings figures available for {symbol} '
                                 '(ETFs and indexes have none).')
            return
        latest = quarterly.iloc[-1]
        parts = [f'Latest quarter {quarterly.index[-1]:%b %Y}: revenue ${short_number(latest["revenue"])}']
        if not pd.isna(latest['revenue_yoy']):
            parts.append(f'{latest["revenue_yoy"]:+.1f}% YoY')
        parts.append(f'EPS {latest["eps"]:.2f}')
        if not pd.isna(latest['eps_yoy']):
            parts.append(f'{latest["eps_yoy"]:+.1f}% YoY')
        self.summary.setText(' · '.join(parts))

"""History view: the price data behind the candles, as a table (newest first)."""
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QLabel, QTableView, QVBoxLayout, QWidget

from chart_view import DOWN, UP

COLUMNS = ['Date', 'Open', 'High', 'Low', 'Close', 'Change', 'Volume']
TOOLTIPS = {
    'Date': 'First trading day of the candle',
    'Open': 'Price of the first trade',
    'High': 'Highest price traded',
    'Low': 'Lowest price traded',
    'Close': 'Price of the last trade',
    'Change': 'Close compared with the previous close',
    'Volume': 'Number of shares traded',
}


class HistoryModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.rows = pd.DataFrame()

    def set_first_row(self, candles: pd.DataFrame, first_slot: int) -> None:
        """Show candles from first_slot onwards; the change column still uses the candle before it."""
        self.beginResetModel()
        rows = candles.assign(change=candles['close'].pct_change() * 100).iloc[first_slot:]
        self.rows = rows.iloc[::-1]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        if role == Qt.ItemDataRole.ToolTipRole:
            return TOOLTIPS[COLUMNS[section]]
        if role == Qt.ItemDataRole.TextAlignmentRole and section > 0:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        column = COLUMNS[index.column()]
        row = self.rows.iloc[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 'Date':
                return f'{self.rows.index[index.row()]:%Y-%m-%d}'
            if column == 'Change':
                return '' if pd.isna(row['change']) else f'{row["change"]:+.2f}%'
            if column == 'Volume':
                return f'{int(row["volume"]):,}'
            return f'{row[column.lower()]:,.2f}'
        if role == Qt.ItemDataRole.TextAlignmentRole and column != 'Date':
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ForegroundRole and column == 'Change' and not pd.isna(row['change']):
            return QColor(UP if row['change'] >= 0 else DOWN)
        return None


class HistoryView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.candles = pd.DataFrame()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.summary = QLabel()
        self.summary.setObjectName('summary')
        layout.addWidget(self.summary)

        self.model = HistoryModel()
        self.table = QTableView()
        self.table.setObjectName('historyTable')
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        self.candles = candles

    def set_range(self, start: pd.Timestamp) -> None:
        first_slot = int(self.candles.index.searchsorted(start))
        self.model.set_first_row(self.candles, first_slot)
        self.table.scrollToTop()
        self._show_summary(self.candles.iloc[first_slot:])

    def _show_summary(self, shown: pd.DataFrame) -> None:
        """One line describing the range: how many rows, which dates, highest and lowest price."""
        if shown.empty:
            self.summary.clear()
            return
        self.summary.setText(
            f'{len(shown):,} rows · {shown.index[0]:%b %d, %Y} to {shown.index[-1]:%b %d, %Y} · '
            f'high {shown["high"].max():,.2f} · low {shown["low"].min():,.2f}')

"""History view: the price data behind the candles, as a table (newest first)."""
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QLabel, QTableView, QVBoxLayout, QWidget

from core.panels import HISTORY_COLUMNS, HISTORY_TOOLTIPS, history_cell, history_rows, history_summary

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class HistoryModel(QAbstractTableModel):
    """Qt's view of the rows; what each cell says comes from core.panels.history_cell."""

    def __init__(self) -> None:
        super().__init__()
        self.rows = pd.DataFrame()

    def set_first_row(self, candles: pd.DataFrame, first_slot: int) -> None:
        """Show candles from first_slot onwards."""
        self.beginResetModel()
        self.rows = history_rows(candles, first_slot)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(HISTORY_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return HISTORY_COLUMNS[section]
        if role == Qt.ItemDataRole.ToolTipRole:
            return HISTORY_TOOLTIPS[HISTORY_COLUMNS[section]]
        if role == Qt.ItemDataRole.TextAlignmentRole and section > 0:
            return RIGHT
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        cell = history_cell(self.rows, index.row(), HISTORY_COLUMNS[index.column()])
        if role == Qt.ItemDataRole.DisplayRole:
            return cell.text
        if role == Qt.ItemDataRole.TextAlignmentRole and cell.align_right:
            return RIGHT
        if role == Qt.ItemDataRole.ForegroundRole and cell.color:
            return QColor(cell.color)
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
        self.summary.setText(history_summary(self.candles.iloc[first_slot:]))

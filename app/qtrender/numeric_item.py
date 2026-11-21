"""A table cell that is shown as text but sorts by a number."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

SORT_ROLE = Qt.ItemDataRole.UserRole + 1  # where the number to sort by is kept


class NumberItem(QTableWidgetItem):
    """A cell shown as text ($12,340.00) that sorts by its number, so $9,000 comes before $12,000."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        mine, theirs = self.data(SORT_ROLE), other.data(SORT_ROLE)
        if mine is None or theirs is None:
            return super().__lt__(other)
        return mine < theirs

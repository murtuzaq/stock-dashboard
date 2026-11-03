"""Explorer panel: one parent node per searched symbol, with child nodes for each view of it."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

# Views available under every symbol. Add RSI, moving averages, etc. here later.
VIEWS = [('candles', 'Candles')]

VIEW_ROLE = Qt.ItemDataRole.UserRole


class Explorer(QTreeWidget):
    view_selected = Signal(str, str)  # symbol, view

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderLabel('EXPLORER')
        self.setMinimumWidth(160)
        self.symbols: dict[str, QTreeWidgetItem] = {}
        self.currentItemChanged.connect(self._handle_select)

    def add_symbol(self, symbol: str) -> None:
        """Add a symbol (unless already present) and select its first view."""
        parent = self.symbols.get(symbol)
        if parent is None:
            parent = QTreeWidgetItem(self, [symbol])
            for key, label in VIEWS:
                child = QTreeWidgetItem(parent, [label])
                child.setData(0, VIEW_ROLE, key)
            self.symbols[symbol] = parent
        parent.setExpanded(True)
        self.setCurrentItem(parent.child(0))

    def _handle_select(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        if item.parent() is None:  # a symbol was clicked: open its first view
            self.setCurrentItem(item.child(0))
            return
        self.view_selected.emit(item.parent().text(0), item.data(0, VIEW_ROLE))

"""Explorer panel: one parent node per searched symbol, with child nodes for each view of it.

Click a view to show it alone; Ctrl+click or Shift+click to stack several views of the same symbol.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

# Views available under every symbol, in the order they stack. Add RSI, moving averages, etc. here later.
VIEWS = [('price', 'Price'), ('candles', 'Candles'), ('sma', 'SMA 50/150/200'), ('volume', 'Volume'),
         ('macd', 'MACD'), ('stoch_rsi', 'Stoch RSI'), ('atr', 'ATR'), ('rel_strength', 'Rel. Strength'),
         ('growth', 'Revenue/EPS Growth'), ('history', 'History')]

VIEW_ROLE = Qt.ItemDataRole.UserRole


class Explorer(QTreeWidget):
    views_selected = Signal(str, list)  # symbol, view keys in stacking order

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderLabel('EXPLORER')
        self.setMinimumWidth(160)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setToolTip('Click a view to show it.\nCtrl+click or Shift+click to stack several views.')
        self.symbols: dict[str, QTreeWidgetItem] = {}
        self.itemSelectionChanged.connect(self._handle_selection)

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

    def _handle_selection(self) -> None:
        current = self.currentItem()
        if current is None:
            return
        if current.parent() is None:  # a symbol was clicked: open its first view
            self.setCurrentItem(current.child(0))
            return
        symbol_item = current.parent()
        # Views can only be stacked within one symbol; drop anything else a Shift+click swept up.
        self.blockSignals(True)
        for item in self.selectedItems():
            if item.parent() is not symbol_item:
                item.setSelected(False)
        self.blockSignals(False)

        children = [symbol_item.child(i) for i in range(symbol_item.childCount())]
        views = [child.data(0, VIEW_ROLE) for child in children if child.isSelected()]
        if views:  # Ctrl+clicking away the last view keeps showing it
            self.views_selected.emit(symbol_item.text(0), views)

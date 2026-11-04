"""Explorer panel: one parent node per searched symbol, with child nodes for each view of it.

Click a view to show it alone; Ctrl+click or Shift+click to stack several views of the same symbol.
The Strategies folder lists the stock's own strategies, then the library templates (in italics);
right-click a stock, the folder or a strategy for New / Edit / Duplicate / Copy / Delete.
"""
from PySide6.QtCore import QItemSelectionModel, QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeWidget, QTreeWidgetItem

from strategy import describe, repository

# Views available under every symbol, in the order they stack. Add RSI, moving averages, etc. here later.
VIEWS = [('price', 'Price'), ('candles', 'Candles'), ('sma', 'SMA 50/150/200'), ('volume', 'Volume'),
         ('macd', 'MACD'), ('stoch_rsi', 'Stoch RSI'), ('atr', 'ATR'), ('rel_strength', 'Rel. Strength'),
         ('growth', 'Revenue/EPS Growth'), ('history', 'History')]
STRATEGIES_BEFORE = 'history'  # the Strategies folder sits just above this view
STRATEGY_PREFIX = 'strategy:'  # view key for a strategy: 'strategy:<id>'

VIEW_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1  # 'view', 'folder' or 'strategy'
LIBRARY_ROLE = Qt.ItemDataRole.UserRole + 2


def strategy_key(strategy_id: str) -> str:
    return STRATEGY_PREFIX + strategy_id


class Explorer(QTreeWidget):
    views_selected = Signal(str, list)  # symbol, view keys in stacking order
    strategy_action = Signal(str, str, str)  # action, symbol, strategy id ('' for a new strategy)

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderLabel('EXPLORER')
        self.setMinimumWidth(160)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setToolTip('Click a view to show it.\nCtrl+click or Shift+click to stack several views.\n'
                        'Right-click a stock or a strategy for strategy actions.')
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self.symbols: dict[str, QTreeWidgetItem] = {}
        self.folders: dict[str, QTreeWidgetItem] = {}
        self.itemSelectionChanged.connect(self._handle_selection)
        self.itemClicked.connect(lambda item: item.data(0, KIND_ROLE) == 'folder'
                                 and item.setExpanded(not item.isExpanded()))

    # --- building the tree ---

    def add_symbol(self, symbol: str) -> None:
        """Add a symbol (unless already present) and select its first view."""
        parent = self.symbols.get(symbol)
        if parent is None:
            parent = QTreeWidgetItem(self, [symbol])
            parent.setData(0, KIND_ROLE, 'symbol')
            for key, label in VIEWS:
                if key == STRATEGIES_BEFORE:
                    self.folders[symbol] = self._add_folder(parent)
                child = QTreeWidgetItem(parent, [label])
                child.setData(0, VIEW_ROLE, key)
                child.setData(0, KIND_ROLE, 'view')
            self.symbols[symbol] = parent
            self._fill_folder(symbol)
        parent.setExpanded(True)
        self.setCurrentItem(parent.child(0))

    def _add_folder(self, parent: QTreeWidgetItem) -> QTreeWidgetItem:
        folder = QTreeWidgetItem(parent, ['Strategies'])
        folder.setData(0, KIND_ROLE, 'folder')
        folder.setFlags(Qt.ItemFlag.ItemIsEnabled)  # a heading: clicking opens/closes it, it is not a view
        folder.setToolTip(0, 'Right-click for New Strategy…')
        return folder

    def _fill_folder(self, symbol: str) -> None:
        folder = self.folders[symbol]
        folder.takeChildren()
        for strategy in repository.for_symbol(symbol) + repository.library():
            item = QTreeWidgetItem(folder, [strategy.name])
            item.setData(0, VIEW_ROLE, strategy_key(strategy.id))
            item.setData(0, KIND_ROLE, 'strategy')
            item.setData(0, LIBRARY_ROLE, strategy.symbol is None)
            item.setToolTip(0, describe(strategy))
            if strategy.symbol is None:
                item.setText(0, f'{strategy.name} · library')
                font = QFont(item.font(0))
                font.setItalic(True)
                item.setFont(0, font)
                item.setForeground(0, QColor('#9598a1'))
                item.setToolTip(0, f'Library template (try it on {symbol}; right-click to copy and customise)\n\n'
                                + describe(strategy))
        folder.setExpanded(True)

    def refresh_strategies(self) -> None:
        """Re-read the strategy files (after creating, editing or deleting), keeping the selection if possible."""
        selected = {item.data(0, VIEW_ROLE) for item in self.selectedItems()}
        current = self.currentItem()
        current_key = current.data(0, VIEW_ROLE) if current else None
        current_symbol = self._symbol_item(current).text(0) if current else None
        self.blockSignals(True)
        for symbol in self.symbols:
            self._fill_folder(symbol)
        restored = None
        if current_symbol in self.symbols:
            for item in self._view_items(self.symbols[current_symbol]):
                key = item.data(0, VIEW_ROLE)
                item.setSelected(key in selected)
                if key == current_key:
                    restored = item
        self.blockSignals(False)
        if current_symbol in self.symbols:
            if restored is None or not self.selectedItems():
                self.setCurrentItem(self.symbols[current_symbol].child(0))  # e.g. the selected strategy was deleted
            else:
                self.setCurrentItem(restored, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
                self._handle_selection()

    def select_strategy(self, symbol: str, strategy_id: str) -> None:
        if symbol not in self.symbols:
            self.add_symbol(symbol)
        for item in self._view_items(self.symbols[symbol]):
            if item.data(0, VIEW_ROLE) == strategy_key(strategy_id):
                self.setCurrentItem(item)
                return

    # --- selection ---

    @staticmethod
    def _symbol_item(item: QTreeWidgetItem) -> QTreeWidgetItem:
        while item.parent() is not None:
            item = item.parent()
        return item

    def _view_items(self, symbol_item: QTreeWidgetItem) -> list[QTreeWidgetItem]:
        """The symbol's views and strategies, top to bottom."""
        items = []
        for i in range(symbol_item.childCount()):
            child = symbol_item.child(i)
            if child.data(0, KIND_ROLE) == 'folder':
                items += [child.child(j) for j in range(child.childCount())]
            else:
                items.append(child)
        return items

    def _handle_selection(self) -> None:
        current = self.currentItem()
        if current is None:
            return
        if current.data(0, KIND_ROLE) == 'symbol':  # a symbol was clicked: open its first view
            self.setCurrentItem(current.child(0))
            return
        symbol_item = self._symbol_item(current)
        items = self._view_items(symbol_item)
        chosen_strategy = current if current.data(0, KIND_ROLE) == 'strategy' and current.isSelected() else None
        if chosen_strategy is None:
            chosen_strategy = next((i for i in items if i.isSelected() and i.data(0, KIND_ROLE) == 'strategy'), None)
        # Only one symbol's views at a time, and only one strategy at a time.
        self.blockSignals(True)
        for item in self.selectedItems():
            if item not in items or (item.data(0, KIND_ROLE) == 'strategy' and item is not chosen_strategy):
                item.setSelected(False)
        self.blockSignals(False)

        views = [item.data(0, VIEW_ROLE) for item in items if item.isSelected()]
        if views:  # Ctrl+clicking away the last view keeps showing it
            self.views_selected.emit(symbol_item.text(0), views)

    # --- right-click menu ---

    def _show_menu(self, position: QPoint) -> None:
        item = self.itemAt(position)
        if item is None:
            return
        symbol = self._symbol_item(item).text(0)
        kind = item.data(0, KIND_ROLE)
        menu = QMenu(self)
        if kind in ('symbol', 'folder', 'view'):
            self._action(menu, 'New Strategy…', 'new', symbol, '')
        elif kind == 'strategy':
            strategy_id = item.data(0, VIEW_ROLE).removeprefix(STRATEGY_PREFIX)
            if item.data(0, LIBRARY_ROLE):
                self._action(menu, f'Copy to {symbol} and customise…', 'copy_here', symbol, strategy_id)
                self._action(menu, 'Edit library template…', 'edit', symbol, strategy_id)
                self._action(menu, 'Copy to another stock…', 'copy_to', symbol, strategy_id)
                menu.addSeparator()
                self._action(menu, 'Delete from library…', 'delete', symbol, strategy_id)
            else:
                self._action(menu, 'Edit…', 'edit', symbol, strategy_id)
                self._action(menu, 'Duplicate', 'duplicate', symbol, strategy_id)
                self._action(menu, 'Copy to another stock…', 'copy_to', symbol, strategy_id)
                self._action(menu, 'Save to Library', 'save_to_library', symbol, strategy_id)
                menu.addSeparator()
                self._action(menu, 'Delete…', 'delete', symbol, strategy_id)
            menu.addSeparator()
            self._action(menu, 'New Strategy…', 'new', symbol, '')
        menu.exec(self.viewport().mapToGlobal(position))

    def _action(self, menu: QMenu, text: str, action: str, symbol: str, strategy_id: str) -> QAction:
        return menu.addAction(text, lambda: self.strategy_action.emit(action, symbol, strategy_id))

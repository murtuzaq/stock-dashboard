"""Explorer panel: one parent node per searched symbol, with child nodes for each view of it.

Click a view to show it alone; Ctrl+click or Shift+click to stack several views of the same symbol.
The Strategies folder lists the stock's own strategies, then the library templates (in italics);
right-click a stock, the folder or a strategy for New / Edit / Duplicate / Copy / Delete.

What the tree lists and what the menus offer is decided in core (views, explorer_model, strategy_service);
this widget builds the tree from it and reports the user's choices.
"""
from PySide6.QtCore import QItemSelectionModel, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeWidget, QTreeWidgetItem

from core.explorer_model import strategy_entries
from core.explorer_selection import Entry, resolve_selection
from core.strategy_service import menu_for
from core.views import STRATEGIES_BEFORE, STRATEGY_PREFIX, VIEWS

VIEW_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1  # 'view', 'folder' or 'strategy'
LIBRARY_ROLE = Qt.ItemDataRole.UserRole + 2
LIBRARY_COLOR = '#9598a1'


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
        for entry in strategy_entries(symbol):
            item = QTreeWidgetItem(folder, [entry.label])
            item.setData(0, VIEW_ROLE, entry.key)
            item.setData(0, KIND_ROLE, 'strategy')
            item.setData(0, LIBRARY_ROLE, entry.is_library)
            item.setToolTip(0, entry.tooltip)
            if entry.is_library:
                font = QFont(item.font(0))
                font.setItalic(True)
                item.setFont(0, font)
                item.setForeground(0, QColor(LIBRARY_COLOR))
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
            if item.data(0, VIEW_ROLE) == STRATEGY_PREFIX + strategy_id:
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
        entries = [Entry(item.data(0, VIEW_ROLE), item.data(0, KIND_ROLE) == 'strategy', item.isSelected())
                   for item in items]
        keep = resolve_selection(entries, current.data(0, VIEW_ROLE))
        # Only one symbol's views at a time, and only one strategy at a time.
        self.blockSignals(True)
        for item in self.selectedItems():
            if item not in items or item.data(0, VIEW_ROLE) not in keep:
                item.setSelected(False)
        self.blockSignals(False)

        if keep:  # Ctrl+clicking away the last view keeps showing it
            self.views_selected.emit(symbol_item.text(0), keep)

    # --- right-click menu ---

    def _show_menu(self, position: QPoint) -> None:
        item = self.itemAt(position)
        if item is None:
            return
        symbol = self._symbol_item(item).text(0)
        kind = item.data(0, KIND_ROLE)
        strategy_id = ''
        if kind == 'strategy':
            strategy_id = item.data(0, VIEW_ROLE).removeprefix(STRATEGY_PREFIX)
        entries = menu_for(kind, symbol, bool(item.data(0, LIBRARY_ROLE)))
        menu = QMenu(self)
        for entry in entries:
            if entry is None:
                menu.addSeparator()
            else:
                menu.addAction(entry.text, lambda action=entry.action: self.strategy_action.emit(action, symbol,
                                                                                                strategy_id))
        menu.exec(self.viewport().mapToGlobal(position))

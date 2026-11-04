"""Explorer panel (renderer): one parent node per searched symbol, with child nodes for each view of it.

Click a view to show it alone; Ctrl+click or Shift+click to stack several views of the same symbol.
The Strategies folder lists the stock's own strategies, then the library templates (in italics);
right-click a stock, the folder or a strategy for New / Edit / Duplicate / Copy / Delete.

This widget only draws the tree and reports clicks. Which stocks are open, the selection rules, what the menus
offer and what a pick means are decided by core.explorer.controller.ExplorerController (the ExplorerTreeView
protocol is what it needs from this widget).
"""
from collections.abc import Callable

from PySide6.QtCore import QItemSelectionModel, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeWidget, QTreeWidgetItem

from core.explorer.controller import FOLDER, STRATEGY, SYMBOL, VIEW, Node, TreeRow
from core.explorer.entries import StrategyEntry
from core.strategies.service import MenuEntry

KEY_ROLE = Qt.ItemDataRole.UserRole  # the view key, or 'strategy:<id>'
KIND_ROLE = Qt.ItemDataRole.UserRole + 1  # SYMBOL, VIEW, FOLDER or STRATEGY
LIBRARY_ROLE = Qt.ItemDataRole.UserRole + 2
LIBRARY_COLOR = '#9598a1'


class Explorer(QTreeWidget):
    selection_changed = Signal(object, object)  # current Node, list of selected Nodes
    action_chosen = Signal(str, object)  # menu action name, the Node it was chosen on

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderLabel('EXPLORER')
        self.setMinimumWidth(160)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setToolTip('Click a view to show it.\nCtrl+click or Shift+click to stack several views.\n'
                        'Right-click a stock or a strategy for strategy actions.')
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self.menu_source: Callable[[Node], list[MenuEntry | None]] = lambda node: []  # set by the controller wiring
        self.symbol_items: dict[str, QTreeWidgetItem] = {}
        self.folders: dict[str, QTreeWidgetItem] = {}
        self.items: dict[tuple[str, str], QTreeWidgetItem] = {}  # (symbol, key) -> view or strategy row
        self.itemSelectionChanged.connect(lambda: self.selection_changed.emit(*self.read_selection()))
        self.itemClicked.connect(lambda item: item.data(0, KIND_ROLE) == FOLDER
                                 and item.setExpanded(not item.isExpanded()))

    # --- ExplorerTreeView: what the controller asks for ---

    def add_symbol(self, symbol: str, rows: list[TreeRow], strategies: list[StrategyEntry]) -> None:
        parent = QTreeWidgetItem(self, [symbol])
        parent.setData(0, KIND_ROLE, SYMBOL)
        self.symbol_items[symbol] = parent
        for row in rows:
            if row.kind == FOLDER:
                self.folders[symbol] = self._add_folder(parent, row.label)
                continue
            child = QTreeWidgetItem(parent, [row.label])
            child.setData(0, KEY_ROLE, row.key)
            child.setData(0, KIND_ROLE, VIEW)
            self.items[(symbol, row.key)] = child
        self.set_strategies(symbol, strategies)

    def set_strategies(self, symbol: str, strategies: list[StrategyEntry]) -> None:
        folder = self.folders[symbol]
        self.blockSignals(True)  # removing a selected row must not look like the user clicked
        folder.takeChildren()
        for key in [key for (sym, key), item in self.items.items() if sym == symbol and
                    item.data(0, KIND_ROLE) == STRATEGY]:
            del self.items[(symbol, key)]
        for entry in strategies:
            item = QTreeWidgetItem(folder, [entry.label])
            item.setData(0, KEY_ROLE, entry.key)
            item.setData(0, KIND_ROLE, STRATEGY)
            item.setData(0, LIBRARY_ROLE, entry.is_library)
            item.setToolTip(0, entry.tooltip)
            if entry.is_library:
                font = QFont(item.font(0))
                font.setItalic(True)
                item.setFont(0, font)
                item.setForeground(0, QColor(LIBRARY_COLOR))
            self.items[(symbol, entry.key)] = item
        folder.setExpanded(True)
        self.blockSignals(False)

    def select_only(self, symbol: str, keys: list[str]) -> None:
        self.symbol_items[symbol].setExpanded(True)
        if len(keys) == 1:
            self.setCurrentItem(self.items[(symbol, keys[0])])
            return
        self.clearSelection()
        for key in keys:
            self.items[(symbol, key)].setSelected(True)

    def restore_selection(self, symbol: str, keys: list[str], current_key: str | None) -> None:
        self.blockSignals(True)
        for (sym, key), item in self.items.items():
            if sym == symbol:
                item.setSelected(key in keys)
        if current_key is not None:
            self.setCurrentItem(self.items[(symbol, current_key)], 0, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.blockSignals(False)

    def apply_selection(self, symbol: str, keep: list[str]) -> None:
        keep_items = {self.items[(symbol, key)] for key in keep}
        self.blockSignals(True)
        for item in self.selectedItems():
            if item not in keep_items:
                item.setSelected(False)
        self.blockSignals(False)

    def read_selection(self) -> tuple[Node | None, list[Node]]:
        current = self.currentItem()
        return (self._node(current) if current else None), [self._node(item) for item in self.selectedItems()]

    # --- helpers ---

    def _add_folder(self, parent: QTreeWidgetItem, label: str) -> QTreeWidgetItem:
        folder = QTreeWidgetItem(parent, [label])
        folder.setData(0, KIND_ROLE, FOLDER)
        folder.setFlags(Qt.ItemFlag.ItemIsEnabled)  # a heading: clicking opens/closes it, it is not a view
        folder.setToolTip(0, 'Right-click for New Strategy…')
        return folder

    @staticmethod
    def _node(item: QTreeWidgetItem) -> Node:
        top = item
        while top.parent() is not None:
            top = top.parent()
        return Node(top.text(0), item.data(0, KEY_ROLE), item.data(0, KIND_ROLE), bool(item.data(0, LIBRARY_ROLE)))

    # --- right-click menu ---

    def _show_menu(self, position: QPoint) -> None:
        item = self.itemAt(position)
        if item is None:
            return
        node = self._node(item)
        menu = QMenu(self)
        for entry in self.menu_source(node):
            if entry is None:
                menu.addSeparator()
            else:
                menu.addAction(entry.text, lambda action=entry.action: self.action_chosen.emit(action, node))
        menu.exec(self.viewport().mapToGlobal(position))

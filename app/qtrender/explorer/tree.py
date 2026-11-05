"""Explorer panel (renderer): one parent node per searched symbol, with child nodes for each view of it.

Click a view to show it alone; Ctrl+click or Shift+click to stack several views of the same symbol.
The Strategies folder lists the stock's own strategies, then the library templates (in italics);
right-click a stock, the folder or a strategy for New / Edit / Duplicate / Copy / Delete.

This widget only draws the tree and reports clicks. Which stocks are open, the selection rules, what the menus
offer and what a pick means are decided by core.explorer.controller.ExplorerController (the ExplorerTreeView
protocol is what it needs from this widget). A stock row is identified by its `Scope`, since the same ticker can
be open more than once.
"""
from collections.abc import Callable

from PySide6.QtCore import QItemSelectionModel, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeWidget, QTreeWidgetItem

from core.dashboard.layout import OVERVIEW
from core.explorer.controller import FOLDER, PORTFOLIO, STRATEGY, SYMBOL, VIEW, Node, Scope, TreeRow
from core.explorer.entries import StrategyEntry
from core.learn import ui_terms
from qtrender.learn import info_mode
from qtrender.richtext import LINK_COLOR
from core.strategies.service import MenuEntry

KEY_ROLE = Qt.ItemDataRole.UserRole  # the view key, 'strategy:<id>', or OVERVIEW on a stock's own row
KIND_ROLE = Qt.ItemDataRole.UserRole + 1  # SYMBOL, VIEW, FOLDER, STRATEGY or PORTFOLIO
LIBRARY_ROLE = Qt.ItemDataRole.UserRole + 2
PORTFOLIO_ROLE = Qt.ItemDataRole.UserRole + 3  # a portfolio row's id
TERM_ROLE = Qt.ItemDataRole.UserRole + 4  # the topic that explains the row, if any
LIBRARY_COLOR = '#9598a1'


class Explorer(QTreeWidget):
    selection_changed = Signal(object, object)  # current Node, list of selected Nodes
    action_chosen = Signal(str, object, object)  # menu action name, the Node it was chosen on, the entry's argument
    rename_requested = Signal(str, str)  # portfolio id, the name the user typed

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
        self.portfolio_items: dict[str, QTreeWidgetItem] = {}
        self.symbol_items: dict[Scope, QTreeWidgetItem] = {}
        self.folders: dict[Scope, QTreeWidgetItem] = {}
        self.items: dict[tuple[Scope, str], QTreeWidgetItem] = {}  # (scope, key) -> view or strategy row
        self.itemSelectionChanged.connect(lambda: self.selection_changed.emit(*self.read_selection()))
        self.itemChanged.connect(self._on_item_changed)
        self.mode = info_mode.current()
        self._normal_triggers = self.editTriggers()
        self.itemDoubleClicked.connect(self._on_double_click)
        if self.mode:
            self.mode.changed.connect(self._on_info_mode)
        self.itemClicked.connect(lambda item: item.data(0, KIND_ROLE) == FOLDER
                                 and item.setExpanded(not item.isExpanded()))

    # --- ExplorerTreeView: what the controller asks for ---

    def add_portfolio(self, portfolio_id: str, name: str) -> None:
        self.blockSignals(True)  # building the row changes its data: that is not a rename
        item = QTreeWidgetItem(self, [name])
        item.setData(0, KIND_ROLE, PORTFOLIO)
        item.setData(0, PORTFOLIO_ROLE, portfolio_id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)  # F2 or double-click renames it
        item.setToolTip(0, 'Right-click to add stocks. Double-click or F2 to rename.')
        font = QFont(item.font(0))
        font.setBold(True)
        item.setFont(0, font)
        self.portfolio_items[portfolio_id] = item
        item.setData(0, TERM_ROLE, ui_terms.EXPLORER_PORTFOLIO)
        self._style_term(item)
        item.setExpanded(True)
        self.blockSignals(False)

    def rename_portfolio(self, portfolio_id: str, name: str) -> None:
        item = self.portfolio_items[portfolio_id]
        self.blockSignals(True)  # not a user edit: must not be reported back as one
        item.setText(0, name)
        self.blockSignals(False)

    def begin_rename(self, portfolio_id: str) -> None:
        item = self.portfolio_items[portfolio_id]
        self.setCurrentItem(item)
        self.editItem(item, 0)

    def remove_portfolio(self, portfolio_id: str) -> None:
        item = self.portfolio_items.pop(portfolio_id)
        for scope in [scope for scope in self.symbol_items if scope.portfolio == portfolio_id]:
            self._forget(scope)
        self.blockSignals(True)
        self.takeTopLevelItem(self.indexOfTopLevelItem(item))
        self.blockSignals(False)

    def add_symbol(self, scope: Scope, rows: list[TreeRow], strategies: list[StrategyEntry]) -> None:
        if scope.portfolio is None:
            parent = QTreeWidgetItem(self, [scope.symbol])
        else:
            parent = QTreeWidgetItem(self.portfolio_items[scope.portfolio], [scope.symbol])
        parent.setData(0, KIND_ROLE, SYMBOL)
        parent.setData(0, KEY_ROLE, OVERVIEW)  # clicking the stock's name shows its company overview
        parent.setToolTip(0, f'Click for the {scope.symbol} company overview')
        self.symbol_items[scope] = parent
        self.items[(scope, OVERVIEW)] = parent
        for row in rows:
            if row.kind == FOLDER:
                self.folders[scope] = self._add_folder(parent, row.label)
                continue
            child = QTreeWidgetItem(parent, [row.label])
            child.setData(0, KEY_ROLE, row.key)
            child.setData(0, KIND_ROLE, VIEW)
            child.setData(0, TERM_ROLE, ui_terms.EXPLORER_VIEWS.get(row.key))
            self._style_term(child)
            self.items[(scope, row.key)] = child
        self._fill_strategies(scope, strategies)

    def remove_symbol(self, scope: Scope) -> None:
        item = self.symbol_items[scope]
        self._forget(scope)
        self.blockSignals(True)  # removing a selected row must not look like the user clicked
        (item.parent() or self.invisibleRootItem()).removeChild(item)
        self.blockSignals(False)

    def set_strategies(self, symbol: str, strategies: list[StrategyEntry]) -> None:
        self.blockSignals(True)  # removing a selected row must not look like the user clicked
        for scope in [scope for scope in self.folders if scope.symbol == symbol]:
            self._fill_strategies(scope, strategies)
        self.blockSignals(False)

    def select_only(self, scope: Scope, keys: list[str]) -> None:
        self.symbol_items[scope].setExpanded(True)
        if len(keys) == 1:
            self.setCurrentItem(self.items[(scope, keys[0])])
            return
        self.clearSelection()
        for key in keys:
            self.items[(scope, key)].setSelected(True)

    def restore_selection(self, scope: Scope, keys: list[str], current_key: str | None) -> None:
        self.blockSignals(True)
        for (item_scope, key), item in self.items.items():
            if item_scope == scope:
                item.setSelected(key in keys)
        if current_key is not None:
            self.setCurrentItem(self.items[(scope, current_key)], 0, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.blockSignals(False)

    def apply_selection(self, scope: Scope, keep: list[str]) -> None:
        keep_items = {self.items[(scope, key)] for key in keep}
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
        folder.setData(0, TERM_ROLE, ui_terms.EXPLORER_STRATEGIES_FOLDER)
        self._style_term(folder)
        return folder

    def _fill_strategies(self, scope: Scope, strategies: list[StrategyEntry]) -> None:
        folder = self.folders[scope]
        folder.takeChildren()
        for key in [key for (item_scope, key), item in self.items.items()
                    if item_scope == scope and item.data(0, KIND_ROLE) == STRATEGY]:
            del self.items[(scope, key)]
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
            self.items[(scope, entry.key)] = item
        folder.setExpanded(True)

    def _forget(self, scope: Scope) -> None:
        """Drop the registry entries of a stock that is leaving the tree."""
        del self.symbol_items[scope]
        del self.folders[scope]
        for key in [key for (item_scope, key) in self.items if item_scope == scope]:
            del self.items[(scope, key)]

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if item.data(0, KIND_ROLE) == PORTFOLIO:  # the user finished typing a new name
            self.rename_requested.emit(item.data(0, PORTFOLIO_ROLE), item.text(0))

    @staticmethod
    def _node(item: QTreeWidgetItem) -> Node:
        if item.data(0, KIND_ROLE) == PORTFOLIO:
            return Node('', None, PORTFOLIO, portfolio=item.data(0, PORTFOLIO_ROLE))
        stock = item
        while stock.data(0, KIND_ROLE) != SYMBOL and stock.parent() is not None:
            stock = stock.parent()
        owner = stock.parent()
        portfolio = owner.data(0, PORTFOLIO_ROLE) if owner is not None else None
        return Node(stock.text(0), item.data(0, KEY_ROLE), item.data(0, KIND_ROLE),
                    bool(item.data(0, LIBRARY_ROLE)), portfolio)

    # --- Info mode: terms are underlined, double-click explains them ---

    def _style_term(self, item: QTreeWidgetItem) -> None:
        """Underline (and tint) a row that has an explanation while Info mode is on; plain otherwise."""
        term = item.data(0, TERM_ROLE)
        on = bool(self.mode and self.mode.on and self.mode.is_known(term))
        font = QFont(item.font(0))
        font.setUnderline(on)
        item.setFont(0, font)
        item.setData(0, Qt.ItemDataRole.ForegroundRole, QColor(LINK_COLOR) if on else None)

    def _on_info_mode(self, on: bool) -> None:
        for item in [*self.portfolio_items.values(), *self.folders.values(), *self.items.values()]:
            if item.data(0, TERM_ROLE):
                self._style_term(item)
        # While on, a double-click means "explain this", so it must not also expand a row or rename a portfolio.
        self.setExpandsOnDoubleClick(not on)
        triggers = self._normal_triggers
        self.setEditTriggers(triggers & ~QAbstractItemView.EditTrigger.DoubleClicked if on else triggers)

    def _on_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        if not (self.mode and self.mode.on):
            return
        term = item.data(0, TERM_ROLE)
        if self.mode.is_known(term):
            self.mode.open(term)
        elif item.childCount():
            item.setExpanded(not item.isExpanded())  # keep the usual double-click behaviour on other rows

    # --- right-click menu ---

    def _show_menu(self, position: QPoint) -> None:
        item = self.itemAt(position)
        if item is None:
            return
        node = self._node(item)
        menu = QMenu(self)
        self._fill_menu(menu, self.menu_source(node), node)
        if self.mode and self.mode.on:
            menu.addSeparator()
            self.mode.add_actions(menu, item.data(0, TERM_ROLE), item.text(0), 'explorer')
        menu.exec(self.viewport().mapToGlobal(position))

    def _fill_menu(self, menu: QMenu, entries: list[MenuEntry | None], node: Node) -> None:
        for entry in entries:
            if entry is None:
                menu.addSeparator()
            elif entry.children:
                self._fill_menu(menu.addMenu(entry.text), list(entry.children), node)
            else:
                menu.addAction(entry.text, lambda e=entry: self.action_chosen.emit(e.action, node, e.argument))

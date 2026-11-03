"""The search bar widget: type a symbol, company name or group; pick from a live results list.

Choosing a group (e.g. Nasdaq-100) turns it into a filter chip, so the next search only looks inside it.
"""
import threading

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QWidget

from .catalog import Catalog, Group, Security, load_catalog
from .matcher import MAX_RESULTS, match_groups, match_securities

PLACEHOLDER = 'Search symbol, company or index (e.g. AAPL, Apple, Nasdaq)'
RESULT_ROLE = Qt.ItemDataRole.UserRole
GROUP_COLOR = QColor('#5b8def')


class ResultsPopup(QTreeWidget):
    """Results list that floats under the search bar. Never takes focus, so typing continues uninterrupted."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName('searchResults')
        self.setColumnCount(3)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setColumnWidth(0, 130)
        self.setColumnWidth(1, 420)
        self.hide()

    def move_selection(self, step: int) -> None:
        row = self.indexOfTopLevelItem(self.currentItem()) if self.currentItem() else -1
        for _ in range(self.topLevelItemCount()):
            row = (row + step) % self.topLevelItemCount()
            if self.topLevelItem(row).data(0, RESULT_ROLE):
                self.setCurrentItem(self.topLevelItem(row))
                return


class SearchBar(QWidget):
    symbol_chosen = Signal(str)
    _catalog_loaded = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.catalog: Catalog | None = None
        self.scope: Group | None = None
        self.popup: ResultsPopup | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.scope_chip = QPushButton()
        self.scope_chip.setObjectName('scopeChip')
        self.scope_chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scope_chip.setToolTip('Remove filter (or press Backspace in an empty search)')
        self.scope_chip.clicked.connect(self.clear_scope)
        self.scope_chip.hide()
        layout.addWidget(self.scope_chip)

        self.input = QLineEdit()
        self.input.setPlaceholderText('Loading symbol list…')
        self.input.setClearButtonEnabled(True)
        self.input.setFixedWidth(380)
        self.input.textEdited.connect(self._refresh)
        self.input.installEventFilter(self)
        layout.addWidget(self.input)

        # The catalog may need downloading on first run, so load it without freezing the window.
        self._catalog_loaded.connect(self._on_catalog_loaded)
        threading.Thread(target=lambda: self._catalog_loaded.emit(load_catalog()), daemon=True).start()

    def _on_catalog_loaded(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self.input.setPlaceholderText(PLACEHOLDER)
        if self.input.hasFocus():
            self._refresh()

    # --- scope (group filter) ---

    def set_scope(self, group: Group) -> None:
        self.scope = group
        self.scope_chip.setText(f'{group.label}  ✕')
        self.scope_chip.show()
        self.input.clear()
        self.input.setPlaceholderText(f'Search within {group.label} ({len(group.symbols):,} symbols)')
        self._refresh()

    def clear_scope(self) -> None:
        self.scope = None
        self.scope_chip.hide()
        self.input.setPlaceholderText(PLACEHOLDER)
        self._refresh()

    # --- results list ---

    def _refresh(self) -> None:
        text = self.input.text()
        if self.catalog is None or (not text.strip() and self.scope is None):
            self._hide_popup()
            return

        groups = [] if self.scope else match_groups(self.catalog, text)
        securities = match_securities(self.catalog, text, self.scope)
        popup = self._ensure_popup()
        popup.clear()
        for group in groups:
            self._add_group_row(popup, group)
        for security in securities:
            self._add_security_row(popup, security)
        if len(securities) == MAX_RESULTS:
            self._add_note_row(popup, f'Showing the first {MAX_RESULTS}. Keep typing to narrow down.')
        if not groups and not securities:
            self._add_note_row(popup, 'No matches. Press Enter to open it as a symbol anyway.')
        popup.move_selection(1)
        self._place_popup(popup)

    def _add_group_row(self, popup: ResultsPopup, group: Group) -> None:
        item = QTreeWidgetItem(popup, [f'▸ {group.label}', group.about, f'{group.kind} · {len(group.symbols):,}'])
        item.setData(0, RESULT_ROLE, group)
        item.setToolTip(0, f'Show only {group.label} symbols')
        font = QFont(item.font(0))
        font.setBold(True)
        for column in range(3):
            item.setForeground(column, GROUP_COLOR)
        item.setFont(0, font)

    def _add_security_row(self, popup: ResultsPopup, security: Security) -> None:
        details = security.exchange + (' · ETF' if security.is_etf else '')
        item = QTreeWidgetItem(popup, [security.symbol, security.name, details])
        item.setData(0, RESULT_ROLE, security)
        font = QFont(item.font(0))
        font.setBold(True)
        item.setFont(0, font)

    def _add_note_row(self, popup: ResultsPopup, text: str) -> None:
        item = QTreeWidgetItem(popup, ['', text, ''])
        item.setFlags(Qt.ItemFlag.NoItemFlags)

    def _ensure_popup(self) -> ResultsPopup:
        if self.popup is None:
            # A child of the main window (not a separate window), so it stays put and never steals focus.
            self.popup = ResultsPopup(self.window())
            self.popup.itemClicked.connect(self._choose)
        return self.popup

    def _place_popup(self, popup: ResultsPopup) -> None:
        window = self.window()
        top_left = self.mapTo(window, QPoint(0, self.height() + 4))
        content_height = popup.topLevelItemCount() * popup.sizeHintForRow(0) + 2 * popup.frameWidth() + 10
        popup.setGeometry(top_left.x(), top_left.y(), max(self.width(), 720), min(content_height, 440))
        popup.raise_()
        popup.show()

    def _hide_popup(self) -> None:
        if self.popup:
            self.popup.hide()

    # --- choosing ---

    def _choose(self, item: QTreeWidgetItem | None) -> None:
        result = item.data(0, RESULT_ROLE) if item else None
        if isinstance(result, Group):
            self.set_scope(result)
        elif isinstance(result, Security):
            self._emit(result.symbol)

    def _choose_current(self) -> None:
        if self.popup and self.popup.isVisible() and self.popup.currentItem():
            self._choose(self.popup.currentItem())
        elif self.input.text().strip():
            self._emit(self.input.text().strip().upper())

    def _emit(self, symbol: str) -> None:
        self.input.clear()
        self._hide_popup()
        self.symbol_chosen.emit(symbol)

    # --- keyboard ---

    def eventFilter(self, obj, event) -> bool:
        if obj is self.input:
            if event.type() == QEvent.Type.KeyPress:
                return self._handle_key(event.key())
            if event.type() == QEvent.Type.FocusIn:
                self._refresh()
            elif event.type() == QEvent.Type.FocusOut:
                self._hide_popup()
        return super().eventFilter(obj, event)

    def _handle_key(self, key: int) -> bool:
        popup_open = self.popup is not None and self.popup.isVisible()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and popup_open:
            self.popup.move_selection(1 if key == Qt.Key.Key_Down else -1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._choose_current()
            return True
        if key == Qt.Key.Key_Escape:
            if popup_open:
                self._hide_popup()
            elif self.scope:
                self.clear_scope()
            return True
        if key == Qt.Key.Key_Backspace and not self.input.text() and self.scope:
            self.clear_scope()
            return True
        return False

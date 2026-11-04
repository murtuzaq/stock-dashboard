"""The search bar widget: type a symbol, company name or group; pick from a live results list.

Choosing a group (e.g. Nasdaq-100) turns it into a filter chip, so the next search only looks inside it.
The catalogue, the filter and the matching live in core.searchbar.session; this widget shows them.
"""
from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QWidget

from core.common.background import BackgroundLoader
from core.searchbar.controller import SearchController
from core.searchbar.session import SearchResults
from search import MAX_RESULTS, Group, Security, load_catalog

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

    def __init__(self, loader: BackgroundLoader) -> None:
        super().__init__()
        self.popup: ResultsPopup | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.scope_chip = QPushButton()
        self.scope_chip.setObjectName('scopeChip')
        self.scope_chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scope_chip.setToolTip('Remove filter (or press Backspace in an empty search)')
        self.scope_chip.clicked.connect(lambda: self.controller.clear_scope())
        self.scope_chip.hide()
        layout.addWidget(self.scope_chip)

        self.input = QLineEdit()
        self.input.setClearButtonEnabled(True)
        self.input.setFixedWidth(380)
        self.input.installEventFilter(self)
        layout.addWidget(self.input)

        self.controller = SearchController(self, on_symbol=self.symbol_chosen.emit)
        self.input.textEdited.connect(lambda _: self.controller.refresh())
        # The catalog may need downloading on first run, so load it without freezing the window.
        loader.run(load_catalog, lambda catalog: self.controller.catalog_loaded(catalog, self.input.hasFocus()))

    # --- SearchView: what the controller (core.searchbar.controller) asks for ---

    def text(self) -> str:
        return self.input.text()

    def clear_text(self) -> None:
        self.input.clear()

    def set_placeholder(self, text: str) -> None:
        self.input.setPlaceholderText(text)

    def show_scope(self, group: Group | None) -> None:
        if group is None:
            self.scope_chip.hide()
            return
        self.scope_chip.setText(f'{group.label}  ✕')
        self.scope_chip.show()

    def show_results(self, results: SearchResults) -> None:
        popup = self._ensure_popup()
        popup.clear()
        for group in results.groups:
            self._add_group_row(popup, group)
        for security in results.securities:
            self._add_security_row(popup, security)
        if results.capped:
            self._add_note_row(popup, f'Showing the first {MAX_RESULTS}. Keep typing to narrow down.')
        if results.empty:
            self._add_note_row(popup, 'No matches. Press Enter to open it as a symbol anyway.')
        popup.move_selection(1)
        self._place_popup(popup)

    def hide_results(self) -> None:
        if self.popup:
            self.popup.hide()

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
            self.popup.itemClicked.connect(lambda item: self.controller.choose(item.data(0, RESULT_ROLE)))
        return self.popup

    def _place_popup(self, popup: ResultsPopup) -> None:
        window = self.window()
        top_left = self.mapTo(window, QPoint(0, self.height() + 4))
        content_height = popup.topLevelItemCount() * popup.sizeHintForRow(0) + 2 * popup.frameWidth() + 10
        popup.setGeometry(top_left.x(), top_left.y(), max(self.width(), 720), min(content_height, 440))
        popup.raise_()
        popup.show()

    def _results_open(self) -> bool:
        return self.popup is not None and self.popup.isVisible()

    def _current_result(self):
        if self._results_open() and self.popup.currentItem():
            return self.popup.currentItem().data(0, RESULT_ROLE)
        return None

    # --- keyboard ---

    def eventFilter(self, obj, event) -> bool:
        if obj is self.input:
            if event.type() == QEvent.Type.KeyPress:
                return self._handle_key(event.key())
            if event.type() == QEvent.Type.FocusIn:
                self.controller.refresh()
            elif event.type() == QEvent.Type.FocusOut:
                self.hide_results()
        return super().eventFilter(obj, event)

    def _handle_key(self, key: int) -> bool:
        """Qt key codes -> controller calls. Returns True when the key is consumed."""
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._results_open():
            self.popup.move_selection(1 if key == Qt.Key.Key_Down else -1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.controller.enter(self._results_open(), self._current_result())
            return True
        if key == Qt.Key.Key_Escape:
            self.controller.escape(self._results_open())
            return True
        if key == Qt.Key.Key_Backspace:
            return self.controller.backspace_in_empty_box()
        return False

"""The questions only the user can answer (core.strategies.controller.Dialogs and core.portfolios.controller
.PortfolioDialogs), asked with Qt dialogs."""
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QMessageBox,
                               QVBoxLayout, QWidget)

from core.common.background import BackgroundLoader
from core.portfolios.service import PortfolioSummary
from qtrender.searchbar.bar import SearchBar


class SymbolDialog(QDialog):
    """Pick a stock with the same search bar as the top bar."""

    def __init__(self, parent: QWidget, title: str, loader: BackgroundLoader) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(760, 420)  # room for the results list under the search box
        self.symbol: str | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        self.search = SearchBar(loader)
        self.search.symbol_chosen.connect(self._chosen)
        layout.addWidget(self.search)
        layout.addStretch()

    def _chosen(self, symbol: str) -> None:
        self.symbol = symbol
        self.accept()


class PortfolioPickerDialog(QDialog):
    """Choose one of the saved portfolios (double-click, or select and press OK)."""

    def __init__(self, parent: QWidget, options: list[PortfolioSummary]) -> None:
        super().__init__(parent)
        self.setWindowTitle('Load Portfolio')
        self.setMinimumSize(380, 300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Choose a saved portfolio to open:'))
        self.list = QListWidget()
        for option in options:
            noun = 'stock' if option.stock_count == 1 else 'stocks'
            item = QListWidgetItem(f'{option.name}  ·  {option.stock_count} {noun}')
            item.setData(Qt.ItemDataRole.UserRole, option.id)
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class QtDialogs:
    def __init__(self, window: QWidget, loader: BackgroundLoader, show_wizard: Callable[[], None]) -> None:
        self.window = window
        self.loader = loader
        self._show_wizard = show_wizard  # opening the wizard panel is the window's job

    def ask_symbol(self, title: str) -> str | None:
        dialog = SymbolDialog(self.window, title, self.loader)
        return dialog.symbol if dialog.exec() == QDialog.DialogCode.Accepted else None

    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self.window, 'Confirm', text) == QMessageBox.StandardButton.Yes

    def notify(self, text: str) -> None:
        QMessageBox.information(self.window, 'Stock Dashboard', text)

    def choose_portfolio(self, options: list[PortfolioSummary]) -> str | None:
        dialog = PortfolioPickerDialog(self.window, options)
        return dialog.chosen_id() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def show_wizard(self) -> None:
        self._show_wizard()

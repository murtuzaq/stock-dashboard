"""The questions only the user can answer (core.strategies.controller.Dialogs), asked with Qt dialogs."""
from collections.abc import Callable

from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from core.common.background import BackgroundLoader
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


class QtDialogs:
    def __init__(self, window: QWidget, loader: BackgroundLoader, show_wizard: Callable[[], None]) -> None:
        self.window = window
        self.loader = loader
        self._show_wizard = show_wizard  # opening the wizard panel is the window's job

    def ask_symbol(self, title: str) -> str | None:
        dialog = SymbolDialog(self.window, title, self.loader)
        return dialog.symbol if dialog.exec() == QDialog.DialogCode.Accepted else None

    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self.window, 'Delete strategy', text) == QMessageBox.StandardButton.Yes

    def show_wizard(self) -> None:
        self._show_wizard()

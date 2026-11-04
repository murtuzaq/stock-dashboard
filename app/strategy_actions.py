"""What happens when the user picks a strategy action (from the Explorer's right-click menu or the results panel)."""
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from search import SearchBar
from strategy import repository


class SymbolDialog(QDialog):
    """Pick a stock with the same search bar as the top bar."""

    def __init__(self, parent: QWidget, title: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(760, 420)  # room for the results list under the search box
        self.symbol: str | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        self.search = SearchBar()
        self.search.symbol_chosen.connect(self._chosen)
        layout.addWidget(self.search)
        layout.addStretch()

    def _chosen(self, symbol: str) -> None:
        self.symbol = symbol
        self.accept()


class StrategyActions(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.explorer, self.wizard, self.view_area = window.explorer, window.wizard, window.view_area
        self.wizard.saved.connect(self._saved)
        self.wizard.closed.connect(self.wizard.hide)
        self.explorer.strategy_action.connect(self.handle)
        self.view_area.edit_strategy.connect(lambda strategy_id: self.handle('edit', self.view_area.symbol,
                                                                             strategy_id))

    def handle(self, action: str, symbol: str, strategy_id: str) -> None:
        getattr(self, action)(symbol, strategy_id)

    # --- actions (all take the stock the user was looking at, and the strategy id) ---

    def new(self, symbol: str, strategy_id: str) -> None:
        self.wizard.start_new(symbol)
        self.window.show_wizard()

    def edit(self, symbol: str, strategy_id: str) -> None:
        strategy = repository.get(strategy_id)
        if strategy:
            self.wizard.start_edit(strategy, symbol)
            self.window.show_wizard()

    def copy_here(self, symbol: str, strategy_id: str) -> None:
        """Library template -> this stock's own copy, opened for customising."""
        copy = repository.copy(strategy_id, symbol)
        self.explorer.refresh_strategies()
        self.explorer.select_strategy(symbol, copy.id)
        self.edit(symbol, copy.id)

    def duplicate(self, symbol: str, strategy_id: str) -> None:
        original = repository.get(strategy_id)
        copy = repository.copy(strategy_id, original.symbol, f'{original.name} (copy)')
        self.explorer.refresh_strategies()
        self.explorer.select_strategy(symbol, copy.id)

    def copy_to(self, symbol: str, strategy_id: str) -> None:
        target = self.ask_symbol('Copy the strategy to which stock?')
        if target:
            copy = repository.copy(strategy_id, target)
            self.explorer.add_symbol(target)
            self.explorer.refresh_strategies()
            self.explorer.select_strategy(target, copy.id)

    def save_to_library(self, symbol: str, strategy_id: str) -> None:
        repository.copy(strategy_id, None)
        self.explorer.refresh_strategies()

    def delete(self, symbol: str, strategy_id: str) -> None:
        strategy = repository.get(strategy_id)
        where = 'the library' if strategy.symbol is None else strategy.symbol
        if self.confirm(f'Delete "{strategy.name}" from {where}?\n\nThis removes its file from the strategies folder.'):
            repository.delete(strategy_id)
            self.explorer.refresh_strategies()

    # --- helpers (separate so tests can replace the dialogs) ---

    def ask_symbol(self, title: str) -> str | None:
        dialog = SymbolDialog(self.window, title)
        return dialog.symbol if dialog.exec() == QDialog.DialogCode.Accepted else None

    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self.window, 'Delete strategy', text) == QMessageBox.StandardButton.Yes

    def _saved(self, strategy) -> None:
        self.wizard.hide()
        symbol = strategy.symbol or self.wizard.symbol
        self.explorer.refresh_strategies()
        self.explorer.select_strategy(symbol, strategy.id)
        self.view_area.update_strategy()  # the rules may have changed under the same selection

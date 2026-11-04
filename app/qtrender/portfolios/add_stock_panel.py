"""The Add Stock panel (renderer): the search bar, what the portfolio holds so far, and a Done button.

Picking a stock in the search bar adds it at once; the search box clears and stays ready for the next one.
core.portfolios.add_stock.AddStockController decides what a pick means (AddStockView is what it needs from here).
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget

from core.common.background import BackgroundLoader
from qtrender.searchbar.bar import SearchBar


class AddStockPanel(QWidget):
    symbol_chosen = Signal(str)  # the user picked a stock in the search bar
    done_requested = Signal()
    closed = Signal()  # the panel should be dismissed

    def __init__(self, loader: BackgroundLoader) -> None:
        super().__init__()
        self.setObjectName('wizard')  # same look as the strategy builder panel
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setObjectName('chartTitle')
        layout.addWidget(self.title)
        hint = QLabel('Search a symbol or company and pick it to add it. Add as many as you like, then press Done.')
        hint.setObjectName('summary')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.search = SearchBar(loader)
        self.search.symbol_chosen.connect(self._chosen)
        layout.addWidget(self.search)
        self.notice = QLabel()
        self.notice.setObjectName('summary')
        layout.addWidget(self.notice)

        heading = QLabel('In this portfolio')
        heading.setObjectName('barLabel')
        layout.addWidget(heading)
        self.members = QListWidget()
        layout.addWidget(self.members, stretch=1)

        self.done_button = QPushButton('Done')
        self.done_button.setDefault(True)
        self.done_button.clicked.connect(self.done_requested)
        layout.addWidget(self.done_button)

    def _chosen(self, symbol: str) -> None:
        self.symbol_chosen.emit(symbol)
        self.search.input.setFocus()  # ready for the next one

    # --- AddStockView: what the controller (core.portfolios.add_stock) asks for ---

    def show_title(self, text: str) -> None:
        self.title.setText(text)
        self.search.input.setFocus()

    def show_members(self, symbols: list[str]) -> None:
        self.members.clear()
        self.members.addItems(symbols)
        self.members.scrollToBottom()  # the stock just added is last

    def show_notice(self, text: str) -> None:
        self.notice.setText(text)

    def close(self) -> None:
        self.closed.emit()

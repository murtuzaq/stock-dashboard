"""The window's menu bar. It only reports which item was chosen; the controllers decide what that does."""
from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMenuBar


class AppMenuBar(QMenuBar):
    new_portfolio_requested = Signal()
    load_portfolio_requested = Signal()
    exit_requested = Signal()
    info_wizard_toggled = Signal(bool)
    stock_library_requested = Signal()
    strategy_library_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        file_menu = self.addMenu('&File')
        self.new_action = file_menu.addAction('&New Portfolio')
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.new_portfolio_requested)
        self.load_action = file_menu.addAction('&Load Portfolio…')
        self.load_action.setShortcut(QKeySequence.StandardKey.Open)
        self.load_action.triggered.connect(self.load_portfolio_requested)
        file_menu.addSeparator()
        self.exit_action = file_menu.addAction('E&xit')
        self.exit_action.triggered.connect(self.exit_requested)

        view_menu = self.addMenu('&View')
        self.info_action = view_menu.addAction('&Info Wizard')
        self.info_action.setCheckable(True)
        self.info_action.setShortcut('Ctrl+I')
        self.info_action.setToolTip('Underline the terms that have an explanation; double-click one to learn about it')
        self.info_action.toggled.connect(self.info_wizard_toggled)

        tools_menu = self.addMenu('&Tools')
        self.stocks_action = tools_menu.addAction('&Stocks…')
        self.stocks_action.setShortcut('Ctrl+Shift+S')
        self.stocks_action.setToolTip('Every stock stored on this computer: add or update them, or put them in a portfolio')
        self.stocks_action.triggered.connect(self.stock_library_requested)
        self.strategies_action = tools_menu.addAction('S&trategies…')
        self.strategies_action.setShortcut('Ctrl+Shift+T')
        self.strategies_action.setToolTip('Every saved strategy: browse, try one on a stock, or create a template')
        self.strategies_action.triggered.connect(self.strategy_library_requested)

    def set_info_checked(self, checked: bool) -> None:
        """Show the checkbox state without reporting it as a user choice."""
        self.info_action.blockSignals(True)
        self.info_action.setChecked(checked)
        self.info_action.blockSignals(False)

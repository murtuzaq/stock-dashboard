"""The window's menu bar. It only reports which item was chosen; core.portfolios decides what that does."""
from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMenuBar


class AppMenuBar(QMenuBar):
    new_portfolio_requested = Signal()
    load_portfolio_requested = Signal()
    exit_requested = Signal()

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

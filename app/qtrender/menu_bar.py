"""The window's menu bar. It only reports which item was chosen; the controllers decide what that does."""
from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMenuBar


class AppMenuBar(QMenuBar):
    new_portfolio_requested = Signal()
    load_portfolio_requested = Signal()
    exit_requested = Signal()
    info_wizard_toggled = Signal(bool)

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

    def set_info_checked(self, checked: bool) -> None:
        """Show the checkbox state without reporting it as a user choice."""
        self.info_action.blockSignals(True)
        self.info_action.setChecked(checked)
        self.info_action.blockSignals(False)

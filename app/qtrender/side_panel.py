"""The panel on the right of the window: shows one page at a time (the strategy wizard, or Add Stock)."""
from PySide6.QtWidgets import QStackedWidget, QWidget


class SidePanel(QStackedWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumWidth(560)
        self.hide()

    def show_page(self, page: QWidget) -> None:
        self.setCurrentWidget(page)
        self.show()

    def dismiss(self) -> None:
        self.hide()

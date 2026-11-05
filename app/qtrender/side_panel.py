"""The dock on the right of the window: shows one page at a time (the strategy wizard, or Add Stock).

It is a real dock: it has a title bar with a close button, can be dragged to float and docked back, and is shown
only when something needs it.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QStackedWidget, QWidget

MINIMUM_WIDTH = 560


class SideDock(QDockWidget):
    def __init__(self) -> None:
        super().__init__('Strategy Builder')
        self.setObjectName('sideDock')
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable |
                         QDockWidget.DockWidgetFeature.DockWidgetMovable |
                         QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.stack = QStackedWidget()
        self.stack.setMinimumWidth(MINIMUM_WIDTH)
        self.setWidget(self.stack)
        self.titles: dict[QWidget, str] = {}
        self.hide()

    def add_page(self, page: QWidget, title: str) -> None:
        self.titles[page] = title
        self.stack.addWidget(page)

    def show_page(self, page: QWidget) -> None:
        self.stack.setCurrentWidget(page)
        self.setWindowTitle(self.titles[page])
        self.show()

    def dismiss(self) -> None:
        self.hide()

"""Stock Dashboard entry point. Run with: python app/main.py"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QSplitter

from explorer import Explorer
from header import TIMEFRAMES, Header
from strategy_actions import StrategyActions
from strategy_wizard import StrategyWizard
from view_area import ViewArea

STYLE = '''
QToolBar { background: #131722; border-bottom: 1px solid #2a2e39; padding: 6px; spacing: 8px; }
QLabel#appTitle { font-size: 15px; font-weight: 600; padding: 0 8px; }
QLineEdit { background: #1e222d; border: 1px solid #2a2e39; border-radius: 4px; padding: 5px 8px; }
QToolButton { padding: 4px 10px; border-radius: 4px; }
QToolButton:hover { background: #2a2e39; }
QToolButton:checked { background: #2962ff; color: white; }
QTreeWidget { background: #131722; border: none; }
QHeaderView::section { background: #131722; color: #787b86; border: none; padding: 8px; font-size: 11px; font-weight: 600; }
QSplitter::handle { background: #2a2e39; }
QLabel#placeholder { color: #787b86; font-size: 16px; }
QLabel#chartTitle { font-size: 14px; font-weight: 600; }
QLabel#lastPrice { font-size: 14px; padding-left: 12px; }
QLabel#summary { color: #787b86; padding: 2px 0 6px 0; }
QTableView#historyTable { background: #131722; alternate-background-color: #171b26; border: none; gridline-color: #1e222d; }
QTableView#historyTable::item:selected { background: #2a2e39; color: #d1d4dc; }
QLabel#indicatorLegend { font-size: 12px; padding: 2px 4px; }
QWidget#wizard { background: #171b26; border-left: 1px solid #2a2e39; }
QFrame#ruleRow { background: #1e222d; border: 1px solid #2a2e39; border-radius: 4px; }
QComboBox, QSpinBox, QDoubleSpinBox { background: #1e222d; border: 1px solid #2a2e39; border-radius: 3px; padding: 3px 6px; }
QPushButton { background: #2a2e39; border: none; border-radius: 4px; padding: 5px 12px; }
QPushButton:hover { background: #363a45; }
QPushButton:default { background: #2962ff; color: white; }
QLabel#barLabel { color: #787b86; font-size: 11px; font-weight: 600; padding-right: 4px; }
QPushButton#scopeChip { background: #2962ff; color: white; border: none; border-radius: 4px; padding: 5px 10px; }
QPushButton#scopeChip:hover { background: #1e53e5; }
QTreeWidget#searchResults { background: #1e222d; border: 1px solid #2a2e39; border-radius: 4px; padding: 4px; }
QTreeWidget#searchResults::item { height: 26px; }
QTreeWidget#searchResults::item:selected { background: #2a2e39; color: #d1d4dc; }
'''


def dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor('#131722'))
    palette.setColor(QPalette.ColorRole.Base, QColor('#131722'))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor('#1e222d'))
    palette.setColor(QPalette.ColorRole.WindowText, QColor('#d1d4dc'))
    palette.setColor(QPalette.ColorRole.Text, QColor('#d1d4dc'))
    palette.setColor(QPalette.ColorRole.Button, QColor('#1e222d'))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor('#d1d4dc'))
    palette.setColor(QPalette.ColorRole.Highlight, QColor('#2962ff'))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor('white'))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor('#787b86'))
    return palette


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('Stock Dashboard')
        self.resize(1400, 850)
        self.symbol: str | None = None
        self.views: list[str] = []
        self.timeframe = TIMEFRAMES[0]

        self.header = Header()
        self.addToolBar(self.header)
        self.explorer = Explorer()
        self.view_area = ViewArea()
        self.wizard = StrategyWizard()  # third panel, shown only while creating or editing a strategy
        self.wizard.hide()

        self.splitter = splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.explorer)
        splitter.addWidget(self.view_area)
        splitter.addWidget(self.wizard)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(2, False)
        splitter.setSizes([240, 1160, 0])
        self.setCentralWidget(splitter)

        self.header.symbol_searched.connect(self.explorer.add_symbol)
        self.header.timeframe_changed.connect(self.on_timeframe)
        self.explorer.views_selected.connect(self.on_select)
        self.strategy_actions = StrategyActions(self)

    def show_wizard(self) -> None:
        """Open the Strategy Builder as a third panel on the right, taking room from the charts."""
        explorer, charts, wizard = self.splitter.sizes()
        if not self.wizard.isVisible() or wizard < self.wizard.minimumWidth():
            width = max(self.wizard.minimumWidth(), 620)
            self.wizard.show()
            self.splitter.setSizes([explorer, max(charts + wizard - width, 300), width])

    def on_select(self, symbol: str, views: list[str]) -> None:
        self.symbol, self.views = symbol, views
        self.view_area.show_views(symbol, views, self.timeframe)

    def on_timeframe(self, timeframe: str) -> None:
        self.timeframe = timeframe
        if self.symbol:
            self.view_area.show_views(self.symbol, self.views, timeframe)


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setPalette(dark_palette())
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

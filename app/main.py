"""Stock Dashboard entry point. Run with: python app/main.py"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QSplitter

from chart_view import ChartView
from explorer import Explorer
from header import TIMEFRAMES, Header

STYLE = '''
QToolBar { background: #131722; border-bottom: 1px solid #2a2e39; padding: 6px; spacing: 8px; }
QLabel#appTitle { font-size: 15px; font-weight: 600; padding: 0 8px; }
QLineEdit { background: #1e222d; border: 1px solid #2a2e39; border-radius: 4px; padding: 5px 8px; }
QToolButton { padding: 4px 10px; border-radius: 4px; }
QToolButton:checked { background: #2962ff; color: white; }
QTreeWidget { background: #131722; border: none; }
QHeaderView::section { background: #131722; color: #787b86; border: none; padding: 8px; font-size: 11px; font-weight: 600; }
QSplitter::handle { background: #2a2e39; }
QLabel#placeholder { color: #787b86; font-size: 16px; }
QLabel#chartTitle { font-size: 14px; font-weight: 600; }
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
        self.view: str | None = None
        self.timeframe = TIMEFRAMES[0]

        self.header = Header()
        self.addToolBar(self.header)
        self.explorer = Explorer()
        self.chart_view = ChartView()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.explorer)
        splitter.addWidget(self.chart_view)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 1160])
        self.setCentralWidget(splitter)

        self.header.symbol_searched.connect(self.explorer.add_symbol)
        self.header.timeframe_changed.connect(self.on_timeframe)
        self.explorer.view_selected.connect(self.on_select)

    def on_select(self, symbol: str, view: str) -> None:
        self.symbol, self.view = symbol, view
        self.chart_view.show_view(symbol, view, self.timeframe)

    def on_timeframe(self, timeframe: str) -> None:
        self.timeframe = timeframe
        if self.symbol:
            self.chart_view.show_view(self.symbol, self.view, timeframe)


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

"""Application look: the dark stylesheet and palette."""
from PySide6.QtGui import QColor, QPalette

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

"""Top bar: app name, symbol search and timeframe selector."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QLabel, QSizePolicy, QToolBar, QToolButton, QWidget

from search import SearchBar

# Candle sizes. Only daily candles will be downloaded; the rest are built from them.
TIMEFRAMES = ['1D', '1W', '2W', '1M', '3M']


class Header(QToolBar):
    symbol_searched = Signal(str)
    timeframe_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__('Top bar')
        self.setMovable(False)

        title = QLabel('Stock Dashboard')
        title.setObjectName('appTitle')
        self.addWidget(title)
        self.addSeparator()

        self.search = SearchBar()
        self.search.symbol_chosen.connect(self.symbol_searched)
        self.addWidget(self.search)
        self.addSeparator()

        self.candle_label = QLabel('Candle')
        self.candle_label.setObjectName('barLabel')
        self.candle_label.setToolTip('How much time each candle covers')
        self.addWidget(self.candle_label)
        self.timeframes = QButtonGroup(self)
        self.timeframes.setExclusive(True)
        for timeframe in TIMEFRAMES:
            button = QToolButton()
            button.setText(timeframe)
            button.setCheckable(True)
            button.setChecked(timeframe == TIMEFRAMES[0])
            self.timeframes.addButton(button)
            self.addWidget(button)
        self.timeframes.buttonClicked.connect(lambda button: self.timeframe_changed.emit(button.text()))

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

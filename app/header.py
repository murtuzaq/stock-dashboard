"""Top bar: app name, symbol search and timeframe selector."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QLabel, QLineEdit, QToolBar, QToolButton, QWidget, QSizePolicy

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

        self.search = QLineEdit()
        self.search.setPlaceholderText('Search symbol (e.g. AAPL)')
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(240)
        self.search.returnPressed.connect(self._submit)
        self.addWidget(self.search)
        self.addSeparator()

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

    def _submit(self) -> None:
        symbol = self.search.text().strip().upper()
        if symbol:
            self.symbol_searched.emit(symbol)
            self.search.clear()

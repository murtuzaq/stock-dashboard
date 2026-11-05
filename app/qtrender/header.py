"""Top bar: app name, symbol search and timeframe selector."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QLabel, QSizePolicy, QToolBar, QToolButton, QWidget

from core.dashboard.layout import TIMEFRAMES
from core.learn import ui_terms
from qtrender.learn import info_mode
from qtrender.searchbar.bar import SearchBar


class Header(QToolBar):
    symbol_searched = Signal(str)
    timeframe_changed = Signal(str)

    def __init__(self, search: SearchBar) -> None:
        super().__init__('Top bar')
        self.setMovable(False)

        title = QLabel('Stock Dashboard')
        title.setObjectName('appTitle')
        self.addWidget(title)
        self.addSeparator()

        self.search = search
        self.search.symbol_chosen.connect(self.symbol_searched)
        self.addWidget(self.search)
        self.addSeparator()

        self.candle_label = QLabel('Candle')
        self.candle_label.setObjectName('barLabel')
        self.candle_label.setToolTip('How much time each candle covers')
        if info_mode.current():
            info_mode.current().mark(self.candle_label, ui_terms.LABELS['Candle'], 'candle size buttons')
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

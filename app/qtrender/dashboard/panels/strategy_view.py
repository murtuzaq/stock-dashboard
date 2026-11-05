"""Strategy results: settings, a performance summary, the equity curve versus buy & hold, and every trade."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDoubleSpinBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.learn import ui_terms
from core.strategies.results import TRADE_COLUMNS, equity_curves, result_cards, rules_line, trade_rows
from core.common.theme import EQUITY_COLOR, GRID_TEXT, HOLD_COLOR
from qtrender.dashboard.chart_view import TimePlot
from qtrender.learn import info_mode
from qtrender.learn.headers import mark_table_headers
from qtrender.learn.info_label import InfoLabel
from strategy import Costs, Strategy
from strategy.backtest import BacktestResult

OPEN_TRADE_BACKGROUND = '#1e2a4a'


class EquityPlot(TimePlot):
    """Account value at each candle close, against buying and holding. Lines up with the other charts."""

    def __init__(self) -> None:
        super().__init__()
        self.showGrid(x=False, y=True, alpha=0.15)
        self.getViewBox().setAutoVisible(y=True)
        self.enableAutoRange(axis='y')
        self.hold_line = self.plot(pen=pg.mkPen(HOLD_COLOR, width=1.5, style=Qt.PenStyle.DashLine), connect='finite')
        self.equity_line = self.plot(pen=pg.mkPen(EQUITY_COLOR, width=2), connect='finite')
        self.legend = pg.LegendItem(offset=(10, 6), labelTextColor=GRID_TEXT, brush=pg.mkBrush(19, 23, 34, 200),
                                    colCount=2)
        self.legend.setParentItem(self.getPlotItem())
        self.legend.addItem(self.equity_line, 'Strategy')
        self.legend.addItem(self.hold_line, 'Buy & hold')

    def set_values(self, dates: pd.DatetimeIndex, result: BacktestResult) -> None:
        self.set_dates(dates)
        slots = np.arange(len(dates))
        equity, hold = equity_curves(result)
        self.equity_line.setData(slots, equity)
        self.hold_line.setData(slots, hold)


class StrategyView(QWidget):
    costs_changed = Signal(object)  # Costs, after the user edits capital / commission / slippage
    edit_requested = Signal(str)  # strategy id

    def __init__(self) -> None:
        super().__init__()
        self.strategy: Strategy | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        self.rules = InfoLabel('strategy rules')
        self.rules.setObjectName('summary')
        self.rules.setWordWrap(True)
        top.addWidget(self.rules, stretch=1)
        self.edit_button = QPushButton('Edit rules…')
        self.edit_button.clicked.connect(lambda: self.strategy and self.edit_requested.emit(self.strategy.id))
        top.addWidget(self.edit_button, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        layout.addLayout(self._build_settings())
        self.cards = InfoLabel('strategy summary')
        self.cards.setObjectName('indicatorLegend')
        layout.addWidget(self.cards)

        split = QSplitter(Qt.Orientation.Vertical)
        self.plot_widget = EquityPlot()  # named like the other views so the time axes get linked
        split.addWidget(self.plot_widget)
        self.table = QTableWidget(0, len(TRADE_COLUMNS))
        self.table.setObjectName('historyTable')
        self.table.setHorizontalHeaderLabels(TRADE_COLUMNS)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        mark_table_headers(self.table, 'trade table')
        split.addWidget(self.table)
        split.setSizes([300, 200])
        layout.addWidget(split, stretch=1)

    def _build_settings(self) -> QGridLayout:
        grid = QGridLayout()
        self.capital = self._spin(100, 100_000_000, 0, '$ ', 1000, 'Starting cash')
        self.commission = self._spin(0, 1000, 2, '$ ', 1, 'Paid on every buy and every sell')
        self.slippage = self._spin(0, 5, 3, '', 0.01, 'Each fill is this % worse than the open (spread, market impact)')
        self.slippage.setSuffix(' %')
        for column, (label, spin) in enumerate((('Capital', self.capital), ('Commission / trade', self.commission),
                                                ('Slippage', self.slippage))):
            caption = QLabel(label)
            caption.setObjectName('barLabel')
            if info_mode.current() and label in ui_terms.LABELS:
                info_mode.current().mark(caption, ui_terms.LABELS[label], 'strategy settings')
            grid.addWidget(caption, 0, column * 2)
            grid.addWidget(spin, 0, column * 2 + 1)
        grid.setColumnStretch(6, 1)
        return grid

    def _spin(self, low, high, decimals, prefix, step, tip) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(decimals)
        spin.setPrefix(prefix)
        spin.setSingleStep(step)
        spin.setToolTip(tip)
        spin.setGroupSeparatorShown(True)
        spin.editingFinished.connect(self._emit_costs)
        return spin

    def _emit_costs(self) -> None:
        if self.strategy is None:
            return
        costs = Costs(self.capital.value(), self.commission.value(), self.slippage.value())
        if costs != self.strategy.costs:
            self.costs_changed.emit(costs)

    # --- showing results ---

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        pass  # results arrive through show_result()

    def set_range(self, start: pd.Timestamp) -> None:
        self.plot_widget.set_range(start)

    def show_result(self, strategy: Strategy, result: BacktestResult) -> None:
        self.strategy = strategy
        self.rules.set_line(rules_line(strategy))
        for spin, value in ((self.capital, strategy.costs.capital), (self.commission, strategy.costs.commission),
                            (self.slippage, strategy.costs.slippage_pct)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.plot_widget.set_values(result.dates, result)
        self.plot_widget.set_range(result.start)
        self.cards.set_line(result_cards(result))
        self._show_trades(result)

    def _show_trades(self, result: BacktestResult) -> None:
        rows = trade_rows(result)
        self.table.setRowCount(len(rows))
        for row, trade in enumerate(rows):
            for column, cell in enumerate(trade.cells):
                item = QTableWidgetItem(cell.text)
                if cell.align_right:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if cell.color:
                    item.setForeground(QColor(cell.color))
                if trade.is_open:
                    item.setBackground(QColor(OPEN_TRADE_BACKGROUND))
                if cell.tooltip:
                    item.setToolTip(cell.tooltip)
                self.table.setItem(row, column, item)
        self.table.scrollToBottom()

"""Strategy results: settings, a performance summary, the equity curve versus buy & hold, and every trade."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDoubleSpinBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from chart_view import DOWN, GRID_TEXT, UP, TimePlot
from strategy import Costs, Strategy, describe
from strategy.backtest import BacktestResult

EQUITY_COLOR = '#2962ff'
HOLD_COLOR = '#787b86'
TRADE_COLUMNS = ['#', 'BUY signal', 'Bought', 'Buy price', 'SELL signal', 'Sold', 'Sell price', 'Shares',
                 'P/L $', 'P/L %', 'Exit reason']


def money(value: float) -> str:
    return f'-${-value:,.2f}' if value < 0 else f'${value:,.2f}'


def colored(text: str, value: float) -> str:
    return f'<span style="color:{UP if value >= 0 else DOWN}">{text}</span>'


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
        equity, hold = np.full(len(dates), np.nan), np.full(len(dates), np.nan)
        equity[result.first_slot:] = result.equity.to_numpy()
        hold[result.first_slot:] = result.buy_hold.to_numpy()
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
        self.rules = QLabel()
        self.rules.setObjectName('summary')
        self.rules.setWordWrap(True)
        top.addWidget(self.rules, stretch=1)
        self.edit_button = QPushButton('Edit rules…')
        self.edit_button.clicked.connect(lambda: self.strategy and self.edit_requested.emit(self.strategy.id))
        top.addWidget(self.edit_button, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        layout.addLayout(self._build_settings())
        self.cards = QLabel()
        self.cards.setObjectName('indicatorLegend')
        self.cards.setTextFormat(Qt.TextFormat.RichText)
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
        where = 'library template' if strategy.symbol is None else strategy.symbol
        self.rules.setText(f'<b>{strategy.name}</b> <span style="color:#787b86">({where})</span><br>'
                           + describe(strategy).replace('\n', '<br>'))
        for spin, value in ((self.capital, strategy.costs.capital), (self.commission, strategy.costs.commission),
                            (self.slippage, strategy.costs.slippage_pct)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.plot_widget.set_values(result.dates, result)
        self.plot_widget.set_range(result.start)
        self._show_cards(result)
        self._show_trades(result)

    def _show_cards(self, result: BacktestResult) -> None:
        m = result.metrics
        win_rate = '—' if m['win_rate_pct'] is None else f'{m["win_rate_pct"]:.0f}%'
        versus = m['return_pct'] - m['buy_hold_return_pct']
        parts = [
            f'Return {colored(f"{m["return_pct"]:+.2f}%", m["return_pct"])} '
            f'({colored(money(m["pnl"]), m["pnl"])}) → {money(m["end_capital"])}',
            f'Buy & hold {colored(f"{m["buy_hold_return_pct"]:+.2f}%", m["buy_hold_return_pct"])} '
            f'({colored(f"{versus:+.1f} pts", versus)})',
            f'Trades {m["trades"]} ({m["wins"]} won, {m["losses"]} lost, win rate {win_rate})',
            f'Max drawdown {m["max_drawdown_pct"]:.1f}% (hold {m["buy_hold_max_drawdown_pct"]:.1f}%)',
            f'In market {m["time_in_market_pct"]:.0f}%',
        ]
        if result.open_trade:
            parts.append(f'Open position {colored(money(m["unrealized_pnl"]), m["unrealized_pnl"])} unrealized')
        if result.pending:
            parts.append(f'<span style="color:#f7c948">{result.pending}</span>')
        self.cards.setText(' · '.join(parts))

    def _show_trades(self, result: BacktestResult) -> None:
        dates = result.dates
        day = lambda slot: '' if slot is None else f'{dates[slot]:%Y-%m-%d}'
        self.table.setRowCount(len(result.trades))
        for row, trade in enumerate(result.trades):
            values = [str(row + 1), day(trade.signal_slot), day(trade.entry_slot), f'{trade.entry_price:,.2f}',
                      day(trade.exit_signal_slot), 'still open' if trade.is_open else day(trade.exit_slot),
                      f'{trade.exit_price:,.2f}' + (' (last close)' if trade.is_open else ''), f'{trade.shares:,}',
                      money(trade.pnl), f'{trade.pnl_pct:+.2f}%',
                      'unrealized' if trade.is_open else trade.exit_reason]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column in (3, 6, 7, 8, 9):  # numbers
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if column in (8, 9):
                    item.setForeground(QColor(UP if trade.pnl >= 0 else DOWN))
                if trade.is_open:
                    item.setBackground(QColor('#1e2a4a'))
                    item.setToolTip('Still open at the end of the backtest: valued at the last close (unrealized)')
                self.table.setItem(row, column, item)
        self.table.scrollToBottom()

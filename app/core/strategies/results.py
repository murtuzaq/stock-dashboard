"""A backtest result as text and numbers ready to draw: the rules heading, the summary cards, the trade table."""
from dataclasses import dataclass

import numpy as np

from core.common import theme
from core.common.formatting import Cell, Line, Span, money, plain
from strategy import Strategy, describe
from strategy.backtest import BacktestResult

TRADE_COLUMNS = ['#', 'BUY signal', 'Bought', 'Buy price', 'SELL signal', 'Sold', 'Sell price', 'Shares',
                 'P/L $', 'P/L %', 'Exit reason']
OPEN_TRADE_TIP = 'Still open at the end of the backtest: valued at the last close (unrealized)'
_NUMBER_COLUMNS = (3, 6, 7, 8, 9)
_PNL_COLUMNS = (8, 9)


def _colored(text: str, value: float) -> Span:
    return Span(text, theme.change_color(value))


def rules_line(strategy: Strategy) -> Line:
    """Name, where it lives, then the rules in plain English."""
    where = 'library template' if strategy.symbol is None else strategy.symbol
    return [Span(strategy.name, bold=True), plain(' '), Span(f'({where})', theme.MUTED), plain('\n'),
            plain(describe(strategy))]


def result_cards(result: BacktestResult) -> Line:
    m = result.metrics
    win_rate = '—' if m['win_rate_pct'] is None else f'{m["win_rate_pct"]:.0f}%'
    versus = m['return_pct'] - m['buy_hold_return_pct']
    parts: list[Line] = [
        [plain('Return '), _colored(f'{m["return_pct"]:+.2f}%', m['return_pct']), plain(' ('),
         _colored(money(m['pnl']), m['pnl']), plain(f') → {money(m["end_capital"])}')],
        [plain('Buy & hold '), _colored(f'{m["buy_hold_return_pct"]:+.2f}%', m['buy_hold_return_pct']), plain(' ('),
         _colored(f'{versus:+.1f} pts', versus), plain(')')],
        [plain(f'Trades {m["trades"]} ({m["wins"]} won, {m["losses"]} lost, win rate {win_rate})')],
        [plain(f'Max drawdown {m["max_drawdown_pct"]:.1f}% (hold {m["buy_hold_max_drawdown_pct"]:.1f}%)')],
        [plain(f'In market {m["time_in_market_pct"]:.0f}%')],
    ]
    if result.open_trade:
        parts.append([plain('Open position '), _colored(money(m['unrealized_pnl']), m['unrealized_pnl']),
                      plain(' unrealized')])
    if result.pending:
        parts.append([Span(result.pending, theme.WARNING)])
    line: Line = []
    for index, part in enumerate(parts):
        if index:
            line.append(plain(' · '))
        line.extend(part)
    return line


@dataclass
class TradeRow:
    cells: list[Cell]
    is_open: bool


def trade_rows(result: BacktestResult) -> list[TradeRow]:
    dates = result.dates

    def day(slot: int | None) -> str:
        return '' if slot is None else f'{dates[slot]:%Y-%m-%d}'

    rows = []
    for number, trade in enumerate(result.trades, start=1):
        values = [str(number), day(trade.signal_slot), day(trade.entry_slot), f'{trade.entry_price:,.2f}',
                  day(trade.exit_signal_slot), 'still open' if trade.is_open else day(trade.exit_slot),
                  f'{trade.exit_price:,.2f}' + (' (last close)' if trade.is_open else ''), f'{trade.shares:,}',
                  money(trade.pnl), f'{trade.pnl_pct:+.2f}%',
                  'unrealized' if trade.is_open else trade.exit_reason]
        cells = []
        for column, text in enumerate(values):
            color = theme.change_color(trade.pnl) if column in _PNL_COLUMNS else None
            tooltip = OPEN_TRADE_TIP if trade.is_open else None
            cells.append(Cell(text, color, tooltip, align_right=column in _NUMBER_COLUMNS))
        rows.append(TradeRow(cells, trade.is_open))
    return rows


def equity_curves(result: BacktestResult) -> tuple[np.ndarray, np.ndarray]:
    """Strategy and buy-and-hold account value per candle (NaN before the range starts)."""
    count = len(result.dates)
    equity, hold = np.full(count, np.nan), np.full(count, np.nan)
    equity[result.first_slot:] = result.equity.to_numpy()
    hold[result.first_slot:] = result.buy_hold.to_numpy()
    return equity, hold

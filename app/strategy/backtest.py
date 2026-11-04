"""Simulates a strategy's trades on historical candles and measures how it did.

Execution rules (chosen to avoid look-ahead and to be slightly conservative):
- Signals are judged at a candle's close; the trade fills at the NEXT candle's open.
- Fills are worse than the open by the slippage %, and each buy or sell pays the commission.
- Whole shares only, all available cash, long-only, one position at a time.
- While a trade is open, stop-loss / ATR stop / take-profit are checked inside every candle (from the entry
  candle on) using its high and low. A candle that opens beyond the level fills at the open (a gap).
  If the stop and the target are both touched in one candle, the stop is assumed to have come first.
- Trades can only open inside the selected range; earlier candles just warm up the indicators.
- A position still open at the end is valued at the last close and reported as unrealized.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .model import Operand, Strategy
from .signals import SeriesCache, evaluate


@dataclass
class Trade:
    signal_slot: int  # candle whose close produced the BUY signal
    entry_slot: int  # candle whose open the buy filled at
    entry_price: float
    shares: int
    entry_reason: str
    stop_price: float | None = None
    stop_reason: str | None = None  # 'stop-loss' or 'ATR stop', whichever set stop_price
    target_price: float | None = None
    exit_signal_slot: int | None = None  # candle whose close produced the SELL signal (None for stops)
    exit_slot: int | None = None  # candle the sell filled in (for open trades: the last candle)
    exit_price: float | None = None  # for open trades: the last close
    exit_reason: str | None = None
    is_open: bool = False
    entry_commission: float = 0.0
    exit_commission: float = 0.0  # stays 0 while open: an open position is valued at the last close

    @property
    def cost(self) -> float:
        return self.shares * self.entry_price + self.entry_commission

    @property
    def proceeds(self) -> float:
        return self.shares * self.exit_price - self.exit_commission

    @property
    def pnl(self) -> float:
        return self.proceeds - self.cost

    @property
    def pnl_pct(self) -> float:
        return self.pnl / self.cost * 100


@dataclass
class BacktestResult:
    symbol: str | None
    strategy_name: str
    strategy_hash: str
    candle_size: str
    start: pd.Timestamp
    dates: pd.DatetimeIndex  # all candles (slot i = dates[i]); trades refer to slots
    first_slot: int  # first candle inside the range
    trades: list[Trade]  # closed trades, then the open one (if any) last
    equity: pd.Series  # account value at each candle close inside the range
    buy_hold: pd.Series  # the same for buying at the range's first open and holding
    signals: pd.DataFrame
    pending: str | None = None  # a signal on the last candle that would trade at the next open
    metrics: dict = field(default_factory=dict)

    @property
    def closed_trades(self) -> list[Trade]:
        return [t for t in self.trades if not t.is_open]

    @property
    def open_trade(self) -> Trade | None:
        return self.trades[-1] if self.trades and self.trades[-1].is_open else None


def strategy_hash(strategy: Strategy) -> str:
    """Identifies the rules, exits and costs, so cached results are dropped when any of them change."""
    data = {k: v for k, v in strategy.to_dict().items() if k in ('buy', 'sell', 'exits', 'costs')}
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


def _shares_affordable(cash: float, price: float, commission: float) -> int:
    return max(0, math.floor((cash - commission) / price)) if price > 0 else 0


def run(strategy: Strategy, candles: pd.DataFrame, benchmark: pd.DataFrame | None, start: pd.Timestamp,
        symbol: str | None = None) -> BacktestResult:
    signals = evaluate(strategy, candles, benchmark)
    costs, exits = strategy.costs, strategy.exits
    slip = costs.slippage_pct / 100
    atr = SeriesCache(candles, benchmark).series(Operand('atr')).to_numpy() if exits.atr_stop_multiple else None
    opens, highs, lows, closes = (candles[c].to_numpy(dtype=float) for c in ('open', 'high', 'low', 'close'))
    buys, sells = signals['buy_signal'].to_numpy(), signals['sell_signal'].to_numpy()
    first = int(candles.index.searchsorted(start))
    last = len(candles) - 1

    cash, position = costs.capital, None
    trades: list[Trade] = []
    pending_buy: int | None = None  # slot of the BUY signal waiting for the next open
    pending_sell: int | None = None
    equity = np.full(len(candles), np.nan)

    def close_position(slot: int, price: float, reason: str, signal_slot: int | None = None) -> None:
        nonlocal cash, position
        position.exit_slot, position.exit_price = slot, price
        position.exit_reason, position.exit_signal_slot = reason, signal_slot
        position.exit_commission = costs.commission
        cash += position.shares * price - costs.commission
        position = None

    for i in range(first, last + 1):
        # 1. Orders from yesterday's signals fill at today's open.
        if pending_sell is not None and position:
            close_position(i, opens[i] * (1 - slip), 'SELL rules', pending_sell)
        if pending_buy is not None and position is None:
            price = opens[i] * (1 + slip)
            shares = _shares_affordable(cash, price, costs.commission)
            if shares:
                stops = []
                if exits.stop_loss_pct:
                    stops.append((price * (1 - exits.stop_loss_pct / 100), 'stop-loss'))
                if exits.atr_stop_multiple and not np.isnan(atr[pending_buy]):
                    stops.append((price - exits.atr_stop_multiple * atr[pending_buy], 'ATR stop'))
                stop_price, stop_reason = max(stops) if stops else (None, None)  # the tighter stop wins
                target = price * (1 + exits.take_profit_pct / 100) if exits.take_profit_pct else None
                position = Trade(pending_buy, i, price, shares, 'BUY rules', stop_price, stop_reason, target,
                                 entry_commission=costs.commission)
                cash -= shares * price + costs.commission
                trades.append(position)
        pending_buy = pending_sell = None

        # 2. Stops and targets inside the candle (stop first if both are touched).
        if position and position.stop_price is not None and lows[i] <= position.stop_price:
            close_position(i, min(opens[i], position.stop_price) * (1 - slip), position.stop_reason)
        elif position and position.target_price is not None and highs[i] >= position.target_price:
            close_position(i, max(opens[i], position.target_price) * (1 - slip), 'take-profit')

        # 3. Signals at today's close become orders for tomorrow's open.
        if i < last:
            if position and sells[i]:
                pending_sell = i
            elif position is None and buys[i]:
                pending_buy = i

        equity[i] = cash + (position.shares * closes[i] if position else 0.0)

    pending = None
    if position is None and buys[last] and last >= first:
        pending = 'BUY signal on the last candle: would buy at the next open'
    elif position and sells[last]:
        pending = 'SELL signal on the last candle: would sell at the next open'
    if position:
        position.is_open, position.exit_slot, position.exit_price = True, last, closes[last]
        position.exit_reason = 'still open'

    in_range = candles.index[first:]
    equity_series = pd.Series(equity[first:], index=in_range)
    buy_hold = _buy_and_hold(opens, closes, first, costs.capital, slip, costs.commission, in_range)
    result = BacktestResult(symbol, strategy.name, strategy_hash(strategy), candles.attrs.get('candle_size', '1D'),
                            start, candles.index, first, trades, equity_series, buy_hold, signals, pending)
    result.metrics = _metrics(result, costs.capital, in_position_candles=_candles_in_position(trades, first, last))
    return result


def _buy_and_hold(opens, closes, first, capital, slip, commission, index) -> pd.Series:
    if first >= len(opens):
        return pd.Series(dtype=float)
    price = opens[first] * (1 + slip)
    shares = _shares_affordable(capital, price, commission)
    cash = capital - shares * price - (commission if shares else 0)
    return pd.Series(cash + shares * closes[first:], index=index)


def _candles_in_position(trades: list[Trade], first: int, last: int) -> int:
    return sum(min(t.exit_slot, last) - t.entry_slot + 1 for t in trades if t.exit_slot is not None)


def _max_drawdown_pct(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peaks = equity.cummax()
    return float(((equity - peaks) / peaks).min() * 100)


def _metrics(result: BacktestResult, capital: float, in_position_candles: int) -> dict:
    closed = result.closed_trades
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    end = float(result.equity.iloc[-1]) if len(result.equity) else capital
    hold_end = float(result.buy_hold.iloc[-1]) if len(result.buy_hold) else capital
    candles_in_range = len(result.equity)
    return {
        'start_capital': capital,
        'end_capital': end,
        'pnl': end - capital,
        'return_pct': (end / capital - 1) * 100,
        'trades': len(closed),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate_pct': len(wins) / len(closed) * 100 if closed else None,
        'average_win_pct': float(np.mean([t.pnl_pct for t in wins])) if wins else None,
        'average_loss_pct': float(np.mean([t.pnl_pct for t in losses])) if losses else None,
        'max_drawdown_pct': _max_drawdown_pct(result.equity),
        'time_in_market_pct': in_position_candles / candles_in_range * 100 if candles_in_range else 0.0,
        'unrealized_pnl': result.open_trade.pnl if result.open_trade else 0.0,
        'buy_hold_end': hold_end,
        'buy_hold_return_pct': (hold_end / capital - 1) * 100,
        'buy_hold_max_drawdown_pct': _max_drawdown_pct(result.buy_hold),
    }

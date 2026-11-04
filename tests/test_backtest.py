"""Backtest simulation, checked against hand-calculated trades on tiny made-up price series."""
import numpy as np
import pandas as pd
import pytest

from conftest import indicator, number, random_walk
from strategy import Condition, Costs, Exits, RuleGroup, Strategy
from strategy.backtest import run
from strategy.signals import SeriesCache


def candles_from(opens, closes, highs=None, lows=None, start='2024-01-01'):
    opens, closes = np.asarray(opens, float), np.asarray(closes, float)
    highs = np.maximum(opens, closes) + 0.5 if highs is None else np.asarray(highs, float)
    lows = np.minimum(opens, closes) - 0.5 if lows is None else np.asarray(lows, float)
    index = pd.bdate_range(start, periods=len(closes), name='date')
    candles = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes,
                            'volume': np.full(len(closes), 1000.0)}, index=index)
    candles.attrs['candle_size'] = '1D'
    return candles


def cross_strategy(level=10.0, exits=None, costs=None) -> Strategy:
    """BUY when the close crosses above `level`, SELL when it crosses back below."""
    return Strategy('cross', RuleGroup('all', [Condition(indicator('close'), 'crosses_above', number(level))]),
                    RuleGroup('all', [Condition(indicator('close'), 'crosses_below', number(level))]),
                    exits or Exits(), costs or Costs(capital=1000, commission=0, slippage_pct=0))


# signal BUY on day 1 (close 11 > 10), SELL signal on day 4 (close 9 < 10)
OPENS = [9, 10.5, 11.5, 12.5, 12, 8.5]
CLOSES = [9, 11, 12, 13, 9, 8]


def test_trades_fill_at_the_next_candles_open():
    candles = candles_from(OPENS, CLOSES)
    result = run(cross_strategy(), candles, None, candles.index[0])
    [trade] = result.trades
    assert (trade.signal_slot, trade.entry_slot, trade.entry_price, trade.shares) == (1, 2, 11.5, 86)
    assert (trade.exit_signal_slot, trade.exit_slot, trade.exit_price, trade.exit_reason) == (4, 5, 8.5, 'SELL rules')
    assert trade.pnl == pytest.approx(86 * (8.5 - 11.5))
    assert result.equity.iloc[-1] == pytest.approx(1000 - 86 * 11.5 + 86 * 8.5)
    assert result.equity.iloc[2] == pytest.approx(1000 - 86 * 11.5 + 86 * 12)  # marked at the close
    assert result.metrics['trades'] == 1 and result.metrics['losses'] == 1 and result.metrics['win_rate_pct'] == 0


def test_slippage_and_commission_make_fills_worse():
    candles = candles_from(OPENS, CLOSES)
    result = run(cross_strategy(costs=Costs(capital=1000, commission=5, slippage_pct=1)), candles, None,
                 candles.index[0])
    [trade] = result.trades
    buy, sell = 11.5 * 1.01, 8.5 * 0.99
    shares = int((1000 - 5) // buy)
    assert trade.entry_price == pytest.approx(buy) and trade.exit_price == pytest.approx(sell)
    assert trade.shares == shares
    assert trade.pnl == pytest.approx(shares * sell - 5 - (shares * buy + 5))
    assert result.metrics['end_capital'] == pytest.approx(1000 + trade.pnl)


def test_a_gap_below_the_stop_fills_at_the_open():
    # entry at 11.5 with a 10% stop = 10.35; day 3 opens at 9 (gapped through), so the fill is 9, not 10.35
    candles = candles_from([9, 10.5, 11.5, 9, 9], [9, 11, 12, 9.5, 9])
    [trade] = run(cross_strategy(exits=Exits(stop_loss_pct=10)), candles, None, candles.index[0]).trades
    assert trade.stop_price == pytest.approx(10.35)
    assert (trade.exit_slot, trade.exit_price, trade.exit_reason) == (3, 9, 'stop-loss')


def test_a_stop_inside_the_candle_fills_at_the_stop():
    candles = candles_from([9, 10.5, 11.5, 11.8], [9, 11, 12, 11], lows=[8.5, 10, 11, 10])
    [trade] = run(cross_strategy(exits=Exits(stop_loss_pct=10)), candles, None, candles.index[0]).trades
    assert (trade.exit_slot, trade.exit_price) == (3, pytest.approx(10.35))


def test_stop_is_assumed_first_when_stop_and_target_hit_in_one_candle():
    candles = candles_from([9, 10.5, 11.5, 11.5], [9, 11, 12, 11.5], highs=[9.5, 11.5, 12.5, 14], lows=[8.5, 10, 11, 9])
    [trade] = run(cross_strategy(exits=Exits(stop_loss_pct=10, take_profit_pct=10)), candles, None,
                  candles.index[0]).trades
    assert trade.exit_reason == 'stop-loss'


def test_take_profit():
    candles = candles_from([9, 10.5, 11.5, 12], [9, 11, 12, 12.5], highs=[9.5, 11.5, 12.5, 13])
    [trade] = run(cross_strategy(exits=Exits(take_profit_pct=10)), candles, None, candles.index[0]).trades
    assert (trade.exit_reason, trade.exit_price) == ('take-profit', pytest.approx(12.65))


def test_the_tighter_of_percent_stop_and_atr_stop_is_used():
    closes = [9.0] * 30 + [11, 12, 12]
    candles = candles_from([9.0] * 30 + [10, 11.5, 12], closes)
    result = run(cross_strategy(exits=Exits(stop_loss_pct=50, atr_stop_multiple=1)), candles, None,
                 candles.index[0])
    [trade] = result.trades
    atr = SeriesCache(candles, None).series(indicator('atr')).iloc[trade.signal_slot]
    assert trade.stop_reason == 'ATR stop' and trade.stop_price == pytest.approx(trade.entry_price - atr)


def test_an_open_position_is_reported_as_unrealized():
    candles = candles_from([9, 10.5, 11.5, 12.5], [9, 11, 12, 14])
    result = run(cross_strategy(), candles, None, candles.index[0])
    trade = result.open_trade
    assert trade and trade.is_open and trade.exit_price == 14 and trade.exit_reason == 'still open'
    assert result.metrics['trades'] == 0 and result.metrics['win_rate_pct'] is None
    assert result.metrics['unrealized_pnl'] == pytest.approx(trade.shares * (14 - 11.5))


def test_signals_before_the_range_do_not_open_trades():
    candles = candles_from(OPENS, CLOSES)
    result = run(cross_strategy(), candles, None, candles.index[3])  # range starts after the BUY signal
    assert result.trades == [] and result.first_slot == 3
    assert result.equity.iloc[-1] == 1000


def test_a_signal_on_the_last_candle_is_reported_as_pending():
    candles = candles_from([9, 9, 10.5], [9, 9, 11])
    result = run(cross_strategy(), candles, None, candles.index[0])
    assert result.trades == [] and result.pending.startswith('BUY signal')


def test_buy_and_hold_and_drawdown():
    candles = candles_from([10, 12, 9, 11], [10, 12, 9, 11])
    result = run(cross_strategy(level=100), candles, None, candles.index[0])  # never trades
    assert result.buy_hold.tolist() == [1000, 1200, 900, 1100]  # 100 shares bought at the first open
    assert result.metrics['buy_hold_return_pct'] == pytest.approx(10)
    assert result.metrics['buy_hold_max_drawdown_pct'] == pytest.approx(-25)
    assert result.metrics['max_drawdown_pct'] == 0 and result.metrics['return_pct'] == 0


def realistic_strategy() -> Strategy:
    return Strategy('trend', RuleGroup('all', [
        Condition(indicator('close'), 'above', indicator('sma', days=50)),
        Condition(indicator('macd', 'macd'), 'crosses_above', indicator('macd', 'signal'))]),
        RuleGroup('any', [Condition(indicator('macd', 'macd'), 'crosses_below', indicator('macd', 'signal'))]),
        Exits(stop_loss_pct=5, take_profit_pct=15), Costs(capital=10_000, commission=1, slippage_pct=0.05))


def test_money_adds_up_on_a_long_random_history():
    candles = random_walk(1500, seed=7)
    result = run(realistic_strategy(), candles, None, candles.index[200])
    assert len(result.closed_trades) > 10
    realized = sum(t.pnl for t in result.closed_trades)
    assert result.metrics['end_capital'] == pytest.approx(10_000 + realized + result.metrics['unrealized_pnl'])
    assert (result.equity > 0).all()
    for earlier, later in zip(result.trades, result.trades[1:]):
        assert earlier.exit_slot <= later.entry_slot  # one position at a time
    for trade in result.trades:
        assert trade.entry_slot == trade.signal_slot + 1  # always the next candle's open


def test_no_look_ahead_trades_do_not_change_when_future_candles_arrive():
    candles = random_walk(1500, seed=8)
    full = run(realistic_strategy(), candles, None, candles.index[200])
    cut = 1000
    partial = run(realistic_strategy(), candles.iloc[:cut + 1], None, candles.index[200])
    finished = [t for t in full.trades if t.exit_slot is not None and t.exit_slot <= cut and not t.is_open]
    assert [vars(t) for t in partial.closed_trades] == [vars(t) for t in finished]
    pd.testing.assert_series_equal(partial.equity, full.equity.iloc[:len(partial.equity)])

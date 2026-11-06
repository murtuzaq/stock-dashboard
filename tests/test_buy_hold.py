"""Buy & hold per stock: the number the Stock Library shows must be the number a backtest's buy & hold line ends on."""
import pandas as pd
import pytest

from conftest import make_candles
from prices import store
from strategy import Costs
from strategy.backtest import buy_and_hold_end, run
from strategy.buy_hold import stock_buy_hold


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'prices.db')


def saved(symbol: str, closes, start: str = '2020-01-01', opens=None) -> None:
    """Store daily rows (one per business day) with the given closes (and opens, default the same)."""
    index = pd.bdate_range(start, periods=len(closes), name='date')
    closes = pd.Series(closes, index=index, dtype=float)
    frame = pd.DataFrame({'open': closes if opens is None else pd.Series(opens, index=index, dtype=float),
                          'high': closes + 1, 'low': closes - 1, 'close': closes, 'volume': 100,
                          'dividend': 0.0, 'split': 0.0})
    store.save(symbol, frame)


def test_it_ends_where_a_backtests_buy_and_hold_line_ends(spec_example):
    candles = make_candles([50 + i * 0.37 for i in range(300)])
    start = candles.index[40]
    result = run(spec_example, candles, None, start, 'AAA')
    first = int(candles.index.searchsorted(start))
    ends = buy_and_hold_end(candles['open'].iloc[first], candles['close'].iloc[-1], spec_example.costs)
    assert ends == pytest.approx(result.metrics['buy_hold_end'])


def test_it_follows_the_range_and_uses_the_same_costs_as_the_charts(database):
    saved('AAA', [100 + i for i in range(1000)])  # rises $1 a day for 1000 business days
    stocks = store.stored_stocks()
    year, everything = stock_buy_hold(stocks, '1Y')['AAA'], stock_buy_hold(stocks, 'Max')['AAA']
    first_price = 100 * 1.0005  # a fill 0.05% worse than the open
    shares = int(10_000 // first_price)
    assert everything.first_date == pd.Timestamp('2020-01-01') and not everything.short_history
    assert everything.end_value == pytest.approx(10_000 - shares * first_price + shares * 1099)
    assert year.first_date > everything.first_date and year.return_pct < everything.return_pct
    assert year.return_pct > 0 and not year.short_history


def test_a_stock_younger_than_the_range_starts_at_its_first_day_and_says_so(database):
    saved('NEW', [20 + i * 0.1 for i in range(100)], start='2025-06-02')
    long_range, everything = stock_buy_hold(store.stored_stocks(), '5Y')['NEW'], stock_buy_hold(
        store.stored_stocks(), 'Max')['NEW']
    assert long_range.first_date == pd.Timestamp('2025-06-02') and long_range.short_history
    assert not everything.short_history and everything.end_value == pytest.approx(long_range.end_value)


def test_a_flat_stock_loses_only_the_slippage(database):
    saved('FLAT', [100.0] * 300)
    hold = stock_buy_hold(store.stored_stocks(), 'Max')['FLAT']
    assert -0.1 < hold.return_pct < 0  # 99 whole shares bought slightly above the open; $96 left over as cash


def test_a_range_that_starts_on_a_weekend_buys_at_the_next_trading_days_open(database):
    saved('AAA', [10 + i for i in range(30)], opens=[1000 + i for i in range(30)])  # opens differ from closes
    saturday = pd.Timestamp('2020-01-18')
    found = store.opens_from({'AAA': saturday, 'NONE': saturday})
    assert found == {'AAA': (pd.Timestamp('2020-01-20'), 1000 + 13)}  # Monday's open; unknown symbols are left out


def test_a_stock_with_no_price_in_the_range_is_left_out(database):
    saved('AAA', [10.0] * 5)
    stocks = store.stored_stocks()
    assert 'AAA' in stock_buy_hold(stocks, 'Max') and store.opens_from({'AAA': pd.Timestamp('2030-01-01')}) == {}

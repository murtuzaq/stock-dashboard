"""Buy & hold over a time range for every stored stock: what a fixed starting sum would have become.

Calculated exactly like the buy & hold line in a backtest (buy whole shares at the first open of the range, with the
same slippage and commission, value at the latest close), so the numbers here match what the charts show.
"""
from dataclasses import dataclass

import pandas as pd

from prices import range_start, store
from prices.candles import RANGE_OFFSETS
from .backtest import buy_and_hold_end
from .model import Costs


@dataclass(frozen=True)
class BuyHold:
    first_date: pd.Timestamp  # the day it was bought (the range's first trading day, or the stock's first stored day)
    end_value: float  # what the starting cash is worth at the latest close
    return_pct: float
    short_history: bool  # the stock has no prices as far back as the range asked for


def _asked_for(last_date: pd.Timestamp, range_label: str) -> pd.Timestamp | None:
    """The day the range reaches back to, before it is cut off at the stock's first day (None for 'Max')."""
    if range_label == 'Max':
        return None
    if range_label == 'YTD':
        return pd.Timestamp(year=last_date.year, month=1, day=1)
    return last_date - RANGE_OFFSETS[range_label]


def stock_buy_hold(stocks: pd.DataFrame, range_label: str, costs: Costs | None = None) -> dict[str, BuyHold]:
    """`stocks` is prices.store.stored_stocks(): symbol, first_date, last_date, last_close. Stocks with no usable
    price on or after the range's start are left out."""
    costs = costs or Costs()
    wanted = {row.symbol: range_start(row.last_date, row.first_date, range_label) for row in stocks.itertuples()}
    opens = store.opens_from(wanted)
    result = {}
    for row in stocks.itertuples():
        if row.symbol not in opens:
            continue
        first_date, first_open = opens[row.symbol]
        end_value = buy_and_hold_end(first_open, float(row.last_close), costs)
        asked = _asked_for(row.last_date, range_label)
        result[row.symbol] = BuyHold(first_date, end_value, (end_value / costs.capital - 1) * 100,
                                     short_history=asked is not None and asked < row.first_date)
    return result

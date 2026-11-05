"""Which strategy would have worked best on a stock: backtest each one over the same period and compare.

Past results don't guarantee future ones, and the best of several tries is partly luck (the more strategies
compared, the more likely one looks good by chance), so the result is a starting point, not a prediction.
"""
from dataclasses import dataclass

import pandas as pd

from .backtest import BacktestResult, run
from .model import Strategy


@dataclass(frozen=True)
class Ranked:
    strategy: Strategy
    result: BacktestResult

    @property
    def return_pct(self) -> float:
        return self.result.metrics['return_pct']

    @property
    def beats_buy_and_hold(self) -> bool:
        return self.return_pct > self.result.metrics['buy_hold_return_pct']


def rank(strategies: list[Strategy], candles: pd.DataFrame, benchmark: pd.DataFrame | None, start: pd.Timestamp,
         symbol: str | None = None) -> list[Ranked]:
    """Every strategy backtested on the same candles from `start`, best total return first.

    A strategy that cannot run on this data (e.g. it needs the S&P 500 and that is missing) is left out.
    """
    ranked = []
    for strategy in strategies:
        try:
            ranked.append(Ranked(strategy, run(strategy, candles, benchmark, start, symbol)))
        except ValueError:
            continue
    return sorted(ranked, key=lambda r: r.return_pct, reverse=True)

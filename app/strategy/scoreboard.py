"""Every strategy on every stock: which ones reliably beat buy & hold, and is "the best strategy" just luck?

Pure functions, no Qt and no database. `score_stock` backtests all the strategies on one stock three ways: over the
whole range, over the first part of it (the "pick" period) and over the rest (the "test" period). `summarise` turns the
scores of many stocks into the scoreboard, the best strategy per stock and the out-of-sample result: how the strategy
that looked best in the pick period did afterwards, compared with buy & hold.

The best of several tries is partly luck, and the stocks are survivors, so none of this predicts the future.
The test period's indicators warm up on the candles before it, so its signals are the ones a person would have seen.
"""
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from .backtest import run
from .model import Strategy

PICK_SHARE = 0.6  # the first 60% of the range is where the best strategy is picked; the rest is the test
MIN_PART = 20  # fewer candles than this in either part and the stock has no out-of-sample result


@dataclass(frozen=True)
class Run:
    """One strategy on one stretch of one stock."""
    return_pct: float
    hold_pct: float
    max_drawdown_pct: float = 0.0
    trades: int = 0

    @property
    def margin(self) -> float:
        """Percentage points ahead of buy & hold (negative: behind)."""
        return self.return_pct - self.hold_pct

    @property
    def beat_hold(self) -> bool:
        return self.return_pct > self.hold_pct


@dataclass(frozen=True)
class StockScore:
    symbol: str
    whole: dict[str, Run]  # strategy id -> the whole range
    skipped: dict[str, str] = field(default_factory=dict)  # strategy id -> why it could not run on this stock
    pick: dict[str, Run] = field(default_factory=dict)  # the first part
    test: dict[str, Run] = field(default_factory=dict)  # the rest
    split: pd.Timestamp | None = None  # where the test part starts; None when the range is too short to split


def _run_of(result) -> Run:
    m = result.metrics
    return Run(m['return_pct'], m['buy_hold_return_pct'], m.get('max_drawdown_pct', 0.0), m.get('trades', 0))


def score_stock(strategies: list[Strategy], candles: pd.DataFrame, benchmark: pd.DataFrame | None, start: pd.Timestamp,
                symbol: str, backtest: Callable = run) -> StockScore:
    """Backtest every strategy on this stock. One that cannot run here (it needs the S&P 500 and that is missing, or
    there is too little history) is recorded in `skipped` with the reason, not left out silently."""
    first = int(candles.index.searchsorted(start))
    in_range = len(candles) - first
    split_slot = first + int(in_range * PICK_SHARE)
    can_split = split_slot - first >= MIN_PART and len(candles) - split_slot >= MIN_PART
    split = candles.index[split_slot] if can_split else None
    pick_candles = candles.iloc[:split_slot] if can_split else None
    whole, skipped, pick, test = {}, {}, {}, {}
    for strategy in strategies:
        try:
            whole[strategy.id] = _run_of(backtest(strategy, candles, benchmark, start, symbol))
            if can_split:
                pick[strategy.id] = _run_of(backtest(strategy, pick_candles, benchmark, start, symbol))
                test[strategy.id] = _run_of(backtest(strategy, candles, benchmark, split, symbol))
        except ValueError as error:
            whole.pop(strategy.id, None)
            pick.pop(strategy.id, None)
            test.pop(strategy.id, None)
            skipped[strategy.id] = str(error)
    return StockScore(symbol, whole, skipped, pick, test, split)


def best_of(runs: dict[str, Run]) -> str | None:
    """The strategy with the highest return, but only if it clearly leads (a tie with the runner-up means nothing was
    separated, for example when none of them traded) and beat buy & hold. Same rule as the star in the Explorer."""
    if len(runs) < 2:
        return None
    ordered = sorted(runs.items(), key=lambda item: item[1].return_pct, reverse=True)
    (best_id, best), (_, second) = ordered[0], ordered[1]
    if best.return_pct <= second.return_pct or not best.beat_hold:
        return None
    return best_id


def pick_of(runs: dict[str, Run]) -> str | None:
    """The strategy with the highest return in the pick period, if it clearly leads. Unlike the star it need not have
    beaten buy & hold there: this is the strategy a person would have chosen, and the test is what happened next."""
    if len(runs) < 2:
        return None
    ordered = sorted(runs.items(), key=lambda item: item[1].return_pct, reverse=True)
    if ordered[0][1].return_pct <= ordered[1][1].return_pct:
        return None
    return ordered[0][0]


@dataclass(frozen=True)
class BoardRow:
    """One strategy across all the stocks it ran on."""
    strategy_id: str
    name: str
    ran: int
    skipped: int
    beat: int
    median_margin: float
    median_return: float
    avg_return: float
    avg_hold: float
    median_drawdown: float
    stars: int  # stocks where it was the best strategy

    @property
    def beat_pct(self) -> float:
        return 100 * self.beat / self.ran if self.ran else 0.0


@dataclass(frozen=True)
class BestRow:
    symbol: str
    best_id: str | None  # None: nothing clearly beat buy & hold
    best: Run | None
    runner_up_id: str | None
    runner_up: Run | None
    beating_hold: int  # how many of the strategies beat buy & hold here
    ran: int


@dataclass(frozen=True)
class OutRow:
    symbol: str
    picked_id: str
    picked_pick: Run
    picked_test: Run
    test_win_rate: float  # share of all strategies that beat buy & hold in the test part of this stock


@dataclass(frozen=True)
class Scoreboard:
    board: list[BoardRow]
    best: list[BestRow]
    out_of_sample: list[OutRow]
    stocks: int  # stocks scored
    skipped_stocks: int  # stocks where no strategy could run

    @property
    def pick_win_pct(self) -> float:
        """How often the picked strategy beat buy & hold in the period it was picked in."""
        rows = self.out_of_sample
        return 100 * sum(r.picked_pick.beat_hold for r in rows) / len(rows) if rows else 0.0

    @property
    def test_win_pct(self) -> float:
        """How often the same strategy beat buy & hold afterwards."""
        rows = self.out_of_sample
        return 100 * sum(r.picked_test.beat_hold for r in rows) / len(rows) if rows else 0.0

    @property
    def average_test_win_pct(self) -> float:
        """How often a strategy chosen at random would have beaten buy & hold in the test part."""
        rows = self.out_of_sample
        return 100 * statistics.mean(r.test_win_rate for r in rows) if rows else 0.0


def summarise(scores: list[StockScore], strategies: list[Strategy]) -> Scoreboard:
    names = {s.id: s.name for s in strategies}
    best_rows, out_rows = [], []
    stars = dict.fromkeys(names, 0)
    for score in scores:
        runs = score.whole
        best_id = best_of(runs)
        if best_id:
            stars[best_id] += 1
        ordered = sorted(runs.items(), key=lambda item: item[1].return_pct, reverse=True)
        runner = ordered[1] if best_id and len(ordered) > 1 else None
        best_rows.append(BestRow(score.symbol, best_id, runs[best_id] if best_id else None,
                                 runner[0] if runner else None, runner[1] if runner else None,
                                 sum(r.beat_hold for r in runs.values()), len(runs)))
        picked = pick_of(score.pick) if score.split is not None else None
        if picked and picked in score.test:
            rate = sum(r.beat_hold for r in score.test.values()) / len(score.test)
            out_rows.append(OutRow(score.symbol, picked, score.pick[picked], score.test[picked], rate))

    board = []
    for strategy in strategies:
        runs = [score.whole[strategy.id] for score in scores if strategy.id in score.whole]
        skipped = sum(1 for score in scores if strategy.id in score.skipped)
        if not runs:
            board.append(BoardRow(strategy.id, strategy.name, 0, skipped, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0))
            continue
        board.append(BoardRow(
            strategy.id, strategy.name, len(runs), skipped, sum(r.beat_hold for r in runs),
            statistics.median(r.margin for r in runs), statistics.median(r.return_pct for r in runs),
            statistics.mean(r.return_pct for r in runs), statistics.mean(r.hold_pct for r in runs),
            statistics.median(r.max_drawdown_pct for r in runs), stars[strategy.id]))
    board.sort(key=lambda row: (-row.beat_pct, row.name))
    best_rows.sort(key=lambda row: (row.best is None, -(row.best.margin if row.best else 0), row.symbol))
    out_rows.sort(key=lambda row: -row.picked_test.margin)
    return Scoreboard(board, best_rows, out_rows, sum(1 for s in scores if s.whole),
                      sum(1 for s in scores if not s.whole))

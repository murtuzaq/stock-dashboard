"""A portfolio-level test: every January, move the money into last calendar year's biggest winners.

This is not a rule about one stock. It looks at many stocks at once:

- On the first trading day of each year, every stock that traded through the whole previous year is ranked by its return
  that year (first trading day's open to last close). The top N get equal money, bought at that day's open; whatever
  was held is sold at the same open. The last year is valued at the latest close.
- Three baselines start from the same money on the same day: buying and holding the original stocks (never touched),
  holding all of them equally and rebalancing every January (this separates "picking winners" from "rebalancing"), and
  the S&P 500 index.

Money is split exactly (fractional shares). Slippage and commission come from `Costs`, as in a backtest. Prices only:
dividends are not included. The stocks it is given are whatever is in the database, which is today's survivors, so the
absolute results flatter every line; compare the lines with each other.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .model import Costs

ROTATION, ORIGINAL, EQUAL_WEIGHT, INDEX = 'rotation', 'original', 'equal_weight', 'index'


@dataclass(frozen=True)
class RotationSettings:
    n: int = 10  # how many of last year's winners to hold
    first_year: int | None = None  # the first January to invest; None = the earliest with a real choice (see below)
    costs: Costs = field(default_factory=Costs)  # capital (the seed), commission per trade, slippage %


@dataclass(frozen=True)
class Line:
    """One strategy or baseline over time."""
    key: str
    label: str
    values: np.ndarray  # account value at each close from the first January
    final: float
    cagr_pct: float
    max_drawdown_pct: float
    yearly_pct: dict[int, float]  # return in each calendar year (the first is from the seed)

    @property
    def best_year(self) -> tuple[int, float]:
        return max(self.yearly_pct.items(), key=lambda item: item[1])

    @property
    def worst_year(self) -> tuple[int, float]:
        return min(self.yearly_pct.items(), key=lambda item: item[1])


@dataclass(frozen=True)
class Pick:
    symbol: str
    ranked_pct: float  # its return in the previous year: why it was picked
    held_pct: float  # its return while held (open to the next January's open; the last year to the latest close)


@dataclass(frozen=True)
class YearRow:
    year: int  # the year the picks were held
    picks: list[Pick]
    eligible: int  # how many stocks could have been picked
    strategy_pct: float  # the rotation's return that year
    universe_pct: float  # all the eligible stocks held equally, rebalanced each January

    @property
    def beat_universe(self) -> bool:
        return self.strategy_pct - self.universe_pct > 1e-9  # a tie is not a win (and float noise is not a lead)


@dataclass(frozen=True)
class RotationResult:
    n: int
    first_year: int
    dates: pd.DatetimeIndex
    lines: list[Line]  # rotation, original stocks, equal weight, then the index if it was given
    yearly: list[YearRow]
    next_year: int  # the year now in progress (its leaders so far would be next January's picks)
    next_picks: list[tuple[str, float]]  # (symbol, return so far this year), best first
    universe_size: int  # stocks that were eligible in the first January
    seed: float = 10_000.0  # the starting money every line began with

    def line(self, key: str) -> Line:
        return next(line for line in self.lines if line.key == key)


def _wide(prices: dict[str, pd.DataFrame], column: str) -> pd.DataFrame:
    return pd.DataFrame({symbol: frame[column] for symbol, frame in prices.items()}).sort_index()


class _Calendar:
    """First and last trading day of every year, from all the stocks' dates together."""

    def __init__(self, days: pd.DatetimeIndex) -> None:
        self.days = days
        series = days.to_series()
        self.first = {int(year): day for year, day in series.groupby(days.year).min().items()}
        self.last = {int(year): day for year, day in series.groupby(days.year).max().items()}

    def can_invest_in(self, year: int) -> bool:
        """A January to buy on (one that is not the very last day of data), after a year of prices to rank."""
        return year - 1 in self.first and year in self.first and self.first[year] < self.days[-1]


def _year_returns(opens: pd.DataFrame, closes: pd.DataFrame, calendar: _Calendar, year: int) -> pd.Series:
    """Each stock's return over a calendar year: open on the first trading day to close on the last. Only stocks that
    had both are included, i.e. those that traded through the whole year."""
    if year not in calendar.first:
        return pd.Series(dtype=float)
    start, end = opens.loc[calendar.first[year]], closes.loc[calendar.last[year]]
    return (end / start - 1).dropna()


def _eligible(opens: pd.DataFrame, closes: pd.DataFrame, calendar: _Calendar, year: int) -> pd.Series:
    """Stocks that can be bought on the first trading day of `year`, with their return in `year - 1`."""
    previous = _year_returns(opens, closes, calendar, year - 1)
    tradable = opens.loc[calendar.first[year]].notna()
    return previous[tradable.reindex(previous.index, fill_value=False)]


def choice_wanted(n: int) -> int:
    """How many eligible stocks a first January needs before 'the top n' means anything: three times n (at least 20)."""
    return max(3 * n, 20)


def earliest_first_year(prices: dict[str, pd.DataFrame], at_least: int) -> int | None:
    """The first January with at least `at_least` stocks that traded through the whole year before and can be bought."""
    if not prices:
        return None
    opens, closes = _wide(prices, 'open'), _wide(prices, 'close')
    calendar = _Calendar(opens.index)
    for year in sorted(calendar.first):
        if calendar.can_invest_in(year) and len(_eligible(opens, closes, calendar, year)) >= at_least:
            return year
    return None


def _drawdown_pct(values: np.ndarray, seed: float) -> float:
    path = np.concatenate([[seed], values])
    return float(((path / np.maximum.accumulate(path)) - 1).min() * 100)


def _yearly_pct(dates: pd.DatetimeIndex, values: np.ndarray, seed: float) -> dict[int, float]:
    result, before = {}, seed
    for year in sorted(set(dates.year)):
        end = float(values[np.flatnonzero(dates.year == year)[-1]])
        result[int(year)] = (end / before - 1) * 100
        before = end
    return result


def _line(key: str, label: str, dates: pd.DatetimeIndex, values: np.ndarray, seed: float) -> Line:
    years = max((dates[-1] - dates[0]).days / 365.25, 1 / 365.25)
    final = float(values[-1])
    return Line(key, label, values, final, ((final / seed) ** (1 / years) - 1) * 100, _drawdown_pct(values, seed),
                _yearly_pct(dates, values, seed))


@dataclass
class _Holdings:
    """What was held from one rebalance until the next."""
    position: int  # index into `dates` of the day it was bought
    year: int
    cash: float
    shares: pd.Series  # symbol -> shares
    entry: dict[str, float]  # symbol -> price paid (before slippage)


def _simulate(prices_open: pd.DataFrame, opens_ff: pd.DataFrame, closes_ff: pd.DataFrame, calendar: _Calendar,
              dates: pd.DatetimeIndex, years: list[int], choose, settings: RotationSettings,
              every_year: bool) -> tuple[np.ndarray, list[_Holdings]]:
    """Run one allocation rule: at each rebalance day sell everything and buy `choose(year)` with equal money."""
    costs, slip = settings.costs, settings.costs.slippage_pct / 100
    cash, shares = costs.capital, pd.Series(dtype=float)
    book: list[_Holdings] = []
    for index, year in enumerate(years):
        if index > 0 and not every_year:
            break
        day = calendar.first[year]
        if len(shares):
            cash += float((shares * opens_ff.loc[day, shares.index] * (1 - slip)).sum()) - costs.commission * len(shares)
        symbols = choose(year)
        shares = pd.Series(dtype=float)
        entry: dict[str, float] = {}
        if symbols:
            spend = max(cash - costs.commission * len(symbols), 0.0) / len(symbols)
            prices = prices_open.loc[day, symbols]
            shares = spend / (prices * (1 + slip))
            cash -= spend * len(symbols) + costs.commission * len(symbols)
            entry = {symbol: float(prices[symbol]) for symbol in symbols}
        book.append(_Holdings(int(dates.get_loc(day)), year, cash, shares, entry))
    values = np.empty(len(dates))
    for index, held in enumerate(book):
        stop = book[index + 1].position if index + 1 < len(book) else len(dates)
        window = dates[held.position:stop]
        if len(held.shares):
            values[held.position:stop] = held.cash + closes_ff.loc[window, held.shares.index].to_numpy() @ held.shares.to_numpy()
        else:
            values[held.position:stop] = held.cash
    return values, book


def run_rotation(prices: dict[str, pd.DataFrame], benchmark: pd.DataFrame | None,
                 settings: RotationSettings = RotationSettings()) -> RotationResult:
    """`prices` maps each symbol to its daily rows (columns 'open' and 'close', indexed by date); `benchmark` is the
    S&P 500 index rows (or None). Raises ValueError when there are not enough stocks with a full year of prices."""
    n, costs = settings.n, settings.costs
    first_year = settings.first_year or earliest_first_year(prices, choice_wanted(n))
    if first_year is None:
        raise ValueError(f'Fewer than {choice_wanted(n)} stocks have a whole year of prices followed by a January to '
                         f'invest in, so there is not enough to choose the top {n} from.')
    raw_opens, raw_closes = _wide(prices, 'open'), _wide(prices, 'close')
    calendar = _Calendar(raw_opens.index)
    last_year = max(calendar.first)
    if not calendar.can_invest_in(first_year):
        raise ValueError(f'There are no prices for {first_year - 1} and {first_year}, or {first_year} has just begun.')
    years = [year for year in range(first_year, last_year + 1) if calendar.can_invest_in(year)]
    opens_ff, closes_ff = raw_opens.ffill(), raw_closes.ffill()
    dates = raw_opens.index[raw_opens.index >= calendar.first[first_year]]

    eligibility = {year: _eligible(raw_opens, raw_closes, calendar, year) for year in years}
    if len(eligibility[first_year]) == 0:
        raise ValueError(f'No stock traded through all of {first_year - 1} and can be bought in {first_year}.')
    original = list(eligibility[first_year].index)

    def best(year: int) -> list[str]:
        ranked = sorted(eligibility[year].items(), key=lambda item: (-item[1], item[0]))
        return [symbol for symbol, _ in ranked[:n]]

    def everyone(year: int) -> list[str]:
        return sorted(eligibility[year].index)

    rotation, book = _simulate(raw_opens, opens_ff, closes_ff, calendar, dates, years, best, settings, True)
    held_forever, _ = _simulate(raw_opens, opens_ff, closes_ff, calendar, dates, years, lambda year: original,
                                settings, False)
    equal, _ = _simulate(raw_opens, opens_ff, closes_ff, calendar, dates, years, everyone, settings, True)

    seed = costs.capital
    lines = [_line(ROTATION, f'Top {n} of last year\'s winners', dates, rotation, seed),
             _line(ORIGINAL, f'Buy & hold the original {len(original)} stocks', dates, held_forever, seed),
             _line(EQUAL_WEIGHT, 'All stocks, equal weight, rebalanced yearly', dates, equal, seed)]
    if benchmark is not None and not benchmark.empty and dates[0] in benchmark.index and benchmark.loc[dates[0], 'open'] > 0:
        index_values = seed * benchmark['close'].reindex(dates, method='ffill').to_numpy() / float(benchmark.loc[dates[0], 'open'])
        lines.append(_line(INDEX, 'S&P 500 index (price only)', dates, index_values, seed))

    yearly = _year_rows(years, book, eligibility, raw_opens, opens_ff, closes_ff, calendar, lines)
    so_far = _to_date_returns(raw_opens, closes_ff, calendar, last_year)
    next_picks = sorted(so_far.items(), key=lambda item: (-item[1], item[0]))[:n]
    return RotationResult(n, first_year, dates, lines, yearly, last_year, next_picks, len(original), seed)


def _to_date_returns(opens: pd.DataFrame, closes_ff: pd.DataFrame, calendar: _Calendar, year: int) -> pd.Series:
    """Each stock's return so far in `year` (first trading day's open to the latest close)."""
    start, now = opens.loc[calendar.first[year]], closes_ff.iloc[-1]
    return (now / start - 1).dropna()


def _year_rows(years: list[int], book: list[_Holdings], eligibility: dict[int, pd.Series], opens: pd.DataFrame,
               opens_ff: pd.DataFrame, closes_ff: pd.DataFrame, calendar: _Calendar, lines: list[Line]) -> list[YearRow]:
    rotation, equal = lines[0].yearly_pct, next(line for line in lines if line.key == EQUAL_WEIGHT).yearly_pct
    rows = []
    for index, held in enumerate(book):
        year = held.year
        exit_prices = (opens_ff.loc[calendar.first[years[index + 1]]] if index + 1 < len(years) else closes_ff.iloc[-1])
        picks = [Pick(symbol, float(eligibility[year][symbol]) * 100, float(exit_prices[symbol] / price - 1) * 100)
                 for symbol, price in held.entry.items()]
        rows.append(YearRow(year, picks, len(eligibility[year]), rotation[year], equal[year]))
    return rows

"""The yearly 'rotate into last year's winners' portfolio test, on made-up prices whose answers can be worked by hand.

Every stock's price rises (or falls) in a straight line through each calendar year, from the previous year's last close,
so a stock's return in a year is exactly the growth rate chosen here and nothing else moves between years.
"""
import numpy as np
import pandas as pd
import pytest

from strategy import Costs
from strategy.rotation import (EQUAL_WEIGHT, INDEX, ORIGINAL, ROTATION, RotationSettings, choice_wanted,
                               earliest_first_year, run_rotation)

DAYS = pd.bdate_range('2020-01-01', '2023-12-29')
# growth over 2020, 2021, 2022, 2023
GROWTH = {'A': [0.50, -0.10, 0.05, 0.10], 'B': [0.20, 0.30, 0.10, 0.20],
          'C': [-0.10, 0.80, -0.20, 0.0], 'D': [0.30, 0.0, 0.40, -0.10]}


def path(growth: list[float], first_year: int = 2020, start: float = 100.0, days=DAYS) -> pd.DataFrame:
    """Daily rows (open = close) that rise in a straight line through each year by that year's growth."""
    prices = pd.Series(np.nan, index=days)
    level = start
    for offset, rate in enumerate(growth):
        year = prices[prices.index.year == first_year + offset].index
        if len(year) == 0:
            continue
        prices[year] = level * (1 + rate * np.arange(len(year)) / (len(year) - 1))
        level *= 1 + rate
    prices = prices.dropna()
    return pd.DataFrame({'open': prices, 'close': prices})


def market() -> dict[str, pd.DataFrame]:
    return {symbol: path(growth) for symbol, growth in GROWTH.items()}


def no_costs(n=2, first_year=2021, **costs) -> RotationSettings:
    return RotationSettings(n=n, first_year=first_year, costs=Costs(capital=10_000, commission=0.0,
                                                                    slippage_pct=0.0, **costs))


def test_it_picks_the_biggest_winners_of_the_previous_year_and_reports_how_they_did():
    result = run_rotation(market(), None, no_costs())
    first, second, third = result.yearly
    assert [row.year for row in result.yearly] == [2021, 2022, 2023]
    assert [p.symbol for p in first.picks] == ['A', 'D']  # ranked by 2020: A +50%, D +30%
    assert [p.ranked_pct for p in first.picks] == pytest.approx([50.0, 30.0])
    assert [p.held_pct for p in first.picks] == pytest.approx([-10.0, 0.0])  # what they did in 2021
    assert [p.symbol for p in second.picks] == ['C', 'B'] and [p.symbol for p in third.picks] == ['D', 'B']
    assert first.eligible == 4


def test_the_three_lines_end_where_the_hand_calculation_says():
    result = run_rotation(market(), None, no_costs())
    assert result.line(ROTATION).final == pytest.approx(10_000 * 0.95 * 0.95 * 1.05)  # -5%, -5%, +5% a year
    assert result.line(EQUAL_WEIGHT).final == pytest.approx(10_000 * 1.25 * 1.0875 * 1.05)  # all four, every January
    original = (0.9 * 1.05 * 1.10 + 1.3 * 1.1 * 1.2 + 1.8 * 0.8 * 1.0 + 1.0 * 1.4 * 0.9) / 4  # never rebalanced
    assert result.line(ORIGINAL).final == pytest.approx(10_000 * original)
    assert [line.key for line in result.lines] == [ROTATION, ORIGINAL, EQUAL_WEIGHT]  # no index was given


def test_each_year_is_compared_with_holding_everything_equally():
    result = run_rotation(market(), None, no_costs())
    assert [round(row.strategy_pct, 6) for row in result.yearly] == [-5.0, -5.0, 5.0]
    assert [round(row.universe_pct, 6) for row in result.yearly] == [25.0, 8.75, 5.0]
    assert [row.beat_universe for row in result.yearly] == [False, False, False]  # level is not a win


def test_slippage_is_paid_on_every_buy_and_sell():
    slip = 0.001
    result = run_rotation(market(), None, RotationSettings(n=2, first_year=2021, costs=Costs(slippage_pct=slip * 100)))
    # three buys at 0.1% above the open, two sells at 0.1% below it (the last year is valued, not sold)
    expected = 10_000 * 0.95 * 0.95 * 1.05 * (1 - slip) ** 2 / (1 + slip) ** 3
    assert result.line(ROTATION).final == pytest.approx(expected)


def test_commission_is_charged_per_trade():
    free = run_rotation(market(), None, no_costs()).line(ROTATION).final
    paid = run_rotation(market(), None, RotationSettings(n=2, first_year=2021,
                                                         costs=Costs(commission=10.0, slippage_pct=0.0))).line(ROTATION).final
    assert paid < free and free - paid == pytest.approx(100, rel=0.1)  # 10 trades (6 buys, 4 sells) at $10 each


def test_the_first_year_starts_with_the_seed_and_the_dates_begin_on_the_first_trading_day():
    result = run_rotation(market(), None, no_costs())
    assert result.dates[0] == pd.Timestamp('2021-01-01') and result.dates[-1] == pd.Timestamp('2023-12-29')
    assert result.line(ROTATION).values[0] == pytest.approx(10_000)  # bought at that day's open, valued at its close
    assert len(result.line(ROTATION).values) == len(result.dates)


def test_yearly_returns_max_drawdown_and_best_and_worst_year():
    line = run_rotation(market(), None, no_costs()).line(ROTATION)
    assert {year: round(pct, 6) for year, pct in line.yearly_pct.items()} == {2021: -5.0, 2022: -5.0, 2023: 5.0}
    assert line.best_year == (2023, pytest.approx(5.0)) and line.worst_year[0] in (2021, 2022)
    assert line.max_drawdown_pct == pytest.approx(((0.95 * 0.95) - 1) * 100)  # down 9.75% from the seed, at the low
    assert line.cagr_pct == pytest.approx(((line.final / 10_000) ** (1 / 3) - 1) * 100, abs=0.2)


def test_a_stock_without_a_whole_previous_year_cannot_be_picked_that_year():
    late = path([0.5, 0.2, 0.9, 0.0], days=pd.bdate_range('2020-07-01', '2023-12-29'))  # listed mid-2020
    prices = {**market(), 'E': late}
    result = run_rotation(prices, None, no_costs())
    assert result.yearly[0].eligible == 4 and 'E' not in [p.symbol for p in result.yearly[0].picks]
    assert result.yearly[1].eligible == 5  # by 2022 it has a full year behind it
    assert result.universe_size == 4  # the original stocks are those eligible in the first January


def test_fewer_eligible_stocks_than_n_means_holding_them_all():
    result = run_rotation(market(), None, no_costs(n=10))
    assert all(len(row.picks) == 4 for row in result.yearly)
    assert result.line(ROTATION).final == pytest.approx(result.line(EQUAL_WEIGHT).final)  # the same stocks, same money


def test_a_year_with_nothing_to_rank_is_refused_with_a_reason():
    with pytest.raises(ValueError, match='no prices for 2019'):
        run_rotation(market(), None, no_costs(first_year=2020))
    with pytest.raises(ValueError, match='no prices'):
        run_rotation(market(), None, no_costs(first_year=2030))
    with pytest.raises(ValueError, match='Fewer than 20 stocks'):
        run_rotation(market(), None, RotationSettings(n=2))  # the default needs a real choice: 20 stocks eligible


def test_the_default_first_year_is_the_earliest_with_a_real_choice():
    assert choice_wanted(2) == 20 and choice_wanted(10) == 30 and choice_wanted(5) == 20
    assert earliest_first_year(market(), at_least=4) == 2021  # 2020 has no year before it
    assert earliest_first_year(market(), at_least=5) is None
    assert earliest_first_year({}, at_least=1) is None
    many = {f'S{i}': path([0.1 * (i % 5), 0.1, 0.1, 0.1]) for i in range(20)}
    assert run_rotation(many, None, RotationSettings(n=3)).first_year == 2021


def test_the_index_line_starts_from_the_same_money_on_the_same_day():
    index = path([0.10, 0.20, 0.0, 0.10])
    index = index.assign(open=index['close'])
    result = run_rotation(market(), index, no_costs())
    line = result.line(INDEX)
    assert line.label.startswith('S&P 500') and line.values[0] == pytest.approx(10_000, rel=1e-3)
    assert line.final == pytest.approx(10_000 * (110 * 1.2 * 1.0 * 1.1) / 110)  # 13,200: bought at January 2021's open
    assert INDEX not in [l.key for l in run_rotation(market(), pd.DataFrame(), no_costs()).lines]


def test_next_januarys_picks_are_the_leaders_of_the_year_so_far():
    result = run_rotation(market(), None, no_costs())
    assert result.next_year == 2023
    assert [symbol for symbol, _ in result.next_picks] == ['B', 'A']  # 2023: B +20%, A +10%, C 0%, D -10%
    assert [value for _, value in result.next_picks] == pytest.approx([0.20, 0.10])

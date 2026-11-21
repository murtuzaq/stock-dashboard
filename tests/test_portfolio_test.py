"""Tools > Portfolio Test: the controller and the chart/table models, with made-up prices and a fake view."""
from datetime import date

import pandas as pd
import pytest

from core.common import theme
from core.common.background import BackgroundLoader
from core.portfolio_test import model
from core.portfolio_test.controller import ALL_STOCKS, PortfolioTestController
from strategy import Costs
from strategy.rotation import run_rotation
from test_rotation import market, no_costs


class FakeView:
    def __init__(self) -> None:
        self.universes, self.current, self.settings, self.warning = [], '', None, ''
        self.result, self.notices, self.running = None, [], False

    def show_universes(self, names, current): self.universes, self.current = names, current
    def show_settings(self, n, first_year, last_year): self.settings = (n, first_year, last_year)
    def show_warning(self, text): self.warning = text
    def show_result(self, result): self.result = result
    def show_notice(self, text): self.notices.append(text)
    def set_running(self, running): self.running = running


PRICES = market()
STORED = pd.DataFrame({'symbol': sorted(PRICES)})


def make(portfolios=None, stocks=STORED, series=None):
    view = FakeView()
    controller = PortfolioTestController(
        view, BackgroundLoader.immediate(), lambda: dict(portfolios or {}), lambda: stocks,
        series or (lambda symbol: PRICES.get(symbol, pd.DataFrame())), lambda: date(2026, 11, 6),
        Costs(capital=10_000, commission=0.0, slippage_pct=0.0))  # exact numbers: no slippage
    controller.start_panel()
    return controller, view


def test_opening_lists_the_universes_sets_defaults_and_shows_the_warning():
    controller, view = make({'Tech picks': ['A', 'B']})
    assert view.universes == [ALL_STOCKS, 'Tech picks'] and view.current == ALL_STOCKS
    assert view.settings == (10, 2016, 2026)  # ten winners, from ten years ago
    assert 'survivors' in view.warning and 'fractional shares' in view.warning


def test_running_on_all_stored_stocks_shows_the_chart_both_tables_and_the_explanations():
    controller, view = make()
    controller.run(2, 2021)
    result = view.result
    assert [s.label for s in result.chart.series] == ["Top 2 of last year's winners", 'Buy & hold the original 4 stocks',
                                                      'All stocks, equal weight, rebalanced yearly']
    assert [s.is_hold for s in result.chart.series] == [False, True, True]  # the strategy solid, baselines dashed
    assert result.chart.series[0].end_value == pytest.approx(10_000 * 0.95 * 0.95 * 1.05, rel=1e-3)
    assert [row[0].text for row in result.years] == ['2021', '2022', '2023']
    assert result.years[0][1].text == 'A, D' and 'A: ranked +50% in 2020, then -10%' in result.years[0][1].tooltip
    assert [row[2].text for row in result.years] == ['-5%', '-5%', '+5%'] and result.years[0][2].color == theme.DOWN
    assert result.years[2][2].color == theme.UP and [row[4].text for row in result.years] == ['no', 'no', 'no']
    assert not controller.running and not view.running


def test_the_summary_says_how_often_the_picks_won_and_what_one_lucky_year_did():
    controller, view = make()
    controller.run(2, 2021)
    text = view.result.summary
    assert 'beat the all-stock average in 0 of 3 years' in text
    assert 'behind buying and holding the original 4 stocks' in text
    assert "Take out the rotation's best year (2023: +5%)" in text


def test_next_januarys_picks_are_the_leaders_of_the_year_so_far():
    controller, view = make()
    controller.run(2, 2021)
    assert view.result.next_picks == ("If you rotated today, the leaders of 2023 so far (next January's picks) are "
                                      'B +20%, A +10%. 2023 is not over, so this is not a final list.')


def test_the_lines_table_has_one_row_per_line_with_final_value_per_year_and_drawdown():
    controller, view = make()
    controller.run(2, 2021)
    rotation, original = view.result.lines[0], view.result.lines[1]
    assert rotation[0].text.startswith('Top 2') and rotation[1].text == '$9,476.25'
    assert original[1].text == '$13,638.75' and original[1].color == theme.UP and rotation[1].color == theme.DOWN
    assert rotation[3].text.endswith('%') and rotation[4].text == '2023 +5%'


def test_a_saved_portfolio_is_a_universe_and_missing_stocks_are_reported_and_left_out():
    controller, view = make({'Mine': ['A', 'B', 'C', 'ZZZ']})
    controller.choose_universe('Mine')
    assert controller.symbols() == (['A', 'B', 'C'], ['ZZZ'])
    controller.run(2, 2021)
    assert 'have no stored prices' in view.notices[-1] and 'ZZZ' in view.notices[-1] and view.result is not None
    assert view.result.chart.series[1].label == 'Buy & hold the original 3 stocks'


def test_asking_for_more_winners_than_there_are_stocks_holds_them_all_and_says_so():
    controller, view = make({'Pair': ['A', 'B']})
    controller.choose_universe('Pair')
    controller.run(10, 2021)
    assert 'Only 2 stocks to choose from' in view.notices[-1]
    assert view.result.chart.series[0].label == "Top 2 of last year's winners"


def test_fewer_than_two_usable_stocks_is_refused():
    controller, view = make({'Solo': ['A']})
    controller.choose_universe('Solo')
    controller.run(1, 2021)
    assert 'at least 2 stocks' in view.notices[-1] and view.result is None


def test_a_first_year_that_cannot_work_is_explained_with_the_earliest_year_that_can():
    controller, view = make()
    controller.run(2, 2016)  # the prices start in 2020
    assert view.result is None
    assert 'no prices for 2015' in view.notices[-1]
    assert 'earliest year that can work with these stocks is 2021' in view.notices[-1]
    assert not controller.running


def test_an_unknown_universe_name_is_ignored_and_the_run_does_not_start_twice():
    controller, view = make({'Mine': ['A', 'B']})
    controller.choose_universe('Nope')
    assert controller.universe == ALL_STOCKS
    controller.running = True
    controller.run(2, 2021)
    assert view.result is None


def test_the_chart_model_hovers_like_the_strategy_comparison():
    from core.backtest.model import hover_line
    chart = model.portfolio_chart(run_rotation(PRICES, None, no_costs()))
    text = ''.join(span.text for span in hover_line(chart, 0, len(chart.dates) - 1))
    assert text.startswith('Top 2') and 'a year · max drawdown' in text and 'Best year 2023 +5%' in text
    assert chart.series[0].start_value == 10_000 and chart.start == pd.Timestamp('2021-01-01')

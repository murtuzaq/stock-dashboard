"""The company overview model: facts, likes/dislikes, and the strategy comparison and verdict."""
import numpy as np
import pandas as pd

from company import CompanyProfile
from conftest import random_walk
from core.common.formatting import Span
from core.overview.model import RANK_YEARS, overview_model, rank_strategies, verdict
from strategy import Condition, Costs, Exits, Operand, RuleGroup, Strategy

PROFILE = CompanyProfile('TEST', name='Test Corp', summary='Makes tests.', quote_type='EQUITY', sector='Technology',
                         industry='Software', country='United States', price=99.0, market_cap=2.5e11, trailing_pe=12.0,
                         dividend_yield_pct=3.1, employees=1200, profit_margin=0.3)


def plain(line: list[Span]) -> str:
    return ''.join(span.text for span in line)


def trend_strategy(days: int, name: str, symbol: str | None = 'TEST') -> Strategy:
    return Strategy(name, RuleGroup('all', [Condition(Operand('close'), 'above', Operand('sma', params={'days': days}))]),
                    RuleGroup('any', [Condition(Operand('close'), 'below', Operand('sma', params={'days': days}))]),
                    Exits(), Costs(), symbol=symbol)


def test_facts_heading_and_points():
    daily = random_walk(400, seed=3)
    model = overview_model('TEST', PROFILE, daily, None, [])
    assert plain(model.heading) == 'Test Corp  TEST' and model.subheading == 'Technology · Software · United States'
    facts = dict(model.facts)
    assert facts['Price'] == f'${daily["close"].iloc[-1]:,.2f}'  # the latest stored close beats Yahoo's snapshot
    assert facts['Market value'] == '$250.00B' and facts['P/E'] == '12.0' and facts['Employees'] == '1,200'
    assert any(p.text.startswith('Priced cheaply') for p in model.likes)
    assert 'No strategies to compare' in plain(model.verdict) and model.rank_rows == []


def test_still_loading_and_unknown_symbols():
    assert plain(overview_model('TEST', PROFILE, None, None, None).verdict) == 'Comparing strategies…'
    empty = overview_model('ZZZ', CompanyProfile('ZZZ'), None, None, [])
    assert plain(empty.heading).startswith('ZZZ') and 'No company description' in empty.summary
    assert empty.likes == [] and empty.dislikes == []
    etf = overview_model('SPY', CompanyProfile('SPY', name='SPDR', quote_type='ETF'), None, None, [])
    assert etf.subheading == 'ETF'


def test_strategies_are_ranked_over_the_last_five_years_best_first():
    daily = random_walk(252 * 8, seed=5)
    ranked = rank_strategies([trend_strategy(20, 'Fast'), trend_strategy(150, 'Slow', None)], daily, None, 'TEST')
    assert [r.return_pct for r in ranked] == sorted((r.return_pct for r in ranked), reverse=True)
    start = ranked[0].result.start
    assert start == daily.index[-1] - pd.DateOffset(years=RANK_YEARS)
    model = overview_model('TEST', PROFILE, daily, None, ranked)
    hold, best = model.rank_rows[0], model.rank_rows[1]
    assert hold.strategy_id is None and hold.cells[0].text.startswith('Buy & hold')
    assert best.is_best and best.strategy_id == ranked[0].strategy.id
    library_row = next(row for row in model.rank_rows if row.cells[0].text.endswith('· library'))
    assert library_row.cells[0].text == 'Slow · library'


def drifting(direction: float) -> pd.DataFrame:
    daily = random_walk(252 * 6, seed=5)
    trend = np.exp(np.linspace(0, direction, len(daily)))
    for column in ('open', 'high', 'low', 'close'):
        daily[column] = daily[column] * trend
    return daily


def never_trades(name: str) -> Strategy:
    """Its BUY rule can never be true, so it ends exactly where it started (0%)."""
    return Strategy(name, RuleGroup('all', [Condition(Operand('close'), 'above', Operand(value=1e12))]),
                    RuleGroup('any', []), Exits(stop_loss_pct=5), symbol='TEST')


def test_the_verdict_says_plainly_when_buy_and_hold_won():
    ranked = rank_strategies([never_trades('Patient')], drifting(+2.0), None, 'TEST')
    assert ranked[0].return_pct == 0 and not ranked[0].beats_buy_and_hold
    text = plain(verdict(ranked))
    assert text.startswith('None of the strategies beat simply buying and holding (+')
    assert 'The best was Patient at +0.0%' in text and 'owning it may have been the better plan' in text


def test_the_verdict_names_a_strategy_that_beat_buy_and_hold():
    ranked = rank_strategies([never_trades('Patient')], drifting(-2.0), None, 'TEST')  # the stock fell a lot
    assert ranked[0].beats_buy_and_hold
    assert plain(verdict(ranked)).startswith('Best so far: Patient made +0.0% over the past 5 years, beating buy & hold (-')

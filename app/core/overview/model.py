"""The company overview a stock's name opens: what the company is, what investors like and dislike about it,
and which strategy would have worked best on it. Plain data for the renderer; no toolkit types.
"""
from dataclasses import dataclass, field

import pandas as pd

from company import Assessment, CompanyProfile, Point, assess
from core.common import theme
from core.common.formatting import Cell, Line, Span, plain
from prices import to_candles
from strategy import Strategy
from strategy.ranking import Ranked, rank

RANK_YEARS = 5  # strategies are compared over this many years of daily candles
RANK_COLUMNS = ['Strategy', 'Return', 'vs buy & hold', 'Trades', 'Win rate', 'Max drawdown']


@dataclass(frozen=True)
class RankRow:
    strategy_id: str | None  # None for the buy & hold row
    cells: list[Cell]
    is_best: bool = False


@dataclass
class OverviewModel:
    heading: Line  # name, symbol
    subheading: str  # sector · industry · country
    facts: list[tuple[str, str]]  # (label, value) pairs: price, market cap, P/E ...
    summary: str
    likes: list[Point] = field(default_factory=list)
    dislikes: list[Point] = field(default_factory=list)
    verdict: Line = field(default_factory=list)  # which strategy did best, in words
    rank_rows: list[RankRow] = field(default_factory=list)
    rank_note: str = ''


def _money(value: float | None) -> str:
    return '—' if value is None else f'${value:,.2f}'


def _big(value: float | None) -> str:
    if value is None:
        return '—'
    for limit, suffix in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M')):
        if abs(value) >= limit:
            return f'${value / limit:,.2f}{suffix}'
    return f'${value:,.0f}'


def facts(profile: CompanyProfile, daily: pd.DataFrame | None) -> list[tuple[str, str]]:
    price = profile.price
    if daily is not None and not daily.empty:
        price = float(daily['close'].iloc[-1])
    rows = [('Price', _money(price)), ('Market value', _big(profile.market_cap))]
    if profile.trailing_pe:
        rows.append(('P/E', f'{profile.trailing_pe:.1f}'))
    if profile.dividend_yield_pct:
        rows.append(('Dividend', f'{profile.dividend_yield_pct:.2f}%'))
    if profile.low_52w and profile.high_52w:
        rows.append(('52-week range', f'{_money(profile.low_52w)} – {_money(profile.high_52w)}'))
    if profile.beta is not None:
        rows.append(('Beta', f'{profile.beta:.2f}'))
    if profile.employees:
        rows.append(('Employees', f'{profile.employees:,}'))
    if profile.website:
        rows.append(('Website', profile.website))
    return rows


def rank_strategies(strategies: list[Strategy], daily: pd.DataFrame, benchmark: pd.DataFrame | None,
                    symbol: str) -> list[Ranked]:
    """Every strategy backtested on the last RANK_YEARS of daily candles (or all the history, if shorter)."""
    if daily.empty or not strategies:
        return []
    start = max(daily.index[0], daily.index[-1] - pd.DateOffset(years=RANK_YEARS))
    return rank(strategies, to_candles(daily, '1D'), benchmark, start, symbol)


def _pct_cell(value: float | None) -> Cell:
    if value is None:
        return Cell('—', align_right=True)
    return Cell(f'{value:+.1f}%', theme.change_color(value), align_right=True)


def _points_cell(value: float) -> Cell:
    """A difference between two returns, in percentage points."""
    return Cell(f'{value:+.1f} pts', theme.change_color(value),
                tooltip='Strategy return minus buy & hold return, in percentage points', align_right=True)


def rank_rows(ranked: list[Ranked]) -> list[RankRow]:
    if not ranked:
        return []
    hold = ranked[0].result.metrics
    rows = [RankRow(None, [Cell('Buy & hold (just own it)'), _pct_cell(hold['buy_hold_return_pct']), Cell(''),
                           Cell('1', align_right=True), Cell(''),
                           Cell(f'{hold["buy_hold_max_drawdown_pct"]:.1f}%', align_right=True)])]
    for position, entry in enumerate(ranked):
        m = entry.result.metrics
        win_rate = '—' if m['win_rate_pct'] is None else f'{m["win_rate_pct"]:.0f}%'
        label = entry.strategy.name + (' · library' if entry.strategy.symbol is None else '')
        rows.append(RankRow(entry.strategy.id, [
            Cell(label, tooltip='\n\n'.join(part for part in (entry.strategy.about.summary,
                                                             'Click to open its full backtest') if part)),
            _pct_cell(m['return_pct']),
            _points_cell(m['return_pct'] - m['buy_hold_return_pct']), Cell(str(m['trades']), align_right=True),
            Cell(win_rate, align_right=True), Cell(f'{m["max_drawdown_pct"]:.1f}%', align_right=True)],
            is_best=position == 0))
    return rows


def verdict(ranked: list[Ranked]) -> Line:
    if not ranked:
        return [plain('No strategies to compare yet. Create one (right-click the stock > New Strategy…) or add '
                      'templates with Tools > Strategies.')]
    best = ranked[0]
    hold = best.result.metrics['buy_hold_return_pct']
    years = f'over the past {RANK_YEARS} years'
    if best.beats_buy_and_hold:
        return [plain('Best so far: '), Span(best.strategy.name, bold=True),
                plain(f' made '), Span(f'{best.return_pct:+.1f}%', theme.change_color(best.return_pct)),
                plain(f' {years}, beating buy & hold ('), Span(f'{hold:+.1f}%', theme.change_color(hold)),
                plain(').')]
    return [plain('None of the strategies beat simply buying and holding '),
            Span(f'({hold:+.1f}%)', theme.change_color(hold)), plain(f' {years}. The best was '),
            Span(best.strategy.name, bold=True), plain(' at '),
            Span(f'{best.return_pct:+.1f}%', theme.change_color(best.return_pct)),
            plain('. For this stock, owning it may have been the better plan.')]


RANK_NOTE = (f'Each strategy is backtested on daily candles over the past {RANK_YEARS} years, with its own capital '
             'and costs. Past results don\'t guarantee future ones, and the best of several tries is partly luck.')


def overview_model(symbol: str, profile: CompanyProfile, daily: pd.DataFrame | None,
                   benchmark: pd.DataFrame | None, ranked: list[Ranked] | None) -> OverviewModel:
    """`ranked` None means the comparison is still being worked out."""
    name = profile.name or symbol
    subheading = ' · '.join(part for part in (profile.sector, profile.industry, profile.country) if part)
    if profile.quote_type and profile.quote_type != 'EQUITY':
        subheading = ' · '.join(part for part in (profile.quote_type, subheading) if part)
    assessment = assess(profile, daily, benchmark) if not profile.is_empty else Assessment()
    model = OverviewModel(
        heading=[Span(name, bold=True), Span(f'  {symbol}', theme.MUTED)],
        subheading=subheading,
        facts=facts(profile, daily),
        summary=profile.summary or ('No company description is available for this symbol.' if profile.is_empty
                                    else 'Yahoo has no business description for this symbol.'),
        likes=assessment.likes, dislikes=assessment.dislikes)
    if ranked is None:
        model.verdict = [plain('Comparing strategies…')]
    else:
        model.verdict, model.rank_rows, model.rank_note = verdict(ranked), rank_rows(ranked), RANK_NOTE
    return model

"""Tools > Portfolio Test as data: the chart, the two tables and the sentences that explain a rotation result."""
from dataclasses import dataclass

from core.backtest.model import BacktestChart, BacktestSeries, legend_of
from core.common import theme
from core.common.formatting import Cell, Line, Span, money, plain
from strategy import rotation
from strategy.rotation import EQUAL_WEIGHT, INDEX, ORIGINAL, ROTATION, RotationResult

LINE_COLUMNS = ['', 'Final value', 'Per year', 'Max drawdown', 'Best year', 'Worst year']
YEAR_COLUMNS = ['Year', 'Picked (last year\'s winners)', 'Picks', 'All stocks', 'Beat?']
COLORS = {ROTATION: '#2962ff', ORIGINAL: '#ff6d00', EQUAL_WEIGHT: '#26a69a', INDEX: theme.HOLD_COLOR}
WARNING = ('The stocks in your database are today\'s survivors, many of them today\'s winners, so every line here looks '
           'better than it would have in real time: compare the lines with each other, not with the S&P 500. Prices '
           'only: no dividends or taxes, and no fees beyond slippage. Money is split exactly (fractional shares).')


@dataclass(frozen=True)
class PortfolioResult:
    """Everything the page shows for one run."""
    chart: BacktestChart
    lines: list[list[Cell]]  # one row per line: final value, per year, drawdown, best and worst year
    years: list[list[Cell]]  # one row per January
    summary: str
    next_picks: str


def _pct_cell(value: float, digits: int = 0) -> Cell:
    return Cell(f'{value:+.{digits}f}%', theme.change_color(value), align_right=True, sort_value=value)


def _summary_line(line: rotation.Line) -> Line:
    best_year, best = line.best_year
    worst_year, worst = line.worst_year
    return [plain(f'{line.cagr_pct:+.1f}% a year · max drawdown {line.max_drawdown_pct:.0f}%\n'),
            plain(f'Best year {best_year} {best:+.0f}% · worst year {worst_year} {worst:+.0f}%')]


def portfolio_chart(result: RotationResult) -> BacktestChart:
    """The lines drawn like the strategy comparison: the rotation solid, the baselines dashed, hover for the figures."""
    series = []
    for line in result.lines:
        series.append(BacktestSeries(line.label, COLORS[line.key], line.values, line.final,
                                     (line.final / result.seed - 1) * 100, is_hold=line.key != ROTATION,
                                     start_value=result.seed, summary=_summary_line(line)))
    return BacktestChart(result.dates, result.dates[0], series, legend_of(series), '')


def line_rows(result: RotationResult) -> list[list[Cell]]:
    rows = []
    for line in result.lines:
        best_year, best = line.best_year
        worst_year, worst = line.worst_year
        color = theme.change_color(line.cagr_pct)
        rows.append([Cell(line.label, COLORS[line.key]),
                     Cell(money(line.final), color, align_right=True),
                     Cell(f'{line.cagr_pct:+.1f}%', color, align_right=True),
                     Cell(f'{line.max_drawdown_pct:.0f}%', theme.DOWN, align_right=True),
                     Cell(f'{best_year} {best:+.0f}%', theme.UP, align_right=True),
                     Cell(f'{worst_year} {worst:+.0f}%', theme.DOWN, align_right=True)])
    return rows


def year_rows(result: RotationResult) -> list[list[Cell]]:
    rows = []
    for row in result.yearly:
        detail = '\n'.join(f'{pick.symbol}: ranked {pick.ranked_pct:+.0f}% in {row.year - 1}, then {pick.held_pct:+.0f}%'
                           for pick in row.picks) or 'Nothing was eligible: the money stayed in cash.'
        verdict = 'yes' if row.beat_universe else 'no'
        rows.append([Cell(str(row.year)),
                     Cell(', '.join(pick.symbol for pick in row.picks) or '—', tooltip=detail),
                     _pct_cell(row.strategy_pct), _pct_cell(row.universe_pct),
                     Cell(verdict, theme.UP if row.beat_universe else theme.DOWN)])
    return rows


def _without_best_year(line: rotation.Line) -> float:
    """What the line would have ended at if its single best year had simply been flat."""
    return line.final / (1 + line.best_year[1] / 100)


def summary_text(result: RotationResult) -> str:
    """How often the picks won, and how much of the result is one lucky year."""
    wins = sum(1 for row in result.yearly if row.beat_universe)
    rot, equal = result.line(ROTATION), result.line(EQUAL_WEIGHT)
    year, best = rot.best_year
    original = result.line(ORIGINAL)
    verdict = 'ahead of' if rot.final > original.final else 'behind'
    return (f'The picks beat the all-stock average in {wins} of {len(result.yearly)} years, and finished '
            f'{verdict} buying and holding the original {result.universe_size} stocks '
            f'({money(rot.final)} against {money(original.final)}). Take out the rotation\'s best year ({year}: '
            f'{best:+.0f}%) and it would have ended near {money(_without_best_year(rot))}, against '
            f'{money(_without_best_year(equal))} for the all-stock baseline without its own best year.')


def next_picks_text(result: RotationResult) -> str:
    if not result.next_picks:
        return ''
    leaders = ', '.join(f'{symbol} {value * 100:+.0f}%' for symbol, value in result.next_picks)
    return (f'If you rotated today, the leaders of {result.next_year} so far (next January\'s picks) are {leaders}. '
            f'{result.next_year} is not over, so this is not a final list.')


def portfolio_result(result: RotationResult) -> PortfolioResult:
    return PortfolioResult(portfolio_chart(result), line_rows(result), year_rows(result), summary_text(result),
                           next_picks_text(result))

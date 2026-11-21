"""Tools > Strategy Scoreboard: turn the engine's Scoreboard into table rows, colours, tooltips and plain-English text."""
from dataclasses import dataclass

from core.common import theme
from core.common.formatting import Cell
from core.library.stocks import NO_VALUE
from strategy import Strategy
from strategy.scoreboard import Run, Scoreboard

BOARD_COLUMNS = ['Strategy', 'Beat buy & hold', 'Win %', 'Median vs hold', 'Median return', 'Avg return',
                 'Avg buy & hold', 'Median drawdown', 'Best on']
BEST_COLUMNS = ['Symbol', 'Best strategy', 'Return', 'Buy & hold', 'vs hold', 'Runner-up', 'Beat hold']
OUT_COLUMNS = ['Symbol', 'Picked strategy', 'Pick period', 'Pick vs hold', 'Test period', 'Test vs hold']
BOARD_SORT = 2  # opens sorted by the share of stocks that beat buy & hold
BEST_SORT = 4
OUT_SORT = 5

CAVEAT = ('The best of several tries is partly luck, and the stocks stored here are today\'s survivors, so none of '
          'this predicts the future. Trust a strategy that beats buy & hold on many stocks, not one that tops a few.')


@dataclass(frozen=True)
class Row:
    key: str  # the strategy id (scoreboard) or the symbol (the other tables)
    cells: list[Cell]
    group: str = ''  # the best/picked strategy's id, so the table can be filtered by a strategy


@dataclass(frozen=True)
class ScoreboardResult:
    board: list[Row]
    best: list[Row]
    out_of_sample: list[Row]
    summary: str
    out_summary: str


def _pts(value: float) -> str:
    return f'{value:+.1f} pts'


def _num(text: str, value: float, color: str | None = None, tooltip: str | None = None) -> Cell:
    return Cell(text, color, tooltip, align_right=True, sort_value=value)


def _pct(value: float, signed: bool = True) -> Cell:
    text = f'{value:+.1f}%' if signed else f'{value:.1f}%'
    return _num(text, value, theme.change_color(value) if signed else None)


def board_rows(scoreboard: Scoreboard) -> list[Row]:
    rows = []
    for r in scoreboard.board:
        if r.ran == 0:
            none = [Cell('n/a', align_right=True, sort_value=NO_VALUE) for _ in BOARD_COLUMNS[1:]]
            rows.append(Row(r.strategy_id, [Cell(r.name, tooltip='It could not run on any stock'), *none]))
            continue
        skipped = f' ({r.skipped} stocks could not run it)' if r.skipped else ''
        rows.append(Row(r.strategy_id, [
            Cell(r.name),
            _num(f'{r.beat} of {r.ran}', float(r.beat), tooltip=f'Beat buy & hold on {r.beat} of {r.ran} stocks{skipped}'),
            _num(f'{r.beat_pct:.0f}%', r.beat_pct, theme.change_color(r.beat_pct - 50)),
            _num(_pts(r.median_margin), r.median_margin, theme.change_color(r.median_margin),
                 'The middle stock: strategy return minus buy & hold return, in percentage points'),
            _pct(r.median_return), _pct(r.avg_return),
            _num(f'{r.avg_hold:+.1f}%', r.avg_hold, theme.change_color(r.avg_hold),
                 'What buying and holding made on the same stocks, on average'),
            _num(f'{r.median_drawdown:.1f}%', r.median_drawdown),
            _num(str(r.stars), float(r.stars), tooltip='Stocks where this was the best strategy')]))
    return rows


def _run_tip(name: str, run: Run) -> str:
    return f'{name}: {run.return_pct:+.1f}% against {run.hold_pct:+.1f}% for buy & hold; {run.trades} trades'


def best_rows(scoreboard: Scoreboard, names: dict[str, str]) -> list[Row]:
    rows = []
    for r in scoreboard.best:
        if r.best is None:
            why = (f'No strategy clearly beat buy & hold here ({r.beating_hold} of {r.ran} did, none clearly ahead).'
                   if r.ran else 'No strategy could run on this stock.')
            rows.append(Row(r.symbol, [Cell(r.symbol), Cell('none', tooltip=why),
                                       *[Cell('—', align_right=True, sort_value=NO_VALUE) for _ in range(4)],
                                       _num(f'{r.beating_hold} of {r.ran}', float(r.beating_hold))]))
            continue
        name = names.get(r.best_id, r.best_id)
        runner = names.get(r.runner_up_id, r.runner_up_id)
        rows.append(Row(r.symbol, [
            Cell(r.symbol), Cell(name, tooltip=_run_tip(name, r.best)),
            _pct(r.best.return_pct), _pct(r.best.hold_pct),
            _num(_pts(r.best.margin), r.best.margin, theme.change_color(r.best.margin)),
            Cell(f'{runner} {r.runner_up.return_pct:+.0f}%', tooltip=_run_tip(runner, r.runner_up)),
            _num(f'{r.beating_hold} of {r.ran}', float(r.beating_hold),
                 tooltip='How many strategies beat buy & hold on this stock')], r.best_id))
    return rows


def out_rows(scoreboard: Scoreboard, names: dict[str, str]) -> list[Row]:
    rows = []
    for r in scoreboard.out_of_sample:
        name = names.get(r.picked_id, r.picked_id)
        rows.append(Row(r.symbol, [
            Cell(r.symbol), Cell(name, tooltip='The strategy with the highest return in the first part of the range'),
            _pct(r.picked_pick.return_pct), _num(_pts(r.picked_pick.margin), r.picked_pick.margin,
                                                 theme.change_color(r.picked_pick.margin)),
            _pct(r.picked_test.return_pct), _num(_pts(r.picked_test.margin), r.picked_test.margin,
                                                 theme.change_color(r.picked_test.margin),
                                                 f'{r.picked_test.return_pct:+.1f}% against {r.picked_test.hold_pct:+.1f}% '
                                                 'for buy & hold, in the later part')], r.picked_id))
    return rows


def summary_text(scoreboard: Scoreboard) -> str:
    ran = [r for r in scoreboard.board if r.ran]
    if not ran:
        return 'No strategy could be run on any stock.'
    top = max(ran, key=lambda r: (r.beat_pct, r.median_margin))
    starred = sum(1 for r in scoreboard.best if r.best is not None)
    text = (f'{len(scoreboard.board)} strategies on {scoreboard.stocks} stocks. Some strategy beat buy & hold on '
            f'{starred} stocks, but the most reliable one, {top.name}, beat it on {top.beat} of {top.ran} '
            f'({top.beat_pct:.0f}%); on the middle stock it finished {_pts(top.median_margin)} against buy & hold.')
    if scoreboard.skipped_stocks:
        text += f' {scoreboard.skipped_stocks} stocks could not be tested.'
    return text


def out_summary_text(scoreboard: Scoreboard) -> str:
    n = len(scoreboard.out_of_sample)
    if n == 0:
        return ('Out-of-sample check: not enough history to split the range (each part needs at least 20 candles), or '
                'no strategy clearly led in the first part.')
    wins = sum(1 for r in scoreboard.out_of_sample if r.picked_test.beat_hold)
    return (f'Out-of-sample check: the strategy that was best in the first part of each stock\'s range beat buy & hold '
            f'there on {scoreboard.pick_win_pct:.0f}% of stocks, but only on {wins} of {n} '
            f'({scoreboard.test_win_pct:.0f}%) in the later part. A strategy picked at random beat it on '
            f'{scoreboard.average_test_win_pct:.0f}%. If the picked strategy is not clearly above the random one, '
            f'"best strategy" was mostly luck.')


def scoreboard_result(scoreboard: Scoreboard, strategies: list[Strategy]) -> ScoreboardResult:
    names = {s.id: s.name for s in strategies}
    return ScoreboardResult(board_rows(scoreboard), best_rows(scoreboard, names), out_rows(scoreboard, names),
                            summary_text(scoreboard) + ' ' + CAVEAT, out_summary_text(scoreboard))

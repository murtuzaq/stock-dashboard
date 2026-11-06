"""Tools > Stocks > Download / update: row states, the queue, pacing, backoff, stop/resume, and the price refresh itself.
Everything is driven with fake clocks, pauses and downloads: no network, no real waiting."""
import random
from datetime import datetime

import pandas as pd
import pytest

from core.common.background import BackgroundLoader
from core.downloads import model
from core.downloads.controller import DownloadController, PacingProfile
from core.downloads.model import StockStatus
from prices import RateLimited
from prices import history, store
from search import Catalog, Group, Security

NOW = datetime(2025, 6, 11, 12, 0)  # a Wednesday: the last weekday before it is Tuesday the 10th
HOUR = 3600


def stored(*specs) -> pd.DataFrame:
    """('AAA', '2025-06-10', hours_since_checked or None) -> the frame prices.store.stored_stocks() returns."""
    rows = [{'symbol': symbol, 'last_date': pd.Timestamp(last),
             'checked_at': float('nan') if hours is None else NOW.timestamp() - hours * HOUR}
            for symbol, last, hours in specs]
    return pd.DataFrame(rows, columns=['symbol', 'last_date', 'checked_at'])


# --- states ----------------------------------------------------------------------------------------------------

def test_previous_weekday_skips_the_weekend():
    assert model.previous_weekday(datetime(2025, 6, 9).date()).isoformat() == '2025-06-06'  # Monday -> Friday
    assert model.previous_weekday(datetime(2025, 6, 8).date()).isoformat() == '2025-06-06'  # Sunday -> Friday
    assert model.previous_weekday(NOW.date()).isoformat() == '2025-06-10'


@pytest.mark.parametrize('last, checked_hours_ago, expected', [
    (None, None, StockStatus.NOT_DOWNLOADED),
    ('2025-06-10', None, StockStatus.UP_TO_DATE),  # has the last weekday's close
    ('2025-06-06', 1, StockStatus.UP_TO_DATE),  # old, but Yahoo was asked an hour ago (holiday, delisted...)
    ('2025-06-06', 30, StockStatus.STALE),  # old and not asked in the last 20 hours
    ('2025-06-06', None, StockStatus.STALE),
])
def test_status_of(last, checked_hours_ago, expected):
    last_date = None if last is None else pd.Timestamp(last)
    checked = None if checked_hours_ago is None else NOW.timestamp() - checked_hours_ago * HOUR
    assert model.status_of(last_date, checked, NOW) == expected


def test_a_weekend_does_not_turn_the_database_out_of_date():
    sunday = datetime(2025, 6, 15, 12, 0)
    assert model.status_of(pd.Timestamp('2025-06-13'), None, sunday) == StockStatus.UP_TO_DATE  # Friday's close


def test_rows_filter_totals_and_queue_order():
    database = stored(('FRESH', '2025-06-10', 1), ('OLD', '2025-06-02', 50), ('OLDER', '2025-05-01', 90))
    session = {'BAD': (StockStatus.FAILED, 'timed out'), 'NODATA': (StockStatus.NO_DATA, 'none')}
    rows = model.build_rows(['NEW', 'FRESH', 'OLD', 'OLDER', 'BAD', 'NODATA'], {'NEW': 'New Co'}, database, session, NOW)
    by_symbol = {row.symbol: row.status for row in rows}
    assert by_symbol == {'BAD': StockStatus.FAILED, 'FRESH': StockStatus.UP_TO_DATE, 'NEW': StockStatus.NOT_DOWNLOADED,
                         'NODATA': StockStatus.NO_DATA, 'OLD': StockStatus.STALE, 'OLDER': StockStatus.STALE}
    assert [row.symbol for row in rows] == sorted(by_symbol)  # alphabetical
    assert 'FRESH' not in [row.symbol for row in model.visible_rows(rows, True)]
    assert len(model.visible_rows(rows, False)) == 6
    # never-downloaded and failed first; then out-of-date, the least recently checked first
    assert model.queue_of(rows, 100) == ['BAD', 'NEW', 'OLDER', 'OLD']
    assert model.queue_of(rows, 2) == ['BAD', 'NEW']
    assert model.totals_line(rows) == ('1 up to date · 2 out of date · 1 not downloaded · 1 failed · '
                                       '1 with no data at Yahoo')


def test_a_session_result_wins_over_the_database():
    database = stored(('OLD', '2025-06-02', 50))
    rows = model.build_rows(['OLD'], {}, database, {'OLD': (StockStatus.UP_TO_DATE, 'just downloaded')}, NOW)
    assert rows[0].status == StockStatus.UP_TO_DATE


# --- the controller --------------------------------------------------------------------------------------------

class FakeView:
    def __init__(self) -> None:
        self.rows, self.totals, self.notices, self.running = [], '', [], False
        self.universes, self.current, self.alerts, self.closed, self.updates = [], '', 0, False, []

    def show_universes(self, names, current): self.universes, self.current = names, current
    def show_rows(self, rows): self.rows = rows
    def update_row(self, row): self.updates.append(row)
    def show_totals(self, text): self.totals = text
    def show_progress(self, done, total, text): self.progress = (done, total, text)
    def show_notice(self, text): self.notices.append(text)
    def set_running(self, running): self.running = running
    def alert(self): self.alerts += 1
    def close(self): self.closed = True


SECURITIES = {s: Security(s, f'{s} Inc', 'Nasdaq', False, ()) for s in ('AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF')}
CATALOG = Catalog(SECURITIES, [Group('Test Index', 'Index', '', (), frozenset(SECURITIES))], frozenset())


class Rig:
    """A controller with everything faked; `calls` is what was fetched, `delays` every pause it asked for."""

    def __init__(self, database=None, outcomes=None, pacing=None, cooldown=None, portfolio=()) -> None:
        self.view, self.calls, self.delays, self.cooldown = FakeView(), [], [], cooldown
        self.written, self.awake, self.outcomes = [], [], dict(outcomes or {})
        self.database = database if database is not None else stored()
        self.controller = DownloadController(
            self.view, BackgroundLoader.immediate(), lambda: CATALOG, lambda: self.database.copy(),
            lambda: list(portfolio), pacing or PacingProfile(), self.refresh, clock=lambda: NOW.timestamp(),
            pause=random.Random(1).uniform, wait=self.wait, awake=self.awake.append,
            read_cooldown=lambda: self.cooldown, write_cooldown=self.written.append)
        self.controller.start_panel()

    def refresh(self, symbol):
        self.calls.append(symbol)
        outcome = self.outcomes.get(symbol, 'new')
        if isinstance(outcome, list):  # a script: one answer per attempt
            outcome = outcome.pop(0) if len(outcome) > 1 else outcome[0]
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            outcome()
            return 'new'
        return outcome

    def wait(self, seconds):
        self.delays.append(seconds)
        return self.controller._stop.is_set()

    def row(self, symbol):
        return next(row for row in self.controller.rows if row.symbol == symbol)


def test_opening_lists_the_first_group_with_its_states():
    rig = Rig(stored(('AAA', '2025-06-10', 1), ('BBB', '2025-06-02', 50)))
    assert rig.view.current == 'Test Index'
    assert rig.view.universes == ['Test Index', model.PORTFOLIOS, model.STORED, model.PICKED]
    assert [r.symbol for r in rig.view.rows] == ['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF']
    assert rig.row('AAA').status == StockStatus.UP_TO_DATE and rig.row('BBB').status == StockStatus.STALE
    assert rig.row('CCC').name == 'CCC Inc' and rig.view.totals.startswith('1 up to date · 1 out of date')


def test_the_filter_hides_up_to_date_rows():
    rig = Rig(stored(('AAA', '2025-06-10', 1)))
    rig.controller.set_only_pending(True)
    assert 'AAA' not in [r.symbol for r in rig.view.rows] and len(rig.view.rows) == 5
    rig.controller.set_only_pending(False)
    assert len(rig.view.rows) == 6


def test_start_fetches_everything_that_is_not_up_to_date_and_turns_it_green():
    rig = Rig(stored(('AAA', '2025-06-10', 1), ('BBB', '2025-06-02', 50)))
    rig.controller.start()
    assert rig.calls == ['CCC', 'DDD', 'EEE', 'FFF', 'BBB']  # never-downloaded first, then the out-of-date one
    assert all(rig.row(s).status == StockStatus.UP_TO_DATE for s in SECURITIES)
    assert not rig.controller.running and not rig.view.running and rig.view.alerts == 1
    assert 'Finished: 5 downloaded' in rig.view.notices[-1]
    assert rig.awake == [True, False]  # the computer was kept awake only while downloading


def test_pauses_are_between_stocks_and_always_within_15_to_25_seconds():
    rig = Rig()
    rig.controller.start()
    assert len(rig.calls) == 6 and len(rig.delays) == 5  # none after the last one
    assert all(15 <= delay <= 25 for delay in rig.delays) and len(set(rig.delays)) > 1  # random, not mechanical


def test_nothing_to_download_says_so():
    rig = Rig(stored(*[(s, '2025-06-10', 1) for s in SECURITIES]))
    rig.controller.start()
    assert rig.calls == [] and 'Nothing to download' in rig.view.notices[-1]


def test_stopping_halts_at_once_and_start_continues_with_what_is_left():
    rig = Rig()
    rig.outcomes['BBB'] = lambda: rig.controller.stop()
    rig.controller.start()
    assert rig.calls == ['AAA', 'BBB'] and not rig.controller.running
    assert 'Stopped. 2 downloaded; 4 still to do' in rig.view.notices[-1] and rig.view.alerts == 0
    assert rig.row('CCC').status == StockStatus.NOT_DOWNLOADED
    rig.outcomes.pop('BBB')
    rig.calls.clear()
    rig.controller.start()
    assert rig.calls == ['CCC', 'DDD', 'EEE', 'FFF']  # AAA and BBB are green: not fetched again


def test_a_failure_turns_the_row_red_and_the_run_continues_then_start_retries_it():
    rig = Rig(outcomes={'BBB': OSError('connection reset')})
    rig.controller.start()
    assert rig.calls == ['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF']
    assert rig.row('BBB').status == StockStatus.FAILED and rig.row('BBB').reason == 'connection reset'
    assert 'Finished: 5 downloaded, 1 failed' in rig.view.notices[-1]
    rig.outcomes.pop('BBB')
    rig.calls.clear()
    rig.controller.start()
    assert rig.calls == ['BBB'] and rig.row('BBB').status == StockStatus.UP_TO_DATE


def test_five_failures_in_a_row_stop_the_run():
    rig = Rig(outcomes={s: OSError('offline') for s in ('AAA', 'BBB', 'CCC', 'DDD', 'EEE')})
    rig.controller.start()
    assert rig.calls == ['AAA', 'BBB', 'CCC', 'DDD', 'EEE']
    assert 'Stopped after 5 failures in a row' in rig.view.notices[-1] and '1 still to do' in rig.view.notices[-1]
    assert rig.view.alerts == 1


def test_a_success_resets_the_failure_count():
    outcomes = {s: OSError('x') for s in ('AAA', 'BBB', 'DDD', 'EEE')}  # CCC succeeds between them
    rig = Rig(outcomes=outcomes, pacing=PacingProfile(max_consecutive_failures=3))
    rig.controller.start()
    assert len(rig.calls) == 6  # never three failures in a row


def test_a_symbol_yahoo_has_no_prices_for_turns_grey_and_is_not_retried():
    rig = Rig(outcomes={'CCC': 'no_data'})
    rig.controller.start()
    assert rig.row('CCC').status == StockStatus.NO_DATA
    rig.calls.clear()
    rig.controller.start()
    assert rig.calls == [] and 'Nothing to download' in rig.view.notices[-1]


def test_one_rate_limit_waits_30_minutes_then_retries_the_same_stock():
    rig = Rig(outcomes={'BBB': [RateLimited('Too Many Requests'), 'new']})
    rig.controller.start()
    assert rig.calls == ['AAA', 'BBB', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF']
    assert 30 * 60 in rig.delays and rig.written == []
    assert all(rig.row(s).status == StockStatus.UP_TO_DATE for s in SECURITIES)


def test_two_rate_limits_in_a_row_stop_the_run_and_start_a_cooldown():
    rig = Rig(outcomes={'BBB': RateLimited('Too Many Requests')})
    rig.controller.start()
    assert rig.calls == ['AAA', 'BBB', 'BBB']
    assert rig.written == [NOW.timestamp() + 2 * HOUR]
    assert 'asked us to slow down twice' in rig.view.notices[-1] and rig.view.alerts == 1
    assert rig.row('BBB').status == StockStatus.NOT_DOWNLOADED  # not failed: just not reached


def test_start_is_refused_during_the_cooldown():
    rig = Rig(cooldown=NOW.timestamp() + HOUR)
    rig.controller.start()
    assert rig.calls == [] and 'slow down' in rig.view.notices[-1] and not rig.controller.running
    rig.cooldown = NOW.timestamp() - 1  # over
    rig.controller.start()
    assert len(rig.calls) == 6


def test_update_database_universe_lists_only_stored_stocks_and_queues_the_out_of_date_ones():
    rig = Rig(stored(('AAA', '2025-06-10', 1), ('BBB', '2025-06-02', 50), ('ZZZ', '2025-05-01', 99)))
    rig.controller.choose_universe(model.STORED)
    assert [r.symbol for r in rig.view.rows] == ['AAA', 'BBB', 'ZZZ']
    rig.controller.start()
    assert rig.calls == ['ZZZ', 'BBB']  # the least recently checked first; AAA is current


def test_picking_a_stock_adds_it_to_the_picked_list():
    rig = Rig()
    rig.controller.pick('CCC')
    rig.controller.pick('AAA')
    rig.controller.pick('CCC')
    assert rig.view.current == model.PICKED and [r.symbol for r in rig.view.rows] == ['AAA', 'CCC']
    assert rig.row('CCC').name == 'CCC Inc'


def test_portfolio_stocks_are_a_universe():
    rig = Rig(portfolio=['BBB', 'AAA'])
    rig.controller.choose_universe(model.PORTFOLIOS)
    assert [r.symbol for r in rig.view.rows] == ['AAA', 'BBB']


def test_the_run_is_capped():
    rig = Rig(pacing=PacingProfile(max_per_run=2))
    rig.controller.start()
    assert rig.calls == ['AAA', 'BBB']


def test_the_stock_library_is_told_when_a_run_ends():
    rig = Rig()
    ended = []
    rig.controller.on_ended = lambda: ended.append(True)
    rig.controller.start()
    assert ended == [True]


# --- the price refresh and the offline reader ------------------------------------------------------------------

@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'prices.db')


def frame(days=3) -> pd.DataFrame:
    index = pd.bdate_range('2025-06-02', periods=days, name='date')
    return pd.DataFrame({'open': 1.0, 'high': 2.0, 'low': 0.5, 'close': 1.5, 'volume': 100, 'dividend': 0.0,
                         'split': 0.0}, index=index)


def test_refresh_reports_new_then_updated_and_marks_the_stock_checked(database, monkeypatch):
    monkeypatch.setattr(history, '_download', lambda symbol, start=None, strict=False: frame())
    assert history.refresh('AAA') == history.NEW
    assert history.refresh('AAA') == history.UPDATED
    assert store.checked_at('AAA') is not None and len(history.load_stored('AAA')) == 3


def test_refresh_reports_no_data_when_yahoo_returns_nothing(database, monkeypatch):
    monkeypatch.setattr(history, '_download', lambda symbol, start=None, strict=False: pd.DataFrame(columns=store.COLUMNS))
    assert history.refresh('NOPE') == history.NO_DATA


def test_refresh_turns_a_yahoo_rate_limit_into_ratelimited_and_lets_other_errors_through(database, monkeypatch):
    from yfinance.exceptions import YFRateLimitError

    def limited(symbol, start=None, strict=False):
        raise YFRateLimitError()
    monkeypatch.setattr(history, '_download', limited)
    with pytest.raises(RateLimited):
        history.refresh('AAA')

    def broken(symbol, start=None, strict=False):
        raise OSError('network down')
    monkeypatch.setattr(history, '_download', broken)
    with pytest.raises(OSError):
        history.refresh('AAA')
    assert store.checked_at('AAA') is None  # a failed attempt is not recorded as checked


def test_load_stored_never_asks_yahoo(database, monkeypatch):
    store.save('AAA', frame())

    def forbidden(*args, **kwargs):
        raise AssertionError('load_stored must not download')
    monkeypatch.setattr(history, '_download', forbidden)
    monkeypatch.setattr(history.yf, 'Ticker', forbidden)
    assert len(history.load_stored('AAA')) == 3 and history.load_stored('MISSING').empty

"""Local price database (SQLite): every daily row downloaded so far, kept for charts and backtesting.

One file, data/prices.db. Safe to use from several threads: each call opens its own connection.
"""
import sqlite3
import time
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'prices.db'
COLUMNS = ['open', 'high', 'low', 'close', 'volume', 'dividend', 'split']

SCHEMA = '''
CREATE TABLE IF NOT EXISTS daily (
    symbol   TEXT NOT NULL,
    date     TEXT NOT NULL,      -- YYYY-MM-DD
    open     REAL, high REAL, low REAL, close REAL,
    volume   INTEGER,
    dividend REAL NOT NULL DEFAULT 0,  -- cash dividend paid per share that day
    split    REAL NOT NULL DEFAULT 0,  -- split ratio that day (2.0 = 2-for-1), 0 if none
    PRIMARY KEY (symbol, date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS symbols (
    symbol     TEXT PRIMARY KEY,
    checked_at REAL NOT NULL     -- when Yahoo was last asked for new rows (Unix time)
);
CREATE TABLE IF NOT EXISTS financials (
    symbol   TEXT NOT NULL,
    period   TEXT NOT NULL,      -- 'quarterly' or 'annual'
    end_date TEXT NOT NULL,      -- last day of the quarter or fiscal year, YYYY-MM-DD
    revenue  REAL,               -- total revenue
    eps      REAL,               -- diluted earnings per share
    PRIMARY KEY (symbol, period, end_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS financials_checked (
    symbol     TEXT PRIMARY KEY,
    checked_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    kind     TEXT NOT NULL,      -- e.g. 'profile' (a company's Yahoo profile)
    symbol   TEXT NOT NULL,
    saved_at REAL NOT NULL,      -- Unix time
    body     TEXT NOT NULL,      -- JSON
    PRIMARY KEY (kind, symbol)
) WITHOUT ROWID;
'''
FINANCIAL_COLUMNS = ['revenue', 'eps']


def _connect() -> sqlite3.Connection:
    path = DB_PATH  # read at call time, so tests can point it at a temporary file
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.executescript(SCHEMA)
    return connection


def read(symbol: str) -> pd.DataFrame:
    with _connect() as connection:
        rows = pd.read_sql_query(f'SELECT date, {", ".join(COLUMNS)} FROM daily WHERE symbol = ? ORDER BY date',
                                 connection, params=(symbol,), parse_dates=['date'])
    return rows.set_index('date')


def save(symbol: str, daily: pd.DataFrame, replace_all: bool = False) -> None:
    """Insert or update rows. With replace_all, the symbol's existing rows are removed first."""
    rows = [(symbol, f'{day:%Y-%m-%d}', *(row[c] for c in COLUMNS)) for day, row in daily.iterrows()]
    with _connect() as connection:
        if replace_all:
            connection.execute('DELETE FROM daily WHERE symbol = ?', (symbol,))
        connection.executemany(f'INSERT OR REPLACE INTO daily VALUES ({", ".join("?" * (len(COLUMNS) + 2))})', rows)


def checked_at(symbol: str, table: str = 'symbols') -> float | None:
    with _connect() as connection:
        row = connection.execute(f'SELECT checked_at FROM {table} WHERE symbol = ?', (symbol,)).fetchone()
    return row[0] if row else None


def mark_checked(symbol: str, table: str = 'symbols') -> None:
    with _connect() as connection:
        connection.execute(f'INSERT OR REPLACE INTO {table} VALUES (?, ?)', (symbol, time.time()))


def read_financials(symbol: str, period: str) -> pd.DataFrame:
    with _connect() as connection:
        rows = pd.read_sql_query(
            'SELECT end_date, revenue, eps FROM financials WHERE symbol = ? AND period = ? ORDER BY end_date',
            connection, params=(symbol, period), parse_dates=['end_date'])
    return rows.set_index('end_date')


def save_financials(symbol: str, period: str, figures: pd.DataFrame) -> None:
    """Insert or update; older periods Yahoo no longer returns are kept, so the history grows over time."""
    rows = [(symbol, period, f'{day:%Y-%m-%d}', *(None if pd.isna(row[c]) else float(row[c])
                                                   for c in FINANCIAL_COLUMNS))
            for day, row in figures.iterrows()]
    with _connect() as connection:
        connection.executemany('INSERT OR REPLACE INTO financials VALUES (?, ?, ?, ?, ?)', rows)


def read_document(kind: str, symbol: str) -> tuple[float, str] | None:
    """(saved_at, JSON text) of a stored document, or None."""
    with _connect() as connection:
        row = connection.execute('SELECT saved_at, body FROM documents WHERE kind = ? AND symbol = ?',
                                 (kind, symbol)).fetchone()
    return (row[0], row[1]) if row else None


def save_document(kind: str, symbol: str, body: str) -> None:
    with _connect() as connection:
        connection.execute('INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?)', (kind, symbol, time.time(), body))


def stored_stocks() -> pd.DataFrame:
    """One row per symbol with stored prices: rows, first and last date, the last two closes, when last checked.

    Indexes (symbols starting with '^', such as the S&P 500 used for relative strength) are left out.
    """
    query = '''
        SELECT d.symbol, COUNT(*) AS days, MIN(d.date) AS first_date, MAX(d.date) AS last_date,
               (SELECT close FROM daily WHERE symbol = d.symbol ORDER BY date DESC LIMIT 1) AS last_close,
               (SELECT close FROM daily WHERE symbol = d.symbol ORDER BY date DESC LIMIT 1 OFFSET 1) AS previous_close,
               s.checked_at
        FROM daily d LEFT JOIN symbols s ON s.symbol = d.symbol
        WHERE d.symbol NOT LIKE '^%'
        GROUP BY d.symbol ORDER BY d.symbol'''
    with _connect() as connection:
        return pd.read_sql_query(query, connection, parse_dates=['first_date', 'last_date'])

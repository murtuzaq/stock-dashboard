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
'''


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
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


def checked_at(symbol: str) -> float | None:
    with _connect() as connection:
        row = connection.execute('SELECT checked_at FROM symbols WHERE symbol = ?', (symbol,)).fetchone()
    return row[0] if row else None


def mark_checked(symbol: str) -> None:
    with _connect() as connection:
        connection.execute('INSERT OR REPLACE INTO symbols VALUES (?, ?)', (symbol, time.time()))

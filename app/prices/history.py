"""Daily price history: served from the local database, topped up from Yahoo Finance when it may be out of date."""
import time
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

from . import store

# yfinance 1.7 still uses pandas features that pandas 3.1 has deprecated; the warnings are harmless noise.
warnings.filterwarnings('ignore', module='yfinance')

MAX_AGE_SECONDS = 6 * 3600  # ask Yahoo for new rows at most this often per symbol
OVERLAP = pd.Timedelta(days=14)  # re-download this much already-stored history to detect splits and corrections
PRICE_COLUMNS = ['open', 'high', 'low', 'close', 'volume']


def _download(symbol: str, start: pd.Timestamp | None = None) -> pd.DataFrame:
    # Yahoo writes share classes with a dash (BRK-B) where exchanges use a dot (BRK.B).
    # Prices are adjusted for stock splits only (not dividends), the same as Google Finance and TradingView,
    # so past prices are the ones people actually traded at.
    ticker = yf.Ticker(symbol.replace('.', '-'))
    raw = ticker.history(start=start, interval='1d', auto_adjust=False) if start is not None else \
        ticker.history(period='max', interval='1d', auto_adjust=False)
    if raw.empty:
        return pd.DataFrame(columns=store.COLUMNS)
    daily = raw.rename(columns={'Dividends': 'dividend', 'Stock Splits': 'split'}).rename(columns=str.lower)
    daily = daily[store.COLUMNS].dropna(subset=PRICE_COLUMNS)
    daily.index = pd.DatetimeIndex(daily.index.date, name='date')
    return daily


def _matches(stored: pd.DataFrame, fresh: pd.DataFrame) -> bool:
    """True if the days both copies have agree, i.e. no split or correction happened since the last update."""
    common = stored.index.intersection(fresh.index)
    return len(common) > 0 and np.allclose(stored.loc[common, 'close'], fresh.loc[common, 'close'], rtol=1e-3)


def _update(symbol: str, stored: pd.DataFrame) -> None:
    if stored.empty:
        store.save(symbol, _download(symbol), replace_all=True)
        return
    recent = _download(symbol, start=stored.index[-1] - OVERLAP)
    if recent.empty:
        return
    if _matches(stored, recent):
        store.save(symbol, recent)
    else:
        print(f'{symbol}: stored prices differ from Yahoo (split or correction); downloading full history again')
        store.save(symbol, _download(symbol), replace_all=True)


def load_daily(symbol: str) -> pd.DataFrame:
    """Daily open/high/low/close/volume (plus dividend and split) indexed by date. Empty if no data exists."""
    stored = store.read(symbol)
    last_checked = store.checked_at(symbol)
    if last_checked is None or time.time() - last_checked > MAX_AGE_SECONDS:
        try:
            _update(symbol, stored)
            store.mark_checked(symbol)
            stored = store.read(symbol)
        except Exception as error:
            print(f'Could not update {symbol} ({error}); using stored prices')
    return stored

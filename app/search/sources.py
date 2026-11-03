"""Downloads the lists the search bar needs. Results are cached on disk and refreshed weekly."""
import io
import json
import re
import time
import urllib.request
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parents[2] / 'cache'
MAX_AGE_SECONDS = 7 * 24 * 3600
BROWSER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
WIKIPEDIA_AGENT = 'stock-dashboard/0.1 (personal project)'

# Official directories of every US-listed stock and ETF.
NASDAQ_LISTED = 'https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt'
OTHER_LISTED = 'https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt'
NASDAQ_100 = 'https://api.nasdaq.com/api/quote/list-type/nasdaq100'
SP_500 = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'

EXCHANGES = {'A': 'NYSE American', 'N': 'NYSE', 'P': 'NYSE Arca', 'Z': 'Cboe BZX', 'V': 'IEX'}
# Warrants, rights and units are special-purpose securities, not regular shares.
NOT_SHARES = re.compile(r'\b(warrants?|rights?|units?)\b', re.IGNORECASE)
SHARE_SUFFIX = re.compile(r'\s+(common stock|common shares|ordinary shares)$', re.IGNORECASE)
SHARE_CLASS = re.compile(r'\bClass [A-Z]\b')


def _download(url: str, user_agent: str) -> str:
    request = urllib.request.Request(url, headers={'User-Agent': user_agent, 'Accept': '*/*'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode('utf-8')


def cached(name: str, fetch):
    """Return fresh cached data, otherwise download it. Falls back to a stale copy if offline."""
    path = CACHE_DIR / f'{name}.json'
    if path.exists() and time.time() - path.stat().st_mtime < MAX_AGE_SECONDS:
        return json.loads(path.read_text('utf-8'))
    try:
        data = fetch()
    except Exception as error:
        if path.exists():
            print(f'Could not refresh {name} ({error}); using cached copy')
            return json.loads(path.read_text('utf-8'))
        print(f'Could not download {name}: {error}')
        return None
    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data), 'utf-8')
    return data


def clean_name(raw: str) -> str:
    """'Alphabet Inc. - Class A Common Stock' -> 'Alphabet Inc. (Class A)'."""
    company, _, detail = raw.partition(' - ')
    company = SHARE_SUFFIX.sub('', company.strip())
    share_class = SHARE_CLASS.search(detail or raw)
    return f'{company} ({share_class.group()})' if share_class else company


def fetch_listed() -> list[list]:
    """Every US-listed stock and ETF as [symbol, name, exchange, is_etf]."""
    rows = []
    for url, symbol_col, exchange_col in ((NASDAQ_LISTED, 'Symbol', None), (OTHER_LISTED, 'ACT Symbol', 'Exchange')):
        lines = _download(url, BROWSER_AGENT).splitlines()
        header = lines[0].split('|')
        for line in lines[1:]:
            if line.startswith('File Creation Time'):
                continue
            row = dict(zip(header, line.split('|')))
            symbol, name = row[symbol_col], row['Security Name']
            if row['Test Issue'] == 'Y' or '$' in symbol or NOT_SHARES.search(name):
                continue
            exchange = EXCHANGES.get(row[exchange_col], 'Other') if exchange_col else 'Nasdaq'
            rows.append([symbol, clean_name(name), exchange, row['ETF'] == 'Y'])
    return rows


def fetch_nasdaq_100() -> list[str]:
    data = json.loads(_download(NASDAQ_100, BROWSER_AGENT))
    return [row['symbol'] for row in data['data']['data']['rows']]


def fetch_sp_500() -> list[str]:
    tables = pd.read_html(io.StringIO(_download(SP_500, WIKIPEDIA_AGENT)))
    table = next(t for t in tables if 'Symbol' in t.columns)
    return table['Symbol'].astype(str).tolist()

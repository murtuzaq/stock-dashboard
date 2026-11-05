"""A company's profile from Yahoo Finance: what it does, its key numbers, and what analysts think.

Stored in the local database and refreshed weekly (these figures change slowly), so the overview opens instantly.
Fields Yahoo does not have for a symbol (ETFs have no profit margin, for example) are None.
"""
import json
import logging
import time
import warnings
from dataclasses import asdict, dataclass, fields

import yfinance as yf

from prices import store

warnings.filterwarnings('ignore', module='yfinance')
log = logging.getLogger(__name__)

MAX_AGE_SECONDS = 7 * 24 * 3600
KIND = 'profile'


@dataclass(frozen=True)
class CompanyProfile:
    symbol: str
    name: str | None = None
    summary: str | None = None  # what the business does, in Yahoo's words
    quote_type: str | None = None  # EQUITY, ETF, INDEX ...
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    employees: int | None = None
    website: str | None = None
    price: float | None = None
    market_cap: float | None = None
    trailing_pe: float | None = None  # price ÷ the last 12 months' earnings per share
    forward_pe: float | None = None  # price ÷ next year's expected earnings per share
    peg: float | None = None  # P/E ÷ expected earnings growth
    price_to_book: float | None = None
    dividend_yield_pct: float | None = None  # yearly dividends as % of the price
    payout_ratio: float | None = None  # share of profit paid out as dividends (0.5 = 50%)
    profit_margin: float | None = None  # share of revenue left as profit (0.16 = 16%)
    operating_margin: float | None = None
    return_on_equity: float | None = None
    debt_to_equity: float | None = None  # in percent, as Yahoo gives it (185 = debt is 1.85× equity)
    current_ratio: float | None = None  # short-term assets ÷ short-term bills
    revenue_growth: float | None = None  # latest quarter vs a year earlier (0.047 = +4.7%)
    earnings_growth: float | None = None
    free_cash_flow: float | None = None
    beta: float | None = None  # how much it swings compared with the market (1 = the same)
    high_52w: float | None = None
    low_52w: float | None = None
    recommendation: str | None = None  # analysts' consensus: strong_buy, buy, hold, underperform, sell
    recommendation_mean: float | None = None  # 1 = strong buy ... 5 = sell
    analysts: int | None = None
    target_mean: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    short_pct_float: float | None = None  # share of tradable shares sold short (0.02 = 2%)

    @property
    def is_empty(self) -> bool:
        return self.name is None and self.summary is None


# Yahoo's field names for each profile field (the first one present wins).
YAHOO_FIELDS = {
    'name': ('longName', 'shortName'), 'summary': ('longBusinessSummary',), 'quote_type': ('quoteType',),
    'sector': ('sector',), 'industry': ('industry',), 'country': ('country',), 'employees': ('fullTimeEmployees',),
    'website': ('website',), 'price': ('currentPrice', 'regularMarketPrice'), 'market_cap': ('marketCap',),
    'trailing_pe': ('trailingPE',), 'forward_pe': ('forwardPE',), 'peg': ('pegRatio', 'trailingPegRatio'),
    'price_to_book': ('priceToBook',), 'dividend_yield_pct': ('dividendYield',), 'payout_ratio': ('payoutRatio',),
    'profit_margin': ('profitMargins',), 'operating_margin': ('operatingMargins',),
    'return_on_equity': ('returnOnEquity',), 'debt_to_equity': ('debtToEquity',), 'current_ratio': ('currentRatio',),
    'revenue_growth': ('revenueGrowth',), 'earnings_growth': ('earningsGrowth',), 'free_cash_flow': ('freeCashflow',),
    'beta': ('beta',), 'high_52w': ('fiftyTwoWeekHigh',), 'low_52w': ('fiftyTwoWeekLow',),
    'recommendation': ('recommendationKey',), 'recommendation_mean': ('recommendationMean',),
    'analysts': ('numberOfAnalystOpinions',), 'target_mean': ('targetMeanPrice',),
    'target_high': ('targetHighPrice',), 'target_low': ('targetLowPrice',), 'short_pct_float': ('shortPercentOfFloat',),
}


def from_yahoo(symbol: str, info: dict) -> CompanyProfile:
    """Pick our fields out of Yahoo's ~180-field `info` dictionary."""
    values = {}
    for name, keys in YAHOO_FIELDS.items():
        value = next((info[key] for key in keys if info.get(key) not in (None, '', 'none')), None)
        values[name] = value
    if values['recommendation'] == 'none':
        values['recommendation'] = None
    return CompanyProfile(symbol, **values)


def _download(symbol: str) -> CompanyProfile:
    # Yahoo writes share classes with a dash (BRK-B) where exchanges use a dot (BRK.B).
    return from_yahoo(symbol, yf.Ticker(symbol.replace('.', '-')).info or {})


def _decode(body: str) -> CompanyProfile:
    data = json.loads(body)
    known = {f.name for f in fields(CompanyProfile)}
    return CompanyProfile(**{key: value for key, value in data.items() if key in known})


def load_profile(symbol: str) -> CompanyProfile:
    """The stored profile if it is under a week old; otherwise download it (falling back to a stale copy)."""
    stored = store.read_document(KIND, symbol)
    if stored and time.time() - stored[0] < MAX_AGE_SECONDS:
        return _decode(stored[1])
    try:
        profile = _download(symbol)
    except Exception:
        log.exception('Could not download the profile of %s', symbol)
        return _decode(stored[1]) if stored else CompanyProfile(symbol)
    if not profile.is_empty:
        store.save_document(KIND, symbol, json.dumps(asdict(profile)))
    return profile

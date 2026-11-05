"""Company profiles (Yahoo fields, weekly cache) and the like/dislike rules."""
import numpy as np
import pandas as pd
import pytest

from company import CompanyProfile, assess, from_yahoo, load_profile
from company import profile as profile_module
from conftest import random_walk
from prices import store

IBM_INFO = {
    'longName': 'International Business Machines Corporation', 'longBusinessSummary': 'IBM provides solutions.',
    'quoteType': 'EQUITY', 'sector': 'Technology', 'industry': 'IT Services', 'country': 'United States',
    'fullTimeEmployees': 264300, 'currentPrice': 250.0, 'marketCap': 2.4e11, 'trailingPE': 21.3,
    'forwardPE': 19.2, 'pegRatio': 2.36, 'dividendYield': 2.7, 'payoutRatio': 0.58, 'profitMargins': 0.16,
    'returnOnEquity': 0.35, 'debtToEquity': 185.4, 'currentRatio': 0.85, 'revenueGrowth': 0.047,
    'earningsGrowth': 0.25, 'freeCashflow': 1.24e10, 'beta': 0.76, 'fiftyTwoWeekHigh': 332.5, 'fiftyTwoWeekLow': 199.2,
    'recommendationKey': 'buy', 'recommendationMean': 2.28, 'numberOfAnalystOpinions': 23, 'targetMeanPrice': 259.3,
    'targetHighPrice': 300.0, 'targetLowPrice': 174.0, 'shortPercentOfFloat': 0.023, 'somethingElse': 1,
}


def texts(points):
    return [point.text for point in points]


def test_yahoo_fields_are_mapped_and_missing_ones_are_none():
    profile = from_yahoo('IBM', IBM_INFO)
    assert profile.name == 'International Business Machines Corporation' and profile.employees == 264300
    assert profile.price == 250.0 and profile.analysts == 23 and profile.dividend_yield_pct == 2.7
    etf = from_yahoo('SPY', {'shortName': 'SPDR S&P 500', 'quoteType': 'ETF', 'regularMarketPrice': 600.0,
                             'recommendationKey': 'none'})
    assert etf.name == 'SPDR S&P 500' and etf.price == 600.0 and etf.recommendation is None
    assert etf.profit_margin is None and not etf.is_empty and CompanyProfile('X').is_empty


@pytest.fixture
def temporary_database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'prices.db')


def test_profiles_are_stored_and_reused_for_a_week(temporary_database, monkeypatch):
    downloads = []
    monkeypatch.setattr(profile_module, '_download', lambda symbol: downloads.append(symbol) or from_yahoo(symbol, IBM_INFO))
    first, second = load_profile('IBM'), load_profile('IBM')
    assert first == second and downloads == ['IBM']  # the second came from the database
    monkeypatch.setattr(profile_module, 'MAX_AGE_SECONDS', -1)  # everything is stale now
    load_profile('IBM')
    assert downloads == ['IBM', 'IBM']


def test_a_failed_download_falls_back_to_the_stored_copy_or_an_empty_profile(temporary_database, monkeypatch):
    monkeypatch.setattr(profile_module, '_download', lambda symbol: from_yahoo(symbol, IBM_INFO))
    load_profile('IBM')

    def offline(symbol):
        raise ConnectionError('offline')
    monkeypatch.setattr(profile_module, '_download', offline)
    monkeypatch.setattr(profile_module, 'MAX_AGE_SECONDS', -1)
    assert load_profile('IBM').name == 'International Business Machines Corporation'
    assert load_profile('NEW').is_empty


def test_ibm_like_numbers_give_a_mixed_picture():
    result = assess(from_yahoo('IBM', IBM_INFO))
    likes, dislikes = texts(result.likes), texts(result.dislikes)
    assert 'Sales are growing: revenue +4.7% on a year ago' in likes
    assert 'Profits are growing: earnings +25.0% on a year ago' in likes
    assert 'Analysts are positive: 23 analysts, consensus "Buy"' in likes
    assert 'Pays a 2.7% dividend' in likes and 'Steadier than the market (beta 0.76)' in likes
    assert 'Carries a lot of debt: 1.9× its shareholders\' equity' in dislikes
    assert 'Expensive for its expected growth: PEG 2.36' in dislikes
    assert any(t.startswith('Short-term bills exceed') for t in dislikes)
    assert all(point.why for point in result.likes + result.dislikes)  # every point is explained


def test_a_struggling_company_collects_dislikes():
    profile = CompanyProfile('BAD', revenue_growth=-0.12, earnings_growth=-0.4, profit_margin=-0.08, trailing_pe=60,
                             free_cash_flow=-5e8, short_pct_float=0.22, beta=2.1, price=10.0, target_mean=8.0,
                             recommendation='underperform', recommendation_mean=3.6, analysts=8, dividend_yield_pct=4.0,
                             payout_ratio=1.4)
    dislikes = texts(assess(profile).dislikes)
    for start in ('Sales are shrinking', 'Profits are falling', 'Losing money', 'Priced richly', 'Burns cash',
                  'Many traders are betting against it: 22%', 'Swings a lot', 'Analysts are cautious',
                  'Analysts\' average target $8.00 is -20% below', 'The dividend uses 140% of profits'):
        assert any(text.startswith(start) for text in dislikes), start


def test_missing_numbers_give_no_points_and_a_glitchy_forward_pe_is_ignored():
    assert assess(CompanyProfile('EMPTY')).likes == [] and assess(CompanyProfile('EMPTY')).dislikes == []
    glitch = assess(CompanyProfile('X', trailing_pe=24.0, forward_pe=5.2))  # profits x4.6 next year? a data error
    assert not any('expected to rise' in text for text in texts(glitch.likes))
    real = assess(CompanyProfile('X', trailing_pe=27.2, forward_pe=23.0))
    assert any('expected to rise' in text for text in texts(real.likes))


def trending(direction: float, years: int = 3, seed: int = 1) -> pd.DataFrame:
    daily = random_walk(252 * years, seed=seed)
    trend = np.exp(np.linspace(0, direction, len(daily)))
    for column in ('open', 'high', 'low', 'close'):
        daily[column] = daily[column] * trend
    return daily


def test_trend_and_market_comparison_come_from_the_stored_prices():
    flat_market = trending(0.0, seed=9)
    flat_market[['open', 'high', 'low', 'close']] = 100.0
    rising = assess(CompanyProfile('UP'), trending(2.0), flat_market)
    assert any(t.startswith('Beating the market over the past year') for t in texts(rising.likes))
    assert any(t.startswith('In a long-term uptrend') for t in texts(rising.likes))
    falling = assess(CompanyProfile('DOWN'), trending(-2.0), flat_market)
    dislikes = texts(falling.dislikes)
    assert any(t.startswith('Lagging the market') for t in dislikes)
    assert any(t.startswith('In a long-term downtrend') for t in dislikes)
    assert any('below its 52-week high' in t for t in dislikes)

"""What investors tend to like and dislike about a stock, worked out from its numbers.

Every point is a plain rule with a stated threshold (see the constants below) and quotes the number behind it,
so nothing is invented: a missing figure simply produces no point. `why` explains the measure to a beginner.
"""
from dataclasses import dataclass, field

import pandas as pd

from prices import range_change
from .profile import CompanyProfile

# Thresholds (fractions unless noted). Common rules of thumb, not investment advice.
FAST_GROWTH, SOME_GROWTH = 0.10, 0.02
HIGH_MARGIN, THIN_MARGIN = 0.15, 0.05
HIGH_ROE = 0.20
CHEAP_PE, RICH_PE = 15, 35
RICH_PEG = 2.0
HEAVY_DEBT, LIGHT_DEBT = 150, 50  # debt as % of equity
TIGHT_CURRENT, COMFORTABLE_CURRENT = 1.0, 1.5
GOOD_YIELD_PCT, HIGH_PAYOUT = 2.0, 0.8
POSITIVE_ANALYSTS, CAUTIOUS_ANALYSTS, MIN_ANALYSTS = 2.5, 3.0, 3  # recommendation mean: 1 strong buy ... 5 sell
TARGET_UPSIDE, TARGET_DOWNSIDE = 0.15, -0.05
HIGH_SHORT = 0.10
HIGH_BETA, LOW_BETA = 1.5, 0.8
MARKET_GAP_PTS = 10  # percentage points ahead of / behind the S&P 500 over a year
FAR_FROM_HIGH = 0.25

RECOMMENDATIONS = {'strong_buy': 'Strong buy', 'buy': 'Buy', 'hold': 'Hold', 'underperform': 'Underperform',
                   'sell': 'Sell', 'strong_sell': 'Strong sell'}


@dataclass(frozen=True)
class Point:
    text: str  # the finding, with its number
    why: str  # what the measure means


@dataclass
class Assessment:
    likes: list[Point] = field(default_factory=list)
    dislikes: list[Point] = field(default_factory=list)


def _pct(value: float, digits: int = 1) -> str:
    return f'{value * 100:+.{digits}f}%'


def assess(profile: CompanyProfile, daily: pd.DataFrame | None = None,
           benchmark: pd.DataFrame | None = None) -> Assessment:
    result = Assessment()
    like, dislike = result.likes.append, result.dislikes.append
    p = profile

    # Growth
    if p.revenue_growth is not None:
        why = 'Revenue is everything the company sells. Growing sales usually mean growing demand.'
        if p.revenue_growth >= FAST_GROWTH:
            like(Point(f'Sales are growing fast: revenue {_pct(p.revenue_growth)} on a year ago', why))
        elif p.revenue_growth >= SOME_GROWTH:
            like(Point(f'Sales are growing: revenue {_pct(p.revenue_growth)} on a year ago', why))
        elif p.revenue_growth < 0:
            dislike(Point(f'Sales are shrinking: revenue {_pct(p.revenue_growth)} on a year ago', why))
    if p.earnings_growth is not None:
        why = 'Earnings are the profit left after all costs. Share prices tend to follow earnings over time.'
        if p.earnings_growth >= FAST_GROWTH:
            like(Point(f'Profits are growing: earnings {_pct(p.earnings_growth)} on a year ago', why))
        elif p.earnings_growth < 0:
            dislike(Point(f'Profits are falling: earnings {_pct(p.earnings_growth)} on a year ago', why))

    # Profitability
    if p.profit_margin is not None:
        why = 'Profit margin: how much of each dollar of sales is left as profit.'
        if p.profit_margin >= HIGH_MARGIN:
            like(Point(f'Very profitable: keeps {p.profit_margin * 100:.0f}¢ of every sales dollar as profit', why))
        elif p.profit_margin < 0:
            dislike(Point(f'Losing money: a {abs(p.profit_margin) * 100:.1f}% loss on sales', why))
        elif p.profit_margin < THIN_MARGIN:
            dislike(Point(f'Thin profits: only {p.profit_margin * 100:.1f}% of sales becomes profit', why))
    if p.return_on_equity is not None and p.return_on_equity >= HIGH_ROE:
        like(Point(f'Uses shareholders\' money well: return on equity {p.return_on_equity * 100:.0f}%',
                   'Return on equity: yearly profit as a share of the money shareholders have in the business.'))

    # Valuation
    if p.trailing_pe is not None and p.trailing_pe > 0:
        why = (f'P/E (price ÷ earnings): investors pay ${p.trailing_pe:.0f} for each $1 of yearly profit. '
               'The S&P 500 is often around 20-25.')
        if p.trailing_pe <= CHEAP_PE:
            like(Point(f'Priced cheaply for its profits: P/E {p.trailing_pe:.1f}', why))
        elif p.trailing_pe >= RICH_PE:
            dislike(Point(f'Priced richly for its profits: P/E {p.trailing_pe:.1f}', why))
        # A forward P/E under half of today's would mean profits more than doubling: usually a data glitch.
        if p.forward_pe is not None and p.trailing_pe * 0.5 <= p.forward_pe < p.trailing_pe * 0.9:
            like(Point(f'Profits are expected to rise: next year\'s P/E {p.forward_pe:.1f} vs {p.trailing_pe:.1f} today',
                       'Forward P/E uses analysts\' profit estimates for the next 12 months. Lower than today\'s '
                       'P/E means they expect profits to grow.'))
    if p.peg is not None and p.peg > RICH_PEG:
        dislike(Point(f'Expensive for its expected growth: PEG {p.peg:.2f}',
                      'PEG is the P/E divided by expected yearly earnings growth. Around 1 is often called fair; '
                      'above 2 means paying a lot for that growth.'))

    # Balance sheet and cash
    if p.debt_to_equity is not None:
        why = 'Debt compared with the money shareholders have in the business. Heavy debt adds risk if business slows.'
        if p.debt_to_equity >= HEAVY_DEBT:
            dislike(Point(f'Carries a lot of debt: {p.debt_to_equity / 100:.1f}× its shareholders\' equity', why))
        elif p.debt_to_equity <= LIGHT_DEBT:
            like(Point(f'Little debt: only {p.debt_to_equity:.0f}% of its shareholders\' equity', why))
    if p.current_ratio is not None:
        why = 'Current ratio: cash and other short-term assets ÷ bills due within a year.'
        if p.current_ratio < TIGHT_CURRENT:
            dislike(Point(f'Short-term bills exceed short-term assets (current ratio {p.current_ratio:.2f})', why))
        elif p.current_ratio >= COMFORTABLE_CURRENT:
            like(Point(f'Comfortable cash cushion (current ratio {p.current_ratio:.2f})', why))
    if p.free_cash_flow is not None:
        why = 'Free cash flow: cash left each year after running and investing in the business.'
        if p.free_cash_flow > 0:
            like(Point(f'Generates cash: ${_short(p.free_cash_flow)} of free cash flow a year', why))
        else:
            dislike(Point(f'Burns cash: free cash flow of -${_short(-p.free_cash_flow)} a year', why))

    # Dividend
    if p.dividend_yield_pct is not None and p.dividend_yield_pct >= GOOD_YIELD_PCT:
        like(Point(f'Pays a {p.dividend_yield_pct:.1f}% dividend',
                   'Dividend yield: cash paid to shareholders each year, as a % of the share price.'))
        if p.payout_ratio is not None and p.payout_ratio >= HIGH_PAYOUT:
            dislike(Point(f'The dividend uses {p.payout_ratio * 100:.0f}% of profits, leaving little room to raise it',
                          'Payout ratio: the share of profit paid out as dividends.'))

    # What analysts and traders think
    if p.recommendation_mean is not None and (p.analysts or 0) >= MIN_ANALYSTS:
        label = RECOMMENDATIONS.get(p.recommendation or '', p.recommendation or '')
        why = (f'Wall Street analysts\' average rating, from 1 (strong buy) to 5 (sell): '
               f'{p.recommendation_mean:.1f}. Analysts are often too optimistic, so treat it as one opinion.')
        if p.recommendation_mean <= POSITIVE_ANALYSTS:
            like(Point(f'Analysts are positive: {p.analysts} analysts, consensus "{label}"', why))
        elif p.recommendation_mean >= CAUTIOUS_ANALYSTS:
            dislike(Point(f'Analysts are cautious: {p.analysts} analysts, consensus "{label}"', why))
    if p.target_mean and p.price:
        upside = p.target_mean / p.price - 1
        why = (f'The average 12-month price analysts expect (range ${p.target_low or 0:,.0f} to '
               f'${p.target_high or 0:,.0f}).')
        if upside >= TARGET_UPSIDE:
            like(Point(f'Analysts\' average target ${p.target_mean:,.2f} is {_pct(upside, 0)} above today\'s price', why))
        elif upside <= TARGET_DOWNSIDE:
            dislike(Point(f'Analysts\' average target ${p.target_mean:,.2f} is {_pct(upside, 0)} below today\'s price',
                          why))
    if p.short_pct_float is not None and p.short_pct_float >= HIGH_SHORT:
        dislike(Point(f'Many traders are betting against it: {p.short_pct_float * 100:.0f}% of its shares are sold short',
                      'Short selling profits when the price falls. A lot of it means many expect a drop '
                      '(and can also cause sharp jumps if they rush to buy back).'))
    if p.beta is not None:
        why = 'Beta: how much the price swings compared with the whole market (1 = the same).'
        if p.beta >= HIGH_BETA:
            dislike(Point(f'Swings a lot: about {p.beta:.1f}× as much as the market', why))
        elif 0 < p.beta <= LOW_BETA:
            like(Point(f'Steadier than the market (beta {p.beta:.2f})', why))

    if daily is not None and not daily.empty:
        _price_action(daily, benchmark, like, dislike)
    return result


def _price_action(daily, benchmark, like, dislike) -> None:
    """Trend and performance points from the stored daily prices."""
    close = daily['close']
    year_ago = daily.index[-1] - pd.DateOffset(years=1)
    if daily.index[0] <= year_ago and benchmark is not None and not benchmark.empty:
        _, stock = range_change(daily, year_ago)
        _, market = range_change(benchmark, year_ago)
        gap = stock - market
        text = f'over the past year: {stock:+.0f}% vs the S&P 500\'s {market:+.0f}%'
        why = 'Compared with the S&P 500, the index of 500 large US companies.'
        if gap >= MARKET_GAP_PTS:
            like(Point(f'Beating the market {text}', why))
        elif gap <= -MARKET_GAP_PTS:
            dislike(Point(f'Lagging the market {text}', why))
    if len(close) >= 220:
        sma = close.rolling(200).mean()
        rising = sma.iloc[-1] > sma.iloc[-21]
        why = 'The 200-day average price is the classic long-term trend line.'
        if close.iloc[-1] > sma.iloc[-1] and rising:
            like(Point(f'In a long-term uptrend: price above its rising 200-day average (${sma.iloc[-1]:,.2f})', why))
        elif close.iloc[-1] < sma.iloc[-1] and not rising:
            dislike(Point(f'In a long-term downtrend: price below its falling 200-day average (${sma.iloc[-1]:,.2f})',
                          why))
    recent = daily[daily.index > year_ago]
    if not recent.empty:
        high = recent['high'].max()
        drop = 1 - close.iloc[-1] / high
        if drop >= FAR_FROM_HIGH:
            dislike(Point(f'{drop * 100:.0f}% below its 52-week high of ${high:,.2f}',
                          'A big fall from the year\'s high: either a bargain or a sign of trouble; check why.'))


def _short(value: float) -> str:
    for limit, suffix in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M')):
        if value >= limit:
            return f'{value / limit:.1f}{suffix}'
    return f'{value:,.0f}'

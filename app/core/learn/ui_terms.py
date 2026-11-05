"""Which piece of the UI explains which topic. Data only: widgets look their topic up here, so no topic id is
scattered through widget code. A test checks every id exists in the library.

Text that the app generates (legends, summaries, rule descriptions) does not need to be listed: it is linked
automatically from the topics' titles and aliases (see learn.linker).
"""

# Explorer rows, by view key (see core.dashboard.layout.VIEWS). Views with no topic yet are simply not clickable.
EXPLORER_VIEWS = {
    'candles': 'candlestick', 'sma': 'sma', 'volume': 'volume', 'macd': 'macd', 'stoch_rsi': 'stoch-rsi',
    'atr': 'atr', 'rel_strength': 'relative-strength', 'growth': 'yoy-qoq',
}
EXPLORER_STRATEGIES_FOLDER = 'backtest'
EXPLORER_PORTFOLIO = 'portfolio'

# Table column titles (History, Growth and the strategy's trade table).
COLUMNS = {
    'Open': 'candlestick', 'High': 'candlestick', 'Low': 'candlestick', 'Close': 'candlestick', 'Volume': 'volume',
    'Revenue': 'revenue', 'EPS': 'eps', 'QoQ': 'yoy-qoq', 'YoY': 'yoy-qoq',
    'Exit reason': 'stop-loss',
}

# Plain labels, by their text.
LABELS = {
    'Range': 'range', 'Candle': 'candle-size',
    'Commission / trade': 'commission', 'Slippage': 'slippage',
}

# The topic shown when the Info Wizard is first switched on.
WELCOME = 'welcome-info'


def all_topic_ids() -> set[str]:
    """Every topic id this module refers to (for the test that checks they exist)."""
    return {*EXPLORER_VIEWS.values(), EXPLORER_STRATEGIES_FOLDER, EXPLORER_PORTFOLIO, *COLUMNS.values(),
            *LABELS.values(), WELCOME}

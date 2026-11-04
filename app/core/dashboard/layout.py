"""Which views exist, how they stack, and how a selection of them is laid out. No toolkit types here."""
from dataclasses import dataclass

# Views available under every symbol, in the order they stack. Add RSI, moving averages, etc. here later.
VIEWS = [('price', 'Price'), ('candles', 'Candles'), ('sma', 'SMA 50/150/200'), ('volume', 'Volume'),
         ('macd', 'MACD'), ('stoch_rsi', 'Stoch RSI'), ('atr', 'ATR'), ('rel_strength', 'Rel. Strength'),
         ('growth', 'Revenue/EPS Growth'), ('history', 'History')]
STRATEGIES_BEFORE = 'history'  # the Strategies folder sits just above this view
STRATEGY_PREFIX = 'strategy:'  # view key for a strategy: 'strategy:<id>'
STRATEGY_VIEW = 'strategy'  # the results panel shown when a strategy is selected

# Candle sizes. Only daily candles are downloaded; the rest are built from them.
TIMEFRAMES = ['1D', '1W', '2W', '1M', '3M']

# Stacking order of every panel, including the strategy results panel.
PANEL_ORDER = [key for key, _ in VIEWS[:-1]] + [STRATEGY_VIEW, VIEWS[-1][0]]
# Share of the height each view gets when stacked (price charts get more room than indicators).
HEIGHT_WEIGHTS = {'price': 3, 'candles': 3, 'sma': 3, 'volume': 2, 'macd': 2, 'stoch_rsi': 2, 'atr': 2,
                  'rel_strength': 2, 'growth': 3, 'strategy': 4, 'history': 3}
# Charts the moving averages are drawn on when SMA is selected together with them.
SMA_HOSTS = ('price', 'candles')
# Charts that get BUY/SELL arrows and entry lines; the others get signal lines.
PRICE_CHARTS = ('price', 'candles', 'sma')
# Views that are tables, not charts over time: they have no time axis to link.
TABLE_VIEWS = ('growth', 'history')


def strategy_key(strategy_id: str) -> str:
    return STRATEGY_PREFIX + strategy_id


def strategy_id_of(key: str) -> str:
    return key.removeprefix(STRATEGY_PREFIX)


def is_strategy_key(key: str) -> bool:
    return key.startswith(STRATEGY_PREFIX)


@dataclass(frozen=True)
class PanelLayout:
    shown: list[str]  # selected views that get their own panel, top to bottom
    sma_host: str | None  # the chart the moving averages are drawn on, if SMA rides on one
    dated: str | None  # the bottom chart: the only one that shows dates

    def height_of(self, key: str) -> int:
        if key in self.shown:
            return HEIGHT_WEIGHTS[key]
        return 0


def arrange(selected: list[str]) -> PanelLayout:
    """Show only the selected views. SMA selected together with Price or Candles is drawn on top of the first of
    those, not as its own panel."""
    sma_host = None
    if 'sma' in selected:
        sma_host = next((key for key in selected if key in SMA_HOSTS), None)
    shown = [key for key in selected if not (key == 'sma' and sma_host)]
    charts = [key for key in shown if key not in TABLE_VIEWS]
    dated = charts[-1] if charts else None
    return PanelLayout(shown, sma_host, dated)

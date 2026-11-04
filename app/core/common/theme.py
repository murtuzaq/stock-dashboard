"""Colour tokens shared by the presentation models and the renderer. Plain hex strings: no toolkit types."""

BACKGROUND = '#131722'
GRID_TEXT = '#d1d4dc'
MUTED = '#787b86'
UP = '#26a69a'
DOWN = '#ef5350'
WARNING = '#f7c948'

# Indicator line colours.
MACD_COLOR = '#2962ff'
SIGNAL_COLOR = '#ff6d00'
ATR_COLOR = '#e040fb'
K_COLOR = '#2962ff'
D_COLOR = '#ff6d00'
RS_COLOR = '#2962ff'
AVERAGE_COLOR = '#f7c948'
EQUITY_COLOR = '#2962ff'
HOLD_COLOR = '#787b86'
SMA_COLORS = ('#2962ff', '#f7c948', '#e040fb')

# MACD histogram, as on TradingView: strong when the bar grows, pale when it shrinks.
ABOVE_GROWING, ABOVE_SHRINKING = '#26a69a', '#b2dfdb'
BELOW_GROWING, BELOW_SHRINKING = '#ff5252', '#ffcdd2'


def change_color(value: float) -> str:
    """Green for a gain (or no change), red for a loss."""
    if value >= 0:
        return UP
    return DOWN

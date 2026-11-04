"""What each view shows, worked out from price data: series to draw, legend lines, table cells.

Every function here is pure (data in, plain data out), so it is testable without a display. The renderer
(qtrender/) only turns these models into widgets.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.common import theme
from core.common.formatting import Cell, Line, Span, plain, short_number
from indicators import atr, macd, relative_strength, sma, stoch_rsi
from prices import days_to_candles, range_change, to_candles

BENCHMARK = '^GSPC'  # Yahoo's symbol for the S&P 500 index
BENCHMARK_NAME = 'S&P 500'
SMA_DAYS = (50, 150, 200)
ATR_LENGTH = 14
VOLUME_AVERAGE_LENGTH = 20
OVERBOUGHT = 80
OVERSOLD = 20


# --- Price -------------------------------------------------------------------------------------------------------

@dataclass
class PriceModel:
    dates: pd.DatetimeIndex
    closes: np.ndarray
    daily: pd.DataFrame

    def color(self, start: pd.Timestamp) -> str:
        """Green or red by the change over the selected range."""
        _, percent = range_change(self.daily, start)
        return theme.change_color(percent)

    def cursor_text(self, slot: int) -> str:
        return f'{self.dates[slot]:%b %d, %Y}   {self.closes[slot]:,.2f}'


def price_model(daily: pd.DataFrame, candles: pd.DataFrame) -> PriceModel:
    return PriceModel(candles.index, candles['close'].to_numpy(), daily)


# --- SMA ---------------------------------------------------------------------------------------------------------

@dataclass
class SmaLine:
    label: str
    color: str
    values: np.ndarray


@dataclass
class SmaModel:
    dates: pd.DatetimeIndex
    closes: np.ndarray
    lines: list[SmaLine]


def sma_model(candles: pd.DataFrame) -> SmaModel:
    candle_size = candles.attrs.get('candle_size', '1D')
    lines = []
    for days, color in zip(SMA_DAYS, theme.SMA_COLORS):
        length = days_to_candles(days, candle_size)
        note = '' if candle_size == '1D' else f' ({length} × {candle_size} candles)'
        lines.append(SmaLine(f'SMA {days}d{note}', color, sma(candles['close'], length).to_numpy()))
    return SmaModel(candles.index, candles['close'].to_numpy(), lines)


# --- Volume ------------------------------------------------------------------------------------------------------

@dataclass
class VolumeModel:
    dates: pd.DatetimeIndex
    volume: np.ndarray
    bar_colors: list[str]
    average: np.ndarray
    legend: Line


def volume_model(candles: pd.DataFrame) -> VolumeModel:
    volume = candles['volume']
    average = volume.rolling(VOLUME_AVERAGE_LENGTH).mean()
    rising = (candles['close'] >= candles['open']).to_numpy()
    colors = [theme.UP if up else theme.DOWN for up in rising]
    return VolumeModel(candles.index, volume.to_numpy(dtype=float), colors, average.to_numpy(dtype=float),
                       _volume_legend(volume, average))


def _volume_legend(volume: pd.Series, average: pd.Series) -> Line:
    if volume.empty or pd.isna(average.iloc[-1]):
        return [plain('Volume')]
    ratio = volume.iloc[-1] / average.iloc[-1]
    return [plain(f'Volume {short_number(volume.iloc[-1])}   '),
            Span(f'avg({VOLUME_AVERAGE_LENGTH}) {short_number(average.iloc[-1])}', theme.AVERAGE_COLOR),
            plain('   '), Span(f'{ratio:.2f}× average', theme.MUTED)]


# --- MACD --------------------------------------------------------------------------------------------------------

@dataclass
class MacdModel:
    dates: pd.DatetimeIndex
    macd: np.ndarray
    signal: np.ndarray
    histogram: np.ndarray
    bar_colors: list[str]
    legend: Line


def histogram_colors(histogram: np.ndarray) -> list[str]:
    previous = np.concatenate([[np.nan], histogram[:-1]])
    colors = []
    for value, before in zip(histogram, previous):
        growing = np.isnan(before) or abs(value) >= abs(before)
        if value >= 0:
            colors.append(theme.ABOVE_GROWING if growing else theme.ABOVE_SHRINKING)
        else:
            colors.append(theme.BELOW_GROWING if growing else theme.BELOW_SHRINKING)
    return colors


def macd_model(candles: pd.DataFrame) -> MacdModel:
    values = macd(candles['close'])
    histogram = values['histogram'].to_numpy()
    line, signal, latest = values.iloc[-1]
    mood = 'MACD above signal: momentum rising' if latest >= 0 else 'MACD below signal: momentum falling'
    legend = [plain('MACD (12, 26, 9)   '), Span(f'MACD {line:.2f}', theme.MACD_COLOR), plain('   '),
              Span(f'Signal {signal:.2f}', theme.SIGNAL_COLOR), plain(f'   Histogram {latest:+.2f}   '),
              Span(mood, theme.MUTED)]
    return MacdModel(candles.index, values['macd'].to_numpy(), values['signal'].to_numpy(), histogram,
                     histogram_colors(histogram), legend)


# --- Stoch RSI ---------------------------------------------------------------------------------------------------

@dataclass
class StochRsiModel:
    dates: pd.DatetimeIndex
    k: np.ndarray
    d: np.ndarray
    legend: Line


def stoch_rsi_model(candles: pd.DataFrame) -> StochRsiModel:
    values = stoch_rsi(candles['close'])
    return StochRsiModel(candles.index, values['k'].to_numpy(), values['d'].to_numpy(), _stoch_rsi_legend(values))


def _stoch_rsi_legend(values: pd.DataFrame) -> Line:
    latest = values.dropna()
    if latest.empty:
        return [plain('Stoch RSI (14, 14, 3, 3) · not enough history yet')]
    k, d = latest.iloc[-1]
    zone = 'neutral'
    if k > OVERBOUGHT:
        zone = 'overbought'
    elif k < OVERSOLD:
        zone = 'oversold'
    return [plain('Stoch RSI (14, 14, 3, 3)   '), Span(f'K {k:.1f}', theme.K_COLOR), plain('   '),
            Span(f'D {d:.1f}', theme.D_COLOR), plain('   '), Span(zone, theme.MUTED)]


# --- ATR ---------------------------------------------------------------------------------------------------------

@dataclass
class AtrModel:
    dates: pd.DatetimeIndex
    values: np.ndarray
    legend: Line


def atr_model(candles: pd.DataFrame) -> AtrModel:
    values = atr(candles['high'], candles['low'], candles['close'], ATR_LENGTH)
    latest, close = values.iloc[-1], candles['close'].iloc[-1]
    if pd.isna(latest):
        legend = [plain(f'ATR ({ATR_LENGTH}) · not enough history yet')]
    else:
        legend = [Span(f'ATR ({ATR_LENGTH}) {latest:.2f}', theme.ATR_COLOR), plain('   '),
                  Span(f'{latest / close * 100:.1f}% of price per candle · '
                       f'2 × ATR stop = {2 * latest:.2f} below entry', theme.MUTED)]
    return AtrModel(candles.index, values.to_numpy(), legend)


# --- Relative strength -------------------------------------------------------------------------------------------

@dataclass
class RelStrengthModel:
    """The stock's price divided by the benchmark's. Which candle equals 100 depends on the selected range."""
    dates: pd.DatetimeIndex
    ratio: np.ndarray
    daily: pd.DataFrame
    benchmark: pd.DataFrame

    @property
    def available(self) -> bool:
        return not self.benchmark.empty

    def rebased(self, start: pd.Timestamp) -> np.ndarray:
        """Rebase so the first candle of the range is 100."""
        first_slot = min(int(self.dates.searchsorted(start)), len(self.ratio) - 1)
        finite = np.flatnonzero(np.isfinite(self.ratio[first_slot:]))
        base = self.ratio[first_slot + finite[0]] if len(finite) else np.nan
        return self.ratio / base * 100

    def legend(self, start: pd.Timestamp) -> Line:
        if not self.available:
            return [plain(f'Relative strength · {BENCHMARK_NAME} data unavailable')]
        _, stock = range_change(self.daily, start)
        _, market = range_change(self.benchmark, start)
        gap = stock - market
        if gap >= 0:
            verdict = f'beating the market by {gap:.1f} pts'
        else:
            verdict = f'lagging the market by {-gap:.1f} pts'
        since = max(start, self.daily.index[0])
        return [plain(f'Relative strength vs {BENCHMARK_NAME} since {since:%b %d, %Y}   '
                      f'stock {stock:+.2f}%   {BENCHMARK_NAME} {market:+.2f}%   '),
                Span(verdict, theme.change_color(gap))]


def rel_strength_model(daily: pd.DataFrame, candles: pd.DataFrame, benchmark: pd.DataFrame) -> RelStrengthModel:
    if benchmark.empty:
        ratio = pd.Series(np.nan, index=candles.index)
    else:
        benchmark_candles = to_candles(benchmark, candles.attrs.get('candle_size', '1D'))
        ratio = relative_strength(candles['close'], benchmark_candles['close'])
    return RelStrengthModel(candles.index, ratio.to_numpy(), daily, benchmark)


# --- History table -----------------------------------------------------------------------------------------------

HISTORY_COLUMNS = ['Date', 'Open', 'High', 'Low', 'Close', 'Change', 'Volume']
HISTORY_TOOLTIPS = {
    'Date': 'First trading day of the candle',
    'Open': 'Price of the first trade',
    'High': 'Highest price traded',
    'Low': 'Lowest price traded',
    'Close': 'Price of the last trade',
    'Change': 'Close compared with the previous close',
    'Volume': 'Number of shares traded',
}


def history_rows(candles: pd.DataFrame, first_slot: int) -> pd.DataFrame:
    """Candles from first_slot onwards, newest first; the change column still uses the candle before it."""
    rows = candles.assign(change=candles['close'].pct_change() * 100).iloc[first_slot:]
    return rows.iloc[::-1]


def history_cell(rows: pd.DataFrame, row_number: int, column: str) -> Cell:
    row = rows.iloc[row_number]
    if column == 'Date':
        return Cell(f'{rows.index[row_number]:%Y-%m-%d}')
    if column == 'Change':
        if pd.isna(row['change']):
            return Cell('', align_right=True)
        return Cell(f'{row["change"]:+.2f}%', theme.change_color(row['change']), align_right=True)
    if column == 'Volume':
        return Cell(f'{int(row["volume"]):,}', align_right=True)
    return Cell(f'{row[column.lower()]:,.2f}', align_right=True)


def history_summary(shown: pd.DataFrame) -> str:
    """One line describing the range: how many rows, which dates, highest and lowest price."""
    if shown.empty:
        return ''
    return (f'{len(shown):,} rows · {shown.index[0]:%b %d, %Y} to {shown.index[-1]:%b %d, %Y} · '
            f'high {shown["high"].max():,.2f} · low {shown["low"].min():,.2f}')


# --- Growth tables -----------------------------------------------------------------------------------------------

GROWTH_NOT_AVAILABLE = ('Needs the same period a year earlier (or the earlier figure was a loss).\n'
                        'Yahoo only provides about 5 quarters; stored history grows as new quarters are reported.')
GROWTH_COLUMNS = {
    'quarterly': [('Quarter end', None), ('Revenue', 'revenue'), ('QoQ', 'revenue_qoq'), ('YoY', 'revenue_yoy'),
                  ('EPS', 'eps'), ('QoQ', 'eps_qoq'), ('YoY', 'eps_yoy')],
    'annual': [('Year end', None), ('Revenue', 'revenue'), ('YoY', 'revenue_yoy'), ('EPS', 'eps'),
               ('YoY', 'eps_yoy')],
}
GROWTH_HEADER_TIPS = {
    'Revenue': 'Total sales', 'EPS': 'Diluted earnings per share: profit divided by shares',
    'QoQ': 'Growth vs the previous quarter (seasonal businesses swing a lot here)',
    'YoY': 'Growth vs the same period a year earlier: the number most traders watch',
}


def growth_cell(value: float, column: str) -> Cell:
    if pd.isna(value):
        return Cell('—', tooltip=GROWTH_NOT_AVAILABLE, align_right=True)
    if column.endswith(('_yoy', '_qoq')):
        return Cell(f'{value:+.1f}%', theme.change_color(value), align_right=True)
    if column == 'revenue':
        return Cell(f'${short_number(value)}', align_right=True)
    return Cell(f'{value:.2f}', align_right=True)


def growth_rows(period: str, figures: pd.DataFrame) -> list[list[Cell]]:
    """Table rows for one period, newest first."""
    columns = GROWTH_COLUMNS[period]
    rows = []
    for end_date, values in figures.iloc[::-1].iterrows():
        row = []
        for _, column in columns:
            if column is None:
                row.append(Cell(f'{end_date:%Y-%m-%d}'))
            else:
                row.append(growth_cell(values[column], column))
        rows.append(row)
    return rows


def growth_summary(symbol: str, quarterly: pd.DataFrame) -> str:
    if quarterly.empty:
        return f'No revenue or earnings figures available for {symbol} (ETFs and indexes have none).'
    latest = quarterly.iloc[-1]
    parts = [f'Latest quarter {quarterly.index[-1]:%b %Y}: revenue ${short_number(latest["revenue"])}']
    if not pd.isna(latest['revenue_yoy']):
        parts.append(f'{latest["revenue_yoy"]:+.1f}% YoY')
    parts.append(f'EPS {latest["eps"]:.2f}')
    if not pd.isna(latest['eps_yoy']):
        parts.append(f'{latest["eps_yoy"]:+.1f}% YoY')
    return ' · '.join(parts)

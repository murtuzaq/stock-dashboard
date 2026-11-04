"""The indicators a strategy can use, built on the dashboard's existing indicator functions.

Each entry says what it is called, which lines (outputs) it has, which settings (params) it takes,
and its scale, so the wizard can offer sensible comparisons (price lines against price lines,
0-100 oscillators against numbers).

Lengths given in days (SMA) are converted to candles for the chosen candle size, like the SMA view.
Other lengths are in candles, as on TradingView.
"""
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from indicators import atr, macd, relative_strength, rsi, sma, stoch_rsi
from prices import days_to_candles, to_candles

# Scales: values on the same scale can be compared with each other.
PRICE, OSCILLATOR, UNBOUNDED, VOLUME, RATIO = 'price', '0-100', 'unbounded', 'volume', 'ratio'


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    default: int
    minimum: int = 1
    maximum: int = 1000


@dataclass(frozen=True)
class Indicator:
    key: str
    label: str
    scale: str
    outputs: dict[str, str]  # output key -> full name of that line; the first is the main line
    compute: Callable[[pd.DataFrame, pd.DataFrame | None, dict], pd.DataFrame]
    params: tuple[Param, ...] = ()
    needs_benchmark: bool = False

    @property
    def main_output(self) -> str:
        return next(iter(self.outputs))

    def settings(self, overrides: dict) -> dict:
        """Defaults with any overrides applied."""
        return {p.name: int(overrides.get(p.name, p.default)) for p in self.params}


def _candle_size(candles: pd.DataFrame) -> str:
    return candles.attrs.get('candle_size', '1D')


def _single(series: pd.Series) -> pd.DataFrame:
    return series.to_frame('value')


def _price_column(column: str):
    return lambda candles, benchmark, p: _single(candles[column])


def _sma(candles, benchmark, p):
    return _single(sma(candles['close'], days_to_candles(p['days'], _candle_size(candles))))


def _macd(candles, benchmark, p):
    return macd(candles['close'], p['fast'], p['slow'], p['signal'])


def _stoch_rsi(candles, benchmark, p):
    return stoch_rsi(candles['close'], p['rsi_length'], p['stoch_length'], p['k_smoothing'], p['d_smoothing'])


def _rsi(candles, benchmark, p):
    return _single(rsi(candles['close'], p['length']))


def _atr(candles, benchmark, p):
    return _single(atr(candles['high'], candles['low'], candles['close'], p['length']))


def _volume_average(candles, benchmark, p):
    return _single(candles['volume'].rolling(p['length']).mean())


def _rel_strength(candles, benchmark, p):
    if benchmark is None or benchmark.empty:
        raise ValueError('Relative strength needs S&P 500 price data')
    ratio = relative_strength(candles['close'], to_candles(benchmark, _candle_size(candles))['close'])
    return pd.DataFrame({'value': ratio,
                         'average': sma(ratio, days_to_candles(p['days'], _candle_size(candles)))})


INDICATORS: dict[str, Indicator] = {i.key: i for i in [
    Indicator('close', 'Close', PRICE, {'value': 'Close'}, _price_column('close')),
    Indicator('open', 'Open', PRICE, {'value': 'Open'}, _price_column('open')),
    Indicator('high', 'High', PRICE, {'value': 'High'}, _price_column('high')),
    Indicator('low', 'Low', PRICE, {'value': 'Low'}, _price_column('low')),
    Indicator('sma', 'SMA', PRICE, {'value': 'SMA'}, _sma, (Param('days', 'Days', 50, 2, 400),)),
    Indicator('macd', 'MACD', UNBOUNDED, {'macd': 'MACD line', 'signal': 'MACD signal', 'histogram': 'MACD histogram'},
              _macd, (Param('fast', 'Fast', 12), Param('slow', 'Slow', 26), Param('signal', 'Signal', 9))),
    Indicator('stoch_rsi', 'Stoch RSI', OSCILLATOR, {'k': 'Stoch RSI K', 'd': 'Stoch RSI D'}, _stoch_rsi,
              (Param('rsi_length', 'RSI length', 14), Param('stoch_length', 'Stoch length', 14),
               Param('k_smoothing', 'K smoothing', 3), Param('d_smoothing', 'D smoothing', 3))),
    Indicator('rsi', 'RSI', OSCILLATOR, {'value': 'RSI'}, _rsi, (Param('length', 'Length', 14),)),
    Indicator('atr', 'ATR', UNBOUNDED, {'value': 'ATR'}, _atr, (Param('length', 'Length', 14),)),
    Indicator('volume', 'Volume', VOLUME, {'value': 'Volume'}, _price_column('volume')),
    Indicator('volume_average', 'Volume average', VOLUME, {'value': 'Volume average'}, _volume_average,
              (Param('length', 'Candles', 20),)),
    Indicator('rel_strength', 'Rel. Strength', RATIO, {'value': 'Rel. Strength', 'average': 'Rel. Strength SMA'},
              _rel_strength, (Param('days', 'SMA days', 50, 2, 400),), needs_benchmark=True),
]}


def get(key: str) -> Indicator:
    try:
        return INDICATORS[key]
    except KeyError:
        raise ValueError(f'Unknown indicator {key!r}; available: {", ".join(INDICATORS)}') from None

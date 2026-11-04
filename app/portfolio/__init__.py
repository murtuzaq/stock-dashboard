"""Saved portfolios: named sets of stocks, one JSON file each. No GUI code lives here."""
from .model import Portfolio, normalize_symbol

__all__ = ['Portfolio', 'normalize_symbol']

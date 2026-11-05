"""Saved portfolios: one readable JSON file each, in the repo's portfolios/ folder (commit them like code).

    portfolios/<name>.json
"""
import json
import logging
import re
from pathlib import Path

from datadir import DATA_ROOT

from strategy.model import now

from .model import Portfolio

ROOT = DATA_ROOT / 'portfolios'
log = logging.getLogger(__name__)


def _slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'portfolio'


def _files() -> list[Path]:
    return sorted(ROOT.glob('*.json')) if ROOT.exists() else []


def _load(path: Path) -> Portfolio | None:
    try:
        return Portfolio.from_dict(json.loads(path.read_text(encoding='utf-8')))
    except (ValueError, KeyError, TypeError) as error:
        log.warning('Skipping unreadable portfolio file %s: %s', path.name, error)
        return None


def _path_of(portfolio_id: str) -> Path | None:
    for path in _files():
        loaded = _load(path)
        if loaded and loaded.id == portfolio_id:
            return path
    return None


def all_portfolios() -> list[Portfolio]:
    portfolios = [p for p in (_load(path) for path in _files()) if p]
    return sorted(portfolios, key=lambda p: p.name.lower())


def get(portfolio_id: str) -> Portfolio | None:
    path = _path_of(portfolio_id)
    return _load(path) if path else None


def save(portfolio: Portfolio) -> Path:
    """Write (or rewrite) the portfolio's file; renaming it removes the old file."""
    portfolio.updated = now()
    ROOT.mkdir(parents=True, exist_ok=True)
    old = _path_of(portfolio.id)
    path = ROOT / f'{_slug(portfolio.name)}.json'
    if path.exists() and path != old:
        path = ROOT / f'{_slug(portfolio.name)}-{portfolio.id[:6]}.json'  # another portfolio has this name
    path.write_text(json.dumps(portfolio.to_dict(), indent=2) + '\n', encoding='utf-8')
    if old and old != path:
        old.unlink()
    return path


def delete(portfolio_id: str) -> None:
    path = _path_of(portfolio_id)
    if path:
        path.unlink()

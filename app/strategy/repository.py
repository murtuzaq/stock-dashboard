"""Saved strategies: one readable JSON file each, in the repo's strategies/ folder (commit them like code).

    strategies/library/<name>.json   reusable templates (symbol = None)
    strategies/<SYMBOL>/<name>.json  strategies that belong to one stock
"""
import json
import re
from pathlib import Path

from datadir import DATA_ROOT

from .model import Strategy, now

ROOT = DATA_ROOT / 'strategies'
LIBRARY = 'library'


def _slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'strategy'


def _files() -> list[Path]:
    return sorted(ROOT.glob('*/*.json')) if ROOT.exists() else []


def _load(path: Path) -> Strategy | None:
    try:
        return Strategy.from_dict(json.loads(path.read_text(encoding='utf-8')))
    except (ValueError, KeyError, TypeError) as error:
        print(f'Skipping unreadable strategy file {path.name}: {error}')
        return None


def _path_of(strategy_id: str) -> Path | None:
    for path in _files():
        loaded = _load(path)
        if loaded and loaded.id == strategy_id:
            return path
    return None


def all_strategies() -> list[Strategy]:
    return [s for s in (_load(path) for path in _files()) if s]


def for_symbol(symbol: str) -> list[Strategy]:
    return sorted((s for s in all_strategies() if s.symbol == symbol), key=lambda s: s.name.lower())


def library() -> list[Strategy]:
    return sorted((s for s in all_strategies() if s.symbol is None), key=lambda s: s.name.lower())


def get(strategy_id: str) -> Strategy | None:
    path = _path_of(strategy_id)
    return _load(path) if path else None


def save(strategy: Strategy) -> Path:
    """Write (or rewrite) the strategy's file; renaming or moving it removes the old file."""
    strategy.updated = now()
    folder = ROOT / (strategy.symbol or LIBRARY)
    folder.mkdir(parents=True, exist_ok=True)
    old = _path_of(strategy.id)
    path = folder / f'{_slug(strategy.name)}.json'
    if path.exists() and path != old:
        path = folder / f'{_slug(strategy.name)}-{strategy.id[:6]}.json'  # another strategy has this name
    path.write_text(json.dumps(strategy.to_dict(), indent=2) + '\n', encoding='utf-8')
    if old and old != path:
        old.unlink()
    return path


def delete(strategy_id: str) -> None:
    path = _path_of(strategy_id)
    if path:
        path.unlink()
        if path.parent.name != LIBRARY and not any(path.parent.iterdir()):
            path.parent.rmdir()


def copy(strategy_id: str, symbol: str | None, name: str | None = None) -> Strategy:
    """Save an independent copy for another stock (or the library, with symbol None)."""
    original = get(strategy_id)
    if original is None:
        raise ValueError(f'No strategy with id {strategy_id!r}')
    twin = original.copy_for(symbol, name)
    save(twin)
    return twin

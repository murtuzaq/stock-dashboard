"""Terms the user asked to have explained, kept in info_requests.json at the repo root to send to the developer.

    {"version": 1, "requests": [{"text": "Sharpe ratio", "normalized": "sharpe ratio", "count": 3,
                                 "first_requested": "...", "last_requested": "...",
                                 "contexts": [{"view": "strategy", "symbol": "IBM", "where": "summary card"}],
                                 "note": ""}]}

Asking again for the same term (ignoring case and spacing) only raises its count.
"""
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from strategy.model import now

from .library import TopicLibrary
from .model import normalize

FILE = Path(__file__).resolve().parents[2] / 'info_requests.json'
VERSION = 1
log = logging.getLogger(__name__)


@dataclass
class Request:
    text: str
    normalized: str
    count: int = 1
    first_requested: str = field(default_factory=now)
    last_requested: str = field(default_factory=now)
    contexts: list[dict] = field(default_factory=list)
    note: str = ''


def _read() -> list[Request]:
    if not FILE.exists():
        return []
    try:
        data = json.loads(FILE.read_text(encoding='utf-8'))
        return [Request(**item) for item in data['requests']]
    except (ValueError, KeyError, TypeError, OSError) as error:
        backup = FILE.with_suffix('.json.bak')
        log.warning('Unreadable %s (%s): keeping it as %s and starting a new list', FILE.name, error, backup.name)
        try:
            os.replace(FILE, backup)  # never overwrite what the user may still want to send
        except OSError:
            pass
        return []


def _write(requests: list[Request]) -> None:
    payload = {'version': VERSION, 'requests': [asdict(request) for request in requests]}
    temporary = FILE.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temporary, FILE)  # a crash mid-write cannot leave a half-written file


def all_requests() -> list[Request]:
    return _read()


def add(text: str, context: dict | None = None, note: str = '') -> Request:
    """Record a request; returns it (with its updated count if it was asked for before)."""
    text, note = ' '.join(text.split()), note.strip()
    if not text:
        raise ValueError('Say which term you would like explained.')
    key = normalize(text)
    requests = _read()
    request = next((r for r in requests if r.normalized == key), None)
    if request is None:
        request = Request(text=text, normalized=key)
        requests.append(request)
    else:
        request.count += 1
        request.last_requested = now()
    if context and context not in request.contexts:
        request.contexts.append(context)
    if note and note not in request.note:
        request.note = f'{request.note} | {note}' if request.note else note
    _write(requests)
    return request


def pending(library: TopicLibrary) -> list[Request]:
    """Requests the library still cannot answer (most asked for first)."""
    return sorted((r for r in _read() if library.find(r.text) is None), key=lambda r: -r.count)


def answered(library: TopicLibrary) -> list[Request]:
    """Requests that now match a topic, so the developer can tell they are done."""
    return [r for r in _read() if library.find(r.text) is not None]

"""Finding known terms in a piece of text, so generated text (legends, rule descriptions) can be made clickable."""
import re
from functools import lru_cache
from typing import NamedTuple

from .library import TopicLibrary
from .model import normalize


class Match(NamedTuple):
    start: int
    end: int  # exclusive
    topic_id: str


@lru_cache(maxsize=8)
def _compile(terms: tuple[tuple[str, str], ...]) -> tuple[re.Pattern, dict[str, str]] | None:
    if not terms:
        return None
    names = sorted((key for key, _ in terms), key=len, reverse=True)  # longest first: 'stoch rsi' beats 'rsi'
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(name).replace(r'\ ', r'\s+') for name in names) +
                         r')(?!\w)', re.IGNORECASE)
    return pattern, dict(terms)


def find_terms(text: str, library: TopicLibrary, first_only: bool = True) -> list[Match]:
    """The known terms in `text`, left to right, never overlapping. With `first_only` each topic is linked once."""
    compiled = _compile(tuple(sorted(library.autolink_terms().items())))
    if compiled is None:
        return []
    pattern, ids = compiled
    matches, seen = [], set()
    for found in pattern.finditer(text):
        topic_id = ids[normalize(found.group())]
        if first_only and topic_id in seen:
            continue
        seen.add(topic_id)
        matches.append(Match(found.start(), found.end(), topic_id))
    return matches

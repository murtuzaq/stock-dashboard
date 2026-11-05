"""Loading the topic files and checking the library for mistakes.

A topic file is TOML between '+++' lines, then Markdown:

    +++
    id = "macd"
    title = "MACD"
    category = "Indicators"
    aliases = ["moving average convergence divergence"]
    related = ["signal-line"]
    summary = "One or two sentences."
    autolink = true
    +++
    The body, in Markdown. Link other topics with [text](topic:other-id); images sit in assets/.

A bad file never stops the app: it is skipped and reported in `TopicLibrary.issues`.
"""
import re
import tomllib
from pathlib import Path
from typing import NamedTuple

from .model import ID_PATTERN, Topic, normalize

ROOT = Path(__file__).resolve().parent / 'topics'
ASSETS = Path(__file__).resolve().parent / 'assets'

_TOPIC_LINK = re.compile(r'\]\(topic:([^)\s]+)\)')
_IMAGE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)\)')


class Issue(NamedTuple):
    path: str  # the file, relative to the topics folder where possible
    message: str


class TopicError(ValueError):
    """A topic file that cannot be used; the message says what is wrong."""


def parse_topic(text: str, path: Path | None = None, default_category: str = '') -> Topic:
    lines = text.lstrip('﻿').splitlines()
    if not lines or lines[0].strip() != '+++':
        raise TopicError("the file must start with a '+++' line (the TOML header)")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == '+++')
    except StopIteration:
        raise TopicError("the TOML header is not closed with a second '+++' line") from None
    try:
        header = tomllib.loads('\n'.join(lines[1:end]))
    except tomllib.TOMLDecodeError as error:
        raise TopicError(f'the TOML header is invalid: {error}') from None
    body = '\n'.join(lines[end + 1:]).strip()

    topic_id, title = header.get('id'), header.get('title')
    if not isinstance(topic_id, str) or not ID_PATTERN.match(topic_id):
        raise TopicError("'id' is required: lowercase letters, digits and '-' (e.g. \"stop-loss\")")
    if not isinstance(title, str) or not title.strip():
        raise TopicError("'title' is required")
    lists = {}
    for key in ('aliases', 'related'):
        value = header.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            raise TopicError(f"'{key}' must be a list of text, e.g. [\"a\", \"b\"]")
        lists[key] = tuple(item.strip() for item in value)
    autolink = header.get('autolink', True)
    if not isinstance(autolink, bool):
        raise TopicError("'autolink' must be true or false")
    return Topic(id=topic_id, title=title.strip(), category=str(header.get('category') or default_category),
                 summary=str(header.get('summary', '')).strip(), body=body, aliases=lists['aliases'],
                 related=lists['related'], autolink=autolink, path=path)


class TopicLibrary:
    """All topics, indexed by id and by every name they answer to."""

    def __init__(self, topics: list[Topic], issues: list[Issue] | None = None) -> None:
        self.topics: dict[str, Topic] = {}
        self.issues: list[Issue] = list(issues or [])
        self._by_term: dict[str, str] = {}  # normalized title/alias -> topic id
        for topic in topics:
            self._add(topic)
        self._pattern: re.Pattern | None = None
        self._pattern_ids: dict[str, str] = {}

    def _add(self, topic: Topic) -> None:
        name = str(topic.path.name) if topic.path else topic.id
        if topic.id in self.topics:
            self.issues.append(Issue(name, f"duplicate id '{topic.id}' (also in {self.topics[topic.id].path})"))
            return
        self.topics[topic.id] = topic
        for term in topic.terms:
            key = normalize(term)
            owner = self._by_term.get(key)
            if owner is not None and owner != topic.id:
                self.issues.append(Issue(name, f"'{term}' is already a name of '{owner}'"))
            else:
                self._by_term[key] = topic.id

    # --- lookup ---

    def get(self, topic_id: str) -> Topic | None:
        return self.topics.get(topic_id)

    def find(self, text: str) -> Topic | None:
        """The topic a piece of text names (its id, title or an alias), ignoring case and spacing."""
        key = normalize(text)
        topic_id = self._by_term.get(key) or (key if key in self.topics else None)
        return self.topics.get(topic_id) if topic_id else None

    def by_category(self) -> dict[str, list[Topic]]:
        groups: dict[str, list[Topic]] = {}
        for topic in sorted(self.topics.values(), key=lambda t: (t.category.casefold(), t.title.casefold())):
            groups.setdefault(topic.category or 'Other', []).append(topic)
        return groups

    def autolink_terms(self) -> dict[str, str]:
        """normalized name -> topic id, for the topics that may be linked automatically."""
        return {normalize(term): topic.id for topic in self.topics.values() if topic.autolink
                for term in topic.terms if self._by_term.get(normalize(term)) == topic.id}

    # --- checking ---

    def check_references(self, assets: Path = ASSETS) -> list[Issue]:
        """Problems between topics: links to missing topics, missing images, empty bodies."""
        problems = []
        for topic in self.topics.values():
            name = str(topic.path.name) if topic.path else topic.id
            if not topic.body:
                problems.append(Issue(name, 'the body is empty'))
            for other in topic.related:
                if other not in self.topics:
                    problems.append(Issue(name, f"related topic '{other}' does not exist"))
            for other in _TOPIC_LINK.findall(topic.body):
                if other not in self.topics:
                    problems.append(Issue(name, f"link to missing topic '{other}'"))
            for image in _IMAGE.findall(topic.body):
                if image.startswith(('http://', 'https://')):
                    continue
                here = topic.path.parent / image if topic.path else None
                if not (assets / image).exists() and not (here and here.exists()):
                    problems.append(Issue(name, f"image '{image}' not found in the assets folder"))
        return problems


def load_library(root: Path = ROOT, assets: Path = ASSETS) -> TopicLibrary:
    """Read every .md file under `root`. Problems are collected in `.issues`, never raised."""
    topics, issues = [], []
    for path in sorted(root.rglob('*.md')) if root.exists() else []:
        relative = str(path.relative_to(root))
        try:
            category = path.parent.name.replace('-', ' ').title() if path.parent != root else ''
            topics.append(parse_topic(path.read_text(encoding='utf-8'), path, category))
        except (TopicError, OSError, UnicodeDecodeError) as error:
            issues.append(Issue(relative, str(error)))
    library = TopicLibrary(topics, issues)
    library.issues.extend(library.check_references(assets))
    return library

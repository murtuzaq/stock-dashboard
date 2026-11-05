"""A topic: one explained term or concept."""
import re
from dataclasses import dataclass
from pathlib import Path

ID_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]*$')


def normalize(text: str) -> str:
    """How terms are compared: case-insensitive, with runs of spaces collapsed ('  Stop-Loss ' == 'stop-loss')."""
    return re.sub(r'\s+', ' ', text.strip()).casefold()


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    category: str
    summary: str  # one or two sentences: also good for a tooltip
    body: str  # Markdown
    aliases: tuple[str, ...] = ()  # other names the term goes by; also what auto-linking looks for
    related: tuple[str, ...] = ()  # ids of topics to offer next
    autolink: bool = True  # False for ambiguous words, so they are only linked where a widget says so
    path: Path | None = None  # the file it came from

    @property
    def terms(self) -> tuple[str, ...]:
        """Every name this topic answers to: its title, then its aliases."""
        return (self.title, *self.aliases)

"""Text formatting shared by the presentation models. No toolkit types here."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """A run of text, optionally coloured or bold. A list of spans is one line of rich text (a legend, a card).

    A '\\n' inside the text is a line break. `term` is the id of the topic that explains this text (see
    core.learn); the renderer makes it clickable while the Info Wizard is on.
    """
    text: str
    color: str | None = None
    bold: bool = False
    term: str | None = None


Line = list[Span]


@dataclass(frozen=True)
class Cell:
    """One table cell as plain data."""
    text: str
    color: str | None = None
    tooltip: str | None = None
    align_right: bool = False


def plain(text: str) -> Span:
    return Span(text)


def short_number(value: float) -> str:
    """5_583_900 -> '5.58M'."""
    for limit, suffix in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if abs(value) >= limit:
            return f'{value / limit:.3g}{suffix}'
    return f'{value:.0f}'


def money(value: float) -> str:
    if value < 0:
        return f'-${-value:,.2f}'
    return f'${value:,.2f}'

"""Turns core's Span lines into the HTML a QLabel understands."""
from html import escape

from core.common.formatting import Line

LINK_COLOR = '#5b8def'
LINK_PREFIX = 'info:'  # a link's href is 'info:<topic id>'


def line_html(line: Line, links: bool = False) -> str:
    """HTML for a line. With `links`, text that has a `term` becomes an underlined link to that topic."""
    parts = []
    for span in line:
        text = escape(span.text).replace('\n', '<br>')
        if span.bold:
            text = f'<b>{text}</b>'
        if links and span.term:
            text = f'<a href="{LINK_PREFIX}{span.term}" style="color:{LINK_COLOR}">{text}</a>'
        elif span.color:
            text = f'<span style="color:{span.color}">{text}</span>'
        parts.append(text)
    return ''.join(parts)


def plain_text(line: Line) -> str:
    return ''.join(span.text for span in line)

"""Turns core's Span lines into the HTML a QLabel understands."""
from html import escape

from core.formatting import Line


def line_html(line: Line) -> str:
    parts = []
    for span in line:
        text = escape(span.text).replace('\n', '<br>')
        if span.bold:
            text = f'<b>{text}</b>'
        if span.color:
            text = f'<span style="color:{span.color}">{text}</span>'
        parts.append(text)
    return ''.join(parts)

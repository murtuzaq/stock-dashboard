"""Making generated text clickable: tag the known terms in a line of spans with the topic that explains them."""
from dataclasses import replace

from core.common.formatting import Line
from learn import TopicLibrary
from learn.linker import find_terms


def link_line(line: Line, library: TopicLibrary) -> Line:
    """The same line with known terms split out into their own spans carrying a `term`.

    Each topic is linked once per line (its first occurrence), so a legend is not covered in underlines. Spans that
    already have a `term` are left as they are.
    """
    seen = {span.term for span in line if span.term}
    linked: Line = []
    for span in line:
        if span.term or not span.text:
            linked.append(span)
            continue
        position = 0
        for match in find_terms(span.text, library, first_only=False):
            if match.topic_id in seen:
                continue
            seen.add(match.topic_id)
            if match.start > position:
                linked.append(replace(span, text=span.text[position:match.start]))
            linked.append(replace(span, text=span.text[match.start:match.end], term=match.topic_id))
            position = match.end
        if position < len(span.text):
            linked.append(replace(span, text=span.text[position:]))
    return linked

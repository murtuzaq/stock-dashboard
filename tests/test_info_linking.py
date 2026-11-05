"""Tagging generated text with topics (core), and turning tagged spans into links (renderer's HTML helper)."""
from core.common.formatting import Span, plain
from core.learn.linking import link_line
from learn import load_library
from qtrender.richtext import LINK_COLOR, line_html, plain_text

LIBRARY = load_library()


def texts(line):
    return [(span.text, span.term) for span in line]


def test_known_terms_are_split_out_into_their_own_spans_keeping_the_surroundings():
    line = link_line([plain('MACD (12, 26, 9)   '), Span('MACD 1.20', '#2962ff'), plain('   Histogram +0.30')], LIBRARY)
    assert texts(line) == [('MACD', 'macd'), (' (12, 26, 9)   ', None), ('MACD 1.20', None), ('   ', None),
                           ('Histogram', 'histogram'), (' +0.30', None)]
    assert line[3].color is None and line[2].color == '#2962ff'  # styling of the original spans is kept


def test_each_topic_is_linked_once_per_line_even_across_spans():
    line = link_line([plain('SMA 50'), plain('  and SMA 200 vs MACD'), plain(' MACD')], LIBRARY)
    linked = [(span.text, span.term) for span in line if span.term]
    assert linked == [('SMA', 'sma'), ('MACD', 'macd')]


def test_spans_that_already_have_a_term_are_left_alone_and_count_as_linked():
    line = link_line([Span('Range', term='range'), plain(' and the range of prices and SMA')], LIBRARY)
    assert [(s.text, s.term) for s in line if s.term] == [('Range', 'range'), ('SMA', 'sma')]


def test_colour_and_bold_carry_over_to_the_pieces():
    [first, rest] = link_line([Span('SMA works', '#ff0000', bold=True)], LIBRARY)
    assert (first.text, first.term, first.color, first.bold) == ('SMA', 'sma', '#ff0000', True)
    assert (rest.text, rest.term, rest.color, rest.bold) == (' works', None, '#ff0000', True)


def test_lines_with_nothing_to_link_come_back_unchanged():
    line = [plain('Hello'), Span('', term=None), plain('there')]
    assert link_line(line, LIBRARY) == line and link_line([], LIBRARY) == []


def test_the_strategy_summary_words_link_to_their_topics():
    line = [plain('Max drawdown -8.0% (hold -12.0%) · In market 60% · Buy & hold +4.0% · win rate 55%')]
    ids = {span.term for span in link_line(line, LIBRARY) if span.term}
    assert {'max-drawdown', 'buy-and-hold', 'win-rate'} <= ids


def test_the_rule_description_links_the_indicator_and_crossover_words():
    line = [plain('BUY when Close is above SMA 200d AND MACD line crosses above MACD signal')]
    ids = {span.term for span in link_line(line, LIBRARY) if span.term}
    assert {'sma', 'macd', 'crossovers'} <= ids


# --- HTML ------------------------------------------------------------------------------------------------------

def test_links_are_only_emitted_when_asked_for():
    line = [plain('Use '), Span('SMA', term='sma'), plain(' <50>')]
    assert line_html(line) == 'Use SMA &lt;50&gt;'
    html = line_html(line, links=True)
    assert f'<a href="info:sma" style="color:{LINK_COLOR}">SMA</a>' in html and html.endswith('&lt;50&gt;')


def test_bold_and_colour_still_work_and_a_link_wins_over_a_colour():
    assert line_html([Span('x', '#ff0000', bold=True)]) == '<span style="color:#ff0000"><b>x</b></span>'
    html = line_html([Span('SMA', '#ff0000', term='sma')], links=True)
    assert 'info:sma' in html and '#ff0000' not in html


def test_plain_text_and_line_breaks():
    line = [Span('a\nb', bold=True), plain('c')]
    assert plain_text(line) == 'a\nbc' and '<br>' in line_html(line)

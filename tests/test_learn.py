"""The teaching library: topic files, validation, term linking and the request file. No GUI."""
import json
import re
from pathlib import Path

import pytest

from learn import load_library, normalize
from learn import requests as info_requests
from learn.library import TopicError, TopicLibrary, parse_topic
from learn.linker import find_terms


def write_topic(root: Path, name: str, header: str, body: str = 'Some text.', folder: str = 'indicators') -> Path:
    path = root / folder / f'{name}.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'+++\n{header}\n+++\n{body}\n', encoding='utf-8')
    return path


def library_of(tmp_path, *topics: tuple[str, str, str]) -> TopicLibrary:
    """Build a library from (name, header, body) triples."""
    for name, header, body in topics:
        write_topic(tmp_path / 'topics', name, header, body)
    return load_library(tmp_path / 'topics', tmp_path / 'assets')


# --- parsing ---------------------------------------------------------------------------------------------------

def test_a_full_topic_file_is_parsed():
    topic = parse_topic('+++\nid = "macd"\ntitle = "MACD"\ncategory = "Indicators"\naliases = ["MACD line"]\n'
                        'related = ["sma"]\nsummary = " One. "\nautolink = false\n+++\n\nBody *here*.\n')
    assert (topic.id, topic.title, topic.category, topic.summary) == ('macd', 'MACD', 'Indicators', 'One.')
    assert topic.aliases == ('MACD line',) and topic.related == ('sma',) and topic.autolink is False
    assert topic.body == 'Body *here*.' and topic.terms == ('MACD', 'MACD line')


def test_defaults_when_optional_fields_are_missing():
    topic = parse_topic('+++\nid = "x"\ntitle = "X"\n+++\nBody', default_category='Charts')
    assert topic.category == 'Charts' and topic.aliases == () and topic.related == () and topic.autolink is True


@pytest.mark.parametrize('text, message', [
    ('no header\n', "must start with a '+++'"),
    ('+++\nid = "x"\ntitle = "X"\n', 'not closed'),
    ('+++\nid = "x"\ntitle = \n+++\nb', 'TOML header is invalid'),
    ('+++\ntitle = "X"\n+++\nb', "'id' is required"),
    ('+++\nid = "Bad Id"\ntitle = "X"\n+++\nb', "'id' is required"),
    ('+++\nid = "x"\n+++\nb', "'title' is required"),
    ('+++\nid = "x"\ntitle = "X"\naliases = "a"\n+++\nb', "'aliases' must be a list"),
    ('+++\nid = "x"\ntitle = "X"\nrelated = [1]\n+++\nb', "'related' must be a list"),
    ('+++\nid = "x"\ntitle = "X"\nautolink = "yes"\n+++\nb', "'autolink' must be true or false"),
])
def test_bad_topic_files_are_rejected_with_a_helpful_message(text, message):
    with pytest.raises(TopicError, match=re.escape(message)):
        parse_topic(text)


# --- library ---------------------------------------------------------------------------------------------------

def test_loading_finds_topics_in_subfolders_and_uses_the_folder_as_the_default_category(tmp_path):
    library = library_of(tmp_path, ('a', 'id = "a"\ntitle = "Alpha"', 'x'))
    assert library.get('a').category == 'Indicators' and library.issues == []


def test_find_matches_id_title_and_aliases_ignoring_case_and_spacing(tmp_path):
    library = library_of(tmp_path, ('s', 'id = "stop-loss"\ntitle = "Stop-loss"\naliases = ["stop loss"]', 'x'))
    for text in ('stop-loss', 'STOP-LOSS', '  Stop   Loss ', 'stop loss'):
        assert library.find(text).id == 'stop-loss'
    assert library.find('take profit') is None and library.find('') is None


def test_a_bad_file_is_skipped_and_reported_without_stopping_the_rest(tmp_path):
    (tmp_path / 'topics').mkdir()
    (tmp_path / 'topics' / 'broken.md').write_text('nothing useful', encoding='utf-8')
    library = library_of(tmp_path, ('ok', 'id = "ok"\ntitle = "Ok"', 'x'))
    assert list(library.topics) == ['ok']
    assert [(i.path, 'must start' in i.message) for i in library.issues] == [('broken.md', True)]


def test_duplicate_ids_and_names_are_reported(tmp_path):
    library = library_of(tmp_path,
                         ('a', 'id = "a"\ntitle = "Alpha"\naliases = ["shared"]', 'x'),
                         ('b', 'id = "b"\ntitle = "Beta"\naliases = ["SHARED"]', 'x'),
                         ('c', 'id = "a"\ntitle = "Gamma"', 'x'))
    messages = [issue.message for issue in library.issues]
    assert any("'SHARED' is already a name of 'a'" in m for m in messages)
    assert any("duplicate id 'a'" in m for m in messages)
    assert library.find('shared').id == 'a' and library.get('b') is not None  # first wins, nothing is lost


def test_cross_references_are_checked(tmp_path):
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'here.png').write_bytes(b'png')
    library = library_of(tmp_path,
                         ('a', 'id = "a"\ntitle = "A"\nrelated = ["nope"]',
                          'See [b](topic:b) and [x](topic:ghost). ![ok](here.png) ![bad](gone.png) '
                          '![web](https://example.com/p.png)'),
                         ('b', 'id = "b"\ntitle = "B"', ''))
    messages = sorted(issue.message for issue in library.issues)
    assert messages == ["image 'gone.png' not found in the assets folder", "link to missing topic 'ghost'",
                        "related topic 'nope' does not exist", 'the body is empty']


def test_by_category_is_sorted_and_missing_folders_give_an_empty_library(tmp_path):
    library = library_of(tmp_path, ('z', 'id = "z"\ntitle = "Zed"\ncategory = "B"', 'x'),
                         ('a', 'id = "a"\ntitle = "Alpha"\ncategory = "B"', 'x'),
                         ('q', 'id = "q"\ntitle = "Q"\ncategory = "A"', 'x'))
    assert {c: [t.id for t in topics] for c, topics in library.by_category().items()} == {'A': ['q'], 'B': ['a', 'z']}
    assert load_library(tmp_path / 'missing').topics == {}


# --- the real library ------------------------------------------------------------------------------------------

def test_the_shipped_library_has_no_problems():
    library = load_library()
    assert library.issues == [], '\n'.join(f'{i.path}: {i.message}' for i in library.issues)
    assert len(library.topics) >= 25


def test_every_shipped_topic_has_a_summary_and_some_body_text():
    for topic in load_library().topics.values():
        assert topic.summary and len(topic.body) > 80, topic.id
        assert topic.category, topic.id


def test_the_candle_anatomy_image_exists_and_is_used():
    library = load_library()
    assert '![Anatomy of a candle](candle-anatomy.png)' in library.get('candlestick').body


# --- linker ----------------------------------------------------------------------------------------------------

def linked(text, library, **kwargs):
    return [(text[m.start:m.end], m.topic_id) for m in find_terms(text, library, **kwargs)]


def test_known_terms_are_found_with_word_boundaries_and_any_case(tmp_path):
    library = library_of(tmp_path, ('m', 'id = "macd"\ntitle = "MACD"\naliases = ["MACD line"]', 'x'),
                         ('s', 'id = "sma"\ntitle = "SMA"', 'x'))
    assert linked('Close is above SMA 200d and macd rises', library) == [('SMA', 'sma'), ('macd', 'macd')]
    assert linked('MACDX and ASMA are not terms', library) == []
    assert linked('(SMA)', library) == [('SMA', 'sma')]


def test_the_longest_name_wins_and_spaces_may_vary(tmp_path):
    library = library_of(tmp_path, ('r', 'id = "rsi"\ntitle = "RSI"', 'x'),
                         ('s', 'id = "stoch-rsi"\ntitle = "Stoch RSI"', 'x'))
    assert linked('Stoch   RSI K 12.0, RSI 40', library, first_only=False) == [('Stoch   RSI', 'stoch-rsi'),
                                                                               ('RSI', 'rsi')]


def test_each_topic_is_linked_once_unless_asked_otherwise(tmp_path):
    library = library_of(tmp_path, ('m', 'id = "macd"\ntitle = "MACD"', 'x'))
    assert len(linked('MACD above MACD', library)) == 1
    assert len(linked('MACD above MACD', library, first_only=False)) == 2


def test_topics_with_autolink_off_are_never_found(tmp_path):
    library = library_of(tmp_path, ('r', 'id = "range"\ntitle = "Range"\nautolink = false', 'x'))
    assert linked('the range of prices', library) == [] and library.find('range').id == 'range'


def test_names_with_symbols_and_an_empty_library(tmp_path):
    library = library_of(tmp_path, ('s', 'id = "sp-500"\ntitle = "S&P 500"', 'x'))
    assert linked('vs S&P 500 today', library) == [('S&P 500', 'sp-500')]
    assert find_terms('anything', TopicLibrary([])) == []


def test_the_shipped_library_links_the_words_the_app_shows():
    library = load_library()
    legend = 'MACD (12, 26, 9)   MACD 1.20   Signal 0.90   Histogram +0.30   MACD above signal: momentum rising'
    ids = {topic_id for _, topic_id in linked(legend, library)}
    assert {'macd', 'histogram'} <= ids
    rule = 'BUY when Close is above SMA 200d AND MACD line crosses above MACD signal'
    assert {'sma', 'crossovers', 'macd', 'signal-line'} <= {i for _, i in linked(rule, library, first_only=False)}
    assert 'Stoch RSI (14, 14, 3, 3) K 12.0 overbought' and \
        {'stoch-rsi', 'overbought-oversold'} <= {i for _, i in linked('Stoch RSI K 90 overbought', library)}


# --- requests --------------------------------------------------------------------------------------------------

@pytest.fixture
def requests_file(tmp_path, monkeypatch):
    monkeypatch.setattr(info_requests, 'FILE', tmp_path / 'info_requests.json')
    return tmp_path / 'info_requests.json'


def test_normalize():
    assert normalize('  Sharpe   RATIO ') == 'sharpe ratio'


def test_a_request_is_saved_with_its_context(requests_file):
    request = info_requests.add('Sharpe ratio', {'view': 'strategy', 'symbol': 'IBM', 'where': 'cards'}, 'what is good?')
    data = json.loads(requests_file.read_text(encoding='utf-8'))
    assert data['version'] == 1 and len(data['requests']) == 1
    saved = data['requests'][0]
    assert saved['text'] == 'Sharpe ratio' and saved['normalized'] == 'sharpe ratio' and saved['count'] == 1
    assert saved['contexts'] == [{'view': 'strategy', 'symbol': 'IBM', 'where': 'cards'}]
    assert saved['note'] == 'what is good?' and request.count == 1


def test_asking_again_only_raises_the_count_and_adds_new_context_and_notes(requests_file):
    info_requests.add('Sharpe ratio', {'view': 'strategy'})
    info_requests.add('  sharpe   RATIO ', {'view': 'strategy'}, 'note a')  # same context: not repeated
    info_requests.add('Sharpe ratio', {'view': 'history'}, 'note b')
    [only] = info_requests.all_requests()
    assert only.count == 3 and only.text == 'Sharpe ratio'
    assert only.contexts == [{'view': 'strategy'}, {'view': 'history'}] and only.note == 'note a | note b'


def test_blank_requests_are_refused(requests_file):
    with pytest.raises(ValueError, match='Say which term'):
        info_requests.add('   ')
    assert not requests_file.exists()


def test_pending_and_answered_follow_the_library(requests_file, tmp_path):
    library = library_of(tmp_path, ('s', 'id = "slippage"\ntitle = "Slippage"\naliases = ["fill drift"]', 'x'))
    info_requests.add('Sharpe ratio')
    info_requests.add('sharpe ratio')
    info_requests.add('Fill Drift')
    info_requests.add('Beta')
    assert [(r.text, r.count) for r in info_requests.pending(library)] == [('Sharpe ratio', 2), ('Beta', 1)]
    assert [r.text for r in info_requests.answered(library)] == ['Fill Drift']


def test_an_unreadable_file_is_kept_as_a_backup_and_a_new_list_started(requests_file):
    requests_file.write_text('{broken', encoding='utf-8')
    info_requests.add('Beta')
    assert requests_file.with_suffix('.json.bak').read_text(encoding='utf-8') == '{broken'
    assert [r.text for r in info_requests.all_requests()] == ['Beta']


def test_no_file_means_no_requests_and_nothing_is_created_by_reading(requests_file):
    assert info_requests.all_requests() == [] and not requests_file.exists()

"""Saving, loading, copying and deleting strategy files (in a temporary folder, never the real strategies/)."""
import pytest

from strategy import repository


@pytest.fixture(autouse=True)
def temporary_root(tmp_path, monkeypatch):
    monkeypatch.setattr(repository, 'ROOT', tmp_path / 'strategies')
    return tmp_path / 'strategies'


def test_save_and_load_per_stock_and_library(spec_example, temporary_root):
    path = repository.save(spec_example)
    assert path == temporary_root / 'IBM' / 'macd-stoch-rsi.json'
    template = spec_example.copy_for(None, 'Template')
    repository.save(template)
    assert (temporary_root / 'library' / 'template.json').exists()
    assert [s.id for s in repository.for_symbol('IBM')] == [spec_example.id]
    assert [s.id for s in repository.library()] == [template.id]
    assert repository.get(spec_example.id).to_dict() == spec_example.to_dict()


def test_renaming_moves_the_file(spec_example, temporary_root):
    repository.save(spec_example)
    spec_example.name = 'Renamed'
    repository.save(spec_example)
    assert sorted(p.name for p in (temporary_root / 'IBM').iterdir()) == ['renamed.json']


def test_two_strategies_with_the_same_name_get_separate_files(spec_example):
    twin = spec_example.copy_for('IBM')
    first, second = repository.save(spec_example), repository.save(twin)
    assert first != second and len(repository.for_symbol('IBM')) == 2


def test_copy_to_another_stock_is_independent_and_remembers_its_origin(spec_example):
    repository.save(spec_example)
    copy = repository.copy(spec_example.id, 'NVDA', 'NVDA swing')
    copy.buy.conditions[2].right.value = 30
    repository.save(copy)
    assert repository.get(spec_example.id).buy.conditions[2].right.value == 20
    stored = repository.get(copy.id)
    assert stored.symbol == 'NVDA' and stored.origin_id == spec_example.id and stored.name == 'NVDA swing'
    assert stored.buy.conditions[2].right.value == 30


def test_delete_removes_the_file_and_an_empty_stock_folder(spec_example, temporary_root):
    repository.save(spec_example)
    repository.delete(spec_example.id)
    assert repository.get(spec_example.id) is None and not (temporary_root / 'IBM').exists()


def test_unreadable_files_are_skipped(temporary_root, capsys):
    (temporary_root / 'IBM').mkdir(parents=True)
    (temporary_root / 'IBM' / 'broken.json').write_text('{"name": "no rules"}', encoding='utf-8')
    assert repository.all_strategies() == []
    assert 'broken.json' in capsys.readouterr().out


def test_the_built_in_library_strategies_load():
    repository.ROOT = repository.Path(__file__).resolve().parents[1] / 'strategies'  # undone by monkeypatch
    names = [s.name for s in repository.library()]
    assert {'Long-Term Trend', 'MACD + Stoch RSI', 'ATR Swing Trade'} <= set(names)


def test_every_built_in_library_strategy_is_documented_and_runs():
    from conftest import random_walk
    from prices import to_candles
    from strategy import describe
    from strategy.backtest import run
    repository.ROOT = repository.Path(__file__).resolve().parents[1] / 'strategies'  # undone by monkeypatch
    library = repository.library()
    assert len(library) >= 12
    daily, benchmark = random_walk(1500, seed=11), random_walk(1500, seed=12)
    for strategy in library:
        about = strategy.about
        assert about.summary and about.style and about.why and about.caveats, strategy.name
        assert about.references and all('(' in r and ')' in r for r in about.references), strategy.name  # (year)
        assert describe(strategy)
        result = run(strategy, to_candles(daily, '1D'), benchmark, daily.index[300], 'TEST')
        assert result.metrics['end_capital'] > 0, strategy.name

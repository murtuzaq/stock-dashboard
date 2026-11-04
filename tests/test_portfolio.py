"""Portfolio data (model + files) and the service rules, with no GUI."""
import json

import pytest

from core.portfolios.service import PortfolioError, PortfolioService
from portfolio import Portfolio, normalize_symbol, repository


@pytest.fixture(autouse=True)
def temporary_root(tmp_path, monkeypatch):
    monkeypatch.setattr(repository, 'ROOT', tmp_path / 'portfolios')
    return tmp_path / 'portfolios'


# --- model -----------------------------------------------------------------------------------------------------

def test_symbols_are_normalised_deduplicated_and_keep_their_order():
    portfolio = Portfolio('Mine', [' aapl', 'MSFT', 'aapl', '', 'ibm '])
    assert portfolio.symbols == ['AAPL', 'MSFT', 'IBM']
    assert portfolio.has('msft') and not portfolio.has('TSLA')
    assert normalize_symbol(' brk-b ') == 'BRK-B'


def test_round_trip_through_a_dict():
    portfolio = Portfolio('Mine', ['AAPL'])
    again = Portfolio.from_dict(portfolio.to_dict())
    assert again == portfolio and portfolio.to_dict()['version'] == 1


@pytest.mark.parametrize('data', [{}, {'id': 'x', 'name': '  '}, {'id': 'x', 'name': 'A', 'symbols': 'AAPL'},
                                  {'id': 'x', 'name': 'A', 'symbols': [1]}, {'name': 'A'}])
def test_bad_data_is_rejected(data):
    with pytest.raises((KeyError, TypeError, ValueError)):
        Portfolio.from_dict(data)


# --- files -----------------------------------------------------------------------------------------------------

def test_save_and_load(temporary_root):
    portfolio = Portfolio('Tech Stocks', ['AAPL', 'MSFT'])
    path = repository.save(portfolio)
    assert path == temporary_root / 'tech-stocks.json'
    assert repository.get(portfolio.id).symbols == ['AAPL', 'MSFT']
    assert [p.name for p in repository.all_portfolios()] == ['Tech Stocks']
    assert json.loads(path.read_text())['name'] == 'Tech Stocks'


def test_renaming_moves_the_file(temporary_root):
    portfolio = Portfolio('Old')
    repository.save(portfolio)
    portfolio.name = 'New'
    repository.save(portfolio)
    assert sorted(p.name for p in temporary_root.glob('*.json')) == ['new.json']


def test_two_portfolios_with_names_that_make_the_same_file_name_stay_separate(temporary_root):
    first, second = Portfolio('A B'), Portfolio('a-b')
    repository.save(first)
    repository.save(second)
    assert len(list(temporary_root.glob('*.json'))) == 2
    assert {p.name for p in repository.all_portfolios()} == {'A B', 'a-b'}


def test_delete_removes_the_file(temporary_root):
    portfolio = Portfolio('Gone')
    repository.save(portfolio)
    repository.delete(portfolio.id)
    repository.delete('no-such-id')  # harmless
    assert repository.all_portfolios() == [] and repository.get(portfolio.id) is None


def test_unreadable_files_are_skipped_and_logged(temporary_root, caplog):
    temporary_root.mkdir()
    (temporary_root / 'broken.json').write_text('{not json', encoding='utf-8')
    (temporary_root / 'wrong.json').write_text('{"id": "x", "name": ""}', encoding='utf-8')
    repository.save(Portfolio('Good'))
    assert [p.name for p in repository.all_portfolios()] == ['Good']
    assert 'broken.json' in caplog.text and 'wrong.json' in caplog.text


def test_nothing_is_created_until_something_is_saved(temporary_root):
    assert repository.all_portfolios() == [] and not temporary_root.exists()


# --- service ---------------------------------------------------------------------------------------------------

def test_default_names_count_up_and_reuse_the_lowest_free_number():
    service = PortfolioService()
    first, second, third = (service.create_default() for _ in range(3))
    assert [first.name, second.name, third.name] == ['Portfolio 1', 'Portfolio 2', 'Portfolio 3']
    service.delete(second.id)
    assert service.create_default().name == 'Portfolio 2'
    assert [s.name for s in service.saved()] == ['Portfolio 1', 'Portfolio 2', 'Portfolio 3']


def test_default_name_skips_a_name_the_user_already_took_even_in_other_case():
    service = PortfolioService()
    service.rename(service.create_default().id, 'portfolio 1')
    assert service.create_default().name == 'Portfolio 2'


def test_rename_trims_and_saves_and_rejects_blank_and_duplicate_names():
    service = PortfolioService()
    one, two = service.create_default(), service.create_default()
    assert service.rename(one.id, '  Retirement  ').name == 'Retirement'
    assert repository.get(one.id).name == 'Retirement'
    with pytest.raises(PortfolioError, match='needs a name'):
        service.rename(one.id, '   ')
    with pytest.raises(PortfolioError, match='already exists'):
        service.rename(two.id, 'RETIREMENT')
    assert service.rename(one.id, 'retirement').name == 'retirement'  # a name may differ from itself only in case
    assert repository.get(two.id).name == 'Portfolio 2'


def test_add_symbols_reports_what_was_added_and_what_was_already_there():
    service = PortfolioService()
    portfolio = service.create_default()
    assert service.add_symbols(portfolio.id, ['aapl', 'MSFT', 'aapl', ' ']) == (['AAPL', 'MSFT'], ['AAPL'])
    assert service.add_symbols(portfolio.id, ['msft', 'ibm']) == (['IBM'], ['MSFT'])
    assert repository.get(portfolio.id).symbols == ['AAPL', 'MSFT', 'IBM']
    assert service.saved()[0].stock_count == 3


def test_remove_symbol_and_unknown_portfolios():
    service = PortfolioService()
    portfolio = service.create_default()
    service.add_symbols(portfolio.id, ['AAPL', 'MSFT'])
    assert service.remove_symbol(portfolio.id, 'aapl').symbols == ['MSFT']
    assert service.remove_symbol(portfolio.id, 'TSLA').symbols == ['MSFT']  # not there: nothing happens
    with pytest.raises(PortfolioError, match='no longer exists'):
        service.add_symbols('missing', ['AAPL'])
    with pytest.raises(PortfolioError):
        service.rename('missing', 'X')

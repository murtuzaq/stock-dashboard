"""The Strategy Builder's rules and the strategy menu, with no widgets."""
import pytest

from core.strategies import service as actions
from core.builder.session import BUY, NAME, REVIEW, SELL, START, WizardForm, WizardSession
from strategy import Condition, Exits, Operand, RuleGroup, repository


@pytest.fixture(autouse=True)
def isolated_repository(tmp_path, monkeypatch):
    monkeypatch.setattr(repository, 'ROOT', tmp_path / 'strategies')


def a_condition():
    return Condition(Operand('close'), 'above', Operand('sma', params={'days': 50}))


def form(**changes):
    values = dict(name='Mine', buy=RuleGroup('all', [a_condition()]), sell=RuleGroup('any', [a_condition()]),
                  exits=Exits(stop_loss_pct=5))
    values.update(changes)
    return WizardForm(**values)


def test_new_strategy_starts_on_the_start_page_and_editing_skips_it():
    session = WizardSession()
    session.start_new('IBM')
    assert session.first_step == START and session.title() == 'New strategy for IBM'
    assert session.step_text(NAME) == 'Step 2 of 5: Name'

    editing = WizardSession()
    editing.start_new('IBM')
    saved = editing.save(form())
    editing.start_edit(saved)
    assert editing.first_step == NAME and editing.clamp(START) == NAME
    assert editing.step_text(NAME) == 'Step 1 of 4: Name'
    assert editing.title() == 'Edit "Mine"'


def test_each_step_explains_what_is_missing():
    session = WizardSession()
    session.start_new('IBM')
    assert 'Choose the strategy to copy' in session.check(START, WizardForm(copy_requested=True))
    assert session.check(START, WizardForm(copy_requested=False)) is None
    assert session.check(NAME, form(name='  ')) == 'Give the strategy a name.'
    assert session.check(BUY, form(buy=RuleGroup('all', []))) == 'Add at least one BUY condition.'
    assert 'trades never close' in session.check(SELL, form(sell=RuleGroup('any', []), exits=Exits()))
    assert session.check(SELL, form(sell=RuleGroup('any', []), exits=Exits(stop_loss_pct=8))) is None


def test_blank_draft_then_save_writes_the_strategy():
    session = WizardSession()
    session.start_new('IBM')
    draft = session.begin(WizardForm())
    assert draft.symbol == 'IBM' and draft.buy.conditions  # starts with a sensible default rule
    saved = session.save(form(name=' Trend '))
    assert saved.name == 'Trend'
    assert repository.get(saved.id).name == 'Trend'


def test_copy_draft_is_independent_of_the_source():
    source = WizardSession()
    source.start_new('IBM')
    original = source.save(form())

    session = WizardSession()
    session.start_new('AAPL')
    draft = session.begin(WizardForm(copy_requested=True, copy_source_id=original.id))
    assert draft.id != original.id and draft.symbol == 'AAPL' and draft.origin_id == original.id


def test_review_names_where_the_strategy_lives():
    session = WizardSession()
    session.start_new('IBM')
    session.begin(WizardForm())
    line = session.review(form())
    assert line[0].bold and ''.join(span.text for span in line).startswith('Mine — IBM')
    assert session.check(REVIEW, form()) is None


def test_existing_strategies_are_grouped_with_the_library_last():
    session = WizardSession()
    session.start_new('IBM')
    session.save(form(name='Zed'))
    library = repository.copy(session.draft.id, None)
    groups = dict(session.existing_strategies())
    assert [s.name for s in groups['IBM']] == ['Zed'] and groups['Library'][0].id == library.id


def test_menus_offer_the_right_actions():
    assert [e.action for e in actions.menu_for('symbol', 'IBM', False)] == [actions.NEW]
    own = [e.action for e in actions.menu_for('strategy', 'IBM', False) if e]
    assert own == [actions.EDIT, actions.DUPLICATE, actions.COPY_TO, actions.SAVE_TO_LIBRARY, actions.DELETE,
                   actions.NEW]
    template = actions.menu_for('strategy', 'IBM', True)
    assert template[0].action == actions.COPY_HERE and None in template
    assert actions.menu_for('unknown', 'IBM', False) == []


def test_strategy_service_copy_duplicate_delete():
    service = actions.StrategyService()
    session = WizardSession()
    session.start_new('IBM')
    saved = session.save(form())

    twin = service.duplicate(saved.id)
    assert twin.name == 'Mine (copy)' and twin.symbol == 'IBM'
    template = service.save_to_library(saved.id)
    assert template.symbol is None
    here = service.copy_here(template.id, 'AAPL')
    assert here.symbol == 'AAPL'
    assert 'from the library' not in service.delete_prompt(saved.id) and 'IBM' in service.delete_prompt(saved.id)
    assert 'the library' in service.delete_prompt(template.id)
    service.delete(saved.id)
    assert service.get(saved.id) is None


def test_explorer_entries_list_own_strategies_before_the_library():
    from core.explorer.entries import strategy_entries
    session = WizardSession()
    session.start_new('IBM')
    saved = session.save(form())
    repository.copy(saved.id, None, 'Template')
    entries = strategy_entries('IBM')
    assert [e.is_library for e in entries] == [False, True]
    assert entries[1].label == 'Template · library' and entries[0].key == f'strategy:{saved.id}'

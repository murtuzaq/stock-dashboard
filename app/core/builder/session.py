"""The Strategy Builder's rules: which steps exist, what each step needs, how the draft becomes a saved strategy.

The renderer reads its widgets into a WizardForm and asks this module what to do; no widget is consulted here.
Steps: 0 Start (new or copy) · 1 Name · 2 BUY rules · 3 SELL rules and exits · 4 Review.
"""
from dataclasses import dataclass

from core.common.formatting import Line, Span, plain
from strategy import Condition, Exits, Operand, RuleGroup, Strategy, describe, repository

STEPS = ['Start', 'Name', 'BUY rules', 'SELL rules & exits', 'Review']
START, NAME, BUY, SELL, REVIEW = range(5)

DEFAULT_BUY = Condition(Operand('close'), 'above', Operand('sma', params={'days': 200}))
DEFAULT_SELL = Condition(Operand('close'), 'below', Operand('sma', params={'days': 200}))


@dataclass
class WizardForm:
    """What the user has entered, read from the widgets."""
    copy_requested: bool = False
    copy_source_id: str | None = None  # the strategy chosen on the Start page, if any
    name: str = ''
    buy: RuleGroup | None = None
    sell: RuleGroup | None = None
    exits: Exits | None = None
    description: str = ''  # the strategy's one- or two-sentence summary


class WizardSession:
    def __init__(self) -> None:
        self.symbol: str | None = None  # the stock the strategy is for
        self.original: Strategy | None = None  # the strategy being edited (None when creating)
        self.draft: Strategy | None = None

    # --- starting ---

    def start_new(self, symbol: str | None) -> None:
        """A new strategy for this stock, or (symbol None) a new library template."""
        self.symbol, self.original, self.draft = symbol, None, None

    def start_edit(self, strategy: Strategy, context_symbol: str | None = None) -> None:
        self.symbol = strategy.symbol or context_symbol
        self.original = self.draft = strategy

    # --- what to show ---

    @property
    def is_template(self) -> bool:
        """True when the strategy being built is a library template (not tied to one stock)."""
        return self.original.symbol is None if self.original else self.symbol is None

    @property
    def first_step(self) -> int:
        """Editing skips the Start page."""
        return NAME if self.original else START

    def title(self) -> str:
        if self.original is None:
            return 'New library template' if self.symbol is None else f'New strategy for {self.symbol}'
        suffix = ' (library template)' if self.original.symbol is None else ''
        return f'Edit "{self.original.name}"{suffix}'

    def step_text(self, index: int) -> str:
        first = self.first_step
        return f'Step {index + 1 - first} of {len(STEPS) - first}: {STEPS[index]}'

    def for_text(self) -> str:
        if self.is_template:
            return 'A reusable library template (not tied to one stock).'
        return f'For {self.symbol}.'

    def clamp(self, index: int) -> int:
        return max(self.first_step, min(index, len(STEPS) - 1))

    def existing_strategies(self) -> list[tuple[str, list[Strategy]]]:
        """Every saved strategy grouped by stock (the library last under its own name), for the Start page."""
        groups: dict[str, list[Strategy]] = {}
        for strategy in sorted(repository.all_strategies(), key=lambda s: (s.symbol or '', s.name.lower())):
            groups.setdefault(strategy.symbol or 'Library', []).append(strategy)
        return list(groups.items())

    # --- rules ---

    def check(self, index: int, form: WizardForm) -> str | None:
        """The problem with this step, or None if the user may move on."""
        if index == START and form.copy_requested and not form.copy_source_id:
            return 'Choose the strategy to copy, or pick "Create a new strategy".'
        if index == NAME and not form.name.strip():
            return 'Give the strategy a name.'
        if index == BUY and not form.buy.conditions:
            return 'Add at least one BUY condition.'
        if index == SELL and not form.sell.conditions and form.exits == Exits():
            return 'Add a SELL condition or an exit (stop-loss, ATR stop or take-profit), or trades never close.'
        return None

    def begin(self, form: WizardForm) -> Strategy:
        """Leaving the Start page: the draft is a copy of the chosen strategy, or a blank one."""
        source = repository.get(form.copy_source_id) if form.copy_requested and form.copy_source_id else None
        self.draft = source.copy_for(self.symbol) if source else self._blank()
        return self.draft

    def build(self, form: WizardForm) -> Strategy:
        strategy = self.draft or self._blank()
        self.draft = strategy  # review and save must act on the same strategy (same id)
        strategy.name = form.name.strip()
        strategy.buy, strategy.sell, strategy.exits = form.buy, form.sell, form.exits
        strategy.about.summary = form.description.strip()  # its reasoning and references are kept as they were
        return strategy

    def save(self, form: WizardForm) -> Strategy:
        strategy = self.build(form)
        repository.save(strategy)
        return strategy

    def review(self, form: WizardForm) -> Line:
        where = 'library' if self.is_template else self.symbol
        line = [Span(form.name, bold=True), plain(f' — {where}\n\n')]
        if form.description.strip():
            line.append(plain(form.description.strip() + '\n\n'))
        return line + [plain(describe(self.build(form)))]

    def _blank(self) -> Strategy:
        return Strategy('', RuleGroup('all', [DEFAULT_BUY]), RuleGroup('any', [DEFAULT_SELL]),
                        Exits(stop_loss_pct=8), symbol=self.symbol)

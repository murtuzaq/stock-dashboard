"""Drives the Strategy Builder: which page is showing, what Next / Back / Cancel do.

The renderer implements `WizardView` (shows pages, reads the form) and forwards button clicks here. The rules for
each step are in core.builder.session.WizardSession; this class is the flow that uses them.
"""
from collections.abc import Callable
from typing import Protocol

from core.common.formatting import Line
from core.builder.session import NAME, REVIEW, START, WizardForm, WizardSession
from strategy import Strategy


class WizardView(Protocol):
    def show_title(self, text: str) -> None: ...
    def show_step(self, index: int, step_text: str, back_enabled: bool, next_text: str, for_text: str) -> None: ...
    def show_error(self, text: str) -> None: ...
    def show_review(self, line: Line) -> None: ...
    def read_form(self) -> WizardForm: ...
    def load_strategy(self, strategy: Strategy) -> None: ...
    def fill_existing(self, groups: list[tuple[str, list[Strategy]]]) -> None: ...
    def choose_new(self) -> None: ...
    def close(self) -> None: ...


class WizardController:
    def __init__(self, view: WizardView, session: WizardSession | None = None,
                 on_saved: Callable[[Strategy], None] | None = None) -> None:
        self.view = view
        self.session = session or WizardSession()
        self.on_saved = on_saved  # called with the strategy after Save & Backtest
        self.step = START

    @property
    def symbol(self) -> str | None:
        """The stock the strategy being built is for."""
        return self.session.symbol

    # --- starting ---

    def start_new(self, symbol: str) -> None:
        self.session.start_new(symbol)
        self.view.show_title(self.session.title())
        self.view.choose_new()
        self.view.fill_existing(self.session.existing_strategies())
        self._go(START)

    def start_edit(self, strategy: Strategy, context_symbol: str | None = None) -> None:
        self.session.start_edit(strategy, context_symbol)
        self.view.show_title(self.session.title())
        self.view.load_strategy(strategy)
        self._go(NAME)

    # --- buttons ---

    def back(self) -> None:
        self._go(self.step - 1)

    def cancel(self) -> None:
        self.view.close()

    def next(self) -> None:
        form = self.view.read_form()
        problem = self.session.check(self.step, form)
        if problem:
            self.view.show_error(problem)
            return
        if self.step == START:
            self.view.load_strategy(self.session.begin(form))
        if self.step == REVIEW:
            strategy = self.session.save(form)
            if self.on_saved:
                self.on_saved(strategy)
            return
        self._go(self.step + 1)

    # --- navigation ---

    def _go(self, index: int) -> None:
        self.step = index = self.session.clamp(index)
        next_text = 'Save && Backtest' if index == REVIEW else 'Next'
        self.view.show_step(index, self.session.step_text(index), index > self.session.first_step, next_text,
                            self.session.for_text())
        if index == REVIEW:
            self.view.show_review(self.session.review(self.view.read_form()))


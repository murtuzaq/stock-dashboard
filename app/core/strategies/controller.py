"""What happens when the user picks a strategy action (Explorer right-click menu, or the results panel's Edit).

This is the flow that used to live in the Qt adapter: ask the user, change the saved strategies, then tell the
Explorer to refresh and select, and open the wizard. Widgets are reached only through the protocols below.
"""
from typing import Protocol

from core.dashboard.controller import DashboardController
from core.strategies.service import StrategyService
from core.builder.controller import WizardController
from strategy import Strategy


class ExplorerView(Protocol):
    def add_symbol(self, symbol: str) -> None: ...
    def refresh_strategies(self) -> None: ...
    def select_strategy(self, symbol: str, strategy_id: str) -> None: ...


class Dialogs(Protocol):
    """Things only the user can answer, and the panel that hosts the wizard."""

    def ask_symbol(self, title: str) -> str | None: ...
    def confirm(self, text: str) -> bool: ...
    def show_wizard(self) -> None: ...


class StrategyController:
    def __init__(self, service: StrategyService, explorer: ExplorerView, wizard: WizardController,
                 dashboard: DashboardController, dialogs: Dialogs) -> None:
        self.service = service
        self.explorer = explorer
        self.wizard = wizard
        self.dashboard = dashboard
        self.dialogs = dialogs
        wizard.on_saved = self.saved

    def handle(self, action: str, symbol: str, strategy_id: str) -> None:
        """Run an action by name (see core.strategies.service). All take the stock being viewed and a strategy id."""
        getattr(self, action)(symbol, strategy_id)

    def edit_current(self, strategy_id: str) -> None:
        """'Edit rules…' on the results panel: edit for the stock currently shown."""
        self.edit(self.dashboard.symbol, strategy_id)

    # --- actions ---

    def new(self, symbol: str, strategy_id: str) -> None:
        self.wizard.start_new(symbol)
        self.dialogs.show_wizard()

    def edit(self, symbol: str, strategy_id: str) -> None:
        strategy = self.service.get(strategy_id)
        if strategy:
            self.wizard.start_edit(strategy, symbol)
            self.dialogs.show_wizard()

    def copy_here(self, symbol: str, strategy_id: str) -> None:
        """Library template -> this stock's own copy, opened for customising."""
        copy = self.service.copy_here(strategy_id, symbol)
        self._show(symbol, copy)
        self.edit(symbol, copy.id)

    def duplicate(self, symbol: str, strategy_id: str) -> None:
        self._show(symbol, self.service.duplicate(strategy_id))

    def copy_to(self, symbol: str, strategy_id: str) -> None:
        target = self.dialogs.ask_symbol('Copy the strategy to which stock?')
        if not target:
            return
        copy = self.service.copy_to(strategy_id, target)
        self.explorer.add_symbol(target)
        self._show(target, copy)

    def save_to_library(self, symbol: str, strategy_id: str) -> None:
        self.service.save_to_library(strategy_id)
        self.explorer.refresh_strategies()

    def delete(self, symbol: str, strategy_id: str) -> None:
        if self.dialogs.confirm(self.service.delete_prompt(strategy_id)):
            self.service.delete(strategy_id)
            self.explorer.refresh_strategies()

    # --- after the wizard ---

    def saved(self, strategy: Strategy) -> None:
        self.wizard.cancel()  # closes the panel
        symbol = strategy.symbol or self.wizard.symbol
        self._show(symbol, strategy)
        self.dashboard.refresh_strategy()  # the rules may have changed under the same selection

    def _show(self, symbol: str, strategy: Strategy) -> None:
        self.explorer.refresh_strategies()
        self.explorer.select_strategy(symbol, strategy.id)


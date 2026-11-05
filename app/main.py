"""Stock Dashboard entry point. Run with: python app/main.py

This is the composition root: it creates the core objects (controller, services), creates the Qt widgets that
render them, and connects the two. No rules live here.
"""
import sys
from collections.abc import Callable

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QSplitter, QWidget

from core.builder.controller import WizardController
from core.common.background import BackgroundLoader
from core.dashboard.controller import DashboardController
from core.explorer.controller import ExplorerController
from core.learn.controller import InfoController
from core.learn.preferences import Preferences
from core.portfolios.add_stock import AddStockController
from core.portfolios.controller import PortfolioController
from core.portfolios.service import PortfolioService
from core.strategies.controller import StrategyController
from core.strategies.service import StrategyService
from learn import TopicLibrary, load_library
from portfolio import Portfolio
from prices import load_daily, load_financials
from qtrender.builder.wizard import StrategyWizard
from qtrender.dashboard.view_area import ViewArea
from qtrender.dialogs import QtDialogs
from qtrender.explorer.tree import Explorer
from qtrender.gui_thread import make_loader
from qtrender.header import Header
from qtrender.learn import info_mode
from qtrender.learn.info_mode import InfoMode
from qtrender.learn.info_panel import MINIMUM_WIDTH as INFO_MINIMUM_WIDTH, InfoDock, InfoPanel
from qtrender.learn.request_dialog import QtInfoDialogs, QtPreferences
from qtrender.learn.view import QtInfoView
from qtrender.menu_bar import AppMenuBar
from qtrender.portfolios.add_stock_panel import AddStockPanel
from qtrender.searchbar.bar import SearchBar
from qtrender.side_panel import MINIMUM_WIDTH, SideDock
from qtrender.style import STYLE, dark_palette


class MainWindow(QMainWindow):
    def __init__(self, loader: BackgroundLoader | None = None,
                 history_source: Callable[[str], pd.DataFrame] = load_daily,
                 financials_source: Callable[[str], dict] = load_financials,
                 preferences: Preferences | None = None, library: TopicLibrary | None = None) -> None:
        """The sources, loader, remembered settings and topic library can be replaced (tests use canned ones)."""
        super().__init__()
        self.setWindowTitle('Stock Dashboard')
        self.resize(1400, 850)

        loader = loader or make_loader()
        strategy_service, portfolio_service = StrategyService(), PortfolioService()
        preferences = preferences or QtPreferences()
        library = library or load_library()

        # Info mode comes first: the widgets below ask for it when they are built.
        self.info_mode = InfoMode(library)
        info_mode.set_current(self.info_mode)

        self.menu = AppMenuBar()
        self.setMenuBar(self.menu)
        self.header = Header(SearchBar(loader))
        self.addToolBar(self.header)
        self.explorer = Explorer()
        self.view_area = ViewArea(loader, financials_source)
        self.wizard = StrategyWizard()  # a page of the right-hand panel, for creating or editing a strategy
        self.add_stock_panel = AddStockPanel(loader)  # the other page: adding stocks to a portfolio
        self.side_panel = SideDock()  # a dock on the right: one page at a time, shown only when needed
        self.side_panel.add_page(self.wizard, 'Strategy Builder')
        self.side_panel.add_page(self.add_stock_panel, 'Add Stock')
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.side_panel)
        self.info_panel = InfoPanel()
        self.info_dock = InfoDock(self.info_panel)  # below the strategy builder dock when both are showing
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.info_dock)
        self.splitDockWidget(self.side_panel, self.info_dock, Qt.Orientation.Vertical)
        self.controller = DashboardController(self.view_area, loader, strategy_service, history_source)

        self.splitter = splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.explorer)
        splitter.addWidget(self.view_area)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 1160])
        self.setCentralWidget(splitter)

        self.dialogs = QtDialogs(self, loader, lambda: self.show_panel(self.wizard))
        self.explorer_controller = ExplorerController(self.explorer, on_views_selected=self.controller.select,
                                                      on_selection_cleared=self.controller.clear)
        self.wizard_controller = WizardController(self.wizard)
        self.strategy_controller = StrategyController(strategy_service, self.explorer_controller,
                                                      self.wizard_controller, self.controller, self.dialogs)
        self.add_stock_controller = AddStockController(self.add_stock_panel, portfolio_service,
                                                       self.explorer_controller)
        self.portfolio_controller = PortfolioController(portfolio_service, self.explorer_controller, self.dialogs,
                                                        self.open_add_stock)
        self.info_controller = InfoController(
            QtInfoView(self.info_panel, self.info_mode, self.menu, self.show_info_dock, self.info_dock.hide),
            library, QtInfoDialogs(self), preferences, context=self._info_context)
        self.info_mode.bind(self.info_controller)
        self.explorer_controller.on_strategy_action = self.strategy_controller.handle
        self.explorer_controller.on_portfolio_action = self.portfolio_controller.handle
        self.explorer.menu_source = self.explorer_controller.menu_for

        # Widgets report what the user did; the controllers decide what it means.
        self.menu.new_portfolio_requested.connect(self.portfolio_controller.new_portfolio)
        self.menu.load_portfolio_requested.connect(self.portfolio_controller.load_portfolio)
        self.menu.exit_requested.connect(self.close)
        self.menu.info_wizard_toggled.connect(self.info_controller.set_enabled)
        self.info_panel.back_requested.connect(self.info_controller.back)
        self.info_panel.forward_requested.connect(self.info_controller.forward)
        self.info_panel.topic_requested.connect(self.info_controller.open)
        self.info_panel.request_requested.connect(lambda text: self.info_controller.request(text, 'Info panel'))
        self.header.symbol_searched.connect(self.explorer_controller.add_symbol)
        self.header.timeframe_changed.connect(self.controller.set_candle_size)
        self.explorer.selection_changed.connect(self.explorer_controller.on_selection_changed)
        self.explorer.action_chosen.connect(self.explorer_controller.menu_action)
        self.explorer.rename_requested.connect(self.explorer_controller.rename_requested)
        self.view_area.range_selected.connect(self.controller.set_range)
        self.view_area.costs_changed.connect(self.controller.update_costs)
        self.view_area.edit_strategy.connect(self.strategy_controller.edit_current)
        self.wizard.next_requested.connect(self.wizard_controller.next)
        self.wizard.back_requested.connect(self.wizard_controller.back)
        self.wizard.cancel_requested.connect(self.wizard_controller.cancel)
        self.wizard.closed.connect(self.side_panel.dismiss)
        self.add_stock_panel.symbol_chosen.connect(self.add_stock_controller.add)
        self.add_stock_panel.done_requested.connect(self.add_stock_controller.done)
        self.add_stock_panel.closed.connect(self.side_panel.dismiss)
        self.info_controller.restore()  # apply the remembered View > Info Wizard setting

    def open_add_stock(self, portfolio: Portfolio) -> None:
        """Right-click > Add Stock…: the panel replaces the strategy builder, after confirming if that is in use."""
        if self.wizard.isVisible() and not self.dialogs.confirm(
                'Discard the strategy you are editing and add stocks instead?'):
            return
        self.add_stock_controller.start(portfolio)
        self.show_panel(self.add_stock_panel)

    def _info_context(self) -> dict:
        """What was on screen, saved with an info request so the developer can see where the term appeared."""
        context = {}
        if self.controller.symbol:
            context = {'symbol': self.controller.symbol, 'view': ','.join(self.controller.shown)}
        return context

    def show_info_dock(self) -> None:
        """Open the Info dock (below the strategy builder dock if that is showing), sized sensibly the first time."""
        was_open = self.info_dock.isVisible()
        self.info_dock.show()
        if was_open:
            return
        if self.side_panel.isVisible():
            self.resizeDocks([self.side_panel, self.info_dock], [560, 320], Qt.Orientation.Vertical)
        else:
            self.resizeDocks([self.info_dock], [max(INFO_MINIMUM_WIDTH, 420)], Qt.Orientation.Horizontal)

    def show_panel(self, page: QWidget) -> None:
        """Show a page in the right-hand dock, giving it room (taken from the charts) if it was closed."""
        was_open = self.side_panel.isVisible()
        self.side_panel.show_page(page)
        if not was_open:
            self.resizeDocks([self.side_panel], [max(MINIMUM_WIDTH, 620)], Qt.Orientation.Horizontal)


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setPalette(dark_palette())
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

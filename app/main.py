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
from core.portfolios.add_stock import AddStockController
from core.portfolios.controller import PortfolioController
from core.portfolios.service import PortfolioService
from core.strategies.controller import StrategyController
from core.strategies.service import StrategyService
from portfolio import Portfolio
from prices import load_daily, load_financials
from qtrender.builder.wizard import StrategyWizard
from qtrender.dashboard.view_area import ViewArea
from qtrender.dialogs import QtDialogs
from qtrender.explorer.tree import Explorer
from qtrender.gui_thread import make_loader
from qtrender.header import Header
from qtrender.menu_bar import AppMenuBar
from qtrender.portfolios.add_stock_panel import AddStockPanel
from qtrender.searchbar.bar import SearchBar
from qtrender.side_panel import SidePanel
from qtrender.style import STYLE, dark_palette


class MainWindow(QMainWindow):
    def __init__(self, loader: BackgroundLoader | None = None,
                 history_source: Callable[[str], pd.DataFrame] = load_daily,
                 financials_source: Callable[[str], dict] = load_financials) -> None:
        """The sources and loader can be replaced (tests use canned data and an immediate loader)."""
        super().__init__()
        self.setWindowTitle('Stock Dashboard')
        self.resize(1400, 850)

        loader = loader or make_loader()
        strategy_service, portfolio_service = StrategyService(), PortfolioService()

        self.menu = AppMenuBar()
        self.setMenuBar(self.menu)
        self.header = Header(SearchBar(loader))
        self.addToolBar(self.header)
        self.explorer = Explorer()
        self.view_area = ViewArea(loader, financials_source)
        self.wizard = StrategyWizard()  # a page of the right-hand panel, for creating or editing a strategy
        self.add_stock_panel = AddStockPanel(loader)  # the other page: adding stocks to a portfolio
        self.side_panel = SidePanel()
        self.side_panel.addWidget(self.wizard)
        self.side_panel.addWidget(self.add_stock_panel)
        self.controller = DashboardController(self.view_area, loader, strategy_service, history_source)

        self.splitter = splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.explorer)
        splitter.addWidget(self.view_area)
        splitter.addWidget(self.side_panel)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(2, False)
        splitter.setSizes([240, 1160, 0])
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
        self.explorer_controller.on_strategy_action = self.strategy_controller.handle
        self.explorer_controller.on_portfolio_action = self.portfolio_controller.handle
        self.explorer.menu_source = self.explorer_controller.menu_for

        # Widgets report what the user did; the controllers decide what it means.
        self.menu.new_portfolio_requested.connect(self.portfolio_controller.new_portfolio)
        self.menu.load_portfolio_requested.connect(self.portfolio_controller.load_portfolio)
        self.menu.exit_requested.connect(self.close)
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

    def open_add_stock(self, portfolio: Portfolio) -> None:
        """Right-click > Add Stock…: the panel replaces the strategy builder, after confirming if that is in use."""
        if self.wizard.isVisible() and not self.dialogs.confirm(
                'Discard the strategy you are editing and add stocks instead?'):
            return
        self.add_stock_controller.start(portfolio)
        self.show_panel(self.add_stock_panel)

    def show_panel(self, page: QWidget) -> None:
        """Show a page in the right-hand panel, taking room from the charts if the panel was closed."""
        was_open = self.side_panel.isVisible()
        self.side_panel.show_page(page)
        explorer, charts, panel = self.splitter.sizes()
        if not was_open or panel < self.side_panel.minimumWidth():
            width = max(self.side_panel.minimumWidth(), 620)
            self.splitter.setSizes([explorer, max(charts + panel - width, 300), width])


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

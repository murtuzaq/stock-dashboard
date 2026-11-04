"""Stock Dashboard entry point. Run with: python app/main.py

This is the composition root: it creates the core objects (controller, services), creates the Qt widgets that
render them, and connects the two. No rules live here.
"""
import sys
from collections.abc import Callable

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QSplitter

from core.common.background import BackgroundLoader
from core.dashboard.controller import DashboardController
from core.explorer.controller import ExplorerController
from core.strategies.controller import StrategyController
from core.strategies.service import StrategyService
from core.builder.controller import WizardController
from prices import load_daily, load_financials
from qtrender.dialogs import QtDialogs
from qtrender.explorer.tree import Explorer
from qtrender.gui_thread import make_loader
from qtrender.header import Header
from qtrender.searchbar.bar import SearchBar
from qtrender.builder.wizard import StrategyWizard
from qtrender.style import STYLE, dark_palette
from qtrender.dashboard.view_area import ViewArea


class MainWindow(QMainWindow):
    def __init__(self, loader: BackgroundLoader | None = None,
                 history_source: Callable[[str], pd.DataFrame] = load_daily,
                 financials_source: Callable[[str], dict] = load_financials) -> None:
        """The sources and loader can be replaced (tests use canned data and an immediate loader)."""
        super().__init__()
        self.setWindowTitle('Stock Dashboard')
        self.resize(1400, 850)

        loader = loader or make_loader()
        service = StrategyService()

        self.header = Header(SearchBar(loader))
        self.addToolBar(self.header)
        self.explorer = Explorer()
        self.view_area = ViewArea(loader, financials_source)
        self.wizard = StrategyWizard()  # third panel, shown only while creating or editing a strategy
        self.wizard.hide()
        self.controller = DashboardController(self.view_area, loader, service, history_source)

        self.splitter = splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.explorer)
        splitter.addWidget(self.view_area)
        splitter.addWidget(self.wizard)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(2, False)
        splitter.setSizes([240, 1160, 0])
        self.setCentralWidget(splitter)

        self.explorer_controller = ExplorerController(self.explorer, on_views_selected=self.controller.select)
        self.wizard_controller = WizardController(self.wizard)
        self.strategy_controller = StrategyController(service, self.explorer_controller, self.wizard_controller,
                                                      self.controller, QtDialogs(self, loader, self.show_wizard))
        self.explorer_controller.on_strategy_action = self.strategy_controller.handle
        self.explorer.menu_source = self.explorer_controller.menu_for

        # Widgets report what the user did; the controllers decide what it means.
        self.header.symbol_searched.connect(self.explorer_controller.add_symbol)
        self.header.timeframe_changed.connect(self.controller.set_candle_size)
        self.explorer.selection_changed.connect(self.explorer_controller.on_selection_changed)
        self.explorer.action_chosen.connect(self.explorer_controller.menu_action)
        self.view_area.range_selected.connect(self.controller.set_range)
        self.view_area.costs_changed.connect(self.controller.update_costs)
        self.view_area.edit_strategy.connect(self.strategy_controller.edit_current)
        self.wizard.next_requested.connect(self.wizard_controller.next)
        self.wizard.back_requested.connect(self.wizard_controller.back)
        self.wizard.cancel_requested.connect(self.wizard_controller.cancel)

    def show_wizard(self) -> None:
        """Open the Strategy Builder as a third panel on the right, taking room from the charts."""
        explorer, charts, wizard = self.splitter.sizes()
        if not self.wizard.isVisible() or wizard < self.wizard.minimumWidth():
            width = max(self.wizard.minimumWidth(), 620)
            self.wizard.show()
            self.splitter.setSizes([explorer, max(charts + wizard - width, 300), width])


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

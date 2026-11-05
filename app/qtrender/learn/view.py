"""Puts the Info panel, the dock and Info mode together as the single InfoView the controller drives."""
from collections.abc import Callable

from core.learn.controller import TopicPage
from qtrender.learn.info_mode import InfoMode
from qtrender.learn.info_panel import InfoPanel
from qtrender.menu_bar import AppMenuBar


class QtInfoView:
    def __init__(self, panel: InfoPanel, mode: InfoMode, menu: AppMenuBar, show_dock: Callable[[], None],
                 hide_dock: Callable[[], None]) -> None:
        self.panel, self.mode, self.menu = panel, mode, menu
        self._show_dock, self._hide_dock = show_dock, hide_dock

    def show_topic(self, page: TopicPage) -> None:
        self.panel.show_topic(page)

    def show_not_found(self, text: str) -> None:
        self.panel.show_not_found(text)

    def set_navigation(self, can_back: bool, can_forward: bool) -> None:
        self.panel.set_navigation(can_back, can_forward)

    def show_panel(self) -> None:
        self._show_dock()

    def hide_panel(self) -> None:
        self._hide_dock()

    def set_highlighting(self, enabled: bool) -> None:
        self.mode.set_on(enabled)
        self.menu.set_info_checked(enabled)  # keep View > Info Wizard in step (e.g. after restoring the setting)

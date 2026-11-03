"""Explorer panel: one parent node per searched symbol, with child nodes for each view of it."""
from typing import Callable

from nicegui import ui

# Views available under every symbol. Add RSI, moving averages, etc. here later.
VIEWS = [('candles', 'Candles', 'candlestick_chart')]


class Explorer:
    def __init__(self, on_select: Callable[[str, str], None]) -> None:
        self.on_select = on_select
        self.nodes: list[dict] = []

        ui.label('EXPLORER').classes('text-xs font-semibold tracking-wider text-gray-400 px-3 pt-3')
        self.empty_hint = ui.label('No symbols yet').classes('text-sm text-gray-500 px-3')
        self.tree = ui.tree(self.nodes, node_key='id', label_key='label',
                            on_select=lambda e: self._handle_select(e.value)) \
            .props('dark dense selected-color=primary').classes('w-full')

    def add_symbol(self, symbol: str) -> None:
        """Add a symbol (unless already present) and select its first view."""
        if not any(node['id'] == symbol for node in self.nodes):
            self.nodes.append({
                'id': symbol,
                'label': symbol,
                'icon': 'show_chart',
                'children': [{'id': f'{symbol}/{key}', 'label': label, 'icon': icon} for key, label, icon in VIEWS],
            })
            self.empty_hint.set_visibility(False)
            self.tree.update()
        self.tree.expand([symbol])
        self.select(f'{symbol}/{VIEWS[0][0]}')

    def select(self, node_id: str) -> None:
        self.tree.select(node_id)
        self._handle_select(node_id)

    def _handle_select(self, node_id: str | None) -> None:
        if not node_id:  # clicking the selected node again deselects it; keep the current view
            return
        if '/' not in node_id:  # a symbol was clicked: open its first view
            self.select(f'{node_id}/{VIEWS[0][0]}')
            return
        symbol, view = node_id.split('/', 1)
        self.on_select(symbol, view)

"""Top bar: app name, symbol search and timeframe selector."""
from typing import Callable

from nicegui import ui

# Candle sizes. Only daily candles will be downloaded; the rest are built from them.
TIMEFRAMES = ['1D', '1W', '2W', '1M', '3M']


def build_header(on_search: Callable[[str], None], on_timeframe: Callable[[str], None]) -> None:
    with ui.header().classes('h-14 items-center gap-6 px-4 bg-[#131722] border-b border-[#2a2e39]'):
        ui.label('Stock Dashboard').classes('text-lg font-semibold')

        search = ui.input(placeholder='Search symbol (e.g. AAPL)') \
            .props('dense outlined dark clearable input-class="uppercase"') \
            .classes('w-64')

        def submit() -> None:
            symbol = (search.value or '').strip().upper()
            if symbol:
                on_search(symbol)
                search.value = ''

        search.on('keydown.enter', submit)
        with search.add_slot('prepend'):
            ui.icon('search')

        ui.toggle(TIMEFRAMES, value=TIMEFRAMES[0], on_change=lambda e: on_timeframe(e.value)) \
            .props('dense no-caps toggle-color=primary')

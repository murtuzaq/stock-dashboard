"""Stock Dashboard entry point. Run with: python app/main.py"""
from nicegui import ui

from chart_view import ChartView, add_chart_library
from explorer import Explorer
from header import TIMEFRAMES, build_header


@ui.page('/')
def index() -> None:
    add_chart_library()
    ui.query('body').style('background-color: #131722')
    ui.query('.nicegui-content').classes('p-0 gap-0')

    state = {'symbol': None, 'view': None, 'timeframe': TIMEFRAMES[0]}

    def refresh() -> None:
        chart_view.show(state['symbol'], state['view'], state['timeframe'])

    def on_select(symbol: str, view: str) -> None:
        state.update(symbol=symbol, view=view)
        refresh()

    def on_timeframe(timeframe: str) -> None:
        state['timeframe'] = timeframe
        if state['symbol']:
            refresh()

    build_header(on_search=lambda symbol: explorer.add_symbol(symbol), on_timeframe=on_timeframe)

    with ui.splitter(value=18, limits=(10, 40)).classes('w-full').style('height: calc(100vh - 3.5rem)') as splitter:
        with splitter.before:
            explorer = Explorer(on_select=on_select)
        with splitter.after:
            chart_view = ChartView()


if __name__ in {'__main__', '__mp_main__'}:
    ui.run(title='Stock Dashboard', host='127.0.0.1', dark=True, reload=False)

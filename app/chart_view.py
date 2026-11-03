"""Main area: shows the view selected in the Explorer, drawn with TradingView Lightweight Charts."""
from nicegui import ui

LIGHTWEIGHT_CHARTS = 'https://unpkg.com/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js'

# Browser-side helper: replaces any previous chart with an empty dark candlestick chart.
RENDER_JS = '''
<script>
window.renderCandles = (id) => {
  const el = document.getElementById(id);
  if (!el || !window.LightweightCharts) { requestAnimationFrame(() => renderCandles(id)); return; }
  if (window.activeChart) window.activeChart.remove();
  const chart = LightweightCharts.createChart(el, {
    autoSize: true,
    layout: { background: { type: 'solid', color: '#131722' }, textColor: '#d1d4dc' },
    grid: { vertLines: { color: '#1e222d' }, horzLines: { color: '#1e222d' } },
    rightPriceScale: { borderColor: '#2a2e39' },
    timeScale: { borderColor: '#2a2e39' },
  });
  chart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
    wickUpColor: '#26a69a', wickDownColor: '#ef5350',
  });
  window.activeChart = chart;
};
</script>
'''


def add_chart_library() -> None:
    ui.add_head_html(f'<script src="{LIGHTWEIGHT_CHARTS}"></script>{RENDER_JS}')


class ChartView:
    def __init__(self) -> None:
        self.container = ui.column().classes('w-full h-full p-3 gap-2')
        self.show(None, None, '1D')

    def show(self, symbol: str | None, view: str | None, timeframe: str) -> None:
        self.container.clear()
        with self.container:
            if symbol is None:
                with ui.column().classes('w-full h-full items-center justify-center text-gray-500'):
                    ui.icon('candlestick_chart', size='4rem')
                    ui.label('Search a symbol to begin')
                return

            ui.label(f'{symbol} · {view.capitalize()} · {timeframe}').classes('text-base font-semibold')
            chart = ui.element('div').classes('w-full grow rounded border border-[#2a2e39]')
            ui.run_javascript(f'renderCandles("c{chart.id}")')

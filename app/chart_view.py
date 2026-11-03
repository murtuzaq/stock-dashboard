"""Main area: shows the view selected in the Explorer, drawn with pyqtgraph."""
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPicture
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

BACKGROUND = '#131722'
GRID_TEXT = '#d1d4dc'
UP = '#26a69a'
DOWN = '#ef5350'


class CandlestickItem(pg.GraphicsObject):
    """Draws candles from (time, open, high, low, close) rows. Empty until data is loaded."""

    def __init__(self) -> None:
        super().__init__()
        self.picture = QPicture()

    def set_data(self, rows: list[tuple[float, float, float, float, float]], width: float) -> None:
        self.picture = QPicture()
        painter = QPainter(self.picture)
        for time, open_, high, low, close in rows:
            color = pg.mkColor(UP if close >= open_ else DOWN)
            painter.setPen(pg.mkPen(color))
            painter.drawLine(QPointF(time, low), QPointF(time, high))
            painter.setBrush(pg.mkBrush(color))
            painter.drawRect(QRectF(time - width / 2, open_, width, close - open_))
        painter.end()
        self.prepareGeometryChange()
        self.update()

    def paint(self, painter, *args) -> None:
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self) -> QRectF:
        return QRectF(self.picture.boundingRect())


class ChartView(QStackedWidget):
    def __init__(self) -> None:
        super().__init__()

        placeholder = QLabel('Search a symbol to begin')
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName('placeholder')
        self.addWidget(placeholder)

        page = QWidget()
        layout = QVBoxLayout(page)
        self.title = QLabel()
        self.title.setObjectName('chartTitle')
        layout.addWidget(self.title)

        self.plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem()}, background=BACKGROUND)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.hideAxis('left')
        self.plot.showAxis('right')  # price on the right, like trading platforms
        for axis in ('right', 'bottom'):
            self.plot.getAxis(axis).setTextPen(GRID_TEXT)
        self.candles = CandlestickItem()
        self.plot.addItem(self.candles)
        layout.addWidget(self.plot)
        self.addWidget(page)

    def show_view(self, symbol: str, view: str, timeframe: str) -> None:
        self.title.setText(f'{symbol} · {view.capitalize()} · {timeframe}')
        self.setCurrentIndex(1)

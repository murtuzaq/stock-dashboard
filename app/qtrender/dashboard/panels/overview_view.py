"""Company overview (renderer): what the company does, its key numbers, what investors like and dislike,
and how each strategy would have done on it. Clicking a strategy row opens that strategy's backtest.

The content is worked out by core.overview.model (driven by the dashboard controller); this widget only draws it.
"""
from html import escape

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QScrollArea, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from company import Point
from core.common import theme
from core.overview.model import RANK_COLUMNS, OverviewModel
from qtrender.layouts import clear_layout
from qtrender.richtext import line_html

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
FACT_COLUMNS = 4
BEST_BACKGROUND = '#1e2a4a'


def _label(object_name: str = '', wrap: bool = True) -> QLabel:
    label = QLabel()
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(wrap)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _points_html(points: list[Point], mark: str, color: str, empty: str) -> str:
    if not points:
        return f'<span style="color:{theme.MUTED}">{escape(empty)}</span>'
    rows = [f'<p style="margin:0 0 8px 0"><span style="color:{color}"><b>{mark}</b></span> {escape(point.text)}<br>'
            f'<span style="color:{theme.MUTED}">{escape(point.why)}</span></p>' for point in points]
    return ''.join(rows)


class OverviewView(QScrollArea):
    strategy_chosen = Signal(str)  # strategy id, from a click on the comparison table

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName('overview')
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.model: OverviewModel | None = None
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(10)

        self.status = _label('placeholder')
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        self.heading = _label('overviewHeading')
        self.subheading = _label('summary')
        layout.addWidget(self.heading)
        layout.addWidget(self.subheading)
        self.facts = QGridLayout()
        self.facts.setHorizontalSpacing(24)
        layout.addLayout(self.facts)

        layout.addWidget(self._section('About the company'))
        self.summary = _label()
        layout.addWidget(self.summary)

        columns = QHBoxLayout()
        columns.setSpacing(24)
        for attribute, title in (('likes', 'What investors like'), ('dislikes', "What they don't like")):
            column = QVBoxLayout()
            column.addWidget(self._section(title))
            label = _label()
            label.setAlignment(Qt.AlignmentFlag.AlignTop)
            setattr(self, attribute, label)
            column.addWidget(label)
            column.addStretch()
            columns.addLayout(column, stretch=1)
        layout.addLayout(columns)

        self.best_heading = self._section('Best strategy for this stock')
        layout.addWidget(self.best_heading)
        self.verdict = _label()
        layout.addWidget(self.verdict)
        self.table = QTableWidget(0, len(RANK_COLUMNS))
        self.table.setObjectName('historyTable')
        self.table.setHorizontalHeaderLabels(RANK_COLUMNS)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.cellClicked.connect(self._row_clicked)
        layout.addWidget(self.table)
        self.note = _label('summary')
        layout.addWidget(self.note)
        layout.addStretch()
        self.setWidget(content)
        self.detail_widgets = [self.heading, self.subheading, self.summary, self.likes, self.dislikes,
                               self.best_heading, self.verdict, self.table, self.note]

    @staticmethod
    def _section(title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName('overviewSection')
        return label

    # --- what the view area asks for ---

    def set_data(self, daily: pd.DataFrame, candles: pd.DataFrame) -> None:
        pass  # filled through show_overview()

    def set_range(self, start: pd.Timestamp) -> None:
        pass  # the overview does not depend on the range

    def show_overview(self, model: OverviewModel | None, status: str = '') -> None:
        self.model = model
        self.status.setVisible(model is None)
        self.status.setText(escape(status))
        for widget in self.detail_widgets:
            widget.setVisible(model is not None)
        if model is None:
            return
        self.heading.setText(line_html(model.heading))
        self.subheading.setText(escape(model.subheading))
        self._show_facts(model.facts)
        self.summary.setText(escape(model.summary))
        self.likes.setText(_points_html(model.likes, '✓', theme.UP, 'Nothing stands out on the positive side.'))
        self.dislikes.setText(_points_html(model.dislikes, '✗', theme.DOWN, 'Nothing stands out as a concern.'))
        self.verdict.setText(line_html(model.verdict))
        self._show_table(model)
        self.note.setText(escape(model.rank_note))

    def _show_facts(self, facts: list[tuple[str, str]]) -> None:
        clear_layout(self.facts)
        for index, (label, value) in enumerate(facts):
            row, column = divmod(index, FACT_COLUMNS)
            caption = QLabel(label)
            caption.setObjectName('barLabel')
            text = _label(wrap=False)
            text.setText(f'<b>{escape(value)}</b>')
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addWidget(caption)
            cell.addWidget(text)
            holder = QWidget()
            holder.setLayout(cell)
            self.facts.addWidget(holder, row, column)

    def _show_table(self, model: OverviewModel) -> None:
        self.table.setVisible(bool(model.rank_rows))
        self.table.setRowCount(len(model.rank_rows))
        for row, rank_row in enumerate(model.rank_rows):
            for column, cell in enumerate(rank_row.cells):
                item = QTableWidgetItem(cell.text)
                if cell.color:
                    item.setForeground(QColor(cell.color))
                if cell.align_right:
                    item.setTextAlignment(RIGHT)
                if cell.tooltip:
                    item.setToolTip(cell.tooltip)
                if rank_row.is_best:
                    item.setBackground(QColor(BEST_BACKGROUND))
                    font = QFont(item.font())
                    font.setBold(column == 0)
                    item.setFont(font)
                if rank_row.strategy_id is None:
                    item.setForeground(QColor(theme.MUTED) if not cell.color else QColor(cell.color))
                self.table.setItem(row, column, item)
        height = self.table.horizontalHeader().height() + sum(self.table.rowHeight(r) for r in range(len(model.rank_rows)))
        self.table.setFixedHeight(height + 4)

    def _row_clicked(self, row: int, column: int) -> None:
        if self.model and row < len(self.model.rank_rows) and self.model.rank_rows[row].strategy_id:
            self.strategy_chosen.emit(self.model.rank_rows[row].strategy_id)

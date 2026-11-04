"""Strategy Builder: a step-by-step panel for creating, copying and editing strategies.

Steps: 1 Start (new or copy) · 2 Name · 3 BUY rules · 4 SELL rules and exits · 5 Review.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea, QSpinBox, QStackedWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from core.builder import rule_editor
from core.common.formatting import Line
from core.builder.session import DEFAULT_BUY, DEFAULT_SELL, WizardForm
from qtrender.richtext import line_html
from strategy import Condition, Exits, Operand, RuleGroup, Strategy, describe
from strategy import catalog
from strategy.describe import OPERATOR_WORDS
from strategy.model import EVENT_OPERATORS

NUMBER = rule_editor.NUMBER
STATES_VS_EVENTS = ('<b>is above / is below</b> are <i>states</i>: true on every candle where they hold.<br>'
                    '<b>crosses above / below</b> are <i>events</i>: true only on the candle where the cross happens. '
                    'Use <i>within N candles</i> to combine an event with others that happen a little later.')


class OperandPicker(QWidget):
    """Choose an indicator line (and its settings) or, on the right-hand side, a fixed number."""
    changed = Signal()

    def __init__(self, allow_number: bool) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.choice = QComboBox()
        for name, data in rule_editor.operand_choices():
            self.choice.addItem(name, data)
        if allow_number:
            self.choice.addItem('Number', NUMBER)
        layout.addWidget(self.choice)
        self.number = QDoubleSpinBox()
        self.number.setRange(-1e9, 1e9)
        self.number.setDecimals(2)
        layout.addWidget(self.number)
        self.params_row = QHBoxLayout()
        layout.addLayout(self.params_row)
        layout.addStretch()
        self.param_spins: dict[str, QSpinBox] = {}
        self.choice.currentIndexChanged.connect(self._rebuild)
        self._rebuild()

    def _indicator(self) -> catalog.Indicator | None:
        return rule_editor.indicator_of(self.choice.currentData())

    def _rebuild(self) -> None:
        while self.params_row.count():
            self.params_row.takeAt(0).widget().deleteLater()
        self.param_spins = {}
        indicator = self._indicator()
        self.number.setVisible(indicator is None)
        for param in indicator.params if indicator else ():
            spin = QSpinBox()
            spin.setRange(param.minimum, param.maximum)
            spin.setValue(param.default)
            spin.setPrefix(f'{param.label}: ')
            spin.setMinimumWidth(spin.fontMetrics().horizontalAdvance(f'{param.label}: 0000') + 30)
            spin.valueChanged.connect(self.changed)
            self.params_row.addWidget(spin)
            self.param_spins[param.name] = spin
        self.changed.emit()

    def choice_key(self) -> str | None:
        return self.choice.currentData()

    def scale(self) -> str | None:
        return rule_editor.scale_of(self.choice.currentData())

    def operand(self) -> Operand:
        values = {name: spin.value() for name, spin in self.param_spins.items()}
        return rule_editor.build_operand(self.choice.currentData(), self.number.value(), values)

    def set_operand(self, operand: Operand) -> None:
        if operand.is_number:
            self.choice.setCurrentIndex(self.choice.findData(NUMBER))
            self.number.setValue(operand.value)
            return
        indicator = catalog.get(operand.indicator)
        self.choice.setCurrentIndex(self.choice.findData(rule_editor.choice_key(operand)))
        if set(self.param_spins) != {p.name for p in indicator.params}:
            self._rebuild()
        for name, value in rule_editor.setting_values(operand).items():
            self.param_spins[name].setValue(value)


class ConditionRow(QFrame):
    removed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._loading = False
        self.setObjectName('ruleRow')
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 6, 8, 6)
        self.left = OperandPicker(allow_number=False)
        self.op = QComboBox()
        for op, words in OPERATOR_WORDS.items():
            self.op.addItem(words, op)
        self.right = OperandPicker(allow_number=True)
        self.within = QSpinBox()
        self.within.setRange(1, 50)
        self.within.setPrefix('within ')
        self.within.setSuffix(' candles')
        self.within.setToolTip('The cross counts if it happened in the last N candles (1 = this candle only)')
        remove = QPushButton('✕')
        remove.setToolTip('Remove this condition')
        remove.setFixedWidth(28)
        remove.clicked.connect(lambda: self.removed.emit(self))
        # Three lines: [left side ✕] / [operator, within] / [right side], so settings boxes have room.
        grid.addWidget(self.left, 0, 0, 1, 2)
        grid.addWidget(remove, 0, 2)
        grid.addWidget(self.op, 1, 0)
        grid.addWidget(self.within, 1, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(self.right, 2, 0, 1, 2)
        grid.setColumnStretch(1, 1)
        self.op.currentIndexChanged.connect(self._update_within)
        self.left.choice.currentIndexChanged.connect(self._suggest_right)
        self._update_within()

    def _update_within(self) -> None:
        self.within.setVisible(self.op.currentData() in EVENT_OPERATORS)  # only meaningful for crosses

    def _suggest_right(self) -> None:
        if self._loading:
            return  # keep the stored right-hand side
        suggestion = rule_editor.suggest_right(self.left.choice_key(), self.right.choice_key())
        if suggestion:
            self.right.set_operand(suggestion)

    def condition(self) -> Condition:
        within = self.within.value() if self.op.currentData() in EVENT_OPERATORS else 1
        return Condition(self.left.operand(), self.op.currentData(), self.right.operand(), within)

    def set_condition(self, condition: Condition) -> None:
        self._loading = True
        self.left.set_operand(condition.left)
        self.op.setCurrentIndex(self.op.findData(condition.op))
        self.right.set_operand(condition.right)
        self.within.setValue(condition.within)
        self._loading = False


class RuleGroupEditor(QWidget):
    """'Match ALL/ANY of these conditions' plus a list of condition rows."""

    def __init__(self, default: Condition) -> None:
        super().__init__()
        self.default = default
        self.nested: list[RuleGroup] = []  # nested groups from a file are kept as they are (not editable here)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addWidget(QLabel('Match'))
        self.match = QComboBox()
        self.match.addItem('ALL of these (AND)', 'all')
        self.match.addItem('ANY of these (OR)', 'any')
        header.addWidget(self.match)
        header.addStretch()
        layout.addLayout(header)
        self.rows_layout = QVBoxLayout()
        layout.addLayout(self.rows_layout)
        self.nested_note = QLabel()
        self.nested_note.setObjectName('summary')
        layout.addWidget(self.nested_note)
        add = QPushButton('+ Add condition')
        add.clicked.connect(lambda: self.add_row(self.default))
        layout.addWidget(add, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        self.rows: list[ConditionRow] = []

    def add_row(self, condition: Condition | None = None) -> ConditionRow:
        row = ConditionRow()
        if condition:
            row.set_condition(condition)
        row.removed.connect(self._remove_row)
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        return row

    def _remove_row(self, row: ConditionRow) -> None:
        self.rows.remove(row)
        row.deleteLater()

    def group(self) -> RuleGroup:
        return RuleGroup(self.match.currentData(), [row.condition() for row in self.rows] + self.nested)

    def set_group(self, group: RuleGroup) -> None:
        for row in list(self.rows):
            self._remove_row(row)
        self.match.setCurrentIndex(self.match.findData(group.match))
        self.nested = [item for item in group.conditions if isinstance(item, RuleGroup)]
        for item in group.conditions:
            if isinstance(item, Condition):
                self.add_row(item)
        self.nested_note.setText(f'Also keeps {len(self.nested)} nested group(s) from the file (edit the JSON to '
                                 'change them).' if self.nested else '')


class ExitsEditor(QWidget):
    def __init__(self) -> None:
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        self.fields = {}
        for row, (name, text, suffix, default, tip) in enumerate((
                ('stop_loss_pct', 'Stop-loss', ' % below entry', 8, 'Sell if the price falls this far below what you paid'),
                ('atr_stop_multiple', 'ATR stop', ' × ATR below entry', 2,
                 'Sell if the price falls this many ATRs (typical daily moves) below what you paid'),
                ('take_profit_pct', 'Take-profit', ' % above entry', 15, 'Sell once the price rises this far'))):
            check = QCheckBox(text)
            check.setToolTip(tip)
            spin = QDoubleSpinBox()
            spin.setRange(0.1, 500)
            spin.setDecimals(1)
            spin.setValue(default)
            spin.setSuffix(suffix)
            spin.setEnabled(False)
            check.toggled.connect(spin.setEnabled)
            grid.addWidget(check, row, 0)
            grid.addWidget(spin, row, 1)
            self.fields[name] = (check, spin)
        grid.setColumnStretch(2, 1)

    def exits(self) -> Exits:
        return Exits(**{name: spin.value() if check.isChecked() else None
                        for name, (check, spin) in self.fields.items()})

    def set_exits(self, exits: Exits) -> None:
        for name, (check, spin) in self.fields.items():
            value = getattr(exits, name)
            check.setChecked(value is not None)
            if value is not None:
                spin.setValue(value)


class StrategyWizard(QWidget):
    next_requested = Signal()
    back_requested = Signal()
    cancel_requested = Signal()
    closed = Signal()  # the panel should be dismissed

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName('wizard')
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setObjectName('chartTitle')
        layout.addWidget(self.title)
        self.step = QLabel()
        self.step.setObjectName('barLabel')
        layout.addWidget(self.step)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._start_page())
        self.pages.addWidget(self._name_page())
        self.buy = RuleGroupEditor(DEFAULT_BUY)
        self.pages.addWidget(self._rules_page('Buy when…', self.buy))
        self.sell = RuleGroupEditor(DEFAULT_SELL)
        self.exits = ExitsEditor()
        self.pages.addWidget(self._rules_page('Sell when…', self.sell, self.exits))
        self.pages.addWidget(self._review_page())
        layout.addWidget(self.pages, stretch=1)

        self.error = QLabel()
        self.error.setStyleSheet('color: #ef5350')
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        self.cancel_button = QPushButton('Cancel')
        self.back_button = QPushButton('Back')
        self.next_button = QPushButton('Next')
        self.next_button.setDefault(True)
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.back_button.clicked.connect(self.back_requested)
        self.next_button.clicked.connect(self.next_requested)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        layout.addLayout(buttons)

    # --- pages ---

    def _start_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.new_radio = QRadioButton('Create a new strategy')
        self.copy_radio = QRadioButton('Copy an existing strategy (from any stock or the library)')
        self.new_radio.setChecked(True)
        group = QButtonGroup(page)
        group.addButton(self.new_radio)
        group.addButton(self.copy_radio)
        layout.addWidget(self.new_radio)
        layout.addWidget(self.copy_radio)
        self.existing = QTreeWidget()
        self.existing.setHeaderLabel('Existing strategies')
        self.existing.itemSelectionChanged.connect(lambda: self.copy_radio.setChecked(True))
        layout.addWidget(self.existing, stretch=1)
        hint = QLabel('A copy is independent: changing it never changes the original.')
        hint.setObjectName('summary')
        layout.addWidget(hint)
        return page

    def _name_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel('Strategy name'))
        self.name = QLineEdit()
        self.name.setPlaceholderText('e.g. Trend pullback')
        layout.addWidget(self.name)
        self.for_label = QLabel()
        self.for_label.setObjectName('summary')
        layout.addWidget(self.for_label)
        layout.addStretch()
        return page

    def _rules_page(self, heading: str, editor: RuleGroupEditor, extra: QWidget | None = None) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        title = QLabel(f'<b>{heading}</b>')
        layout.addWidget(title)
        help_text = QLabel(STATES_VS_EVENTS)
        help_text.setObjectName('summary')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        layout.addWidget(editor)
        if extra:
            layout.addWidget(QLabel('<b>…or exit at a price level</b> (checked inside every candle)'))
            layout.addWidget(extra)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def _review_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.review = QLabel()
        self.review.setWordWrap(True)
        self.review.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.review)
        note = QLabel('Backtest assumptions: signals are judged at a candle\'s close and trades fill at the next '
                      'candle\'s open, with the capital, commission and slippage shown on the results panel.')
        note.setObjectName('summary')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return page

    # --- WizardView: what the controller (core.builder.controller) asks for ---

    def show_title(self, text: str) -> None:
        self.title.setText(text)

    def choose_new(self) -> None:
        self.new_radio.setChecked(True)

    def fill_existing(self, groups: list[tuple[str, list[Strategy]]]) -> None:
        self.existing.clear()
        for folder_name, strategies in groups:
            folder = QTreeWidgetItem(self.existing, [folder_name])
            folder.setFlags(Qt.ItemFlag.ItemIsEnabled)
            folder.setExpanded(True)
            for strategy in strategies:
                item = QTreeWidgetItem(folder, [strategy.name])
                item.setData(0, Qt.ItemDataRole.UserRole, strategy.id)
                item.setToolTip(0, describe(strategy))

    def load_strategy(self, strategy: Strategy) -> None:
        self.name.setText(strategy.name)
        self.buy.set_group(strategy.buy)
        self.sell.set_group(strategy.sell)
        self.exits.set_exits(strategy.exits)

    def read_form(self) -> WizardForm:
        """Read the widgets; core.builder.session decides what the values mean."""
        chosen = self.existing.selectedItems()
        source_id = chosen[0].data(0, Qt.ItemDataRole.UserRole) if chosen else None
        return WizardForm(self.copy_radio.isChecked(), source_id, self.name.text(), self.buy.group(),
                          self.sell.group(), self.exits.exits())

    def show_step(self, index: int, step_text: str, back_enabled: bool, next_text: str, for_text: str) -> None:
        self.pages.setCurrentIndex(index)
        self.step.setText(step_text)
        self.back_button.setEnabled(back_enabled)
        self.next_button.setText(next_text)
        self.error.clear()
        self.for_label.setText(for_text)

    def show_error(self, text: str) -> None:
        self.error.setText(text)

    def show_review(self, line: Line) -> None:
        self.review.setText(line_html(line))

    def close(self) -> None:
        self.closed.emit()

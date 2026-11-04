"""Strategy Builder: a step-by-step panel for creating, copying and editing strategies.

Steps: 1 Start (new or copy) · 2 Name · 3 BUY rules · 4 SELL rules and exits · 5 Review.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea, QSpinBox, QStackedWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from strategy import Condition, Exits, Operand, RuleGroup, Strategy, describe, repository
from strategy import catalog
from strategy.describe import OPERATOR_WORDS
from strategy.model import EVENT_OPERATORS

NUMBER = 'number'
STEPS = ['Start', 'Name', 'BUY rules', 'SELL rules & exits', 'Review']
STATES_VS_EVENTS = ('<b>is above / is below</b> are <i>states</i>: true on every candle where they hold.<br>'
                    '<b>crosses above / below</b> are <i>events</i>: true only on the candle where the cross happens. '
                    'Use <i>within N candles</i> to combine an event with others that happen a little later.')


def _choices() -> list[tuple[str, str]]:
    """Every line a rule can use, e.g. ('MACD signal', 'macd:signal')."""
    return [(name, f'{indicator.key}:{output}') for indicator in catalog.INDICATORS.values()
            for output, name in indicator.outputs.items()]


class OperandPicker(QWidget):
    """Choose an indicator line (and its settings) or, on the right-hand side, a fixed number."""
    changed = Signal()

    def __init__(self, allow_number: bool) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.choice = QComboBox()
        for name, data in _choices():
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
        data = self.choice.currentData()
        return None if data in (NUMBER, None) else catalog.get(data.split(':')[0])

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

    def scale(self) -> str | None:
        indicator = self._indicator()
        return indicator.scale if indicator else None

    def operand(self) -> Operand:
        indicator = self._indicator()
        if indicator is None:
            return Operand(value=self.number.value())
        output = self.choice.currentData().split(':')[1]
        params = {p.name: self.param_spins[p.name].value() for p in indicator.params
                  if self.param_spins[p.name].value() != p.default}
        return Operand(indicator.key, None if output == indicator.main_output else output, params)

    def set_operand(self, operand: Operand) -> None:
        if operand.is_number:
            self.choice.setCurrentIndex(self.choice.findData(NUMBER))
            self.number.setValue(operand.value)
            return
        indicator = catalog.get(operand.indicator)
        self.choice.setCurrentIndex(self.choice.findData(f'{indicator.key}:{operand.output or indicator.main_output}'))
        if set(self.param_spins) != {p.name for p in indicator.params}:
            self._rebuild()
        for name, value in indicator.settings(operand.params).items():
            self.param_spins[name].setValue(value)


# A sensible right-hand side when the left-hand side changes scale, e.g. Stoch RSI K -> the number 20.
SUGGESTIONS = {
    catalog.PRICE: Operand('sma', params={'days': 200}),
    catalog.OSCILLATOR: Operand(value=20),
    catalog.UNBOUNDED: Operand(value=0),
    catalog.VOLUME: Operand('volume_average'),
    catalog.RATIO: Operand('rel_strength', 'average'),
}


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
        if self.right.scale() != self.left.scale():
            suggestion = SUGGESTIONS.get(self.left.scale())
            if self.left.choice.currentData() == 'macd:macd':
                suggestion = Operand('macd', 'signal')
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
    saved = Signal(object)  # the saved Strategy
    closed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName('wizard')
        self.setMinimumWidth(560)
        self.symbol: str | None = None  # the stock the strategy is for
        self.original: Strategy | None = None  # the strategy being edited (None when creating)
        self.draft: Strategy | None = None
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
        self.buy = RuleGroupEditor(Condition(Operand('close'), 'above', Operand('sma', params={'days': 200})))
        self.pages.addWidget(self._rules_page('Buy when…', self.buy))
        self.sell = RuleGroupEditor(Condition(Operand('close'), 'below', Operand('sma', params={'days': 200})))
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
        self.cancel_button.clicked.connect(self.closed)
        self.back_button.clicked.connect(lambda: self._go(self.pages.currentIndex() - 1))
        self.next_button.clicked.connect(self._next)
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

    # --- starting ---

    def start_new(self, symbol: str) -> None:
        self.symbol, self.original, self.draft = symbol, None, None
        self.title.setText(f'New strategy for {symbol}')
        self.new_radio.setChecked(True)
        self._fill_existing()
        self._go(0)

    def start_edit(self, strategy: Strategy, context_symbol: str | None = None) -> None:
        self.symbol = strategy.symbol or context_symbol
        self.original = self.draft = strategy
        self.title.setText(f'Edit "{strategy.name}"' + (' (library template)' if strategy.symbol is None else ''))
        self._load(strategy)
        self._go(1)

    def _fill_existing(self) -> None:
        self.existing.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        for strategy in sorted(repository.all_strategies(), key=lambda s: (s.symbol or '', s.name.lower())):
            folder_name = strategy.symbol or 'Library'
            if folder_name not in groups:
                groups[folder_name] = QTreeWidgetItem(self.existing, [folder_name])
                groups[folder_name].setFlags(Qt.ItemFlag.ItemIsEnabled)
                groups[folder_name].setExpanded(True)
            item = QTreeWidgetItem(groups[folder_name], [strategy.name])
            item.setData(0, Qt.ItemDataRole.UserRole, strategy.id)
            item.setToolTip(0, describe(strategy))

    def _load(self, strategy: Strategy) -> None:
        self.name.setText(strategy.name)
        self.buy.set_group(strategy.buy)
        self.sell.set_group(strategy.sell)
        self.exits.set_exits(strategy.exits)

    def _blank(self) -> Strategy:
        return Strategy('', RuleGroup('all', [self.buy.default]), RuleGroup('any', [self.sell.default]),
                        Exits(stop_loss_pct=8), symbol=self.symbol)

    # --- navigation ---

    def _go(self, index: int) -> None:
        first = 1 if self.original else 0
        index = max(first, min(index, len(STEPS) - 1))
        self.pages.setCurrentIndex(index)
        self.step.setText(f'Step {index + 1 - first} of {len(STEPS) - first}: {STEPS[index]}')
        self.back_button.setEnabled(index > first)
        self.next_button.setText('Save && Backtest' if index == len(STEPS) - 1 else 'Next')
        self.error.clear()
        self.for_label.setText('A reusable library template (not tied to one stock).' if self.original and
                               self.original.symbol is None else f'For {self.symbol}.')
        if index == len(STEPS) - 1:
            self.review.setText(f'<b>{self.name.text()}</b> — {self.symbol if not self.original or self.original.symbol else "library"}<br><br>'
                                + describe(self._build()).replace('\n', '<br>'))

    def _next(self) -> None:
        index = self.pages.currentIndex()
        problem = self._check(index)
        if problem:
            self.error.setText(problem)
            return
        if index == 0:
            chosen = self.existing.selectedItems()
            source = repository.get(chosen[0].data(0, Qt.ItemDataRole.UserRole)) if self.copy_radio.isChecked() \
                else None
            self.draft = source.copy_for(self.symbol) if source else self._blank()
            self._load(self.draft)
        if index == len(STEPS) - 1:
            strategy = self._build()
            repository.save(strategy)
            self.saved.emit(strategy)
            return
        self._go(index + 1)

    def _check(self, index: int) -> str | None:
        if index == 0 and self.copy_radio.isChecked() and not self.existing.selectedItems():
            return 'Choose the strategy to copy, or pick "Create a new strategy".'
        if index == 1 and not self.name.text().strip():
            return 'Give the strategy a name.'
        if index == 2 and not self.buy.rows and not self.buy.nested:
            return 'Add at least one BUY condition.'
        if index == 3 and not self.sell.rows and not self.sell.nested and self.exits.exits() == Exits():
            return 'Add a SELL condition or an exit (stop-loss, ATR stop or take-profit), or trades never close.'
        return None

    def _build(self) -> Strategy:
        strategy = self.draft or self._blank()
        strategy.name = self.name.text().strip()
        strategy.buy, strategy.sell, strategy.exits = self.buy.group(), self.sell.group(), self.exits.exits()
        return strategy

"""Strategy definitions: plain data, independent of the GUI and of any stock's prices.

A strategy is a set of BUY rules, SELL rules, exits (stop-loss/take-profit) and trading costs.
It is saved as JSON; `symbol` is None for a reusable library template.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime

# States hold on every candle where the comparison is true; events only on the candle where it happens.
STATE_OPERATORS = ('above', 'below')
EVENT_OPERATORS = ('crosses_above', 'crosses_below')
OPERATORS = STATE_OPERATORS + EVENT_OPERATORS
MATCHES = ('all', 'any')


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now().isoformat(timespec='seconds')


@dataclass
class Operand:
    """One side of a condition: an indicator line (e.g. SMA 200 days) or a fixed number."""
    indicator: str | None = None  # catalog key, e.g. 'sma'
    output: str | None = None  # which line, e.g. 'signal' for MACD; None = the indicator's main line
    params: dict = field(default_factory=dict)  # only values that differ from the catalog defaults
    value: float | None = None  # a fixed number instead of an indicator

    @property
    def is_number(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict:
        if self.is_number:
            return {'value': self.value}
        data = {'indicator': self.indicator}
        if self.output:
            data['output'] = self.output
        if self.params:
            data['params'] = dict(self.params)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Operand:
        if 'value' in data:
            return cls(value=float(data['value']))
        return cls(indicator=data['indicator'], output=data.get('output'), params=dict(data.get('params', {})))


@dataclass
class Condition:
    left: Operand
    op: str
    right: Operand
    within: int = 1  # events only: the event happened in the last `within` candles

    def __post_init__(self) -> None:
        if self.op not in OPERATORS:
            raise ValueError(f'Unknown operator {self.op!r}; expected one of {OPERATORS}')
        if self.left.is_number:
            raise ValueError('The left side of a condition must be an indicator, not a number')
        if self.within < 1:
            raise ValueError('within must be at least 1 candle')

    @property
    def is_event(self) -> bool:
        return self.op in EVENT_OPERATORS

    def to_dict(self) -> dict:
        data = {'left': self.left.to_dict(), 'op': self.op, 'right': self.right.to_dict()}
        if self.is_event and self.within > 1:
            data['within'] = self.within
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Condition:
        return cls(Operand.from_dict(data['left']), data['op'], Operand.from_dict(data['right']),
                   int(data.get('within', 1)))


@dataclass
class RuleGroup:
    """Conditions combined with ALL (AND) or ANY (OR). Groups can be nested."""
    match: str = 'all'
    conditions: list[Condition | RuleGroup] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.match not in MATCHES:
            raise ValueError(f'match must be one of {MATCHES}, not {self.match!r}')

    def to_dict(self) -> dict:
        return {'match': self.match, 'conditions': [item.to_dict() for item in self.conditions]}

    @classmethod
    def from_dict(cls, data: dict) -> RuleGroup:
        items = [RuleGroup.from_dict(item) if 'match' in item else Condition.from_dict(item)
                 for item in data.get('conditions', [])]
        return cls(data.get('match', 'all'), items)


@dataclass
class Exits:
    """Exits measured from the entry price, checked within every candle while a trade is open."""
    stop_loss_pct: float | None = None  # sell if price falls this % below entry
    take_profit_pct: float | None = None  # sell if price rises this % above entry
    atr_stop_multiple: float | None = None  # sell if price falls this many ATRs (at entry) below entry

    def to_dict(self) -> dict:
        return {'stop_loss_pct': self.stop_loss_pct, 'take_profit_pct': self.take_profit_pct,
                'atr_stop_multiple': self.atr_stop_multiple}

    @classmethod
    def from_dict(cls, data: dict) -> Exits:
        return cls(data.get('stop_loss_pct'), data.get('take_profit_pct'), data.get('atr_stop_multiple'))


@dataclass
class Costs:
    capital: float = 10_000.0  # starting cash
    commission: float = 0.0  # dollars per trade (each buy or sell)
    slippage_pct: float = 0.05  # fill price this % worse than the open, each side

    def to_dict(self) -> dict:
        return {'capital': self.capital, 'commission': self.commission, 'slippage_pct': self.slippage_pct}

    @classmethod
    def from_dict(cls, data: dict) -> Costs:
        defaults = cls()
        return cls(float(data.get('capital', defaults.capital)), float(data.get('commission', defaults.commission)),
                   float(data.get('slippage_pct', defaults.slippage_pct)))


@dataclass
class About:
    """What a strategy is for, why it can work, and where it comes from: shown in the Strategy Library so the user
    can judge how much to trust it. Every field is optional (a user's own strategy may only have a summary)."""
    summary: str = ''  # one or two sentences: the idea in plain words
    style: str = ''  # e.g. 'Trend following · weeks to months'
    why: str = ''  # the reasoning and evidence behind it
    caveats: str = ''  # when it fails, what it leaves out
    references: list[str] = field(default_factory=list)  # books and papers, in citation form

    @property
    def is_empty(self) -> bool:
        return not (self.summary or self.style or self.why or self.caveats or self.references)

    def to_dict(self) -> dict:
        return {'summary': self.summary, 'style': self.style, 'why': self.why, 'caveats': self.caveats,
                'references': list(self.references)}

    @classmethod
    def from_dict(cls, data: dict) -> About:
        return cls(data.get('summary', ''), data.get('style', ''), data.get('why', ''), data.get('caveats', ''),
                   list(data.get('references', [])))


@dataclass
class Strategy:
    name: str
    buy: RuleGroup
    sell: RuleGroup
    exits: Exits = field(default_factory=Exits)
    costs: Costs = field(default_factory=Costs)
    symbol: str | None = None  # None = a reusable library template
    origin_id: str | None = None  # the strategy this one was copied from
    id: str = field(default_factory=new_id)
    created: str = field(default_factory=now)
    updated: str = field(default_factory=now)
    about: About = field(default_factory=About)  # description, reasoning and sources

    def to_dict(self) -> dict:
        data = {'id': self.id, 'name': self.name, 'symbol': self.symbol, 'origin_id': self.origin_id,
                'buy': self.buy.to_dict(), 'sell': self.sell.to_dict(), 'exits': self.exits.to_dict(),
                'costs': self.costs.to_dict(), 'created': self.created, 'updated': self.updated}
        if not self.about.is_empty:
            data['about'] = self.about.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Strategy:
        return cls(name=data['name'], buy=RuleGroup.from_dict(data['buy']), sell=RuleGroup.from_dict(data['sell']),
                   exits=Exits.from_dict(data.get('exits', {})), costs=Costs.from_dict(data.get('costs', {})),
                   symbol=data.get('symbol'), origin_id=data.get('origin_id'), id=data.get('id') or new_id(),
                   created=data.get('created') or now(), updated=data.get('updated') or now(),
                   about=About.from_dict(data.get('about', {})))

    def copy_for(self, symbol: str | None, name: str | None = None) -> Strategy:
        """An independent copy for another stock (or the library), remembering where it came from."""
        twin = copy.deepcopy(self)
        twin.id, twin.symbol, twin.origin_id = new_id(), symbol, self.id
        twin.name = name or self.name
        twin.created = twin.updated = now()
        return twin

"""A portfolio: a named, ordered set of stock symbols."""
from dataclasses import dataclass, field

from strategy.model import new_id, now

FORMAT_VERSION = 1  # stored in every file, so portfolio-level strategies can be added later without a migration


def normalize_symbol(text: str) -> str:
    return text.strip().upper()


def _unique_symbols(symbols) -> list[str]:
    """Normalised, without blanks or repeats, in the order given."""
    seen, result = set(), []
    for symbol in symbols:
        symbol = normalize_symbol(symbol)
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


@dataclass
class Portfolio:
    name: str
    symbols: list[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    created: str = field(default_factory=now)
    updated: str = field(default_factory=now)

    def __post_init__(self) -> None:
        self.symbols = _unique_symbols(self.symbols)

    def has(self, symbol: str) -> bool:
        return normalize_symbol(symbol) in self.symbols

    def to_dict(self) -> dict:
        return {'version': FORMAT_VERSION, 'id': self.id, 'name': self.name, 'symbols': list(self.symbols),
                'created': self.created, 'updated': self.updated}

    @classmethod
    def from_dict(cls, data: dict) -> 'Portfolio':
        """Raises KeyError / TypeError / ValueError for a file that is not a portfolio."""
        name = data['name']
        if not isinstance(name, str) or not name.strip():
            raise ValueError('portfolio has no name')
        symbols = data.get('symbols', [])
        if not isinstance(symbols, list) or not all(isinstance(symbol, str) for symbol in symbols):
            raise TypeError('symbols must be a list of text')
        return cls(name=name.strip(), symbols=symbols, id=data['id'], created=data.get('created', now()),
                   updated=data.get('updated', now()))

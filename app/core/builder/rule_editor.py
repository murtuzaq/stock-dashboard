"""The rules behind the Strategy Builder's condition rows: what can be picked, and how a pick becomes an Operand.

A "choice key" names one thing a rule side can be: an indicator line like 'macd:signal', or NUMBER for a fixed
value. The widgets list the choices and read the user's picks; everything about their meaning is here.
"""
from strategy import Operand, catalog

NUMBER = 'number'

# A sensible right-hand side when the left-hand side changes scale, e.g. Stoch RSI K -> the number 20.
SUGGESTIONS = {
    catalog.PRICE: Operand('sma', params={'days': 200}),
    catalog.OSCILLATOR: Operand(value=20),
    catalog.UNBOUNDED: Operand(value=0),
    catalog.VOLUME: Operand('volume_average'),
    catalog.RATIO: Operand('rel_strength', 'average'),
}


def operand_choices() -> list[tuple[str, str]]:
    """Every line a rule can use, as (label, choice key), e.g. ('MACD signal', 'macd:signal')."""
    return [(name, f'{indicator.key}:{output}') for indicator in catalog.INDICATORS.values()
            for output, name in indicator.outputs.items()]


def indicator_of(choice: str | None) -> catalog.Indicator | None:
    """The indicator a choice key refers to (None for a number or no choice)."""
    if choice in (NUMBER, None):
        return None
    return catalog.get(choice.split(':')[0])


def scale_of(choice: str | None) -> str | None:
    indicator = indicator_of(choice)
    if indicator is None:
        return None
    return indicator.scale


def choice_key(operand: Operand) -> str:
    if operand.is_number:
        return NUMBER
    indicator = catalog.get(operand.indicator)
    return f'{indicator.key}:{operand.output or indicator.main_output}'


def setting_values(operand: Operand) -> dict[str, int]:
    """The indicator's settings for this operand, defaults filled in (what the setting boxes should show)."""
    return catalog.get(operand.indicator).settings(operand.params)


def build_operand(choice: str, number: float, setting_boxes: dict[str, int]) -> Operand:
    """The Operand for a picked choice; settings left at their default are not stored."""
    indicator = indicator_of(choice)
    if indicator is None:
        return Operand(value=number)
    output = choice.split(':')[1]
    params = {p.name: setting_boxes[p.name] for p in indicator.params if setting_boxes[p.name] != p.default}
    return Operand(indicator.key, None if output == indicator.main_output else output, params)


def suggest_right(left_choice: str, right_choice: str) -> Operand | None:
    """After the left side changes: a new right side if the old one is on a different scale, else None."""
    left_scale = scale_of(left_choice)
    if scale_of(right_choice) == left_scale:
        return None
    if left_choice == 'macd:macd':
        return Operand('macd', 'signal')
    return SUGGESTIONS.get(left_scale)

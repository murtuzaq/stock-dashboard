"""Strategies in plain English, e.g. 'BUY when Close is above SMA 200d AND MACD line crosses above Signal line'."""
from . import catalog
from .model import Condition, Operand, RuleGroup, Strategy

OPERATOR_WORDS = {'above': 'is above', 'below': 'is below',
                  'crosses_above': 'crosses above', 'crosses_below': 'crosses below'}


def describe_operand(operand: Operand) -> str:
    if operand.is_number:
        return f'{operand.value:g}'
    indicator = catalog.get(operand.indicator)
    output = operand.output or indicator.main_output
    settings = indicator.settings(operand.params)
    name = indicator.outputs[output]
    if 'days' in settings:  # SMA and the relative-strength average are named by their length
        return f'{name} {settings["days"]}d' if output != 'value' or indicator.key == 'sma' else name
    changed = [str(settings[p.name]) for p in indicator.params if settings[p.name] != p.default]
    return f'{name} ({", ".join(changed)})' if changed else name


def describe_condition(condition: Condition) -> str:
    text = f'{describe_operand(condition.left)} {OPERATOR_WORDS[condition.op]} {describe_operand(condition.right)}'
    if condition.is_event and condition.within > 1:
        text += f' (within the last {condition.within} candles)'
    return text


def describe_group(group: RuleGroup) -> str:
    if not group.conditions:
        return 'never (no conditions)'
    joiner = ' AND ' if group.match == 'all' else ' OR '
    parts = [f'({describe_group(item)})' if isinstance(item, RuleGroup) else describe_condition(item)
             for item in group.conditions]
    return joiner.join(parts)


def describe(strategy: Strategy) -> str:
    lines = [f'BUY when {describe_group(strategy.buy)}', f'SELL when {describe_group(strategy.sell)}']
    exits = strategy.exits
    if exits.stop_loss_pct:
        lines.append(f'  or price falls {exits.stop_loss_pct:g}% below the entry price (stop-loss)')
    if exits.atr_stop_multiple:
        lines.append(f'  or price falls {exits.atr_stop_multiple:g} × ATR below the entry price (ATR stop)')
    if exits.take_profit_pct:
        lines.append(f'  or price rises {exits.take_profit_pct:g}% above the entry price (take-profit)')
    return '\n'.join(lines)

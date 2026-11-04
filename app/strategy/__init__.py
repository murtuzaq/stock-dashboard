"""Strategy engine: definitions, indicator catalogue, signal evaluation. No GUI code lives here."""
from .describe import describe
from .model import Condition, Costs, Exits, Operand, RuleGroup, Strategy
from .signals import evaluate

__all__ = ['Condition', 'Costs', 'Exits', 'Operand', 'RuleGroup', 'Strategy', 'describe', 'evaluate']

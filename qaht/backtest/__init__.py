"""Backtesting and validation modules"""

from .simulator import simulate, Trade
from .metrics import (
    calculate_performance,
    calculate_monthly_returns,
    calculate_score_bucket_performance
)
from .labeler import (
    label_explosions,
    label_explosions_triple_barrier,
    get_explosion_stats
)

__all__ = [
    'simulate',
    'Trade',
    'calculate_performance',
    'calculate_monthly_returns',
    'calculate_score_bucket_performance',
    'label_explosions',
    'label_explosions_triple_barrier',
    'get_explosion_stats'
]

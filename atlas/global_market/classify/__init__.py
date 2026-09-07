"""Classification for US-listed ETFs — deterministic rules first, model last (plan L0…L3).

Two pure first-match rule tables over the instrument name, both grounded in the 5,655 real
names in the committed directories: ``leverage_flags`` for the structure flags the universe
filter needs, and ``classify_strategy`` for the primary taxonomy axis. Exposures, sector /
geo / theme and the LLM pass land next, when holdings and ``etf_meta`` exist to classify from
-- and the ~22% of names these rules decline to settle are exactly that layer's input.
"""

from .rules import CLEAN, LeverageFlags, leverage_flags
from .strategy import STRATEGIES, StrategyMatch, classify_strategy

__all__ = [
    "CLEAN",
    "STRATEGIES",
    "LeverageFlags",
    "StrategyMatch",
    "classify_strategy",
    "leverage_flags",
]

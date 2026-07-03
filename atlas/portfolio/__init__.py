"""Portfolio bounded context — pure strategy + accounting math (no I/O).

DB panels in, trades/NAV frames out; scripts/foundation/portfolio_run.py owns
all reads/writes, mirroring the technicals.py / compute_all.py split.
"""

from .engine import PortfolioConfig, replay
from .strategies import STRATEGIES, get_strategy

__all__ = ["STRATEGIES", "PortfolioConfig", "get_strategy", "replay"]

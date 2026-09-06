"""Classification for US-listed ETFs — deterministic rules first, model last (plan L0…L3).

Phase 1 ships only the structure flags the universe filter needs: ``leverage_flags``, a pure
first-match rule table over the instrument name. Exposures, sector/geo/theme and the LLM pass
land in Phase 2, when holdings and ``etf_meta`` exist to classify from.
"""

from .rules import CLEAN, LeverageFlags, leverage_flags

__all__ = ["CLEAN", "LeverageFlags", "leverage_flags"]

"""Cohort key derivation for dwell baselines.

Two orthogonal cohort axes:
  - market_cap: large_cap / mid_cap / small_cap (from Nifty index membership)
  - sector: per-sector key (lowercased + underscored)

The state engine uses these keys to look up per-cohort dwell baselines
from atlas_state_dwell_statistics (table created in migration 073).
"""

from __future__ import annotations


def cohort_for_stock(in_nifty_100: bool, in_nifty_500: bool, sector: str) -> str:
    """Map index-membership flags to market-cap cohort.

    Args:
        in_nifty_100: True if stock is in the Nifty 100 (large-cap).
        in_nifty_500: True if stock is in the Nifty 500 (any cap).
        sector: Sector name (unused for market-cap cohort; reserved for future
            cap-by-sector segmentation).

    Returns:
        'large_cap' | 'mid_cap' | 'small_cap'
    """
    if in_nifty_100:
        return "large_cap"
    if in_nifty_500:
        return "mid_cap"
    return "small_cap"


def sector_cohort_key(sector_name: str | None) -> str:
    """Normalize a sector name to a cohort key.

    Lowercased, with spaces and dashes replaced by underscores. Empty/None
    returns 'sector_unknown'.

    Examples:
        'Information Technology' -> 'sector_information_technology'
        'Consumer Goods - Durable' -> 'sector_consumer_goods___durable'
    """
    if not sector_name:
        return "sector_unknown"
    normalized = sector_name.lower().replace(" ", "_").replace("-", "_")
    return f"sector_{normalized}"

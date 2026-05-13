"""Universe configurations for Atlas multi-universe compute.

Each UniverseConfig describes one investable universe (India, US, Global).
Pass the appropriate config singleton into compute functions; they read all
universe-specific values from it — schema name, benchmark references, RS mode.

No compute code hardcodes 'atlas', 'NIFTY 500', or 'INDIA VIX' directly;
those strings live only in IN_CONFIG below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

_VALID_SCHEMAS = frozenset({"atlas", "us_atlas", "global_atlas"})


@dataclass(frozen=True)
class UniverseConfig:
    """Immutable descriptor for one Atlas investment universe.

    Passed as a parameter to every compute function. This is the single
    place where universe-specific constants live; compute functions are
    pure functions of (data, config).
    """

    schema: str
    """Postgres schema name. One of 'atlas', 'us_atlas', 'global_atlas'."""

    benchmark_index_code: str
    """Broad-market index code for regime computation.
    Matches benchmark_code in {schema}.atlas_benchmark_master.
    India='NIFTY 500', US='^SPX', Global='VT'."""

    vix_code: str | None
    """Volatility index code for regime VIX state.
    India='INDIA VIX', US='^VIX', Global=None (uses realized vol)."""

    primary_etf_benchmark: str
    """Primary benchmark code for single-benchmark ETF RS computation.
    India='NIFTY500', US='SPY', Global='VT'."""

    rs_benchmarks: tuple[str, ...]
    """Ordered tuple of benchmark codes for the 4-benchmark RS model.
    India=() — uses tier benchmarks, not the 4-benchmark model.
    US/Global=('ACWI', 'VT', 'EEM', 'GOLD')."""

    sector_taxonomy: Literal["IN_BSE", "US_GICS", "NONE"]
    """Sector classification system in use.
    NONE = no sector structure (Global Atlas — country ETFs only)."""

    rs_label_mode: Literal["percentile", "quintile", "rank"]
    """How RS scores are labelled in the UI layer.
    percentile = India/US (large universe).
    quintile   = Global (30 instruments; Q1–Q5)."""

    compute_layers: frozenset[str]
    """Compute modules active for this universe.
    Valid tokens: 'stocks', 'etfs', 'sectors', 'regime', 'breadth',
                  'funds', 'decisions'."""

    universe_membership_filter: str | None
    """SQL boolean fragment added to the regime breadth WHERE clause.
    India='in_nifty_500 = TRUE', US='in_sp500 = TRUE', Global=None."""

    historical_start_date: str
    """Earliest date for historical backfill (YYYY-MM-DD).
    Bounded by the inception of the earliest 4-benchmark ETF in rs_benchmarks."""

    def __post_init__(self) -> None:
        if self.schema not in _VALID_SCHEMAS:
            raise ValueError(f"schema must be one of {_VALID_SCHEMAS}, got {self.schema!r}")

    def qualified(self, table: str) -> str:
        """Return schema-qualified table name safe for use in SQL strings.

        Only call this with literal table name strings — never with user input.
        The schema is validated against _VALID_SCHEMAS at construction time.
        """
        return f"{self.schema}.{table}"


# ---------------------------------------------------------------------------
# Singleton configs
# ---------------------------------------------------------------------------

IN_CONFIG = UniverseConfig(
    schema="atlas",
    benchmark_index_code="NIFTY 500",
    vix_code="INDIA VIX",
    primary_etf_benchmark="NIFTY500",
    rs_benchmarks=(),  # India uses tier-based RS; 4-benchmark model not applied
    sector_taxonomy="IN_BSE",
    rs_label_mode="percentile",
    compute_layers=frozenset(
        {
            "stocks",
            "etfs",
            "sectors",
            "regime",
            "breadth",
            "funds",
            "decisions",
        }
    ),
    universe_membership_filter="in_nifty_500 = TRUE",
    historical_start_date="2016-04-07",  # bounded by JIP de_index_prices history
)

US_CONFIG = UniverseConfig(
    schema="us_atlas",
    benchmark_index_code="^SPX",
    vix_code="^VIX",
    primary_etf_benchmark="SPY",
    rs_benchmarks=("ACWI", "VT", "EEM", "GOLD"),
    sector_taxonomy="US_GICS",
    rs_label_mode="percentile",
    compute_layers=frozenset(
        {
            "stocks",
            "etfs",
            "regime",
            "breadth",
        }
    ),
    universe_membership_filter="in_sp500 = TRUE",
    historical_start_date="2008-03-28",  # ACWI inception — earliest 4-benchmark data
)

GLOB_CONFIG = UniverseConfig(
    schema="global_atlas",
    benchmark_index_code="VT",
    vix_code=None,  # no VIX for Global; regime uses VT realized vol
    primary_etf_benchmark="VT",
    rs_benchmarks=("ACWI", "VT", "EEM", "GOLD"),
    sector_taxonomy="NONE",
    rs_label_mode="quintile",
    compute_layers=frozenset(
        {
            "etfs",
            "regime",
        }
    ),
    universe_membership_filter=None,  # all 30 country ETFs are always in universe
    historical_start_date="2008-06-26",  # VT inception
)

UNIVERSE_CONFIGS: dict[str, UniverseConfig] = {
    "in": IN_CONFIG,
    "us": US_CONFIG,
    "global": GLOB_CONFIG,
}

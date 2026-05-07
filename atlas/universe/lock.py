"""Atlas universe lock orchestrator (M1 entry point logic).

Runs the seven universe-population steps in their dependency order:

1. ``atlas_sector_master`` — sectors from ``de_instrument.sector``.
2. ``atlas_benchmark_master`` — 9 benchmarks (must precede funds; FK).
3. ``atlas_fund_category_benchmark_map`` — category → benchmark.
4. ``atlas_universe_stocks`` — 750 stocks with tier classification.
5. ``atlas_universe_etfs`` — 100 ETFs with theme classification.
6. ``atlas_universe_indices`` — 75 curated indices.
7. ``atlas_universe_funds`` — ~450-500 equity Regular/Growth schemes.
8. ``atlas_thresholds`` (+ history) — 35 v0 thresholds.

After this runs successfully, M1 Phase C is complete. Phase D (validation)
is invoked separately via ``atlas.validation``.
"""

from __future__ import annotations

import structlog
from sqlalchemy.engine import Engine

from atlas.config import Config
from atlas.db import get_engine
from atlas.universe import (
    benchmarks,
    etfs,
    funds,
    indices,
    sectors,
    stocks,
    thresholds,
)

log = structlog.get_logger()


def lock_universe(engine: Engine | None = None) -> dict[str, int]:
    """Run all M1 Phase C population steps.

    Returns a dict mapping table name → row count for the run summary.
    Idempotent — re-running upserts.
    """
    eng = engine or get_engine()

    log.info(
        "universe_lock_starting",
        lock_date=Config.UNIVERSE_LOCK_DATE,
        historical_start=Config.HISTORICAL_START_DATE,
    )
    counts: dict[str, int] = {}

    # 1. Sectors must be first — referenced by FK from ETFs and indices
    counts["atlas_sector_master"] = sectors.populate_sector_master(eng)

    # 2-3. Benchmarks must precede funds (FK)
    counts["atlas_benchmark_master"] = benchmarks.populate_benchmark_master(eng)
    counts["atlas_fund_category_benchmark_map"] = benchmarks.populate_fund_category_benchmark_map(
        eng
    )

    # 4-7. Universe tables — order between stocks/ETFs/indices/funds is
    # interchangeable, but stocks must precede sector validation.
    counts["atlas_universe_stocks"] = stocks.populate_universe_stocks(eng)
    counts["atlas_universe_etfs"] = etfs.populate_universe_etfs(eng)
    counts["atlas_universe_indices"] = indices.populate_universe_indices(eng)
    counts["atlas_universe_funds"] = funds.populate_universe_funds(eng)

    # 8. Threshold catalog seed
    counts["atlas_thresholds"] = thresholds.populate_thresholds(eng)

    log.info("universe_lock_complete", counts=counts)
    return counts

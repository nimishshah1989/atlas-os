"""Atlas stock universe builder.

Per methodology Section 3.1: 750 stocks across four mutually-exclusive tiers,
all sourced from JIP's NSE index-constituent membership tables:

| Tier  | JIP index_code        | Members |
|-------|-----------------------|---------|
| Large | ``NIFTY 100``         | 100     |
| Mid   | ``NIFTY MIDCAP 150``  | 150     |
| Small | ``NIFTY SMLCAP 250``  | 250     |
| Micro | ``NIFTY MICROCAP250`` | 250     |

Total = 750 ✓.

This is cleaner than the original methodology fallback ("next 250 by 60-day
median traded value") because NSE publishes a Microcap 250 index and JIP
ingests its constituents. We use the canonical NSE classification.

Note on ``de_instrument`` schema (verified 2026-05-06 against Supabase):
- Has ``nifty_50``, ``nifty_200``, ``nifty_500`` boolean flags but **NOT
  ``nifty_100``** — that's why we go via ``de_index_constituents``.
- Identifier column is ``id`` (UUID).
- Symbol column is ``symbol`` (also has ``current_symbol``; we use ``symbol``).
- Sector / industry come from ``sector`` and ``industry`` text columns.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.config import Config
from atlas.db import get_engine

log = structlog.get_logger()


# Tier → JIP index_code (verified against de_index_constituents)
_TIER_INDEX_CODES: dict[str, str] = {
    "Large": "NIFTY 100",
    "Mid": "NIFTY MIDCAP 150",
    "Small": "NIFTY SMLCAP 250",
    "Micro": "NIFTY MICROCAP250",
}

# Expected member counts per tier (assertion safety net)
_TIER_EXPECTED_COUNTS: dict[str, int] = {
    "Large": 100,
    "Mid": 150,
    "Small": 250,
    "Micro": 250,
}


_LOAD_TIER_QUERY = """
    SELECT
        i.id::text                AS instrument_id,
        i.symbol,
        i.company_name,
        i.sector,
        i.industry,
        i.nifty_50,
        i.nifty_500,
        i.listing_date
    FROM public.de_instrument i
    JOIN public.de_index_constituents ic
        ON ic.instrument_id = i.id
       AND ic.index_code = :index_code
       AND (ic.effective_to IS NULL OR ic.effective_to > CURRENT_DATE)
    WHERE i.is_active = TRUE
      AND i.sector IS NOT NULL
"""


def _classify_tier(
    instrument_id: str,
    in_nifty_100: bool,
    in_nifty_500: bool,
    midcap_ids: set[str],
    smallcap_ids: set[str],
) -> str:
    """Pure-Python tier classifier — no DB required (testable in unit tests).

    Priority: Large > Mid > Small > Micro. A Nifty 500 stock that is not in
    Nifty 100, Midcap 150, or Smallcap 250 falls to Small (the default
    Nifty 500 bucket used for unlabelled constituents).
    """
    if in_nifty_100:
        return "Large"
    if instrument_id in midcap_ids:
        return "Mid"
    if instrument_id in smallcap_ids:
        return "Small"
    if in_nifty_500:
        return "Small"  # fallback for Nifty 500 non-categorised stocks
    return "Micro"


def _load_tier(engine: Engine, tier: str) -> list[dict[str, object]]:
    """Load all stocks for a tier via de_index_constituents membership."""
    expected = _TIER_EXPECTED_COUNTS[tier]
    index_code = _TIER_INDEX_CODES[tier]

    with engine.connect() as conn:
        rows = conn.execute(text(_LOAD_TIER_QUERY), {"index_code": index_code}).mappings().all()

    out: list[dict[str, object]] = []
    for r in rows:
        out.append(
            {
                "instrument_id": r["instrument_id"],
                "symbol": r["symbol"],
                "company_name": r["company_name"],
                "tier": tier,
                "sector": r["sector"],
                "industry": r["industry"],
                "in_nifty_50": bool(r["nifty_50"]),
                # Methodology distinguishes Nifty 100 membership; we know it's TRUE
                # for Large tier (by definition) and FALSE otherwise.
                "in_nifty_100": tier == "Large",
                "in_nifty_500": bool(r["nifty_500"]),
                "listing_date": r["listing_date"],
            }
        )

    if abs(len(out) - expected) > 5:
        # Allow small drift (e.g. recent constituent changes), fail loud on big drift
        raise AssertionError(
            f"{tier} tier ({index_code}) returned {len(out)} stocks, "
            f"expected ~{expected}. Check de_index_constituents freshness."
        )

    log.info("tier_loaded", tier=tier, index_code=index_code, count=len(out))
    return out


def build_stock_universe(engine: Engine | None = None) -> list[dict[str, object]]:
    """Return 750 stock universe rows ready for insert.

    Asserts the total is exactly 750 (allow ±20 drift for active-constituent
    timing). Per-tier expected: 100 + 150 + 250 + 250.
    """
    eng = engine or get_engine()

    rows: list[dict[str, object]] = []
    for tier in ("Large", "Mid", "Small", "Micro"):
        rows.extend(_load_tier(eng, tier))

    # Deduplicate by instrument_id — a stock should appear in only one tier.
    # If a name is in NIFTY 100 AND NIFTY MIDCAP 150 (transition periods),
    # take the higher tier (Large > Mid > Small > Micro).
    tier_priority = {"Large": 0, "Mid": 1, "Small": 2, "Micro": 3}
    by_id: dict[str, dict[str, object]] = {}
    for r in rows:
        iid = str(r["instrument_id"])
        if (
            iid not in by_id
            or tier_priority[str(r["tier"])] < tier_priority[str(by_id[iid]["tier"])]
        ):
            by_id[iid] = r
    deduped = list(by_id.values())

    if abs(len(deduped) - 750) > 20:
        tier_counts: dict[str, int] = {}
        for r in deduped:
            t = str(r["tier"])
            tier_counts[t] = tier_counts.get(t, 0) + 1
        raise AssertionError(
            f"Stock universe size = {len(deduped)} (target 750 ± 20). "
            f"Tier breakdown: {tier_counts}. "
            "Likely cause: tier index members have shifted; reconcile."
        )

    final_counts: dict[str, int] = {}
    for r in deduped:
        t = str(r["tier"])
        final_counts[t] = final_counts.get(t, 0) + 1
    log.info("stock_universe_built", total=len(deduped), tiers=final_counts)
    return deduped


def populate_universe_stocks(engine: Engine | None = None) -> int:
    """Insert the locked stock universe into ``atlas_universe_stocks``."""
    eng = engine or get_engine()
    rows = build_stock_universe(eng)

    insert_sql = text("""
        INSERT INTO atlas.atlas_universe_stocks
            (instrument_id, symbol, company_name, tier, sector, industry,
             in_nifty_50, in_nifty_100, in_nifty_500, listing_date,
             effective_from, effective_to)
        VALUES
            (:instrument_id, :symbol, :company_name, :tier, :sector, :industry,
             :in_nifty_50, :in_nifty_100, :in_nifty_500, :listing_date,
             :effective_from, NULL)
        ON CONFLICT (instrument_id, effective_from) DO UPDATE SET
            symbol = EXCLUDED.symbol,
            company_name = EXCLUDED.company_name,
            tier = EXCLUDED.tier,
            sector = EXCLUDED.sector,
            industry = EXCLUDED.industry,
            in_nifty_50 = EXCLUDED.in_nifty_50,
            in_nifty_100 = EXCLUDED.in_nifty_100,
            in_nifty_500 = EXCLUDED.in_nifty_500,
            updated_at = NOW()
    """)

    with eng.begin() as conn:
        for r in rows:
            conn.execute(insert_sql, {**r, "effective_from": Config.UNIVERSE_LOCK_DATE})

    log.info("universe_stocks_populated", count=len(rows))
    return len(rows)

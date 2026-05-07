"""Atlas sector taxonomy builder.

Materialises ``atlas.atlas_sector_master`` from ``public.de_instrument.sector``
and ``public.de_sector_mapping``. Per methodology Section 10.1, the NSE
Industry Classification is the canonical sector source — Atlas does not
re-classify or remap.

The locked sector list is the output of:

    SELECT DISTINCT sector
    FROM public.de_instrument
    WHERE is_active = TRUE AND sector IS NOT NULL
    ORDER BY sector;

joined left-side to ``de_sector_mapping`` so each sector inherits its
``primary_nse_index`` (e.g. NIFTY BANK for the Bank sector). Sectors
without a mapping fall back to NIFTY 500 as the within-sector benchmark.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger()


def query_distinct_sectors(engine: Engine) -> list[str]:
    """Return the sorted list of distinct sector names from the active universe."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT sector "
                "FROM public.de_instrument "
                "WHERE is_active = TRUE AND sector IS NOT NULL "
                "ORDER BY sector"
            )
        ).all()
    return [r[0] for r in rows]


def query_sector_mapping(engine: Engine) -> dict[str, dict[str, object]]:
    """Return ``{sector_name: {primary, secondary, notes}}`` from de_sector_mapping.

    Sectors with no mapping row are missing from this dict — caller falls
    back to NIFTY 500 per methodology 6.3.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT jip_sector_name, primary_nse_index, "
                "       secondary_nse_indices, notes "
                "FROM public.de_sector_mapping"
            )
        ).all()
    return {
        r[0]: {
            "primary_nse_index": r[1],
            "secondary_nse_indices": r[2] or [],
            "notes": r[3],
        }
        for r in rows
    }


def populate_sector_master(engine: Engine | None = None) -> int:
    """Populate ``atlas_sector_master``. Idempotent — uses ON CONFLICT.

    Returns the number of distinct sectors persisted.
    """
    eng = engine or get_engine()
    sectors = query_distinct_sectors(eng)
    mapping = query_sector_mapping(eng)

    if not sectors:
        raise RuntimeError(
            "No active sectors in public.de_instrument. M0 gap-fill may be incomplete."
        )

    rows = []
    for s in sectors:
        m = mapping.get(s, {})
        rows.append(
            {
                "sector_name": s,
                "primary_nse_index": m.get("primary_nse_index"),
                "secondary_nse_indices": m.get("secondary_nse_indices") or [],
                "notes": m.get("notes"),
            }
        )

    with eng.begin() as conn:
        for r in rows:
            conn.execute(
                text(
                    "INSERT INTO atlas.atlas_sector_master "
                    "  (sector_name, primary_nse_index, secondary_nse_indices, notes) "
                    "VALUES (:sector_name, :primary_nse_index, :secondary, :notes) "
                    "ON CONFLICT (sector_name) DO UPDATE SET "
                    "  primary_nse_index = EXCLUDED.primary_nse_index, "
                    "  secondary_nse_indices = EXCLUDED.secondary_nse_indices, "
                    "  notes = EXCLUDED.notes, "
                    "  updated_at = NOW()"
                ),
                {
                    "sector_name": r["sector_name"],
                    "primary_nse_index": r["primary_nse_index"],
                    "secondary": r["secondary_nse_indices"],
                    "notes": r["notes"],
                },
            )

    log.info(
        "sector_master_populated",
        count=len(rows),
        with_primary_index=sum(1 for r in rows if r["primary_nse_index"]),
    )
    return len(rows)

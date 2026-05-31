"""One-off EC2 runner: expand atlas_etf_scorecard new columns (migration 097).

Populates premium_bps, te_60d, adv_20d_inr for all 34 active ETFs.

Usage (on EC2, inside atlas-os repo):
    python scripts/etf_scorecard_expand.py 2>&1 | tee /tmp/etf_expand.log

Runs a full recompute of atlas_etf_scorecard for the latest snapshot date found
in the table, writing the 3 new columns alongside all existing scores.

Requires .supabase-write-approved marker in the repo root for live writes.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import structlog
from sqlalchemy import text

log = structlog.get_logger()

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _latest_snapshot_date(engine) -> date:  # type: ignore[no-untyped-def]
    """Find the most recent snapshot_date in atlas_etf_scorecard."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT MAX(snapshot_date) FROM atlas.atlas_etf_scorecard")
        ).scalar()
    if result is None:
        raise RuntimeError("atlas_etf_scorecard is empty — nothing to expand")
    return result


def main() -> int:
    from atlas.db import get_engine
    from atlas.inference.etf_scorecard import compute_etf_scorecard, emit_upsert_sql

    engine = get_engine()

    # 1. Find snapshot date
    snapshot_date = _latest_snapshot_date(engine)
    log.info("etf_scorecard_expand_start", snapshot_date=str(snapshot_date))

    # 2. Compute scorecard (includes the 3 new column loaders)
    rows = compute_etf_scorecard(snapshot_date, engine=engine)
    log.info("etf_scorecard_computed", n_rows=len(rows))

    # 3. Validate: count non-null per new col
    n_adv = sum(1 for r in rows if r.adv_20d_inr is not None)
    n_te = sum(1 for r in rows if r.te_60d is not None)
    n_prem = sum(1 for r in rows if r.premium_bps is not None)
    total = len(rows)

    log.info(
        "etf_scorecard_new_col_coverage",
        total=total,
        adv_20d_inr=f"{n_adv}/{total} ({100 * n_adv / max(total, 1):.1f}%)",
        te_60d=f"{n_te}/{total} ({100 * n_te / max(total, 1):.1f}%)",
        premium_bps=f"{n_prem}/{total} ({100 * n_prem / max(total, 1):.1f}%)",
    )

    # 4. Write-marker check
    write_marker = _REPO_ROOT / ".supabase-write-approved"
    if not write_marker.exists():
        log.error(
            "write_marker_missing",
            detail="Create .supabase-write-approved in repo root to enable live writes",
        )
        print("ERROR: .supabase-write-approved marker not found. Aborting write.", file=sys.stderr)
        return 1

    # 5. Build SQL and execute
    sql = emit_upsert_sql(rows)
    if sql.strip().startswith("--"):
        log.warning("etf_scorecard_no_rows_to_write")
        print("No rows to write — aborting.", file=sys.stderr)
        return 1

    with engine.begin() as conn:
        conn.execute(text(sql))

    log.info("etf_scorecard_expand_done", rows_upserted=len(rows))

    # 6. Post-write verification query
    with engine.connect() as conn:
        verify = conn.execute(
            text(
                """
                SELECT
                    COUNT(*) AS rows,
                    ROUND(100.0 * COUNT(premium_bps) / NULLIF(COUNT(*), 0), 2) AS cov_premium,
                    ROUND(100.0 * COUNT(te_60d) / NULLIF(COUNT(*), 0), 2) AS cov_te,
                    ROUND(100.0 * COUNT(adv_20d_inr) / NULLIF(COUNT(*), 0), 2) AS cov_adv,
                    ROUND(100.0 * COUNT(composite_score) / NULLIF(COUNT(*), 0), 2) AS cov_composite
                FROM atlas.atlas_etf_scorecard
                """
            )
        ).first()

    if verify:
        print(
            f"\n--- Post-write verification ---\n"
            f"  rows:          {verify[0]}\n"
            f"  cov_premium:   {verify[1]}%\n"
            f"  cov_te:        {verify[2]}%\n"
            f"  cov_adv:       {verify[3]}%\n"
            f"  cov_composite: {verify[4]}%\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

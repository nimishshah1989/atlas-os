#!/usr/bin/env python3
"""Fast composite re-blend for the Thresholds control panel — atlas_foundation only.

The FM edits lens weights / conviction thresholds in atlas_foundation.atlas_thresholds;
this re-blends the composite + conviction_tier for every stock from the ALREADY-CACHED
per-lens sub-scores (the expensive part), with ONE in-DB UPDATE. Seconds, because only the
cheap weighted blend re-runs — the lens features are untouched.

Faithful to the canonical scorer: it reuses recompute_sql.build_sql (the exact SQL that is
cross-checked against atlas.lenses.compute.composite.compute_composite) — just pointed at
atlas_foundation instead of the legacy atlas schema, and scoped to the latest snapshot by
default so the live frontend reflects the retune immediately.

Usage:
    python -m scripts.foundation.recompute_composite_fast            # preview latest (no write)
    python -m scripts.foundation.recompute_composite_fast --apply    # write latest snapshot
    python -m scripts.foundation.recompute_composite_fast --apply --all-dates
    python -m scripts.foundation.recompute_composite_fast --json      # machine-readable preview
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root → atlas.*
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/foundation → _db, recompute_sql

import recompute_sql as R
from _db import engine
from sqlalchemy import text

from atlas.db import load_thresholds

SCHEMA = "atlas_foundation"
TABLE = f"{SCHEMA}.atlas_lens_scores_daily"


def _weights_and_th() -> tuple[dict, dict]:
    raw = load_thresholds()
    th = {k: (float(v) if hasattr(v, "__float__") else v) for k, v in raw.items()}
    weights = {l: float(th[f"lens_weight_{l}"]) for l in R.CONV}
    return weights, th


def _latest_clause(all_dates: bool) -> str:
    if all_dates:
        return ""
    return f" AND date=(SELECT max(date) FROM {TABLE} WHERE asset_class='stock')"


def compute_impact(all_dates: bool = False) -> dict:
    """Re-blend with the CURRENT saved weights and report the shift vs the stored composite —
    no write. This is the panel's "Preview impact". Compares conviction-tier membership and the
    top-decile (by composite) set on the latest snapshot."""
    weights, th = _weights_and_th()
    sel = R.build_sql(weights, th, where_extra=_latest_clause(all_dates), schema=SCHEMA)
    eng = engine()
    with eng.connect() as c:
        # join the freshly-computed composite/tier against what is stored
        q = text(
            f"""
            WITH new AS ({sel})
            SELECT
              count(*) AS n,
              count(*) FILTER (WHERE round(new.composite,2) IS DISTINCT FROM round(l.composite,2)) AS composite_changed,
              count(*) FILTER (WHERE new.conviction_tier IS DISTINCT FROM l.conviction_tier) AS tier_changed,
              round(avg(abs(new.composite - l.composite))::numeric, 3) AS mean_abs_delta,
              round(max(abs(new.composite - l.composite))::numeric, 3) AS max_abs_delta
            FROM new
            JOIN {TABLE} l USING (instrument_id, date)
            """
        )
        row = c.execute(q).mappings().one()
    return dict(row)


def apply(all_dates: bool = False) -> dict:
    """Verify the SQL still matches the canonical scorer, then write composite + conviction_tier
    back into atlas_foundation in a single UPDATE. Verify-gated so a faithful recompute is the
    only thing that can write (rule #0)."""
    weights, th = _weights_and_th()
    if not R.verify(weights, th):  # canonical cross-check (samples the latest snapshot)
        raise SystemExit("❌ SQL composite diverges from the canonical scorer — NOT writing.")
    sel = R.build_sql(weights, th, where_extra=_latest_clause(all_dates), schema=SCHEMA)
    eng = engine()
    with eng.begin() as c:
        res = c.execute(
            text(
                f"""
                WITH src AS ({sel})
                UPDATE {TABLE} l
                SET composite = src.composite,
                    conviction_tier = src.conviction_tier,
                    coverage_factor = src.coverage_factor,
                    lenses_active = src.lenses_active
                FROM src
                WHERE l.instrument_id = src.instrument_id AND l.date = src.date
                """
            )
        )
        n = res.rowcount
    return {"rows_updated": n, "scope": "all-dates" if all_dates else "latest"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default is preview-only)")
    ap.add_argument(
        "--all-dates", action="store_true", help="whole history (default: latest snapshot)"
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    if args.apply:
        out = apply(all_dates=args.all_dates)
        print(
            json.dumps(out)
            if args.json
            else f"✅ updated {out['rows_updated']} rows ({out['scope']})"
        )
    else:
        out = compute_impact(all_dates=args.all_dates)
        if args.json:
            print(json.dumps({k: (float(v) if v is not None else None) for k, v in out.items()}))
        else:
            print(
                f"preview ({'all-dates' if args.all_dates else 'latest'}): "
                f"{out['n']} stocks · composite changed {out['composite_changed']} · "
                f"tier changed {out['tier_changed']} · mean|Δ| {out['mean_abs_delta']} · max|Δ| {out['max_abs_delta']}"
            )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""``atlas_global.etf_holdings`` → ``atlas_global.etf_exposure_daily`` (L1 exposures).

    python scripts/global_market/build_exposures.py                  # snapshots not yet computed
    python scripts/global_market/build_exposures.py --all --report /tmp/exp.csv
    python scripts/global_market/build_exposures.py --symbols IVV,EWJ --dry-run

WHAT THIS TURNS ON. Holdings are a list; exposures are what the list MEANS. This is the input
to the classification engine's country and sector evidence, the cost lens's concentration
sub-score, the quality lens's look-through gate, and the ``/countries`` and ``/sectors`` pages.

KEYED BY THE SNAPSHOT, NOT THE SESSION. ``etf_exposure_daily`` is ``(instrument_id,
as_of_date)`` where ``as_of_date`` is the HOLDINGS' date, because exposures only change when
holdings do — an N-PORT snapshot is quarterly, and writing one row a night would be four
figures a year repeated sixty times each. Readers take the latest ``as_of_date <= lens date``,
exactly as they do for ``etf_holdings``. So the default run computes only the snapshots that
have no exposure row yet; ``--all`` recomputes every one, which is what a change to the
exposure arithmetic needs.

THE ARITHMETIC IS PURE AND LIVES ELSEWHERE (``atlas.global_market.classify.exposures``), with
its own tests on four real filings. This file is the off-box half: which snapshots, the sector
lookup, and the write.

SECTOR IS THE HOLDING'S OWN. It comes from ``instrument_master.sector_gics`` — the GICS sector
of the scored stock a holding resolved to — mapped onto the taxonomy's ids by name from
``taxonomy_sector`` itself, so there is no second copy of that vocabulary in this file. A
holding that did not resolve has no sector, and a fund whose holdings do not resolve has no
sector vector: the look-through reaches the S&P 500 and nothing else, which is the honest
bound rather than a reason to guess from the fund's name.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report (siblings)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package

import _gdb
import pandas as pd
from _report import Report
from psycopg2.extras import Json

from atlas.global_market.classify.exposures import Exposures, exposures

M = _gdb.M
TABLE = f"{M}.etf_exposure_daily"

DB_COLUMNS: tuple[str, ...] = (
    "instrument_id",
    "as_of_date",
    "country_vec",
    "sector_vec",
    "asset_vec",
    "top_country",
    "top_country_w",
    "equity_w",
    "n_holdings",
    "top10_w",
    "hhi",
    "lookthrough_scored_w",
    "sum_abs_weight",
    "holdings_source",
    "compute_run_id",
)
REPORT_COLUMNS = (
    "symbol",
    "as_of_date",
    "status",
    "holdings",
    "sum_abs_weight",
    "equity_w",
    "top_country",
    "top_country_w",
    "top10_w",
    "lookthrough_scored_w",
    "unmapped_w",
    "detail",
)
STATUS_COMPUTED = "computed"
STATUS_NO_WEIGHTS = "no_weights"

# ── database ──────────────────────────────────────────────────────────────────────────────

# The snapshots to compute. `--all` drops the NOT EXISTS: an exposure row is a pure function of
# its snapshot, so recomputing is only needed when THIS arithmetic changes, never nightly.
SNAPSHOTS_SQL = f"""
SELECT DISTINCT h.instrument_id::text AS instrument_id, h.as_of_date, im.symbol
FROM {M}.etf_holdings h
JOIN {M}.instrument_master im ON im.instrument_id = h.instrument_id
WHERE (:all_snapshots OR NOT EXISTS (
        SELECT 1 FROM {TABLE} e
         WHERE e.instrument_id = h.instrument_id AND e.as_of_date = h.as_of_date))
ORDER BY h.as_of_date DESC, im.symbol
"""

HOLDINGS_SQL = f"""
SELECT holding_instrument_id::text AS holding_instrument_id, weight_frac,
       country_iso2, asset_category, source
FROM {M}.etf_holdings
WHERE instrument_id = :instrument_id AND as_of_date = :as_of_date
"""

# The taxonomy owns the sector vocabulary; this reads it rather than restating it. Level 1 is
# the GICS eleven, and `name` is the spelling instrument_master.sector_gics carries.
SECTOR_IDS_SQL = f"SELECT id, name FROM {M}.taxonomy_sector WHERE level = 1"

SECTOR_BY_INSTRUMENT_SQL = f"""
SELECT instrument_id::text AS instrument_id, sector_gics
FROM {M}.instrument_master
WHERE sector_gics IS NOT NULL
"""

UPSERT_SQL = f"""
insert into {TABLE} ({", ".join(DB_COLUMNS)}, computed_at)
values %s
on conflict (instrument_id, as_of_date) do update set
    {", ".join(f"{c} = excluded.{c}" for c in DB_COLUMNS if c not in ("instrument_id", "as_of_date"))},
    computed_at = now()
"""


def snapshots(all_snapshots: bool, symbols: str | None, limit: int | None) -> pd.DataFrame:
    frame = _gdb.read_df(SNAPSHOTS_SQL, {"all_snapshots": all_snapshots})
    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",") if s.strip()}
        frame = pd.DataFrame(frame[frame["symbol"].isin(sorted(wanted))])
        missing = wanted - set(frame["symbol"])
        if missing:
            raise SystemExit("REFUSED: no holdings snapshot for " + ", ".join(sorted(missing)))
    return pd.DataFrame(frame.head(limit)) if limit else frame


def sector_by_instrument() -> dict[str, str]:
    """``instrument_id -> taxonomy sector id`` for every stock whose GICS sector is known.

    A sector name the taxonomy does not carry is DROPPED rather than passed through: the
    vector's keys are taxonomy ids, and a stray display name in there would reach the board as
    a sector that does not exist.
    """
    ids = _gdb.read_df(SECTOR_IDS_SQL)
    by_name = {str(n): str(i) for i, n in zip(ids["id"], ids["name"], strict=True)}
    frame = _gdb.read_df(SECTOR_BY_INSTRUMENT_SQL)
    out: dict[str, str] = {}
    for iid, name in zip(frame["instrument_id"], frame["sector_gics"], strict=True):
        found = by_name.get(str(name))
        if found is not None:
            out[str(iid)] = found
    return out


def db_row(
    found: Exposures, instrument_id: str, as_of: dt.date, source: str | None, run_id: str
) -> dict[str, Any]:
    """One ``etf_exposure_daily`` record. The three vectors are jsonb of STRINGS, because a
    Decimal weight rendered through float would land in the document at a precision the
    ``numeric`` columns beside it do not have."""
    return {
        "instrument_id": instrument_id,
        "as_of_date": as_of,
        "country_vec": Json({k: str(v) for k, v in found.country_vec.items()}),
        "sector_vec": Json({k: str(v) for k, v in found.sector_vec.items()}),
        "asset_vec": Json({k: str(v) for k, v in found.asset_vec.items()}),
        "top_country": found.top_country,
        "top_country_w": found.top_country_w,
        "equity_w": found.equity_w,
        "n_holdings": found.n_holdings,
        "top10_w": found.top10_w,
        "hhi": found.hhi,
        "lookthrough_scored_w": found.lookthrough_scored_w,
        "sum_abs_weight": found.sum_abs_weight,
        "holdings_source": source,
        "compute_run_id": run_id,
    }


# ── run ───────────────────────────────────────────────────────────────────────────────────


def run(
    *, all_snapshots: bool, symbols: str | None, limit: int | None, dry_run: bool, report: Report
) -> dict[str, int]:
    run_id = str(uuid.uuid4())
    picked = snapshots(all_snapshots, symbols, limit)
    if picked.empty:
        print(
            f"[exposures] nothing to compute — every {M}.etf_holdings snapshot already has an "
            "exposure row (--all recomputes them; ingest_nport.py writes the holdings)"
        )
        return {"snapshots": 0, "written": 0}
    sectors = sector_by_instrument()
    print(
        f"[exposures] {len(picked):,d} snapshot(s) to compute; sector known for "
        f"{len(sectors):,d} scored instrument(s)"
    )

    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for snapshot in picked.to_dict("records"):
        iid, as_of, symbol = snapshot["instrument_id"], snapshot["as_of_date"], snapshot["symbol"]
        holdings = _gdb.read_df(
            HOLDINGS_SQL, {"instrument_id": iid, "as_of_date": as_of}, coerce_float=False
        )
        found = exposures(holdings, sectors)
        source = next((s for s in holdings["source"] if s), None) if not holdings.empty else None
        status = STATUS_COMPUTED if found.sum_abs_weight else STATUS_NO_WEIGHTS
        counts[status] += 1
        report.add(
            symbol,
            as_of,
            status,
            found.n_holdings,
            found.sum_abs_weight,
            found.equity_w,
            found.top_country,
            found.top_country_w,
            found.top10_w,
            found.lookthrough_scored_w,
            found.unmapped_w,
            "" if found.unmapped_w == 0 else f"unmapped asset codes carry {found.unmapped_w}",
        )
        if status == STATUS_COMPUTED:
            rows.append(db_row(found, str(iid), as_of, source, run_id))

    print(
        f"  {counts[STATUS_COMPUTED]:,d} computed · {counts[STATUS_NO_WEIGHTS]:,d} with no "
        f"weight to compute on {report.where()}"
    )
    if dry_run:
        print("  --dry-run: nothing written")
    else:
        write(rows)
        print(f"  upserted {len(rows):,d} row(s) into {TABLE}")
    return {"snapshots": len(picked), "written": 0 if dry_run else len(rows)}


def write(rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    import psycopg2
    from psycopg2.extras import execute_values

    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with conn, conn.cursor() as cur:
            execute_values(
                cur,
                UPSERT_SQL,
                [tuple(r[c] for c in DB_COLUMNS) for r in rows],
                template="(" + ", ".join(["%s"] * len(DB_COLUMNS)) + ", now())",
                page_size=500,
            )
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--all", action="store_true", help="recompute every snapshot, not just the new ones"
    )
    p.add_argument("--symbols", help="comma-separated ETF symbols instead of every snapshot")
    p.add_argument("--limit", type=int, help="stop after N snapshots (newest first)")
    p.add_argument("--dry-run", action="store_true", help="compute and report, write nothing")
    p.add_argument("--report", type=Path, help="CSV of the per-snapshot exposures")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = Report(args.report, REPORT_COLUMNS)
    try:
        counts = run(
            all_snapshots=args.all,
            symbols=args.symbols,
            limit=args.limit,
            dry_run=args.dry_run,
            report=report,
        )
    finally:
        report.close()
    return 0 if counts["snapshots"] == 0 or counts["written"] or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())

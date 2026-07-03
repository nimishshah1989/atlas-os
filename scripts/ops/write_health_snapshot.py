#!/usr/bin/env python3
"""Write the nightly observability snapshot → atlas_foundation health tables.

The three health tables (atlas_pipeline_runs / atlas_validator_results /
atlas_health_daily) power /health and /admin/data-status. Their original writers were
retired atlas.* scripts (deleted in the consolidation), so the tables had frozen at a
cloned 06-25 snapshot. This is the single live writer, called at the END of
atlas_daily.sh with the real per-step outcomes.

RULE #0: every row is REAL produced output — per-step timings/status come from the
orchestrator's own runfile (which includes the gate steps validate_lenses_A/B and
freshness_guard) and the freshness metrics from live max(date)/row-count on the served
tables. Nothing synthetic.

    python write_health_snapshot.py --runfile <tsv> --eod <YYYY-MM-DD>

Runfile is TSV, one line per orchestrator step (compute steps AND gate steps):
    <script_name>\t<started_iso>\t<ended_iso>\t<status>

The gate steps (validate_lenses_A/B, freshness_guard) are ALSO written to
atlas_validator_results (its old M2-M5-only CHECK constraint was dropped 2026-07-02), so
the /health validator panel shows the current run's gate outcomes.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import uuid

import _db


def _insert(table: str, df) -> int:
    """Plain bulk INSERT (append-only logs; the cloned health tables carry no PK, so
    ON CONFLICT / upsert_df cannot be used)."""
    if df.empty:
        return 0
    import pandas as pd
    from psycopg2.extras import execute_values

    cols = list(df.columns)
    clean = df.astype(object).where(pd.notna(df), None)
    rows = list(map(tuple, clean.to_numpy()))
    sql = f"insert into {table} ({', '.join(cols)}) values %s"
    raw = _db.engine().raw_connection()
    try:
        with raw.cursor() as cur:
            execute_values(cur, sql, rows, page_size=500)
        raw.commit()
    finally:
        raw.close()
    return len(rows)


# The derived tables the live product serves (mirror of health.ts TRACKED_TABLES /
# FOUNDATION_TABLES). Covers every derived table the freshness guard watches.
TRACKED = [
    ("technical_daily", "date"),
    ("atlas_lens_scores_daily", "date"),
    ("sector_lens_daily", "date"),
    ("fund_rank_daily", "date"),
    ("atlas_index_metrics_daily", "date"),
    ("atlas_market_regime_daily", "date"),
    ("breadth_nifty500_daily", "date"),
    ("mv_sector_cards", "as_of_date"),
    ("mv_sector_breadth", "as_of_date"),
    ("mv_sector_deepdive", "data_as_of"),
    ("atlas_macro_daily", "date"),
]


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return None


def _write_runs(runfile: str, host: str, sha: str | None) -> int:
    rows = []
    with open(runfile) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4 or not parts[0]:
                continue
            name, started, ended, status = parts[0], parts[1], parts[2], parts[3]
            rows.append(
                {
                    "run_id": str(uuid.uuid4()),
                    "script_name": name[:64],
                    "milestone": "daily",
                    "started_at": started,
                    "ended_at": ended or None,
                    "status": status,
                    "host": host,
                    "git_sha": sha,
                }
            )
    if not rows:
        return 0
    import pandas as pd

    return _insert("atlas_foundation.atlas_pipeline_runs", pd.DataFrame(rows))


# Gate step (runfile) → validator table. Names kept <=16 (validator col limit); status is
# PASS/FAIL (the surviving chk_validator_results_status constraint).
_GATE_VALIDATORS = {
    "validate_lenses_A": "lens_gate_A",
    "validate_lenses_B": "lens_gate_B",
    "freshness_guard": "freshness_guard",
}


def _write_validators(runfile: str, host: str, sha: str | None) -> int:
    import pandas as pd

    rows = []
    with open(runfile) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            name, _started, ended, status = parts[0], parts[1], parts[2], parts[3]
            vname = _GATE_VALIDATORS.get(name)
            if not vname:
                continue
            ok = status == "success"
            rows.append(
                {
                    "run_id": str(uuid.uuid4()),
                    "validator": vname,
                    "ran_at": ended or str(pd.Timestamp.now(tz="Asia/Kolkata")),
                    "total_checks": 1,
                    "failures": 0 if ok else 1,
                    "status": "PASS" if ok else "FAIL",
                    "host": host,
                    "git_sha": sha,
                }
            )
    if not rows:
        return 0
    return _insert("atlas_foundation.atlas_validator_results", pd.DataFrame(rows))


def _write_freshness(eod: str) -> int:
    """One health_daily row per tracked table: freshness lag (days) vs the EOD anchor."""
    import pandas as pd

    now = pd.Timestamp.now(tz="Asia/Kolkata")
    rows = []
    for tbl, dcol in TRACKED:
        try:
            r = _db.read_df(f"select count(*) n, max({dcol}) mx from atlas_foundation.{tbl}")
        except Exception:
            continue
        n = int(r["n"][0])
        mx = r["mx"][0]
        lag = None if mx is None else (pd.Timestamp(eod).date() - mx).days
        anomaly = lag is None or lag > 3
        rows.append(
            {
                "data_date": eod,
                "table_name": tbl,
                "metric_name": "freshness_lag_days",
                "value_today": lag,
                "is_anomaly": anomaly,
                "severity": "critical" if anomaly else "info",
                "notes": f"{n} rows; latest {mx}",
                "computed_at": now,
            }
        )
    if not rows:
        return 0
    # Idempotent for the day: clear this EOD's freshness rows then insert.
    _db.exec_sql(
        "delete from atlas_foundation.atlas_health_daily "
        "where data_date = :d and metric_name = 'freshness_lag_days'",
        {"d": eod},
    )
    return _insert("atlas_foundation.atlas_health_daily", pd.DataFrame(rows))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runfile", required=True)
    ap.add_argument("--eod", required=True)
    args = ap.parse_args()

    host = socket.gethostname()
    sha = _git_sha()
    nr = _write_runs(args.runfile, host, sha)
    nv = _write_validators(args.runfile, host, sha)
    nf = _write_freshness(args.eod)
    print(f"health snapshot: {nr} runs, {nv} validators, {nf} freshness rows (git {sha})")


if __name__ == "__main__":
    main()

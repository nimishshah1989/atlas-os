#!/usr/bin/env python3
"""Write the orchestrator's health snapshot → the atlas_global health tables.

India's scripts/ops/write_health_snapshot.py over atlas_global: the single writer of
atlas_pipeline_runs / atlas_validator_results / atlas_health_daily (the global /health page),
called at the END of atlas_global_daily.sh and atlas_global_weekly.sh:

    python write_health_snapshot.py --runfile <tsv> --eod <YYYY-MM-DD> --milestone daily|weekly

The runfile is the orchestrator's TSV, one line per step (compute steps AND gate steps):
    <script_name>\\t<started_iso>\\t<ended_iso>\\t<status>

RULE #0: every row is REAL produced output — the per-step outcomes from the runfile, the
freshness from live max(date)/count(*) on the served tables. Lag is counted in SPY SESSIONS
on freshness_guard's own anchor calendar (a weekday holiday is not lag; with no SPY bar there
is no lag to count and the note says so); tolerance and tier come from the guard's registries.
The health tables carry primary keys, so every write is an upsert: run_id is uuid5 of
(milestone, step, started_at) and a re-run over the same runfile replaces its rows.
"""

from __future__ import annotations

import argparse
import datetime as dt
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, freshness_guard (siblings)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # atlas package, run as a script
import _gdb
import freshness_guard as guard

from atlas.global_market import calendar as gcal

M = _gdb.M

# The tables the Phase 1 pipeline fills, with the column that dates a row: every table the
# guard watches plus the ones its registries gain as P1-B/D/E land.
TRACKED: list[tuple[str, str]] = [
    ("instrument_master", "updated_at"),
    ("index_membership", "updated_at"),
    ("macro_daily", "date"),
    ("ohlcv_daily", "date"),
    ("technical_daily", "date"),
    ("universe_snapshot", "date"),
]

# Gate step (runfile) → validator name (<= 16 chars, the column's width); PASS/FAIL status.
_GATE_VALIDATORS = {"freshness_guard": "freshness_guard", "validate_global_A": "gate_A"}

Step = tuple[str, str, str, str]  # (script_name, started_iso, ended_iso, status)


def run_id(milestone: str, name: str, started: str) -> str:
    """Deterministic per orchestrator step — the idempotency key of both run tables."""
    ns = uuid.UUID("6f1c2a54-9b7e-4d3a-8e51-0d4b2c7a9e10")
    return str(uuid.uuid5(ns, f"{milestone}\t{name}\t{started}"))


def read_runfile(path: str | Path) -> list[Step]:
    """The orchestrator's TSV, malformed lines skipped (a step name is mandatory)."""
    steps: list[Step] = []
    with open(path) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4 or not parts[0]:
                continue
            steps.append((parts[0], parts[1], parts[2], parts[3]))
    return steps


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return None


def run_rows(
    steps: list[Step], milestone: str, host: str, sha: str | None, now: dt.datetime
) -> list[dict[str, Any]]:
    return [
        {
            "run_id": run_id(milestone, name, started),
            "script_name": name[:64],
            "milestone": milestone,
            "started_at": started,
            "ended_at": ended or None,
            "status": status,
            "host": host,
            "git_sha": sha,
            "updated_at": now,
        }
        for name, started, ended, status in steps
    ]


def validator_rows(
    steps: list[Step], milestone: str, host: str, sha: str | None, now: dt.datetime
) -> list[dict[str, Any]]:
    """The gate steps only. run_id is the gate's own pipeline_runs id, so the two rows of
    one gate outcome share a key."""
    rows = []
    for name, started, ended, status in steps:
        vname = _GATE_VALIDATORS.get(name)
        if not vname:
            continue
        ok = status == "success"
        rows.append(
            {
                "run_id": run_id(milestone, name, started),
                "validator": vname,
                "ran_at": ended or now,
                "total_checks": 1,
                "failures": 0 if ok else 1,
                "status": "PASS" if ok else "FAIL",
                "host": host,
                "git_sha": sha,
            }
        )
    return rows


def freshness_row(
    table: str,
    n: int,
    mx: dt.date | None,
    eod: dt.date,
    cal: list[dt.date],
    tol: tuple[int, str] | None,
    now: dt.datetime,
) -> dict[str, Any]:
    """One atlas_health_daily row. ``mx`` is the live max(date_col), a date or an aware
    timestamp (None = empty table);
    ``cal`` the SPY sessions (empty = no anchor bar, so no lag can be counted); ``tol`` the
    guard's (max lag, severity) for the table, None when it is not guarded."""
    lag: int | None = None
    if mx is None:
        note = "EMPTY"
    elif not cal:
        note = f"{n:,d} rows; latest {guard._as_date(mx)}; no SPY bar: no session calendar"
    else:
        latest = guard._as_date(mx)
        lag = gcal.sessions_behind(cal, latest, eod)
        note = f"{n:,d} rows; latest {latest}; lag in sessions"
    if tol is None:
        anomaly, severity = False, "info"
        note += "; not guarded by freshness_guard yet"
    else:
        max_lag, tier = tol
        anomaly = lag is None or lag > max_lag
        severity = tier if anomaly else "info"
        note += f"; tolerance {max_lag} session(s), {tier} when exceeded"
    return {
        "data_date": eod,
        "table_name": table,
        "metric_name": "freshness_lag_sessions",
        "value_today": lag,
        "is_anomaly": anomaly,
        "severity": severity,
        "notes": note,
        "computed_at": now,
    }


def freshness_rows(eod: dt.date, now: dt.datetime) -> list[dict[str, Any]]:
    """One row per tracked table from live counts, on the guard's own anchor calendar and
    registries (a KEY table withholds publish — critical; a BOARD table is warn-only). A
    table that cannot be read (missing, statement timeout) is logged and skipped, as India's
    writer does — the other rows still land."""
    cal = guard.spy_sessions()
    tol = {t: (lag, "critical") for t, _c, lag in guard.KEY_TABLES}
    tol |= {t: (lag, "warn") for t, _c, lag in guard.BOARD_TABLES}
    rows = []
    for table, col in TRACKED:
        try:
            # count(*) scans the table: fine at Phase 1 sizes, worth a cheaper estimate once
            # ohlcv_daily holds millions of rows.
            n = int(_gdb.scalar(f"select count(*) from {M}.{table}") or 0)
            mx = _gdb.scalar(f"select max({col}) from {M}.{table}")
        except Exception as e:
            print(f"  skip {table}: {e}", file=sys.stderr)
            continue
        rows.append(freshness_row(table, n, mx, eod, cal, tol.get(table), now))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Write the orchestrator's health snapshot → atlas_global health tables"
    )
    ap.add_argument("--runfile", required=True)
    ap.add_argument("--eod", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--milestone", required=True, choices=("daily", "weekly"))
    args = ap.parse_args()

    now = dt.datetime.now(ZoneInfo(gcal.NEW_YORK))
    host = socket.gethostname()[:64]
    sha = _git_sha()
    steps = read_runfile(args.runfile)
    nr = _gdb.upsert_df(
        f"{M}.atlas_pipeline_runs",
        pd.DataFrame(run_rows(steps, args.milestone, host, sha, now)),
        ["run_id"],
    )
    nv = _gdb.upsert_df(
        f"{M}.atlas_validator_results",
        pd.DataFrame(validator_rows(steps, args.milestone, host, sha, now)),
        ["run_id", "validator"],
    )
    nf = _gdb.upsert_df(
        f"{M}.atlas_health_daily",
        pd.DataFrame(freshness_rows(args.eod, now)),
        ["data_date", "table_name", "metric_name"],
    )
    print(
        f"health snapshot ({args.milestone}, EOD {args.eod}): {nr} runs, {nv} validators, "
        f"{nf} freshness rows (git {sha})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

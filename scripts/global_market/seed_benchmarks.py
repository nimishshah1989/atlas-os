#!/usr/bin/env python3
"""Seed ``atlas_global.benchmark_master`` — the seven benchmark ETFs resolved to instrument ids.

    python scripts/global_market/seed_benchmarks.py             # resolve + upsert

The set is the plan's (docs/global/plan.md, "benchmark_master"): SPY market, QQQ growth, IWM
small, VXUS intl, AGG bond, GLD gold, BIL cash — the roles the DDL's CHECK constraint allows.
Each code resolves to the ACTIVE ``instrument_master`` row with that symbol; ``name`` is that
row's name (the directory's security name, never typed here). Any code that does not resolve
is named and the run exits 2 WITHOUT writing — P1-D's technicals need all seven, so a partial
table is worse than none. Writes are ``ON CONFLICT (code) DO UPDATE`` (idempotent; an instrument
re-minted by build_identity re-points the code); ``ingest_state(source='benchmarks',
key='seed')`` records what was resolved, in the same transaction. Weekly step in
``atlas_global_weekly.sh``, before ``ingest_index_membership``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from datetime import UTC, datetime

import _gdb
import psycopg2
from psycopg2.extras import execute_values

BENCHMARKS: tuple[tuple[str, str], ...] = (
    ("SPY", "market"),
    ("QQQ", "growth"),
    ("IWM", "small"),
    ("VXUS", "intl"),
    ("AGG", "bond"),
    ("GLD", "gold"),
    ("BIL", "cash"),
)
STATE_SOURCE, STATE_KEY = "benchmarks", "seed"

UPSERT_SQL = f"""
insert into {_gdb.M}.benchmark_master (code, instrument_id, role, name, is_active)
values %s
on conflict (code) do update set
    instrument_id = excluded.instrument_id, role = excluded.role, name = excluded.name,
    is_active = true
"""


def resolve(
    active_by_symbol: Mapping[str, tuple[str, str | None]],
) -> tuple[list[tuple[str, str, str, str | None]], list[str]]:
    """``(rows (code, instrument_id, role, name), unresolved codes)`` — pure."""
    rows = [
        (code, active_by_symbol[code][0], role, active_by_symbol[code][1])
        for code, role in BENCHMARKS
        if code in active_by_symbol
    ]
    missing = [code for code, _ in BENCHMARKS if code not in active_by_symbol]
    return rows, missing


def load_active() -> dict[str, tuple[str, str | None]]:
    df = _gdb.read_df(
        f"select symbol, instrument_id::text as instrument_id, name "
        f"from {_gdb.M}.instrument_master where is_active and symbol = any(:codes)",
        {"codes": [c for c, _ in BENCHMARKS]},
    )
    return {
        str(s): (str(i), None if n is None else str(n)) for s, i, n in df.itertuples(index=False)
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.parse_args(argv)
    print(f"{len(BENCHMARKS)} benchmarks → {_gdb.M}.benchmark_master")
    rows, missing = resolve(load_active())
    for code, iid, role, name in rows:
        print(f"  {code:6} {role:7} → {iid}  {name or ''}")
    if missing:
        print(
            f"FAIL: {len(missing)} of {len(BENCHMARKS)} codes have no ACTIVE instrument_master "
            f"row: {', '.join(missing)} — nothing written (run build_identity.py first)"
        )
        return 2
    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with conn, conn.cursor() as cur:
            execute_values(cur, UPSERT_SQL, rows, template="(%s, %s, %s, %s, true)")
            _gdb.record_state(
                cur,
                STATE_SOURCE,
                STATE_KEY,
                {
                    "eod": _gdb.eod_cutoff().isoformat(),
                    "resolved": {code: iid for code, iid, _, _ in rows},
                    "run_at": datetime.now(UTC).isoformat(),
                },
            )
    finally:
        conn.close()
    print(f"upserted {len(rows)} of {len(BENCHMARKS)} benchmark rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())

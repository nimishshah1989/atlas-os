"""DB access for the atlas_global (US-market) scripts — a thin sibling of
``scripts/foundation/_db.py``.

Re-exports the foundation helpers (ONE connection string, ONE statement-timeout policy,
ONE upsert) so the two market trees can never diverge on how they reach Postgres, and adds
the only two things the global tree needs of its own:

* ``SCHEMA`` / ``M`` — the schema every global script qualifies its tables with, read from
  ``atlas.config.MARKETS["us"]`` (the one place it is written);
* ``eod_cutoff(now)`` — the ONE EOD anchor for the US session, delegating to
  :func:`atlas.global_market.calendar.eod_cutoff` (17:00 America/New_York, per the same
  market row) so the orchestrators and the gates can never disagree on what "today" is;
* ``record_provider_calls(cur, run_date, provider, calls)`` — the ONE writer of
  ``provider_calls`` (every adapter's ``calls`` Counter lands through it, on the script's own
  cursor, so the budget rows commit with the data rows or not at all).

House rule (FM 2026-07-01, applied verbatim to the US market): *all calculations are as of
the last EOD; the current day is for live/intraday only.* Every writer stamps from
``eod_cutoff()`` — the ``date.today()`` bug in ``ingest_mf_holdings.py`` hid a fresh
snapshot for a month.
"""

from __future__ import annotations

import datetime as dt
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

# The `atlas` package first, for scripts run as files; India's `scripts/foundation` (for `_db`)
# LAST, so an India script that shares a global script's name (ingest_macro.py,
# build_universe_snapshot.py, freshness_guard.py …) can never shadow the global sibling.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.append(str(Path(__file__).resolve().parents[2] / "scripts" / "foundation"))

from atlas.global_market import calendar as gcal
from atlas.global_market.config import CONFIG

if TYPE_CHECKING:
    # Static analysis resolves the sibling tree by package path (repo root is on extraPaths);
    # at runtime the scripts run as files, so the sys.path insert above does the same job.
    from scripts.foundation._db import (
        db_url,
        engine,
        exec_script,
        exec_sql,
        psycopg2_url,
        read_df,
        scalar,
        upsert_df,
    )
else:
    from _db import (
        db_url,
        engine,
        exec_script,
        exec_sql,
        psycopg2_url,
        read_df,
        scalar,
        upsert_df,
    )

__all__ = [  # noqa: RUF022 -- grouped: schema names, then the re-exported _db helpers
    "M",
    "SCHEMA",
    "db_url",
    "engine",
    "eod_cutoff",
    "exec_script",
    "exec_sql",
    "psycopg2_url",
    "read_df",
    "record_provider_calls",
    "scalar",
    "upsert_df",
]

SCHEMA = CONFIG.schema
M = SCHEMA


def eod_cutoff(now: dt.datetime | None = None) -> dt.date:
    """The last COMPLETE US session's calendar date (America/New_York) as of ``now``.

    ``now`` defaults to the current instant; a naive datetime is refused by the calendar
    (a naive value here would silently anchor the whole pipeline to the box's clock). The
    result is an upper BOUND: callers anchor to the latest SPY bar ``<=`` it.
    """
    return gcal.eod_cutoff(now or dt.datetime.now(dt.UTC))


PROVIDER_CALLS_SQL = f"""
insert into {SCHEMA}.provider_calls (run_date, provider, endpoint, calls, updated_at)
values (%s, %s, %s, %s, now())
on conflict (run_date, provider, endpoint) do update set
    calls = provider_calls.calls + excluded.calls, updated_at = now()
"""


def record_provider_calls(
    cur: Any, run_date: dt.date, provider: str, calls: Mapping[str, int]
) -> int:
    """Add an adapter's per-endpoint request counts to ``provider_calls`` for ``run_date``.

    Counts ACCUMULATE within the day (a rerun spent more budget, it did not replace the
    earlier spend). Zero counts are not rows. Runs on the caller's cursor — the script's
    single transaction — and returns the number of endpoints written.
    """
    rows = [(run_date, provider, endpoint, int(n)) for endpoint, n in calls.items() if n]
    for row in rows:
        cur.execute(PROVIDER_CALLS_SQL, row)
    return len(rows)


if __name__ == "__main__":
    # Self-check mirrors _db's: the raw DSN must be libpq-parseable, and the anchor must be
    # a calendar date in the past.
    import psycopg2.extensions as _ext

    d = psycopg2_url()
    assert d.startswith("postgresql://") and "+psycopg2" not in d, d
    _ext.parse_dsn(d)
    print("_gdb.psycopg2_url OK →", d.rsplit("@", 1)[-1])
    print("eod_cutoff() →", eod_cutoff(), "(schema", SCHEMA + ")")

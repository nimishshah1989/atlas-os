"""DB access for the atlas_global (US-market) scripts — a thin sibling of
``scripts/foundation/_db.py``.

Re-exports the foundation helpers (ONE connection string, ONE statement-timeout policy,
ONE upsert) so the two market trees can never diverge on how they reach Postgres, and adds
the only two things the global tree needs of its own:

* ``SCHEMA`` / ``M`` — the schema every global script qualifies its tables with, read from
  ``atlas.config.MARKETS["us"]`` (the one place it is written);
* ``eod_cutoff(now)`` — the ONE EOD anchor for the US session, delegating to
  :func:`atlas.global_market.calendar.eod_cutoff` (17:00 America/New_York, per the same
  market row) so the orchestrators and the gates can never disagree on what "today" is.

House rule (FM 2026-07-01, applied verbatim to the US market): *all calculations are as of
the last EOD; the current day is for live/intraday only.* Every writer stamps from
``eod_cutoff()`` — the ``date.today()`` bug in ``ingest_mf_holdings.py`` hid a fresh
snapshot for a month.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# `_db` (India's connection helpers) and the `atlas` package, for scripts run as files.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "foundation"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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


if __name__ == "__main__":
    # Self-check mirrors _db's: the raw DSN must be libpq-parseable, and the anchor must be
    # a calendar date in the past.
    import psycopg2.extensions as _ext

    d = psycopg2_url()
    assert d.startswith("postgresql://") and "+psycopg2" not in d, d
    _ext.parse_dsn(d)
    print("_gdb.psycopg2_url OK →", d.rsplit("@", 1)[-1])
    print("eod_cutoff() →", eod_cutoff(), "(schema", SCHEMA + ")")

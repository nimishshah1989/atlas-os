"""DB access for the atlas_global (US-market) scripts — a thin sibling of
``scripts/foundation/_db.py``.

Re-exports the foundation helpers (ONE statement-timeout policy, ONE upsert) so the two
market trees can never diverge on how they reach Postgres — behind ONE difference:
``ATLAS_DB_URL`` is taken from the environment only (the repo ``.env``, which ``atlas.config``
has already loaded, or an export). India's ``_db.db_url`` also falls back to
``frontend/.env.local`` — the India board's file, which carries prod — and the global tree
never reads it, so a laptop dry run of the orchestrators (runbook §6) cannot reach prod by
accident. Adds the only things the global tree needs of its own:

* ``SCHEMA`` / ``M`` — the schema every global script qualifies its tables with, read from
  ``atlas.config.MARKETS["us"]`` (the one place it is written);
* ``eod_cutoff(now)`` — the ONE EOD anchor for the US session, delegating to
  :func:`atlas.global_market.calendar.eod_cutoff` (17:00 America/New_York, per the same
  market row) so the orchestrators and the gates can never disagree on what "today" is;
* ``record_provider_calls(cur, run_date, provider, calls)`` — the ONE writer of
  ``provider_calls`` (every adapter's ``calls`` Counter lands through it), and
  ``commit_provider_calls(run_date, {provider: calls})`` — the same writer in its OWN short
  transaction right after the fetches, so spent budget survives an exit 2 at a gate or a
  rolled-back write;
* ``record_state(cur, source, key, value)`` — the ONE writer of ``ingest_state`` watermarks,
  on the script's cursor so the watermark commits with the rows it describes or not at all.

House rule (FM 2026-07-01, applied verbatim to the US market): *all calculations are as of
the last EOD; the current day is for live/intraday only.* Every writer stamps from
``eod_cutoff()`` — the ``date.today()`` bug in ``ingest_mf_holdings.py`` hid a fresh
snapshot for a month.
"""

from __future__ import annotations

import datetime as dt
import functools
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psycopg2
from psycopg2.extras import Json

# The `atlas` package first, for scripts run as files; India's `scripts/foundation` (for `_db`)
# LAST, so an India script that shares a global script's name (ingest_macro.py,
# build_universe_snapshot.py, freshness_guard.py …) can never shadow the global sibling.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.append(str(Path(__file__).resolve().parents[2] / "scripts" / "foundation"))

from atlas.global_market import calendar as gcal
from atlas.global_market.config import CONFIG

if TYPE_CHECKING:
    # Static analysis resolves the sibling tree by package path (repo root is on extraPaths);
    # at runtime the scripts run as files, so the sys.path append above does the same job.
    from scripts.foundation import _db
else:
    import _db

__all__ = [  # noqa: RUF022 -- grouped: schema names, then the re-exported _db helpers
    "M",
    "SCHEMA",
    "commit_provider_calls",
    "db_url",
    "engine",
    "eod_cutoff",
    "exec_script",
    "exec_sql",
    "psycopg2_url",
    "read_df",
    "record_provider_calls",
    "record_state",
    "scalar",
    "upsert_df",
]

SCHEMA = CONFIG.schema
M = SCHEMA


def db_url() -> str:
    """The SQLAlchemy URL from ``ATLAS_DB_URL`` in the environment — never from a file."""
    if not os.environ.get("ATLAS_DB_URL", "").strip():
        raise RuntimeError(
            "ATLAS_DB_URL is not set: export it, or put it in the repo .env "
            "(the global tree never reads frontend/.env.local)"
        )
    return _db.db_url()


def psycopg2_url() -> str:
    """The same URL as a raw libpq DSN (``psycopg2.connect`` rejects the ``+psycopg2`` suffix)."""
    return db_url().replace("postgresql+psycopg2://", "postgresql://", 1)


def _env_only[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """A ``_db`` helper behind the environment check: each one reaches ``_db.engine`` →
    ``_db.db_url`` internally, so guarding ``db_url`` alone would leave read_df/scalar/
    upsert_df on India's file fallback."""

    @functools.wraps(fn)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        db_url()
        return fn(*args, **kwargs)

    return wrapped


engine = _env_only(_db.engine)
read_df = _env_only(_db.read_df)
scalar = _env_only(_db.scalar)
exec_sql = _env_only(_db.exec_sql)
exec_script = _env_only(_db.exec_script)
upsert_df = _env_only(_db.upsert_df)


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


def commit_provider_calls(
    run_date: dt.date, calls_by_provider: Mapping[str, Mapping[str, int]]
) -> int:
    """:func:`record_provider_calls` for every adapter of a run, in its OWN short transaction.

    Called right after the fetches, BEFORE any gate can exit 2 and before the main
    transaction: the budget was spent whatever the run decides next, and a rollback of the
    data rows must not un-spend it. Nothing to record (an offline rerun) → no connection.
    Returns the number of endpoints written.
    """
    if not any(n for calls in calls_by_provider.values() for n in calls.values()):
        return 0
    conn = psycopg2.connect(psycopg2_url())
    try:
        with conn, conn.cursor() as cur:
            return sum(
                record_provider_calls(cur, run_date, provider, calls)
                for provider, calls in calls_by_provider.items()
            )
    finally:
        conn.close()


STATE_SQL = f"""
insert into {SCHEMA}.ingest_state (source, key, value, updated_at) values (%s, %s, %s, now())
on conflict (source, key) do update set value = excluded.value, updated_at = now()
"""


def record_state(cur: Any, source: str, key: str, value: Mapping[str, Any]) -> None:
    """Upsert one ``ingest_state`` watermark — a jsonb document — on the caller's cursor, the
    script's transaction, so the watermark commits with the rows it describes or not at all."""
    cur.execute(STATE_SQL, (source, key, Json(dict(value))))


if __name__ == "__main__":
    # Self-check mirrors _db's: the raw DSN must be libpq-parseable, and the anchor must be
    # a calendar date in the past.
    import psycopg2.extensions as _ext

    d = psycopg2_url()
    assert d.startswith("postgresql://") and "+psycopg2" not in d, d
    _ext.parse_dsn(d)
    print("_gdb.psycopg2_url OK →", d.rsplit("@", 1)[-1])
    print("eod_cutoff() →", eod_cutoff(), "(schema", SCHEMA + ")")

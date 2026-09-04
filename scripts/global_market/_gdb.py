"""DB access for the atlas_global (US-market) scripts — a thin sibling of
``scripts/foundation/_db.py``.

Re-exports the foundation helpers (ONE connection string, ONE statement-timeout policy,
ONE upsert) so the two market trees can never diverge on how they reach Postgres, and adds
the only two things the global tree needs of its own:

* ``SCHEMA`` / ``M`` — the schema every global script qualifies its tables with;
* ``eod_cutoff(now)`` — the ONE EOD anchor for the US session (17:00 America/New_York).

House rule (FM 2026-07-01, applied verbatim to the US market): *all calculations are as of
the last EOD; the current day is for live/intraday only.* Every writer stamps from
``eod_cutoff()`` — the ``date.today()`` bug in ``ingest_mf_holdings.py`` hid a fresh
snapshot for a month. ``eod_cutoff`` is pure (inject ``now``) so it is unit-testable.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

_FOUNDATION = Path(__file__).resolve().parents[1] / "foundation"
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

if TYPE_CHECKING:
    # Static analysis resolves the sibling tree by package path (repo root is on extraPaths);
    # at runtime the scripts run as files, so the sys.path insert above does the same job.
    from scripts.foundation import _db
else:
    import _db

db_url = _db.db_url
psycopg2_url = _db.psycopg2_url
engine = _db.engine
read_df = _db.read_df
scalar = _db.scalar
exec_sql = _db.exec_sql
exec_script = _db.exec_script
upsert_df = _db.upsert_df

SCHEMA = "atlas_global"
M = SCHEMA

NY_TZ = ZoneInfo("America/New_York")
# Regular session closes 16:00 ET; 17:00 leaves a finalisation buffer for the 1Day bar
# (India's rule uses 16:00 IST for a 15:30 close). Extended-hours prints are not scored.
SESSION_FINAL_HOUR = 17


def eod_cutoff(now: dt.datetime | None = None) -> dt.date:
    """The last COMPLETE US session's calendar date, in America/New_York.

    Returns today (ET) once ``now`` is at or past 17:00 ET, otherwise yesterday. This is an
    upper BOUND, not a trading date: weekends and holidays are not skipped here. Callers
    anchor to the latest SPY bar ``<=`` the cutoff (membership-by-presence), which lands on
    the last trading day automatically.

    ``now`` defaults to the current instant; any tz-aware datetime is converted to ET. A
    naive datetime is refused — tz-aware datetimes are a house rule, and a naive value here
    would silently anchor the whole pipeline to the box's clock.
    """
    if now is None:
        now = dt.datetime.now(NY_TZ)
    elif now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("eod_cutoff: `now` must be tz-aware (got a naive datetime)")
    local = now.astimezone(NY_TZ)
    cutoff = local.date()
    if local.hour < SESSION_FINAL_HOUR:
        cutoff -= dt.timedelta(days=1)
    return cutoff


if __name__ == "__main__":
    # Self-check mirrors _db's: the raw DSN must be libpq-parseable, and the anchor must be
    # a calendar date in the past.
    import psycopg2.extensions as _ext

    d = psycopg2_url()
    assert d.startswith("postgresql://") and "+psycopg2" not in d, d
    _ext.parse_dsn(d)
    print("_gdb.psycopg2_url OK →", d.rsplit("@", 1)[-1])
    print("eod_cutoff() →", eod_cutoff(), "(schema", SCHEMA + ")")

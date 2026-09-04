"""SQLAlchemy engine + helpers for Atlas.

Per architecture Section 2.4: one engine per process *per session timezone*, sync
``psycopg2`` driver, ``pool_pre_ping`` for transient-failure resilience, modest pool size.

Two markets share the one Supabase project, one schema each (ADR-0006):
``atlas_foundation`` (India, ``Asia/Kolkata``) and ``atlas_global`` (US,
``America/New_York``). Nothing in this module reads across that boundary.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

import structlog
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from atlas.config import Config

log = structlog.get_logger()


# Session timezones an engine may be created for — one per market plus UTC. ``SET TIME
# ZONE`` cannot take a bound parameter, so the value is interpolated into the statement,
# but only after validation against this allowlist; an arbitrary string never reaches SQL
# (the same discipline as ``_VALID_SCHEMAS`` below).
_SESSION_TIMEZONES = frozenset({"Asia/Kolkata", "America/New_York", "UTC"})


@lru_cache(maxsize=4)
def get_engine(session_tz: str = "Asia/Kolkata") -> Engine:
    """Return the process-wide SQLAlchemy engine for ``session_tz``.

    Cached per timezone so repeated callers share one pool. ``pool_pre_ping``
    recovers from Supabase transient drops without surfacing them to callers.

    Every new connection runs ``SET TIME ZONE '<session_tz>'`` — so TIMESTAMPTZ
    columns display in that zone when SELECTed. Internal storage stays UTC; this
    only affects the wire-format the client sees.

    India callers keep calling ``get_engine()`` and get IST, exactly as before.
    The global-market pipeline calls ``get_engine("America/New_York")`` and gets
    its own pool. The cache is keyed by the argument as passed, so use one
    spelling per market (zero-arg for India) to share the pool.

    Raises:
        ValueError: if ``session_tz`` is not in ``_SESSION_TIMEZONES``.
    """
    if session_tz not in _SESSION_TIMEZONES:
        raise ValueError(
            f"session_tz must be one of {sorted(_SESSION_TIMEZONES)}, got {session_tz!r}"
        )
    db_url = Config.assert_db_url()
    engine = create_engine(
        db_url,
        pool_size=Config.POOL_SIZE,
        max_overflow=Config.MAX_OVERFLOW,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_session_timezone(dbapi_connection, _connection_record):
        with dbapi_connection.cursor() as cur:
            # session_tz validated against _SESSION_TIMEZONES above — never arbitrary input.
            cur.execute(f"SET TIME ZONE '{session_tz}'")

    log.info(
        "engine_created",
        pool_size=Config.POOL_SIZE,
        max_overflow=Config.MAX_OVERFLOW,
        session_timezone=session_tz,
    )
    return engine


def sanity_check() -> dict[str, str]:
    """Connect and run a trivial query. Used by ``scripts/healthcheck.py``."""
    engine = get_engine()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        db_name = conn.execute(text("SELECT current_database()")).scalar()
        user = conn.execute(text("SELECT current_user")).scalar()
        atlas_schema_exists = conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"
                ")"
            ),
            {"schema": Config.SCHEMA_NAME},
        ).scalar()

    result = {
        "version": str(version),
        "database": str(db_name),
        "user": str(user),
        "atlas_schema_exists": str(atlas_schema_exists),
    }
    log.info("sanity_check_passed", **result)
    return result


# One schema per market, zero cross-schema references (ADR-0006). ``atlas``, ``us_atlas``
# and ``global_atlas`` were dropped with FM decision D7 (docs/table-census.md §4b–4c) and
# are deliberately absent, so a stale caller fails here rather than querying a dead schema.
_VALID_SCHEMAS = frozenset({"atlas_foundation", "atlas_global"})


def load_thresholds(
    schema: str = "atlas_foundation",
    engine: Engine | None = None,
) -> dict[str, Decimal]:
    """Read all active thresholds from ``{schema}.atlas_thresholds`` once per run.

    Default is ``atlas_foundation`` — the SINGLE source the frontend also reads, so the
    pipeline and the rendered site can never run on different weights (the atlas/fs split that
    let the stored composite use 0.6/0.4 while the funds page used 0.9/0.1).

    Per architecture 5.6: every classifier function takes thresholds as a
    parameter rather than looking them up independently. This is the single
    place those values enter the compute pipeline.

    ``atlas_global`` (US market) reads its own copy of the table with the same 13 columns;
    the two markets never share a threshold row.

    Args:
        schema: Postgres schema to read from. Validated against ``_VALID_SCHEMAS``
                (one schema per market, ADR-0006) — never interpolates user input.
        engine: Optional engine override; defaults to the process-wide (IST) engine.
    """
    if schema not in _VALID_SCHEMAS:
        raise ValueError(f"load_thresholds: schema must be one of {_VALID_SCHEMAS}, got {schema!r}")
    eng = engine or get_engine()
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT threshold_key, threshold_value "  # noqa: S608 -- schema validated against _VALID_SCHEMAS whitelist above
                f"FROM {schema}.atlas_thresholds WHERE is_active = TRUE"
            )
        ).all()
    return {key: Decimal(str(value)) for key, value in rows}


if __name__ == "__main__":
    # Quick connectivity test:  python -m atlas.db
    result = sanity_check()
    for k, v in result.items():
        print(f"  {k:24s} {v}")

"""SQLAlchemy engine + helpers for Atlas.

Per architecture Section 2.4: one engine per process *per session timezone*, sync
``psycopg2`` driver, ``pool_pre_ping`` for transient-failure resilience, modest pool size.

Two markets share the one Supabase project, one schema each (ADR-0006):
``atlas_foundation`` (India, ``Asia/Kolkata``) and ``atlas_global`` (US,
``America/New_York``). Nothing in this module reads across that boundary.
"""

from __future__ import annotations

from decimal import Decimal
from functools import cache

import structlog
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from atlas.config import MARKETS, Config

log = structlog.get_logger()


@cache  # unbounded on purpose: only our code calls this, with one zone per market
def _engine(session_tz: str, /) -> Engine:
    """Build — once per timezone value — the engine ``get_engine`` hands out.

    Positional-only so the cache key is the timezone VALUE, whatever spelling the caller
    used: ``get_engine()``, ``get_engine("Asia/Kolkata")`` and
    ``get_engine(session_tz="Asia/Kolkata")`` all land on this one pool. (A keyword-vs-
    positional cache miss once meant three pools against a session pooler with 15 slots.)
    """
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
            # psycopg2 interpolates client-side, so the server receives the literal
            # `SET TIME ZONE 'Asia/Kolkata'` (quotes escaped); Postgres itself rejects an
            # unknown zone — InvalidParameterValue: invalid value for parameter "TimeZone".
            cur.execute("SET TIME ZONE %s", (session_tz,))

    log.info(
        "engine_created",
        pool_size=Config.POOL_SIZE,
        max_overflow=Config.MAX_OVERFLOW,
        session_timezone=session_tz,
    )
    return engine


def get_engine(session_tz: str = "Asia/Kolkata") -> Engine:
    """Return the process-wide SQLAlchemy engine for ``session_tz``.

    One engine (one pool) per timezone for the life of the process, however the argument
    is spelled. ``pool_pre_ping`` recovers from Supabase transient drops without
    surfacing them to callers.

    Every new connection runs ``SET TIME ZONE '<session_tz>'`` — so TIMESTAMPTZ
    columns display in that zone when SELECTed. Internal storage stays UTC; this
    only affects the wire-format the client sees. Postgres validates the zone name,
    so a typo fails loudly on the engine's first connection rather than silently.

    India callers keep calling ``get_engine()`` and get IST, exactly as before.
    The global-market pipeline calls ``get_engine("America/New_York")`` and gets
    its own pool.
    """
    return _engine(session_tz)


_SCHEMA_EXISTS = text(
    "SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema)"
)


def sanity_check() -> dict[str, str]:
    """Connect, run a trivial query and report whether each market's schema exists.

    ``python -m atlas.db`` prints the result (the Phase 0 DoD: it must show
    ``atlas_global``). ``atlas_schema_exists`` is India's original key, kept so callers
    that predate the second market keep working; ``<schema>_exists`` is the per-market form.
    """
    engine = get_engine()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        db_name = conn.execute(text("SELECT current_database()")).scalar()
        user = conn.execute(text("SELECT current_user")).scalar()
        schema_exists = {
            m.schema: bool(conn.execute(_SCHEMA_EXISTS, {"schema": m.schema}).scalar())
            for m in MARKETS.values()
        }

    result = {
        "version": str(version),
        "database": str(db_name),
        "user": str(user),
        "atlas_schema_exists": str(schema_exists[MARKETS["india"].schema]),
        **{f"{schema}_exists": str(exists) for schema, exists in schema_exists.items()},
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

"""SQLAlchemy engine + helpers for Atlas.

Per architecture Section 2.4: a single engine per process, sync ``psycopg2``
driver, ``pool_pre_ping`` for transient-failure resilience, modest pool size.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from atlas.config import Config

log = structlog.get_logger()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine.

    Cached so repeated callers share one pool. ``pool_pre_ping`` recovers from
    Supabase transient drops without surfacing them to callers.
    """
    db_url = Config.assert_db_url()
    engine = create_engine(
        db_url,
        pool_size=Config.POOL_SIZE,
        max_overflow=Config.MAX_OVERFLOW,
        pool_pre_ping=True,
        # echo=False  — never log raw SQL in production; structlog handles audit
    )
    log.info(
        "engine_created",
        pool_size=Config.POOL_SIZE,
        max_overflow=Config.MAX_OVERFLOW,
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


def load_thresholds(engine: Engine | None = None) -> dict[str, Decimal]:
    """Read all active thresholds from ``atlas.atlas_thresholds`` once per run.

    Per architecture 5.6: every classifier function takes thresholds as a
    parameter rather than looking them up independently. This is the single
    place those values enter the compute pipeline.
    """
    eng = engine or get_engine()
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT threshold_key, threshold_value "
                "FROM atlas.atlas_thresholds WHERE is_active = TRUE"
            )
        ).all()
    return {key: Decimal(str(value)) for key, value in rows}


if __name__ == "__main__":
    # Quick connectivity test:  python -m atlas.db
    result = sanity_check()
    for k, v in result.items():
        print(f"  {k:24s} {v}")

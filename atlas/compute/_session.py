"""Compute-session helpers: timeout disablement + bulk upserts.

Design note:

* Supabase's pooler enforces a default ``statement_timeout``. Long compute
  queries (loading 2.3 M OHLCV rows, writing 50-column metric pages) hit it.
  Setting it to ``0`` per session is the canonical fix; URL-level options
  do not propagate through the session pooler.
* Wide-table ``INSERT … ON CONFLICT DO UPDATE`` via psycopg2's
  ``execute_values`` is ~100× faster than SQLAlchemy's ``to_sql`` row-mode.
  Page size 3,000 per architecture §5.2.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pandas as pd
import structlog
from psycopg2.extras import execute_values
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from atlas.db import get_engine

log = structlog.get_logger()

PAGE_SIZE = 3000
"""Rows per ``execute_values`` page. Architecture §5.2 budget; do not raise without
re-profiling Supabase pooler memory headroom."""


def df_to_pg_rows(df: pd.DataFrame) -> list[tuple[Any, ...]]:
    """Convert a DataFrame to psycopg2-safe list of tuples.

    psycopg2's adapters don't handle pandas ``pd.NA`` (``NAType``), and they
    pass ``float NaN`` through as numeric NaN — fine for ``NUMERIC`` columns,
    but it breaks ``BIGINT`` writes. This helper:

    * Coerces every column to object dtype so ``where`` can substitute None.
    * Replaces every NA / NaN / NaT with Python ``None`` (mapped to ``NULL``).
    * Boolean cols that survived as float-with-NaN come back as Python bool/None.

    Cost: one full-frame pass; ~2 s for 2.3 M rows × 50 cols on t3.large.
    """
    if df.empty:
        return []
    # astype(object) preserves NaN/pd.NA as Python objects so where() can
    # substitute None across mixed dtypes (float / Int64 / boolean / object).
    sanitized = df.astype(object).where(df.notna(), other=None)
    # itertuples is faster than .values.tolist() for wide frames and preserves
    # the column order of the DataFrame.
    return list(sanitized.itertuples(index=False, name=None))


@contextmanager
def open_compute_session(
    engine: Engine | None = None,
) -> Generator[Connection, None, None]:
    """Yield a SQLAlchemy connection with ``statement_timeout`` disabled.

    Use this for any read or write that may exceed the Supabase pooler default
    (8 s for free tier, 60 s for paid). The setting is session-scoped — when
    the ``with`` block exits, the connection returns to the pool with its
    original timeout.

    Example:

        with open_compute_session() as conn:
            df = pd.read_sql(query, conn)
    """
    eng = engine or get_engine()
    with eng.connect() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        try:
            yield conn
        except Exception:
            # On any exception, the underlying transaction may be aborted
            # (psycopg2 enters InFailedSqlTransaction). Roll back so the
            # connection is reusable, then re-raise.
            try:
                conn.rollback()
            except Exception:  # pragma: no cover - defensive
                pass
            raise
        finally:
            # Best-effort reset so the connection is clean for next checkout.
            # If the connection is already closed/aborted, swallow the error
            # rather than masking the original exception.
            try:
                conn.execute(text("SET statement_timeout = DEFAULT"))
            except Exception:  # pragma: no cover - defensive
                pass


def bulk_upsert(
    engine: Engine,
    table: str,
    columns: list[str],
    rows: list[tuple[Any, ...]],
    pk_columns: list[str],
    page_size: int = PAGE_SIZE,
) -> int:
    """Insert ``rows`` into ``table`` with ``ON CONFLICT DO UPDATE`` semantics.

    Args:
        engine: SQLAlchemy engine.
        table: Fully-qualified ``schema.table`` name.
        columns: Column names in tuple order. ``rows[i]`` must match this.
        rows: List of value tuples.
        pk_columns: Primary-key columns for the ``ON CONFLICT`` target.
        page_size: ``execute_values`` page size; default 3,000.

    Returns:
        Total rows written.

    Raises:
        psycopg2.Error: any DB error is re-raised after rollback.
    """
    if not rows:
        return 0

    col_csv = ", ".join(columns)
    update_csv = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in pk_columns)
    pk_csv = ", ".join(pk_columns)

    sql = (
        f"INSERT INTO {table} ({col_csv}) VALUES %s "  # noqa: S608 -- table/columns are internal constants, never user input
        f"ON CONFLICT ({pk_csv}) DO UPDATE SET {update_csv}"
    )

    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SET statement_timeout = 0")
        execute_values(cur, sql, rows, page_size=page_size)
        raw.commit()
        log.info(
            "bulk_upsert_complete",
            table=table,
            row_count=len(rows),
            page_size=page_size,
        )
        return len(rows)
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()

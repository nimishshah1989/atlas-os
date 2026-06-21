"""DB access for the Atlas clean data-foundation scripts.

Single source of truth for the connection string. The Supabase URL lives in
``frontend/.env.local`` as ``ATLAS_DB_URL`` (SQLAlchemy form, e.g.
``postgresql+psycopg2://...?sslmode=require``). Nothing here is secret on disk;
we read it at call time.

Cost rule (see docs/atlas-data-foundation.md §6): scripts do the heavy lifting
as plain Python and emit only small summaries — the model never streams raw rows.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / "frontend" / ".env.local"


@lru_cache(maxsize=1)
def db_url() -> str:
    """Return the SQLAlchemy DB URL from env or frontend/.env.local."""
    url = os.environ.get("ATLAS_DB_URL", "").strip()
    if not url and _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            m = re.match(r"^\s*ATLAS_DB_URL\s*=\s*(.+?)\s*$", line)
            if m:
                url = m.group(1).strip().strip('"').strip("'")
                break
    if not url:
        raise RuntimeError(
            f"ATLAS_DB_URL not found in env or {_ENV_FILE}. "
            "Format: postgresql+psycopg2://user:pass@host:5432/db?sslmode=require"
        )
    # Normalise to a psycopg2 SQLAlchemy URL.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


@lru_cache(maxsize=1)
def engine() -> Engine:
    """Process-wide SQLAlchemy engine. Modest pool; statement timeout raised
    reliably via a per-connection SET (connect_args options are silently dropped
    by the Supabase pooler)."""
    eng = create_engine(db_url(), pool_pre_ping=True,
                         connect_args={"connect_timeout": 30})

    @event.listens_for(eng, "connect")
    def _set_timeout(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("set statement_timeout = '600000'")  # 600s
        cur.close()

    return eng


def read_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a read query and return a DataFrame."""
    with engine().connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


def scalar(sql: str, params: dict | None = None):
    """Run a query returning a single scalar."""
    with engine().connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


def exec_sql(sql: str, params: dict | None = None) -> None:
    """Execute a statement (DDL/DML) in its own transaction."""
    with engine().begin() as conn:
        conn.execute(text(sql), params or {})


def exec_script(sql_text: str) -> None:
    """Execute a multi-statement SQL script (DDL). Splits on bare semicolons."""
    with engine().begin() as conn:
        for stmt in _split_statements(sql_text):
            if stmt.strip():
                conn.execute(text(stmt))


def upsert_df(table: str, df: pd.DataFrame, conflict_cols: list[str]) -> int:
    """Idempotent bulk upsert of a DataFrame into `table` (schema-qualified).

    INSERT … ON CONFLICT (conflict_cols) DO UPDATE for every non-conflict column.
    Returns the number of rows sent. NaN/NaT are coerced to NULL.
    """
    if df.empty:
        return 0
    cols = list(df.columns)
    updates = [c for c in cols if c not in conflict_cols]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in updates) or \
        f"{conflict_cols[0]} = excluded.{conflict_cols[0]}"
    collist = ", ".join(cols)
    sql = (
        f"insert into {table} ({collist}) values %s "
        f"on conflict ({', '.join(conflict_cols)}) do update set {set_clause}"
    )
    clean = df.astype(object).where(pd.notna(df), None)
    rows = list(map(tuple, clean.to_numpy()))
    raw = engine().raw_connection()
    try:
        from psycopg2.extras import execute_values
        with raw.cursor() as cur:
            execute_values(cur, sql, rows, page_size=1000)
        raw.commit()
    finally:
        raw.close()
    return len(rows)


def _split_statements(sql_text: str) -> list[str]:
    """Naive splitter: good enough for our own DDL (no dollar-quoted bodies)."""
    out, buf = [], []
    for line in sql_text.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return out

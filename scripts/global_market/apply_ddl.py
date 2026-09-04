#!/usr/bin/env python3
"""Apply the atlas_global DDL files (scripts/global_market/ddl/NN_*.sql) in order.

The DDL files are the source of truth for the schema — prod DDL is managed directly, as it
is for India — and ``migrations/versions/0002_atlas_global.py`` executes the very same files
so CI proves they apply on a fresh Postgres. Every file is idempotent (``IF NOT EXISTS``
throughout, no ``DROP``), so re-running is safe and IS the normal way to add a table: edit
the file, re-apply.

    python scripts/global_market/apply_ddl.py             # apply 00 … 06 in order
    python scripts/global_market/apply_ddl.py --dry-run   # list the files, touch nothing

One transaction per file: a failing statement rolls back that whole file, later files are
not attempted, and the process exits non-zero. The DSN comes from ``_gdb.psycopg2_url()``
(``ATLAS_DB_URL``) — point it at a scratch database to rehearse.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _gdb
import psycopg2

DDL_DIR = Path(__file__).resolve().parent / "ddl"
DDL_GLOB = "[0-9][0-9]_*.sql"


def check_no_percent(sql: str, name: str) -> None:
    """Refuse a bare '%' anywhere in a DDL file, comments included.

    psycopg2 parses '%' as a parameter marker whenever a parameter object is passed — which
    SQLAlchemy's ``exec_driver_sql`` (the migration's path) always does — and fails with an
    opaque TypeError. Enforced here too, so both apply paths accept exactly the same files.
    """
    if "%" in sql:
        raise SystemExit(f"{name}: '%' is not allowed in DDL files; write 'percent'")


def ddl_files() -> list[Path]:
    """The DDL files in apply order."""
    files = sorted(DDL_DIR.glob(DDL_GLOB))
    if not files:
        raise SystemExit(f"no {DDL_GLOB} files under {DDL_DIR}")
    for f in files:
        check_no_percent(f.read_text(), f.name)
    return files


def apply(files: list[Path], dsn: str) -> int:
    """Execute each file whole, in its own transaction (commit per file, rollback on error);
    return the number of tables now present in the schema."""
    conn = psycopg2.connect(dsn)
    try:
        for f in files:
            with conn, conn.cursor() as cur:  # `with conn` = commit on success, rollback on error
                cur.execute(f.read_text())
            print(f"applied {f.name}")
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = %s",
                (_gdb.SCHEMA,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="print the file list; apply nothing")
    args = ap.parse_args(argv)

    files = ddl_files()
    if args.dry_run:
        for f in files:
            print(f"would apply {f.relative_to(DDL_DIR.parent)}")
        return 0

    dsn = _gdb.psycopg2_url()
    print(f"target {dsn.rsplit('@', 1)[-1]}  schema {_gdb.SCHEMA}")
    try:
        n_tables = apply(files, dsn)
    except psycopg2.Error as e:
        print(f"FAILED (file rolled back, later files skipped): {e}", file=sys.stderr)
        return 1
    print(f"{_gdb.SCHEMA}: {n_tables} tables present")
    return 0


if __name__ == "__main__":
    sys.exit(main())

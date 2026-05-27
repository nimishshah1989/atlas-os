"""Core audit logic: extract table references, scan migrations, classify."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from .constants import (
    DEPRECATED_NAMES,
    JSONB_UNPACK_PATTERNS,
    KNOWN_JIP_PUBLIC_TABLES,
    KNOWN_VIEWS,
)

# SQL table-reference patterns in TypeScript template literals.
_FROM_PATTERN = re.compile(r"\bFROM\s+(?:atlas\.)(\w+)", re.IGNORECASE)
_JOIN_PATTERN = re.compile(r"\bJOIN\s+(?:atlas\.)(\w+)", re.IGNORECASE)

# Migration table creation patterns.
_OP_CREATE_TABLE_PATTERN = re.compile(r'op\.create_table\(\s*["\']([a-z_]+)["\']', re.IGNORECASE)
_RAW_CREATE_TABLE_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:atlas\.|public\.)?([a-z_]+)", re.IGNORECASE
)


class TableRef(NamedTuple):
    table: str
    source_file: str
    line_no: int


class AuditResult(NamedTuple):
    ok: bool
    missing: list[TableRef]
    deprecated: list[tuple[TableRef, str]]
    resolved: list[TableRef]
    tables_found: set[str]
    migration_tables: set[str]


def extract_table_refs(ts_file: Path) -> list[TableRef]:
    """Return all atlas-schema table references in a TypeScript query file.

    Skips lines that contain JSONB unpack function calls (those are set-returning
    functions, not table names).
    """
    refs: list[TableRef] = []
    text = ts_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    for line_no, line in enumerate(lines, start=1):
        # Skip JSONB unpack lines — the argument is a column, not a table.
        if any(p.search(line) for p in JSONB_UNPACK_PATTERNS):
            continue
        for m in _FROM_PATTERN.finditer(line):
            refs.append(TableRef(m.group(1).lower(), str(ts_file), line_no))
        for m in _JOIN_PATTERN.finditer(line):
            refs.append(TableRef(m.group(1).lower(), str(ts_file), line_no))

    return refs


def collect_migration_tables(migrations_dir: Path) -> set[str]:
    """Return every table name created in migration files.

    Handles two creation patterns:
      1. op.create_table("name", ...)  — Alembic ORM style
      2. CREATE TABLE IF NOT EXISTS atlas.name — raw SQL inside op.execute()
    """
    tables: set[str] = set()
    for mig_file in sorted(migrations_dir.glob("*.py")):
        if mig_file.name.startswith("__"):
            continue
        text = mig_file.read_text(encoding="utf-8")
        for m in _OP_CREATE_TABLE_PATTERN.finditer(text):
            tables.add(m.group(1).lower())
        for m in _RAW_CREATE_TABLE_PATTERN.finditer(text):
            tables.add(m.group(1).lower())
    return tables


def collect_documented_tables(data_source_map: Path) -> set[str]:
    """Return tables explicitly documented in data-source-map.md as known externals."""
    if not data_source_map.exists():
        return set()
    text = data_source_map.read_text(encoding="utf-8")
    # Look for any backtick-quoted atlas_ or de_ table names in the doc.
    return {m.group(1).lower() for m in re.finditer(r"`((?:atlas|de)_[a-z_]+)`", text)}


def run_audit(repo_root: Path) -> AuditResult:
    """Run the full audit and return results."""
    queries_dir = repo_root / "frontend" / "src" / "lib" / "queries" / "v6"
    migrations_dir = repo_root / "migrations" / "versions"
    data_source_map = repo_root / "docs" / "v6" / "data-source-map.md"

    migration_tables = collect_migration_tables(migrations_dir)
    documented_tables = collect_documented_tables(data_source_map)

    all_refs: list[TableRef] = []
    for ts_file in sorted(queries_dir.glob("*.ts")):
        if ts_file.name.startswith("_"):
            continue
        all_refs.extend(extract_table_refs(ts_file))
    for ts_file in sorted(queries_dir.glob("*.tsx")):
        all_refs.extend(extract_table_refs(ts_file))

    seen: set[tuple[str, str]] = set()
    missing: list[TableRef] = []
    deprecated: list[tuple[TableRef, str]] = []
    resolved: list[TableRef] = []

    for ref in all_refs:
        key = (ref.table, ref.source_file)
        if key in seen:
            continue
        seen.add(key)

        tbl = ref.table

        if tbl in DEPRECATED_NAMES:
            deprecated.append((ref, DEPRECATED_NAMES[tbl]))
            continue
        if tbl in KNOWN_VIEWS:
            resolved.append(ref)
            continue
        if tbl in KNOWN_JIP_PUBLIC_TABLES:
            resolved.append(ref)
            continue
        if tbl in migration_tables:
            resolved.append(ref)
            continue
        if tbl in documented_tables:
            resolved.append(ref)
            continue

        missing.append(ref)

    tables_found = {ref.table for ref in all_refs}
    ok = len(missing) == 0 and len(deprecated) == 0
    return AuditResult(ok, missing, deprecated, resolved, tables_found, migration_tables)

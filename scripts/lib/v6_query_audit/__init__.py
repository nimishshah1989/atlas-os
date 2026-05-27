"""v6 query audit library — table reference extraction and resolution."""

from .constants import (
    DEPRECATED_NAMES,
    JSONB_UNPACK_PATTERNS,
    KNOWN_JIP_PUBLIC_TABLES,
    KNOWN_VIEWS,
)
from .core import (
    AuditResult,
    TableRef,
    collect_documented_tables,
    collect_migration_tables,
    extract_table_refs,
    run_audit,
)

__all__ = [
    "DEPRECATED_NAMES",
    "JSONB_UNPACK_PATTERNS",
    "KNOWN_JIP_PUBLIC_TABLES",
    "KNOWN_VIEWS",
    "AuditResult",
    "TableRef",
    "collect_documented_tables",
    "collect_migration_tables",
    "extract_table_refs",
    "run_audit",
]

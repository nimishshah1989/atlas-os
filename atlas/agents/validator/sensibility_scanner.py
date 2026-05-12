"""Sensibility scanner: scan atlas tables for domain-constraint violations.

``scan_table`` fetches up to ``sample_size`` rows from a whitelisted table
(most recent first) and runs ``check_value`` on every column value. Returns
a list of ``Finding`` dataclasses, one per violation.

Only tables in ``TABLE_WHITELIST`` may be scanned. SQL is generated
dynamically but the table name comes exclusively from this constant.

Phase A scope: ``insensible_value`` finding class only. Other classes (data
gap, inconsistency, calc error, etc.) ship in later phases.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.agents.validator.models import Finding
from atlas.agents.validator.sensibility_rules import RuleViolation, check_value

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Table whitelist — only user-visible metrics tables; never system tables
# ---------------------------------------------------------------------------

TABLE_WHITELIST: frozenset[str] = frozenset(
    [
        "atlas_stock_metrics_daily",
        "atlas_stock_states_daily",
        "atlas_sector_metrics_daily",
        "atlas_market_regime_daily",
        "atlas_fund_lens_daily",
    ]
)

# Primary-key columns per table — used to build ``identifier`` strings.
# Fallback to row index if a table's PK columns are absent.
_PK_COLUMNS: dict[str, list[str]] = {
    "atlas_stock_metrics_daily": ["instrument_id", "date"],
    "atlas_stock_states_daily": ["instrument_id", "date"],
    "atlas_sector_metrics_daily": ["sector", "date"],
    "atlas_market_regime_daily": ["date"],
    "atlas_fund_lens_daily": ["instrument_id", "date"],
}

# Severity mapping: P0 for inf/NaN/future-date rules; P1 for all others
_P0_RULES: frozenset[str] = frozenset(
    [
        "any_numeric: finite",
        "any_numeric: not_nan",
        "date: <= today",
    ]
)


# Finding dataclass lives in atlas.agents.validator.models and is re-exported above.

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _severity_from_rule(rule: str) -> str:
    return "P0" if rule in _P0_RULES else "P1"


def _build_identifier(row: dict[str, Any], table: str) -> str:
    pk_cols = _PK_COLUMNS.get(table, [])
    if pk_cols:
        parts = [f"{c}={row.get(c, '?')}" for c in pk_cols if c in row]
        if parts:
            return ",".join(parts)
    # Fallback: use first few keys
    return ",".join(f"{k}={v}" for k, v in list(row.items())[:2])


def _scan_row(row: dict[str, Any], table: str) -> list[Finding]:
    """Return all violations found in a single row dict.

    Exported (with leading underscore) so tests can call it directly without
    a real DB connection.
    """
    findings: list[Finding] = []
    identifier = _build_identifier(row, table)

    for col, val in row.items():
        violation: RuleViolation | None = check_value(col, val, table)
        if violation is None:
            continue

        severity = _severity_from_rule(violation.rule)
        # Truncate evidence row to avoid JSONB bloat; include only the
        # offending column plus the PK columns for traceability.
        pk_cols = _PK_COLUMNS.get(table, [])
        evidence_row = {
            k: (str(v) if not isinstance(v, str | int | float | type(None)) else v)
            for k, v in row.items()
            if k in pk_cols or k == col
        }
        findings.append(
            Finding(
                finding_class="insensible_value",
                severity=severity,
                surface=f"{table}.{col}",
                identifier=identifier,
                expected_value=violation.rule,
                actual_value=str(val),
                evidence={"row": evidence_row, "message": violation.message},
                remediation=(
                    "Investigate compute pipeline for this column. "
                    "Check for zero-division guards or NaN propagation."
                ),
            )
        )

    return findings


def _build_query(table: str, schema: str, sample_size: int) -> tuple[str, dict[str, Any]]:
    """Return (sql, params) for sampling the table."""
    # All whitelisted tables have a 'date' column; order most-recent-first.
    sql = (
        f"SELECT * FROM {schema}.{table} ORDER BY date DESC NULLS LAST "  # noqa: S608 -- table from TABLE_WHITELIST constant, validated
        f"LIMIT :limit"
    )
    return sql, {"limit": sample_size}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_table(
    engine: Engine,
    table: str,
    schema: str = "atlas",
    sample_size: int = 10_000,
) -> list[Finding]:
    """Scan up to ``sample_size`` rows of ``table`` for sensibility violations.

    Args:
        engine: SQLAlchemy engine (read-only access is sufficient).
        table: Name of the table to scan. Must be in ``TABLE_WHITELIST``.
        schema: Postgres schema (default: 'atlas').
        sample_size: Max rows to inspect (most recent first).

    Returns:
        List of ``Finding`` objects, one per violation. Empty list = clean.

    Raises:
        ValueError: If ``table`` is not in ``TABLE_WHITELIST``.
    """
    if table not in TABLE_WHITELIST:
        raise ValueError(
            f"Table '{table}' is not in TABLE_WHITELIST. "
            f"Allowed tables: {sorted(TABLE_WHITELIST)}"
        )

    sql, params = _build_query(table, schema, sample_size)
    log.info("scan_table_start", table=table, sample_size=sample_size)

    findings: list[Finding] = []
    row_count = 0

    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        col_names = list(result.keys())

        for raw_row in result:
            row_count += 1
            row_dict: dict[str, Any] = dict(zip(col_names, raw_row, strict=True))
            findings.extend(_scan_row(row_dict, table))

    p0 = sum(1 for f in findings if f.severity == "P0")
    p1 = sum(1 for f in findings if f.severity == "P1")
    log.info(
        "scan_table_done",
        table=table,
        rows_scanned=row_count,
        findings_total=len(findings),
        p0=p0,
        p1=p1,
    )
    return findings

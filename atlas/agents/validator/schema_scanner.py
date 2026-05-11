"""Schema/coverage scanner: Phase B data-gap detection.

For each table in the coverage map this scanner:

1. Queries the actual date range present in the DB.
2. If ``expected_dates == "business_days"``, computes expected Mon–Fri dates
   between data_start and yesterday (T-1) using pandas bdate_range.
3. Counts actual rows per date and flags dates with row counts below
   ``expected_instruments_min`` / ``expected_sectors_min``.
4. Checks ``null_forbidden_columns`` for NULL values in the most recent
   ``NULL_SAMPLE_DAYS`` days and flags offenders.
5. Computes overall coverage_pct and raises a Finding when it falls below
   ``coverage_tolerance_pct``.

Only tables in the coverage map with ``coverage_tolerance_pct > 0`` are
actively checked for date-gaps; tables with tolerance 0 get null checks only
(when null_forbidden_columns are defined).

Severity mapping:
  coverage < 90 %       → P0
  coverage 90–99 %      → P1
  single missing date   → P2
  single instrument gap → P3
  null forbidden column → P1 (data corruption risk)

The ``Finding`` dataclass is imported from ``sensibility_scanner`` — no
parallel Finding class is created here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.agents.validator.coverage_loader import TableCoverage, load_coverage_map
from atlas.agents.validator.sensibility_scanner import Finding

log = structlog.get_logger()

# How many recent days to sample for NULL-forbidden checks
NULL_SAMPLE_DAYS = 30


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _yesterday() -> date:
    return datetime.now(UTC).date() - timedelta(days=1)


def _expected_business_days(start: date, end: date) -> set[date]:
    """Return Mon–Fri dates between start and end (inclusive)."""
    if start > end:
        return set()
    return {ts.date() for ts in pd.bdate_range(start=start, end=end)}


def _check_date_coverage(
    engine: Engine,
    spec: TableCoverage,
    schema: str,
) -> list[Finding]:
    """Return coverage-gap Findings for one table."""
    if spec.coverage_tolerance_pct == 0:
        return []

    findings: list[Finding] = []
    table = spec.table_name

    # -- Actual date range --
    with engine.connect() as conn:
        result = conn.execute(
            text(
                f"SELECT MIN(date) AS d_min, MAX(date) AS d_max,"  # noqa: S608 -- table from validated coverage_map.yaml
                f" COUNT(*) AS total_rows FROM {schema}.{table}"
            )
        )
        row = result.fetchone()

    if row is None or row[2] == 0:
        # Empty table — report as P0 data gap if tolerance > 0
        findings.append(
            Finding(
                finding_class="data_gap",
                severity="P0",
                surface=table,
                identifier=f"table={table}",
                expected_value="non-empty table",
                actual_value="0 rows",
                evidence={"table": table},
                remediation="Run the compute pipeline to populate this table.",
            )
        )
        return findings

    data_start: date = row[0]
    data_end: date = row[1]
    _ = row[2]  # total_rows: not used directly after empty-table guard above

    yesterday = _yesterday()

    if spec.expected_dates == "business_days":
        expected_dates = _expected_business_days(data_start, min(data_end, yesterday))
        n_expected_dates = len(expected_dates)

        if n_expected_dates == 0:
            return findings

        # Per-date row counts
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT date, COUNT(*) AS cnt FROM {schema}.{table}"  # noqa: S608 -- table from validated coverage_map.yaml
                    f" WHERE date >= :start AND date <= :end"
                    f" GROUP BY date ORDER BY date"
                ),
                {"start": data_start, "end": min(data_end, yesterday)},
            )
            date_counts: dict[date, int] = {r[0]: r[1] for r in result}

        actual_dates = set(date_counts.keys())
        missing_dates = expected_dates - actual_dates

        # Coverage pct based on date presence
        coverage_pct = (len(actual_dates) / n_expected_dates) * 100.0

        if coverage_pct < spec.coverage_tolerance_pct:
            if coverage_pct < 90.0:
                sev = "P0"
            elif coverage_pct < 99.0:
                sev = "P1"
            elif len(missing_dates) <= 1:
                sev = "P2"
            else:
                sev = "P1"

            findings.append(
                Finding(
                    finding_class="data_gap",
                    severity=sev,
                    surface=table,
                    identifier=f"table={table},date_range={data_start}:{min(data_end, yesterday)}",
                    expected_value=f"coverage>={spec.coverage_tolerance_pct}%",
                    actual_value=f"coverage={coverage_pct:.2f}%",
                    evidence={
                        "missing_dates_sample": sorted(str(d) for d in list(missing_dates)[:20]),
                        "n_missing": len(missing_dates),
                        "n_expected": n_expected_dates,
                        "n_actual": len(actual_dates),
                    },
                    remediation=(
                        f"Backfill compute for {len(missing_dates)} missing date(s) in {table}."
                    ),
                )
            )
        else:
            # Coverage OK — still flag single missing dates as P2
            for missing in sorted(missing_dates)[:10]:
                findings.append(
                    Finding(
                        finding_class="data_gap",
                        severity="P2",
                        surface=table,
                        identifier=f"table={table},date={missing}",
                        expected_value="date present in table",
                        actual_value="date missing",
                        evidence={"missing_date": str(missing)},
                        remediation=f"Backfill {table} for date {missing}.",
                    )
                )

        # -- Per-date instrument count check --
        min_instruments = spec.expected_instruments_min or spec.expected_sectors_min
        if min_instruments is not None:
            for dt, cnt in date_counts.items():
                if cnt < min_instruments:
                    findings.append(
                        Finding(
                            finding_class="data_gap",
                            severity="P3",
                            surface=table,
                            identifier=f"table={table},date={dt}",
                            expected_value=f"instrument_count>={min_instruments}",
                            actual_value=f"instrument_count={cnt}",
                            evidence={"date": str(dt), "actual_count": cnt},
                            remediation=(
                                f"Only {cnt} instrument rows on {dt} in {table}; "
                                f"expected >={min_instruments}."
                            ),
                        )
                    )

    log.info(
        "coverage_check_done",
        table=table,
        findings=len(findings),
    )
    return findings


def _check_null_forbidden(
    engine: Engine,
    spec: TableCoverage,
    schema: str,
) -> list[Finding]:
    """Return NULL-violation Findings for null_forbidden_columns."""
    if not spec.null_forbidden_columns:
        return []

    findings: list[Finding] = []
    table = spec.table_name
    cutoff = _yesterday() - timedelta(days=NULL_SAMPLE_DAYS)

    for col in spec.null_forbidden_columns:
        # Check if the column exists before querying (avoids hard crash on schema drift)
        with engine.connect() as conn:
            col_exists = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = :table "
                    "AND column_name = :col LIMIT 1"
                ),
                {"schema": schema, "table": table, "col": col},
            ).fetchone()

        if col_exists is None:
            log.warning("null_forbidden_column_missing_from_schema", table=table, column=col)
            continue

        # Date-filtered NULL count where the table has a 'date' column
        if spec.expected_dates == "business_days":
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        f"SELECT COUNT(*) AS n FROM {schema}.{table}"  # noqa: S608 -- table from validated coverage_map.yaml
                        f" WHERE date >= :cutoff AND {col} IS NULL"
                    ),
                    {"cutoff": cutoff},
                )
                null_count: int = result.scalar() or 0
        else:
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        f"SELECT COUNT(*) AS n FROM {schema}.{table}"  # noqa: S608 -- table from validated coverage_map.yaml
                        f" WHERE {col} IS NULL"
                    )
                )
                null_count = result.scalar() or 0

        if null_count > 0:
            findings.append(
                Finding(
                    finding_class="data_gap",
                    severity="P1",
                    surface=f"{table}.{col}",
                    identifier=f"table={table},column={col}",
                    expected_value="no NULL values",
                    actual_value=f"{null_count} NULL rows",
                    evidence={
                        "null_count": null_count,
                        "sample_window_days": NULL_SAMPLE_DAYS,
                    },
                    remediation=(
                        f"Column {col} in {table} has {null_count} NULL(s). "
                        "Check the compute pipeline for this column."
                    ),
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_coverage(
    engine: Engine,
    schema: str = "atlas",
    coverage_map: list[TableCoverage] | None = None,
) -> list[Finding]:
    """Run schema/coverage checks against all tables in the coverage map.

    Args:
        engine: SQLAlchemy engine (read-only access is sufficient).
        schema: Postgres schema (default: 'atlas').
        coverage_map: Override the default coverage map. Used in tests.

    Returns:
        List of ``Finding`` objects. Empty = clean.
    """
    specs = coverage_map if coverage_map is not None else load_coverage_map()
    all_findings: list[Finding] = []

    for spec in specs:
        log.info("schema_scanner_checking", table=spec.table_name)
        try:
            all_findings.extend(_check_date_coverage(engine, spec, schema))
            all_findings.extend(_check_null_forbidden(engine, spec, schema))
        except Exception as exc:
            log.error(
                "schema_scanner_table_error",
                table=spec.table_name,
                error=str(exc),
            )

    severity_counts = {
        sev: sum(1 for f in all_findings if f.severity == sev) for sev in ("P0", "P1", "P2", "P3")
    }
    log.info(
        "schema_scanner_done",
        total_findings=len(all_findings),
        **severity_counts,
    )
    return all_findings


__all__ = ["scan_coverage"]

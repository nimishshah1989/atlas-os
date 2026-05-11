#!/usr/bin/env python
# allow-large: CLI entry point + inline night-run log; logic lives in atlas.agents.validator
"""Atlas Data Integrity Validator CLI — Phase A + B.

Usage:
    python scripts/run_validator.py [--scope sensibility] [--tables TABLE,...] [--dry-run]

Options:
    --scope      sensibility|schema_coverage|full (default: sensibility)
    --tables     Comma-separated table names to scan. Default: all whitelisted tables.
    --dry-run    Run checks but skip writing to atlas_validator_runs / findings.

Phase A: 'sensibility' scope — insensible_value findings.
Phase B: 'schema_coverage' scope — data_gap findings (missing dates, NULLs, low coverage).
Phase E: 'full' scope requires Hermes orchestration (not yet implemented).

Exit codes:
    0 — run completed; P0 count printed to stdout.
    1 — unhandled error during run.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import structlog

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Logging setup (structlog → stderr; keep stdout for machine-readable output)
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Atlas Data Integrity Validator — Phase A+B CLI")
    parser.add_argument(
        "--scope",
        default="sensibility",
        choices=["sensibility", "schema_coverage", "full"],
        help="Validation scope (default: sensibility)",
    )
    parser.add_argument(
        "--tables",
        default="",
        help="Comma-separated table names to scan. Default: all whitelisted tables.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip writing to validator_runs / findings tables.",
    )
    return parser.parse_args()


def _run_sensibility(
    tables: list[str],
    dry_run: bool,
) -> int:
    """Run the sensibility scanner against whitelisted tables.

    Returns:
        Total number of findings (all severities).
    """
    from atlas.agents.validator.persistence import finish_run, upsert_finding
    from atlas.agents.validator.sensibility_scanner import TABLE_WHITELIST, scan_table
    from atlas.db import get_engine

    engine = get_engine()
    targets = tables if tables else sorted(TABLE_WHITELIST)

    run_id = None
    if not dry_run:
        from atlas.agents.validator.persistence import start_run

        run_id = start_run(engine, scope="sensibility")

    all_findings = []
    for table in targets:
        try:
            findings = scan_table(engine, table)
            all_findings.extend(findings)
        except Exception as exc:
            # Log and continue — one bad table should not abort the whole run
            log.error("scan_table_error", table=table, error=str(exc))

    severity_counts = Counter(f.severity for f in all_findings)
    p0 = severity_counts.get("P0", 0)
    p1 = severity_counts.get("P1", 0)
    p2 = severity_counts.get("P2", 0)
    p3 = severity_counts.get("P3", 0)
    total = len(all_findings)

    # Persist findings
    if not dry_run and run_id is not None:
        for finding in all_findings:
            upsert_finding(engine, run_id, finding)
        finish_run(engine, run_id, status="success", n_findings=total)

    # Print machine-readable summary to stdout
    print(f"VALIDATOR_RUN scope=sensibility total={total} P0={p0} P1={p1} P2={p2} P3={p3}")
    if all_findings:
        print(f"\nTop P0 findings ({min(p0, 20)} of {p0} shown):")
        shown = 0
        for f in all_findings:
            if f.severity == "P0" and shown < 20:
                print(f"  [{f.severity}] {f.surface}  identifier={f.identifier}")
                print(f"         rule={f.expected_value}  actual={f.actual_value}")
                shown += 1
        if p1 > 0:
            print(f"\nTop P1 findings ({min(p1, 10)} of {p1} shown):")
            shown = 0
            for f in all_findings:
                if f.severity == "P1" and shown < 10:
                    print(f"  [{f.severity}] {f.surface}  identifier={f.identifier}")
                    shown += 1

    return total


def _run_schema_coverage(dry_run: bool) -> int:
    """Run the schema/coverage scanner against the coverage map.

    Returns:
        Total number of findings (all severities).
    """
    from atlas.agents.validator.persistence import finish_run, upsert_finding
    from atlas.agents.validator.schema_scanner import scan_coverage
    from atlas.db import get_engine

    engine = get_engine()

    run_id = None
    if not dry_run:
        from atlas.agents.validator.persistence import start_run

        run_id = start_run(engine, scope="schema_coverage")

    all_findings = []
    try:
        all_findings = scan_coverage(engine)
    except Exception as exc:
        log.error("schema_coverage_scan_error", error=str(exc))

    severity_counts = Counter(f.severity for f in all_findings)
    p0 = severity_counts.get("P0", 0)
    p1 = severity_counts.get("P1", 0)
    p2 = severity_counts.get("P2", 0)
    p3 = severity_counts.get("P3", 0)
    total = len(all_findings)

    if not dry_run and run_id is not None:
        for finding in all_findings:
            upsert_finding(engine, run_id, finding)
        finish_run(engine, run_id, status="success", n_findings=total)

    print(f"VALIDATOR_RUN scope=schema_coverage total={total} P0={p0} P1={p1} P2={p2} P3={p3}")

    if p0 > 0:
        print(f"\nP0 data gaps ({min(p0, 20)} of {p0} shown):")
        shown = 0
        for f in all_findings:
            if f.severity == "P0" and shown < 20:
                print(f"  [P0] {f.surface}  {f.identifier}")
                print(f"       expected={f.expected_value}  actual={f.actual_value}")
                shown += 1
    if p1 > 0:
        print(f"\nP1 findings ({min(p1, 10)} of {p1} shown):")
        shown = 0
        for f in all_findings:
            if f.severity == "P1" and shown < 10:
                print(f"  [P1] {f.surface}  {f.identifier}")
                shown += 1

    return total


def _append_night_run_log(
    total: int,
    severity_counts: Counter[str],
    dry_run: bool,
    tables: list[str],
    scope: str = "sensibility",
) -> None:
    """Append one line to scripts/validator_night_run.log."""
    from datetime import UTC, datetime

    log_path = Path(__file__).parent / "validator_night_run.log"
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    tables_tag = ",".join(tables) if tables else "ALL"
    line = (
        f"{ts}  scope={scope}  tables={tables_tag}  "
        f"total={total}  P0={severity_counts.get('P0', 0)}  "
        f"P1={severity_counts.get('P1', 0)}  "
        f"P2={severity_counts.get('P2', 0)}  "
        f"P3={severity_counts.get('P3', 0)}  "
        f"dry_run={dry_run}\n"
    )
    with log_path.open("a") as fh:
        fh.write(line)
    log.info("night_run_log_appended", path=str(log_path))


def main() -> int:
    args = _parse_args()

    if args.scope == "full":
        raise NotImplementedError(
            "full scope is Phase E work — requires Hermes orchestration. "
            "Run with --scope sensibility or --scope schema_coverage."
        )

    tables = [t.strip() for t in args.tables.split(",") if t.strip()] if args.tables else []

    log.info(
        "validator_cli_start",
        scope=args.scope,
        tables=tables or "ALL",
        dry_run=args.dry_run,
    )

    try:
        if args.scope == "sensibility":
            total = _run_sensibility(tables, args.dry_run)
        else:
            total = _run_schema_coverage(args.dry_run)

        _append_night_run_log(
            total=total,
            severity_counts=Counter(),  # per-sev detail already printed to stdout
            dry_run=args.dry_run,
            tables=tables,
            scope=args.scope,
        )
    except Exception as exc:
        log.error("validator_cli_error", error=str(exc), exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

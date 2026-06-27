#!/usr/bin/env python
"""Atlas Phase C Validator — Frontend Route Crawler CLI.

Crawls the 7 configured Atlas frontend routes using Playwright,
diffs DOM values against SQL source-of-truth, and persists findings
to atlas_validator_findings.

Usage:
    python scripts/crawl_frontend.py [--dry-run] [--base-url URL]

Options:
    --dry-run       Run crawler and print findings but skip DB writes.
    --base-url URL  Override ATLAS_BASE_URL env var.

Required env vars:
    ATLAS_BASE_URL  — Atlas frontend URL (e.g. https://atlas.jslwealth.in)
    ATLAS_PASSWORD  — Password for atlas_auth cookie (same as frontend ATLAS_PASSWORD)
    ATLAS_DB_URL    — PostgreSQL DSN (for SQL source-of-truth lookups + persistence)

Exit codes:
    0 — completed; P0 count printed to stdout.
    1 — unhandled error.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

import structlog

log = structlog.get_logger()

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
    parser = argparse.ArgumentParser(description="Atlas Phase C Frontend Route Crawler")
    parser.add_argument("--dry-run", action="store_true", help="Skip DB writes")
    parser.add_argument("--base-url", default="", help="Override ATLAS_BASE_URL")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    from atlas.agents.validator.persistence import finish_run, start_run, upsert_finding
    from atlas.agents.validator.route_crawler import run_crawl

    from atlas.db import get_engine

    engine = get_engine()

    run_id = None
    if not args.dry_run:
        run_id = start_run(engine, scope="frontend_diff")

    base_url = args.base_url or None

    try:
        all_findings = run_crawl(engine, base_url=base_url)
    except Exception as exc:
        log.error("crawl_frontend_error", error=str(exc), exc_info=True)
        if run_id is not None:
            finish_run(engine, run_id, status="failed", n_findings=0)
        return 1

    severity_counts: Counter[str] = Counter(f.severity for f in all_findings)
    p0 = severity_counts.get("P0", 0)
    p1 = severity_counts.get("P1", 0)
    p2 = severity_counts.get("P2", 0)
    total = len(all_findings)

    if not args.dry_run and run_id is not None:
        for finding in all_findings:
            # route is embedded in finding.evidence["route"]
            route = finding.evidence.get("route") if finding.evidence else None
            upsert_finding(engine, run_id, finding, route=route)
        finish_run(engine, run_id, status="success", n_findings=total)

    print(f"VALIDATOR_RUN scope=frontend_diff total={total} P0={p0} P1={p1} P2={p2}")

    if p0 > 0:
        print(f"\nP0 frontend diffs ({min(p0, 20)} shown):")
        shown = 0
        for f in all_findings:
            if f.severity == "P0" and shown < 20:
                print(f"  [P0] {f.surface}  id={f.identifier}")
                print(f"       expected={f.expected_value}  actual={f.actual_value}")
                shown += 1

    if p1 > 0:
        print(f"\nP1 frontend diffs ({min(p1, 10)} shown):")
        shown = 0
        for f in all_findings:
            if f.severity == "P1" and shown < 10:
                print(f"  [P1] {f.surface}  id={f.identifier}")
                shown += 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

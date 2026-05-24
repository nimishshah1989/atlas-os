"""Thin CLI wrapper for the daily inference orchestrator (#46).

Invocation::

    python -m atlas.inference.cli --target-date 2026-05-23
    python -m atlas.inference.cli --dry-run
    python -m atlas.inference.cli --target-date 2026-05-23 --code-commit-sha abc123

Defaults
========
* ``--target-date`` defaults to "yesterday IST" — the typical daily cron
  schedule fires at ~21:00 IST writing yesterday's snapshot.

Exit codes
==========
* ``0`` — clean run, no errors collected.
* ``1`` — pipeline completed but non-fatal errors collected (e.g. regime
  row absent, fallback applied). Operations should investigate.
* ``2`` — a fatal exception was raised mid-pipeline. The provenance row
  was attempted with partial state.

Output
======
A JSON object printed to stdout summarising the run. Stable shape so cron
log scrapers can parse it.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy.engine import Engine

from atlas.db import get_engine
from atlas.inference.daily import _result_to_json, compute_daily

log = structlog.get_logger()


# IST is UTC+5:30 — used for the "yesterday IST" default. We compute it
# locally rather than depending on ``zoneinfo`` because some EC2 base
# images lack the tzdata package.
_IST_OFFSET = timedelta(hours=5, minutes=30)


def _yesterday_ist() -> date:
    """Yesterday in IST — the conventional daily cron target_date.

    The cron fires after the IST trading close (~16:00 IST) and writes
    today's snapshot. When invoked overnight (~21:00 IST) the
    intent is "the trading day that just ended" — i.e. today IST. When
    invoked the next morning (e.g. 06:00 IST T+1) the intent is still
    "the most recent completed trading day" — i.e. yesterday IST.

    We compromise on **yesterday IST** as the safe default: re-runs on
    T+1 morning still target the right date, and overnight runs can
    explicitly pass ``--target-date $(date +%Y-%m-%d)`` when they want
    today.
    """
    now_ist = datetime.now(UTC) + _IST_OFFSET
    return (now_ist - timedelta(days=1)).date()


def _make_engine() -> Engine:
    """Thin wrapper around :func:`atlas.db.get_engine` for test patchability."""
    return get_engine()


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser. Factored out so tests can introspect it."""
    parser = argparse.ArgumentParser(
        prog="atlas.inference.cli",
        description="Atlas v6 daily inference cron orchestrator",
    )
    parser.add_argument(
        "--target-date",
        type=date.fromisoformat,
        default=None,
        help="ISO date YYYY-MM-DD (default: yesterday IST)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run all phases; skip every DB write (no scorecard/regime/signal_calls rows)",
    )
    parser.add_argument(
        "--code-commit-sha",
        default=None,
        help="explicit commit SHA override (else ATLAS_GIT_SHA env → git rev-parse)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — returns the exit code.

    Exposed as a function (rather than running at module load) so tests
    can drive it without ``subprocess``.
    """
    args = _build_parser().parse_args(argv)

    target_date = args.target_date or _yesterday_ist()
    engine = _make_engine()

    try:
        result = compute_daily(
            target_date=target_date,
            db_engine=engine,
            write=not args.dry_run,
            code_commit_sha=args.code_commit_sha,
        )
    except (RuntimeError, OSError, ValueError, AssertionError) as exc:
        # Fatal exception escaped the orchestrator after provenance write.
        # Surface for the cron log and exit 2.
        log.error(
            "inference_cli_fatal",
            target_date=str(target_date),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        print(
            f'{{"error": "{type(exc).__name__}: {exc}", '
            f'"target_date": "{target_date.isoformat()}"}}'
        )
        return 2

    print(_result_to_json(result))
    return 0 if not result.errors else 1


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())

"""SP05: generate (and optionally persist) the daily Atlas brief.

Usage::

    # Stub mode - print the DailyMarketContext, no Claude call (CI-safe).
    python scripts/generate_daily_brief.py --dry-run-stub

    # Generate via Claude and print only; do NOT persist.
    python scripts/generate_daily_brief.py --dry-run

    # Generate and persist to atlas.atlas_daily_briefs.
    python scripts/generate_daily_brief.py --persist

    # Generate for a specific historical date.
    python scripts/generate_daily_brief.py --as-of 2026-05-12 --persist

Exit codes:
    0 - success
    2 - invalid arguments
    3 - context is empty (no MV data); brief refused
    4 - GROQ_API_KEY missing (only when not --dry-run-stub)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import structlog
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.db import get_engine  # noqa: E402
from atlas.intelligence.briefs import (  # noqa: E402
    build_daily_context,
    generate_brief,
    persist_brief,
)

log = structlog.get_logger()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate the daily Atlas brief from SP02 materialized views."
    )
    p.add_argument(
        "--as-of",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="As-of date (YYYY-MM-DD). Defaults to mv_current_market_regime.date.",
    )
    grp = p.add_mutually_exclusive_group()
    grp.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print; do NOT persist.",
    )
    grp.add_argument(
        "--persist",
        action="store_true",
        help="Generate and persist to atlas_daily_briefs.",
    )
    p.add_argument(
        "--dry-run-stub",
        action="store_true",
        help=(
            "Build context and print it; skip the Claude call entirely. "
            "Used by CI when GROQ_API_KEY is not available."
        ),
    )
    return p.parse_args(argv)


def _resolve_as_of(engine, override: date | None) -> date | None:
    if override is not None:
        return override
    with engine.connect() as c:
        row = c.execute(text("SELECT MAX(date) FROM atlas.mv_current_market_regime")).fetchone()
    return row[0] if row and row[0] else None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    engine = get_engine()
    as_of = _resolve_as_of(engine, args.as_of)
    if as_of is None:
        print(
            "No data in mv_current_market_regime - cannot generate brief.",
            file=sys.stderr,
        )
        return 3

    log.info(
        "daily_brief_cli_start",
        as_of=as_of.isoformat(),
        dry_run=args.dry_run,
        persist=args.persist,
        stub=args.dry_run_stub,
    )

    ctx = build_daily_context(engine, as_of=as_of)
    if ctx.regime == "Unknown" and not ctx.top_sectors:
        print(
            "Context is empty (no MV data). Refusing to call Claude.",
            file=sys.stderr,
        )
        return 3

    if args.dry_run_stub:
        print("--- DailyMarketContext (stub mode, no Claude call) ---")
        print(json.dumps(ctx.to_dict(), indent=2))
        return 0

    if not os.environ.get("GROQ_API_KEY"):
        print(
            "GROQ_API_KEY is not set. Export it or re-run with "
            "--dry-run-stub to test the context build only.",
            file=sys.stderr,
        )
        return 4

    brief = generate_brief(ctx)

    print("--- Daily Atlas Brief ---")
    print(f"As-of: {ctx.as_of.isoformat()}")
    print(f"Regime: {ctx.regime} ({ctx.regime_delta})")
    print(f"Summary: {brief.regime_summary}")
    print()
    print(brief.narrative)
    print()
    print("Key themes:")
    for t in brief.key_themes:
        print(f"  - {t}")
    print(f"Tokens: in={brief.input_tokens} out={brief.output_tokens}")

    if args.persist:
        persist_brief(engine, context=ctx, brief=brief)
        print("\nPersisted to atlas.atlas_daily_briefs.")
    else:
        print("\n(dry-run - not persisted)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

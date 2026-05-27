"""CLI for the 24-cell matrix sweep (#25 Phase 0.5g).

Invocation::

    python -m atlas.discovery.cli --mode synthetic --dry-run
    python -m atlas.discovery.cli --mode synthetic --output-html /tmp/matrix.html
    python -m atlas.discovery.cli --mode supabase                  # NotImplementedError today

The synthetic mode generates a deterministic ~100-instrument universe and
runs the full 24-cell sweep end-to-end. The Mid-cap 12m Pullback + Severely
Broken cells should validate (proves the pipeline); the other 22 cells
should produce ``no_conviction`` (proves the per-tenure IC floor).

Exit codes
==========
* ``0`` — sweep completed successfully.
* ``1`` — sweep ran but produced 0 validated cells (warning condition;
  pipeline ran but no signal cleared the floor).
* ``2`` — a fatal exception was raised mid-pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog
from sqlalchemy.engine import Engine

from atlas.discovery.engine import WalkForwardSweep
from atlas.discovery.matrix_status import generate_matrix_status_html

log = structlog.get_logger()


def _make_engine() -> Engine:
    """Thin wrapper around :func:`atlas.db.get_engine` for test patchability."""
    from atlas.db import get_engine

    return get_engine()


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser. Factored out so tests can introspect it."""
    parser = argparse.ArgumentParser(
        prog="atlas.discovery.cli",
        description="Atlas v6 24-cell matrix discovery sweep (Phase 0.5g)",
    )
    parser.add_argument(
        "--mode",
        default="synthetic",
        choices=["synthetic", "cache", "supabase", "ec2"],
        help="data-source mode (default: synthetic; cache/supabase/ec2 are stubs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="don't persist to DB; just compute and (optionally) write HTML",
    )
    parser.add_argument(
        "--output-html",
        default=None,
        help="path to write the matrix-status HTML (optional)",
    )
    parser.add_argument(
        "--synthetic-seed",
        type=int,
        default=42,
        help="seed for synthetic-mode universe (default: 42)",
    )
    return parser


def run_sweep_cli(argv: list[str] | None = None) -> int:
    """CLI entry point — returns the exit code.

    Exposed as a function (rather than running at module load) so tests
    can drive it without ``subprocess``.
    """
    args = _build_parser().parse_args(argv)

    engine = None
    if not args.dry_run:
        try:
            engine = _make_engine()
        except (RuntimeError, OSError, ValueError) as exc:
            log.error("engine_construction_failed", error=str(exc))
            print(
                json.dumps(
                    {
                        "error": f"engine construction failed: {exc}",
                        "mode": args.mode,
                    }
                )
            )
            return 2

    try:
        sweep = WalkForwardSweep(
            mode=args.mode,
            db_engine=engine,
            synthetic_seed=args.synthetic_seed,
        )
        result = sweep.run_full_matrix()
        if not args.dry_run:
            sweep.persist(result)
    except NotImplementedError as exc:
        log.error("mode_not_implemented", mode=args.mode, error=str(exc))
        print(
            json.dumps(
                {
                    "error": f"mode not implemented: {exc}",
                    "mode": args.mode,
                }
            )
        )
        return 2
    except (RuntimeError, OSError, ValueError, AssertionError) as exc:
        log.error(
            "sweep_fatal",
            mode=args.mode,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        print(
            json.dumps(
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "mode": args.mode,
                }
            )
        )
        return 2

    if args.output_html:
        out_path = Path(args.output_html)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        generate_matrix_status_html(result, output_path=out_path)
        log.info("matrix_html_written", path=str(out_path))

    summary = {
        "mode": result.mode,
        "total_cells": len(result.results),
        "validated": result.validated_count,
        "no_conviction": result.no_conviction_count,
        "run_started_at": result.run_started_at.isoformat(),
        "run_completed_at": result.run_completed_at.isoformat(),
        "output_html": args.output_html,
    }
    print(json.dumps(summary, indent=2, default=str))

    return 0 if result.validated_count > 0 else 1


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(run_sweep_cli())

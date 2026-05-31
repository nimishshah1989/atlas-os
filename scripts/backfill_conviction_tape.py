"""Backfill wrapper for atlas.inference.conviction_tape.

Thin shell over the conviction-tape CLI that loops over a date range.

Live DB writes are gated on ``.supabase-write-approved`` at the repo
root — without that marker the script emits SQL files to
``--output-dir`` instead of executing.

Usage::

    python scripts/backfill_conviction_tape.py \\
        --start 2026-05-01 --end 2026-05-22 \\
        --output-dir ./out/conviction
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    p.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Where the per-day SQL files land",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repo root (used to look for .supabase-write-approved marker)",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Top-K candidates per cell (forward-compat; currently unused)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start > end:
        print("ERROR: --start must be <= --end", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    cur = start
    n_days = 0
    while cur <= end:
        print(f"--- conviction-tape backfill: {cur.isoformat()} ---")
        cmd = [
            sys.executable,
            "-m",
            "atlas.inference.conviction_tape",
            "--date",
            cur.isoformat(),
            "--top-k",
            str(args.top_k),
            "--output-dir",
            str(args.output_dir),
            "--repo-root",
            str(args.repo_root),
            "--backfill",
        ]
        result = subprocess.run(cmd, check=False)  # noqa: S603 — fixed argv
        if result.returncode != 0:
            print(
                f"conviction-tape backfill failed on {cur.isoformat()} (exit={result.returncode})",
                file=sys.stderr,
            )
            return result.returncode
        cur = cur + timedelta(days=1)
        n_days += 1
    print(f"backfill complete: {n_days} day(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

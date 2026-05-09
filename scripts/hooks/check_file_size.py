#!/usr/bin/env python3
"""Pre-commit hook: block files with > 400 lines.

Reasoning: large files become silos. The atlas-os modulith depends on
clear bounded contexts; once a file passes ~400 LOC it almost always has
multiple responsibilities and should be split into a sub-package.

Whitelisted: migration files, generated lockfiles, third-party vendor
copies. Generated assets are excluded by extension.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

LIMIT = 400

# Files in these globs are allowed to exceed the limit.
WHITELIST_PREFIXES: tuple[str, ...] = (
    "migrations/versions/",  # migration files often have full schema dumps
    "decisions.jsonl",
    "package-lock.json",
    "frontend/package-lock.json",
)

# Skip these extensions entirely.
SKIP_EXT: tuple[str, ...] = (
    ".lock",
    ".min.js",
    ".min.css",
    ".svg",
    ".png",
    ".jpg",
    ".pdf",
    ".jsonl",
    ".log",
    ".tsbuildinfo",
)


def staged_files() -> list[str]:
    out = subprocess.check_output(  # noqa: S603
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_whitelisted(path: str) -> bool:
    if any(path.startswith(p) for p in WHITELIST_PREFIXES):
        return True
    if any(path.endswith(ext) for ext in SKIP_EXT):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=LIMIT)
    args = parser.parse_args()

    failures: list[str] = []
    for f in staged_files():
        if is_whitelisted(f):
            continue
        p = Path(f)
        if not p.exists() or not p.is_file():
            continue
        # Only inspect source-like files
        if p.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".sh"}:
            continue
        try:
            n = sum(1 for _ in p.open("r", encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if n > args.limit:
            failures.append(f"{f}: {n} lines (limit {args.limit})")

    if failures:
        print("✗ File-size limit exceeded — split into sub-package:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nRule: a single file should have one bounded purpose. When a file approaches\n"
            "400 LOC it almost always has multiple responsibilities. Split into a\n"
            "sub-package (e.g. atlas/compute/sectors.py → atlas/compute/sectors/{loaders,\n"
            "compute,classify,states,pipeline}.py).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

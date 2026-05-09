#!/usr/bin/env python3
"""Pre-commit hook: tiered file-size limits.

Different file kinds have different reasonable lengths. A 700-line test
suite is normal; a 700-line route handler is a smell. The hook applies
the right tier per file type, with an explicit escape valve for genuinely
cohesive long files.

Tiers:
  source                  600 LOC
  tests                   800 LOC
  frontend page shells    250 LOC   (page.tsx files should be thin)
  schemas / generated     no limit  (whitelisted)

Escape valve:
  Add ``# allow-large: <reason>`` (Python) or
      ``// allow-large: <reason>`` (TS/JS) to any line in the file.
  This bypasses the limit for THAT file and forces the author to write
  a one-line justification in the file itself — visible to every reviewer.
  The reason becomes the load-bearing artifact, not the line count.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Per-tier limits.
LIMIT_SOURCE = 600
LIMIT_TEST = 800
LIMIT_PAGE_SHELL = 250

# Files in these globs are allowed to exceed any limit (no enforcement).
WHITELIST_PREFIXES: tuple[str, ...] = (
    "migrations/versions/",
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

# Source-like extensions we inspect.
SOURCE_EXT: frozenset[str] = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".sql",
        ".sh",
    }
)

# Page-shell pattern (Next.js App Router).
PAGE_SHELL_RE = re.compile(r"frontend/src/app/.*/(page|layout)\.tsx?$")

# Test file pattern.
TEST_RE = re.compile(
    r"(^|/)tests/.*\.py$"
    r"|(^|/)test_[^/]+\.py$"
    r"|\.test\.[tj]sx?$"
    r"|\.spec\.[tj]sx?$"
    r"|/__tests__/"
)

# Escape valve marker — case-sensitive on purpose to make it deliberate.
ALLOW_LARGE_RE = re.compile(r"(?:#|//)\s*allow-large:\s*(\S.*)")


def staged_files() -> list[str]:
    out = subprocess.check_output(  # noqa: S603
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],  # noqa: S607
        text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_whitelisted(path: str) -> bool:
    if any(path.startswith(p) for p in WHITELIST_PREFIXES):
        return True
    if any(path.endswith(ext) for ext in SKIP_EXT):
        return True
    return False


def tier_limit(path: str) -> int:
    """Return the LOC limit applicable to this file."""
    if PAGE_SHELL_RE.search(path):
        return LIMIT_PAGE_SHELL
    if TEST_RE.search(path):
        return LIMIT_TEST
    return LIMIT_SOURCE


def has_allow_large_marker(p: Path) -> tuple[bool, str | None]:
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                m = ALLOW_LARGE_RE.search(line)
                if m:
                    return True, m.group(1).strip()
    except (OSError, UnicodeDecodeError):
        pass
    return False, None


def line_count(p: Path) -> int:
    try:
        with p.open("r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except (OSError, UnicodeDecodeError):
        return 0


def main() -> int:
    failures: list[str] = []
    overrides: list[str] = []

    for f in staged_files():
        if is_whitelisted(f):
            continue
        p = Path(f)
        if not p.exists() or not p.is_file() or p.suffix not in SOURCE_EXT:
            continue

        n = line_count(p)
        limit = tier_limit(f)
        if n <= limit:
            continue

        marker, reason = has_allow_large_marker(p)
        if marker:
            overrides.append(f"{f}: {n} lines (limit {limit}) — allow-large: {reason}")
            continue

        failures.append(f"{f}: {n} lines (limit {limit})")

    if overrides:
        # Print on stdout — informational, not blocking.
        for line in overrides:
            print(f"  override-noted: {line}")

    if failures:
        print("✗ File-size limit exceeded:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nLimits:\n"
            f"  source files                 {LIMIT_SOURCE} LOC\n"
            f"  test files                   {LIMIT_TEST} LOC\n"
            f"  page.tsx / layout.tsx        {LIMIT_PAGE_SHELL} LOC (should be thin shells)\n"
            "  migrations / lockfiles       no limit (whitelisted)\n"
            "\nIf the file is genuinely cohesive at its current size, add a one-line\n"
            "justification to it: `# allow-large: <reason>` (Python) or\n"
            "`// allow-large: <reason>` (TS/JS). The reason becomes the load-bearing\n"
            "artifact reviewers can challenge — line count alone never is.\n"
            "\nOtherwise: split the file into a sub-package. Common pattern:\n"
            "  atlas/compute/sectors.py → atlas/compute/sectors/{loaders,compute,\n"
            "  classify,states,pipeline}.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

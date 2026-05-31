#!/usr/bin/env python3
"""Pre-commit hook: warn when methodology thresholds appear hardcoded.

The atlas.atlas_thresholds table is the single source of truth for all
classifier cutoffs (RS quintiles, AUM percentages, regime thresholds, etc.).
Code should read them via load_thresholds(), not hardcode them.

This is a HEURISTIC check: it scans staged .py files in atlas/compute/ for
module-level numeric assignments that look like methodology thresholds (e.g.
RS_QUINTILE_TOP = 0.80, FUND_STRONG_HOLDINGS_MIN_PCT = 0.60). If a name
matches a methodology pattern AND isn't in the documented allowlist, the
hook flags it.

Suppress per-line with `# noqa: threshold` if the constant is genuinely
not a methodology threshold (e.g. a numerical-stability epsilon).
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

# Constants whose values legitimately live in code (not thresholds).
ALLOWLIST: set[str] = {
    "MIN_COVERAGE_PCT",  # data-quality floor, not user-tunable
    "HIGH_UNKNOWN_THRESHOLD",  # logging-only warning floor
    # Existing module-level fallbacks — authoritative values live in
    # atlas.atlas_thresholds (seeded by migration 022). These constants
    # remain as fallback defaults; remove from allowlist when call sites
    # are fully refactored to load_thresholds().
    "RS_QUINTILE_TOP",
    "RS_QUINTILE_BOTTOM",
}

# Names that look like classifier thresholds.
SUSPICIOUS_PATTERNS = re.compile(
    r"^(RS_|FUND_|REGIME_|SECTOR_|STOCK_|ETF_)?"
    r"(.+_)?"
    r"(THRESHOLD|MIN|MAX|TOP|BOTTOM|PCT|QUINTILE|CUTOFF)"
    r"(_PCT|_MIN|_MAX|_THRESHOLD)?$"
)


def staged_compute_files() -> list[Path]:
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        text=True,
    )
    paths = [Path(line.strip()) for line in out.splitlines() if line.strip()]
    return [p for p in paths if p.suffix == ".py" and str(p).startswith("atlas/compute/")]


def find_threshold_assignments(path: Path) -> list[tuple[int, str, float]]:
    """Return list of (line_no, name, value) for module-level numeric constants."""
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    suppress_lines = {
        i + 1 for i, line in enumerate(text.splitlines()) if "# noqa: threshold" in line
    }

    out: list[tuple[int, str, float]] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, (int, float)):
            continue
        if node.lineno in suppress_lines:
            continue
        out.append((node.lineno, target.id, float(node.value.value)))
    return out


def main() -> int:
    failures: list[str] = []
    for f in staged_compute_files():
        for line_no, name, value in find_threshold_assignments(f):
            if name in ALLOWLIST:
                continue
            if not SUSPICIOUS_PATTERNS.match(name):
                continue
            failures.append(
                f"{f}:{line_no}: {name} = {value!r}  "
                "→ move to atlas_thresholds table or add `# noqa: threshold`"
            )

    if failures:
        print(
            "⚠ Hardcoded threshold-like constants detected:",
            file=sys.stderr,
        )
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nRule: methodology thresholds belong in atlas.atlas_thresholds,\n"
            "loaded once per run via atlas.db.load_thresholds(). This lets\n"
            "you tune behavior without redeploys and gives an audit trail.\n"
            "If the constant is NOT a methodology threshold, append\n"
            "`# noqa: threshold` to the line.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

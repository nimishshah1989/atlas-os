#!/usr/bin/env python3
"""Pyright baseline + ratchet gate.

The atlas tree carries pre-existing pyright debt (hundreds of errors that
predate any type gate). Fixing it all at once would be a huge, risky diff —
many errors are Decimal/float money coercions where a careless cast changes a
calculation. So instead of blocking on the whole backlog we *baseline* it and
*ratchet*: CI fails only if the per-file error count goes UP.

Policy
------
- ``ci/pyright-baseline.json`` records {relative_path: error_count} plus a
  ``_total`` for visibility. It is the grandfathered debt.
- A file regresses if its current error count exceeds its baseline count.
  Files absent from the baseline have an implicit baseline of 0 — so any NEW
  or CHANGED file must be pyright-clean.
- Fixing errors never fails the gate. Burn the baseline down over time and
  re-run ``--update`` to lock in the lower numbers (the gate then holds the
  new floor).

We key on per-file COUNTS, not exact (file, line, rule) identities: line
numbers churn on every edit, which would make the baseline impossibly noisy.
The trade-off — a file could swap one error for a different one with no net
count change and slip through — is acceptable; the gate's job is preventing
per-file regression, and total burn-down is tracked via ``_total``.

Usage
-----
    python scripts/ci/pyright_ratchet.py            # check (CI default)
    python scripts/ci/pyright_ratchet.py --update    # regenerate the baseline

Invoke under ``uv run --extra dev`` so ``pyright`` is on PATH.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "ci" / "pyright-baseline.json"


def run_pyright() -> dict:
    """Run pyright in JSON mode and return the parsed report.

    Pyright exits non-zero whenever it finds errors; that is expected here and
    is NOT the pass/fail signal — this gate decides pass/fail. We only treat a
    failure to produce parseable JSON as fatal.
    """
    proc = subprocess.run(
        ["pyright", "--outputjson"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        sys.stderr.write("pyright produced no JSON output. stderr:\n")
        sys.stderr.write(proc.stderr)
        sys.exit(2)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"could not parse pyright JSON: {exc}\n")
        sys.stderr.write(proc.stdout[:2000])
        sys.exit(2)


def error_counts(report: dict) -> Counter[str]:
    """Count error-severity diagnostics per repo-relative file path."""
    counts: Counter[str] = Counter()
    for diag in report.get("generalDiagnostics", []):
        if diag.get("severity") != "error":
            continue
        path = Path(diag["file"])
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = path.as_posix()
        counts[rel] += 1
    return counts


def load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    data = json.loads(BASELINE_PATH.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def write_baseline(counts: Counter[str]) -> None:
    ordered = dict(sorted(counts.items()))
    payload = {"_total": sum(counts.values()), **ordered}
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    update = "--update" in sys.argv[1:]
    report = run_pyright()
    counts = error_counts(report)
    total = sum(counts.values())

    if update:
        write_baseline(counts)
        print(f"pyright baseline updated: {total} errors across {len(counts)} files")
        print(f"  wrote {BASELINE_PATH.relative_to(REPO_ROOT)}")
        return 0

    baseline = load_baseline()
    regressions: list[tuple[str, int, int]] = []
    for path, current in sorted(counts.items()):
        allowed = baseline.get(path, 0)
        if current > allowed:
            regressions.append((path, allowed, current))

    baseline_total = sum(baseline.values())
    print(f"pyright: {total} errors now / {baseline_total} baselined")

    if regressions:
        print("\nBLOCKED: pyright error count increased in these files:")
        for path, allowed, current in regressions:
            print(f"  {path}: {allowed} -> {current} (+{current - allowed})")
        print(
            "\nFix the new type errors, or — if you genuinely reduced errors "
            "elsewhere and this is intentional — run:\n"
            "  uv run --extra dev python scripts/ci/pyright_ratchet.py --update\n"
            "and commit the updated ci/pyright-baseline.json."
        )
        return 1

    if total < baseline_total:
        print(
            f"\nNice — {baseline_total - total} fewer errors than baseline. "
            "Lock it in:\n"
            "  uv run --extra dev python scripts/ci/pyright_ratchet.py --update"
        )
    print("\npyright ratchet: OK (no per-file regressions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

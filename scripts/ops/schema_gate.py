#!/usr/bin/env python3
"""SINGLE-SCHEMA GATE — the mechanical definition of "G1 done".

Scans ONLY the live-imported files (the scripts the orchestrator runs + the modules
they import + the reachable frontend queries) for any DB reference to a schema other
than atlas_foundation. Prints every hit as file:line and exits 1 if the count is
not zero. No eyeballing, no orphan-file confusion — a provable number.

    python scripts/ops/schema_gate.py            # full report + exit code
    python scripts/ops/schema_gate.py --count    # just the number
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Live backend: orchestrator-invoked scripts + the atlas modules they import.
BACKEND = [
    "scripts/foundation/ingest_kite.py",
    "scripts/foundation/ingest_bhavcopy.py",
    "scripts/foundation/fetch_delivery.py",
    "scripts/foundation/backfill_delivery.py",
    "scripts/foundation/ingest_filings.py",
    "scripts/foundation/ingest_events.py",
    "scripts/foundation/ingest_insider.py",
    "scripts/foundation/ingest_shareholding.py",
    "scripts/foundation/ingest_screener.py",
    "scripts/foundation/ingest_nav.py",
    "scripts/foundation/ingest_mf_holdings.py",
    "scripts/foundation/ingest_fund_master.py",
    "scripts/foundation/compute_all.py",
    "scripts/foundation/build_index_metrics.py",
    "scripts/foundation/rollup_sectors.py",
    "scripts/foundation/build_fund_rank_history.py",
    "scripts/foundation/build_breadth_series.py",
    "scripts/foundation/validate_lenses.py",
    "scripts/foundation/harness.py",
    "scripts/lens_daily.py",
    "scripts/kite_autologin.py",
    "scripts/ops/freshness_guard.py",
    "scripts/ops/qa_weekly.py",
    "atlas/compute/regime.py",
    "atlas/compute/breadth.py",
    "atlas/compute/indices.py",
    "atlas/intraday/auth.py",
]
BACKEND += [str(p.relative_to(REPO)) for p in (REPO / "atlas/lenses").rglob("*.py")]

# Live frontend: reachable queries only (v6/* + the 3 reachable root files).
_V6 = REPO / "frontend/src/lib/queries/v6"
FRONTEND = [str(p.relative_to(REPO)) for p in _V6.glob("*.ts") if "__tests__" not in str(p)]
FRONTEND += [
    "frontend/src/lib/queries/health.ts",
    "frontend/src/lib/queries/lens-scores.ts",
    "frontend/src/lib/queries/regime.ts",
]

# A DB reference to another schema, in SQL context — not a python import, not a comment.
SQL_REF = re.compile(r"\b(atlas|public|us_atlas|global_atlas|mfwatch)\.[a-z_][a-z0-9_]+", re.I)
IMPORT = re.compile(r"^\s*(from|import)\s+atlas\.")
COMMENT = re.compile(r"^\s*(#|//|\*)")
# atlas.<submodule> that are code modules, not schemas:
CODE_MODULES = {
    "lenses",
    "compute",
    "db",
    "intraday",
    "config",
    "intelligence",
    "api",
    "primitives",
}


def scan(files: list[str]) -> list[str]:
    hits = []
    for rel in files:
        p = REPO / rel
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if IMPORT.match(line) or COMMENT.match(line):
                continue
            for m in SQL_REF.finditer(line):
                schema, obj = m.group(0).split(".", 1)
                if schema == "atlas" and obj in CODE_MODULES:
                    continue
                hits.append(f"{rel}:{i}: {m.group(0)}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", action="store_true")
    args = ap.parse_args()
    be, fe = scan(BACKEND), scan(FRONTEND)
    total = len(be) + len(fe)
    if args.count:
        print(total)
        return 0 if total == 0 else 1
    print("=== SINGLE-SCHEMA GATE — references outside atlas_foundation in LIVE code ===")
    print(f"\nBACKEND ({len(be)}):")
    for h in be:
        print(f"  {h}")
    print(f"\nFRONTEND ({len(fe)}):")
    for h in fe:
        print(f"  {h}")
    print(f"\nTOTAL outside-schema references in live path: {total}")
    print("GATE:", "PASS ✅ (single schema)" if total == 0 else "FAIL ❌ — must reach 0 for G1")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

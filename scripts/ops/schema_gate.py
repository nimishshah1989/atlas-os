#!/usr/bin/env python3
"""SCHEMA GATE — one schema per tree, zero cross-schema references (rule #1, ADR-0006).

Atlas serves two markets from one Supabase project, one schema each:

    india    atlas_foundation   the LIVE India path: orchestrator-invoked scripts + the atlas
                                modules they import + the reachable frontend/ queries
    global   atlas_global       scripts/global_market/**, atlas/global_market/**,
                                frontend-global/src/lib/queries/**  (globbed — the tree may
                                not exist yet; an empty tree scans clean)

A tree may name ONLY its own schema in SQL context. Any other `<schema>.<object>` token —
the sibling market's schema, or one of the dropped schemas (`atlas`, `us_atlas`,
`global_atlas`, `mfwatch`, `public`) — is a hit, printed as file:line. Imports
(`from atlas.lenses …`) and comment lines are not SQL and are skipped; so is
`atlas.<code module>` (a docstring naming a module, not the dead `atlas` schema).

Why a mechanical gate: the first US platform (`us_atlas`, dropped under FM decision D7) and
the `atlas.*` / `foundation_staging.*` mirror both rotted through quiet cross-schema reads —
two copies of one fact, disagreeing with nobody watching (docs/table-census.md §4b, §6).
No eyeballing, no orphan-file confusion — a provable number, run in CI for both trees.

    python scripts/ops/schema_gate.py                        # both trees: report + exit code
    python scripts/ops/schema_gate.py --market india         # one tree
    python scripts/ops/schema_gate.py --market global --count  # just the number

Exit 1 on any hit in the selected tree(s).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------------------
# india tree — LIVE files only: orchestrator-invoked scripts + the atlas modules they
# import + the reachable frontend queries. Orphan files are not this gate's business.
# ---------------------------------------------------------------------------------------
INDIA_BACKEND = [
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
INDIA_BACKEND += [str(p.relative_to(REPO)) for p in (REPO / "atlas/lenses").rglob("*.py")]

# Live frontend: reachable queries only (v6/* + the 3 reachable root files).
_V6 = REPO / "frontend/src/lib/queries/v6"
INDIA_FRONTEND = [str(p.relative_to(REPO)) for p in _V6.glob("*.ts") if "__tests__" not in str(p)]
INDIA_FRONTEND += [
    "frontend/src/lib/queries/health.ts",
    "frontend/src/lib/queries/lens-scores.ts",
    "frontend/src/lib/queries/regime.ts",
]


# ---------------------------------------------------------------------------------------
# global tree — everything under the global paths. Globbed, not listed: the tree is new
# and every file in it is in scope; a missing directory simply contributes no files.
# ---------------------------------------------------------------------------------------
def _rglob(rel_dir: str, pattern: str) -> list[str]:
    root = REPO / rel_dir
    if not root.is_dir():
        return []
    return sorted(
        str(p.relative_to(REPO)) for p in root.rglob(pattern) if "__tests__" not in p.parts
    )


GLOBAL_BACKEND = _rglob("scripts/global_market", "*.py") + _rglob("atlas/global_market", "*.py")
GLOBAL_FRONTEND = _rglob("frontend-global/src/lib/queries", "*.ts")

# A DB reference to a foreign schema, in SQL context. Each tree forbids the dropped schemas
# plus the OTHER market's schema; its own schema is never in its pattern.
_DROPPED = "atlas|public|us_atlas|global_atlas|mfwatch"
_OBJ = r"\.[a-z_][a-z0-9_]+"
FOREIGN_INDIA = re.compile(rf"\b({_DROPPED}|atlas_global){_OBJ}", re.I)
FOREIGN_GLOBAL = re.compile(rf"\b({_DROPPED}|atlas_foundation){_OBJ}", re.I)
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
    "global_market",
    "portfolio",
}


@dataclass(frozen=True)
class Tree:
    market: str
    schema: str  # the ONE schema this tree may reference
    backend: tuple[str, ...]
    frontend: tuple[str, ...]
    foreign: re.Pattern[str]  # any match in SQL context is a cross-schema reference


TREES: dict[str, Tree] = {
    "india": Tree(
        "india", "atlas_foundation", tuple(INDIA_BACKEND), tuple(INDIA_FRONTEND), FOREIGN_INDIA
    ),
    "global": Tree(
        "global", "atlas_global", tuple(GLOBAL_BACKEND), tuple(GLOBAL_FRONTEND), FOREIGN_GLOBAL
    ),
}


def scan(files: tuple[str, ...], foreign: re.Pattern[str]) -> list[str]:
    hits = []
    for rel in files:
        p = REPO / rel
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if IMPORT.match(line) or COMMENT.match(line):
                continue
            for m in foreign.finditer(line):
                schema, obj = m.group(0).split(".", 1)
                if schema == "atlas" and obj in CODE_MODULES:
                    continue
                hits.append(f"{rel}:{i}: {m.group(0)}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--market",
        choices=("india", "global", "all"),
        default="all",
        help="which tree(s) to scan (default: all)",
    )
    ap.add_argument("--count", action="store_true", help="print only the total hit count")
    args = ap.parse_args()
    selected = list(TREES) if args.market == "all" else [args.market]

    report = {
        m: (scan(TREES[m].backend, TREES[m].foreign), scan(TREES[m].frontend, TREES[m].foreign))
        for m in selected
    }
    total = sum(len(be) + len(fe) for be, fe in report.values())
    if args.count:
        print(total)
        return 0 if total == 0 else 1

    print("=== SCHEMA GATE — one schema per tree, zero cross-schema references (ADR-0006) ===")
    for m in selected:
        tree = TREES[m]
        be, fe = report[m]
        n_files = sum((REPO / f).exists() for f in tree.backend + tree.frontend)
        note = "" if n_files else " (tree not present yet — nothing to scan)"
        print(f"\n[{m}] may reference only `{tree.schema}` — {n_files} live files scanned{note}")
        print(f"  BACKEND ({len(be)}):")
        for h in be:
            print(f"    {h}")
        print(f"  FRONTEND ({len(fe)}):")
        for h in fe:
            print(f"    {h}")
    print(f"\nTOTAL cross-schema references: {total}")
    print(
        "GATE:",
        "PASS ✅ (one schema per tree)"
        if total == 0
        else "FAIL ❌ — must be 0 (rule #1: one schema per market, zero cross-schema references)",
    )
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

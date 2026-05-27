"""v6 Data Availability Audit.

Greps every frontend/src/lib/queries/v6/*.ts file for SQL table references
(FROM and JOIN patterns) and verifies each table either:
  a) has a matching op.create_table() or CREATE TABLE in migrations/versions/, OR
  b) is documented in docs/v6/data-source-map.md as a known external/view/JSONB dependency.

Exits 0 with a summary table on full success.
Exits 1 with "MISSING TABLE: <name> referenced in <file>" messages on failure.

Usage:
    python scripts/v6_data_availability_audit.py [--repo-root <path>]

Autonomous resolutions (from plan patch header 2026-05-26):
  - atlas_universe_snapshot   → RENAMED to atlas_universe_stocks; flag if found
  - atlas_sector_breadth_daily → DERIVED from atlas_scorecard_daily.features JSONB; flag if FROM found
  - atlas_fund_holdings_history → REPLACED by atlas_fund_scorecard.top_holdings JSONB; flag if FROM found
  - atlas_ledger_public       → RENAMED to atlas_ledger; flag if _public suffix found

Implementation: delegates to scripts/lib/v6_query_audit/ (constants + core).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure scripts/lib is importable regardless of working directory.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.v6_query_audit import AuditResult, run_audit  # noqa: E402


def print_summary(result: AuditResult, repo_root: Path) -> None:
    """Print a human-readable summary to stdout."""
    queries_dir = repo_root / "frontend" / "src" / "lib" / "queries" / "v6"
    ts_files = sorted(queries_dir.glob("*.ts"))

    print("\n=== v6 Data Availability Audit ===")
    print(f"Query modules scanned : {len(ts_files)}")
    print(f"Unique tables found   : {len(result.tables_found)}")
    print(f"Migration tables known: {len(result.migration_tables)}")
    print(f"Resolved references   : {len(result.resolved)}")
    print()

    if result.deprecated:
        print(f"DEPRECATED TABLE REFERENCES ({len(result.deprecated)}):")
        for ref, reason in result.deprecated:
            print(f"  DEPRECATED: {ref.table}")
            print(f"    in  : {ref.source_file}:{ref.line_no}")
            print(f"    why : {reason}")
        print()

    if result.missing:
        print(f"MISSING TABLES ({len(result.missing)}):")
        for ref in result.missing:
            print(f"  MISSING TABLE: {ref.table} referenced in " f"{ref.source_file}:{ref.line_no}")
        print()

    if result.ok:
        print("RESULT: PASS — all table references resolved.")
    else:
        total = len(result.missing) + len(result.deprecated)
        print(f"RESULT: FAIL — {total} unresolved reference(s).")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root directory (default: parent of scripts/).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root: Path = args.repo_root.resolve()

    result = run_audit(repo_root)
    print_summary(result, repo_root)

    if not result.ok:
        for ref in result.missing:
            print(
                f"MISSING TABLE: {ref.table} referenced in {ref.source_file}",
                file=sys.stderr,
            )
        for ref, reason in result.deprecated:
            print(
                f"DEPRECATED TABLE: {ref.table} in {ref.source_file} — {reason}",
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

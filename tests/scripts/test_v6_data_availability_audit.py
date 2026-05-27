"""Tests for scripts/v6_data_availability_audit.py.

Three cases:
  Case 1 — All tables in a query file exist in migrations → audit passes (exit 0).
  Case 2 — A query file references a missing table not in migrations or data-source-map.md
            → audit exits 1 with the specific table name in stderr.
  Case 3 — A JSONB unpack pattern (jsonb_to_recordset(top_holdings)) is correctly
            recognized as a non-table dependency and NOT flagged as missing.

Fixtures are pre-created .ts files in tests/fixtures/v6_query_samples/.
Tests build a temp repo structure pointing at those fixtures.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module path setup — ensure scripts/lib is importable
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "v6_query_samples"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib.v6_query_audit import run_audit  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture: minimal "repo" directory tree
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """Build a minimal repo skeleton in a temp directory.

    Creates:
      <tmp>/frontend/src/lib/queries/v6/  ← target for query .ts files
      <tmp>/migrations/versions/          ← target for migration .py files
      <tmp>/docs/v6/                      ← target for data-source-map.md
    """
    (tmp_path / "frontend" / "src" / "lib" / "queries" / "v6").mkdir(parents=True)
    (tmp_path / "migrations" / "versions").mkdir(parents=True)
    (tmp_path / "docs" / "v6").mkdir(parents=True)
    yield tmp_path


def _write_query(repo: Path, filename: str, content: str) -> Path:
    """Write a TypeScript query file into the v6 queries directory."""
    target = repo / "frontend" / "src" / "lib" / "queries" / "v6" / filename
    target.write_text(content, encoding="utf-8")
    return target


def _write_migration(repo: Path, filename: str, content: str) -> Path:
    """Write a migration file into migrations/versions/."""
    target = repo / "migrations" / "versions" / filename
    target.write_text(content, encoding="utf-8")
    return target


def _write_data_source_map(repo: Path, content: str) -> Path:
    """Write a data-source-map.md stub."""
    target = repo / "docs" / "v6" / "data-source-map.md"
    target.write_text(content, encoding="utf-8")
    return target


def _v6_dir(repo: Path) -> Path:
    """Return the v6 queries directory path."""
    return repo / "frontend" / "src" / "lib" / "queries" / "v6"


def _mig_dir(repo: Path) -> Path:
    """Return the migrations/versions directory path."""
    return repo / "migrations" / "versions"


def _copy_fixture(src_name: str, repo: Path, dest_dir: Path) -> None:
    """Copy a fixture file to a destination directory inside the temp repo."""
    shutil.copy(FIXTURES_DIR / src_name, dest_dir / src_name)


def _copy_mock_migration(repo: Path) -> None:
    """Copy mock_migration_001.py to the temp repo migrations/versions/ dir."""
    shutil.copy(
        FIXTURES_DIR / "mock_migration_001.py",
        _mig_dir(repo) / "001_mock.py",
    )


# ---------------------------------------------------------------------------
# Case 1 — All tables exist in migrations → passes
# ---------------------------------------------------------------------------


class TestAllTablesResolved:
    """Audit finds every table referenced in a query file in migration files.

    Expects: audit passes (ok=True), no missing refs, no deprecated refs.
    """

    def test_audit_passes_when_all_tables_in_migrations(self, temp_repo: Path) -> None:
        # Copy the valid query fixture
        _copy_fixture("valid_query.ts", temp_repo, _v6_dir(temp_repo))

        # Copy the mock migration that creates atlas_universe_stocks + atlas_stock_metrics_daily
        _copy_mock_migration(temp_repo)

        result = run_audit(temp_repo)

        assert result.ok is True, f"Expected ok=True but got missing={result.missing}"
        assert result.missing == []
        assert result.deprecated == []

    def test_tables_found_matches_query_content(self, temp_repo: Path) -> None:
        _copy_fixture("valid_query.ts", temp_repo, _v6_dir(temp_repo))
        _copy_mock_migration(temp_repo)

        result = run_audit(temp_repo)

        # valid_query.ts references atlas_universe_stocks and atlas_stock_metrics_daily
        assert "atlas_universe_stocks" in result.tables_found
        assert "atlas_stock_metrics_daily" in result.tables_found

    def test_migration_tables_collected_from_both_patterns(self, temp_repo: Path) -> None:
        """Both op.create_table() and CREATE TABLE IF NOT EXISTS patterns extracted."""

        _write_migration(
            temp_repo,
            "001_dual_pattern.py",
            """
op.create_table(
    "atlas_foo_table",
    sa.Column("id", sa.UUID),
)

op.execute(sa.text(
    "CREATE TABLE IF NOT EXISTS atlas.atlas_bar_table (id uuid)"
))
""",
        )

        result = run_audit(temp_repo)

        assert "atlas_foo_table" in result.migration_tables
        assert "atlas_bar_table" in result.migration_tables


# ---------------------------------------------------------------------------
# Case 2 — Missing table → exits 1 with table name in stderr
# ---------------------------------------------------------------------------


class TestMissingTableDetected:
    """Audit finds a referenced table NOT in migrations or data-source-map.md.

    Expects: ok=False, the specific table name appears in missing list.
    """

    def test_missing_table_detected(self, temp_repo: Path) -> None:
        # Copy fixture with a missing table reference
        _copy_fixture("missing_table_query.ts", temp_repo, _v6_dir(temp_repo))

        # Provide the mock migration (atlas_universe_stocks exists)
        _copy_mock_migration(temp_repo)

        result = run_audit(temp_repo)

        assert result.ok is False
        missing_names = [r.table for r in result.missing]
        assert "atlas_nonexistent_table_xyz" in missing_names

    def test_missing_table_carries_source_file(self, temp_repo: Path) -> None:
        _copy_fixture("missing_table_query.ts", temp_repo, _v6_dir(temp_repo))
        _copy_mock_migration(temp_repo)

        result = run_audit(temp_repo)

        missing = [r for r in result.missing if r.table == "atlas_nonexistent_table_xyz"]
        assert len(missing) >= 1
        # source_file should contain the query filename
        assert "missing_table_query.ts" in missing[0].source_file

    def test_documented_table_in_map_resolves(self, temp_repo: Path) -> None:
        """A table documented in data-source-map.md is NOT flagged as missing."""

        _write_query(
            temp_repo,
            "custom_query.ts",
            "SELECT * FROM atlas.atlas_some_external_view v WHERE v.date = $1",
        )

        # No migration creates atlas_some_external_view
        _write_migration(temp_repo, "001_empty.py", "# empty migration")

        # But it's documented in the data-source-map
        _write_data_source_map(
            temp_repo,
            "## Known externals\n- `atlas_some_external_view` — VIEW applied directly\n",
        )

        result = run_audit(temp_repo)
        missing_names = [r.table for r in result.missing]
        assert "atlas_some_external_view" not in missing_names

    def test_deprecated_atlas_universe_snapshot_flagged(self, temp_repo: Path) -> None:
        """atlas_universe_snapshot triggers a DEPRECATED (not missing) error."""

        _write_query(
            temp_repo,
            "bad_legacy.ts",
            "SELECT * FROM atlas.atlas_universe_snapshot u WHERE u.date = $1",
        )
        _write_migration(temp_repo, "001_empty.py", "# empty")

        result = run_audit(temp_repo)

        assert result.ok is False
        deprecated_names = [r.table for r, _ in result.deprecated]
        assert "atlas_universe_snapshot" in deprecated_names
        # Should NOT appear in missing (it's classified as deprecated, not unknown)
        missing_names = [r.table for r in result.missing]
        assert "atlas_universe_snapshot" not in missing_names


# ---------------------------------------------------------------------------
# Case 3 — JSONB unpack recognized as non-table dependency
# ---------------------------------------------------------------------------


class TestJsonbUnpackIgnored:
    """JSONB unpack patterns do not create false positive missing-table errors.

    jsonb_to_recordset(top_holdings) looks like a FROM clause but the argument
    is a column reference, not a table name. The audit must skip these lines.
    """

    def test_jsonb_to_recordset_not_flagged(self, temp_repo: Path) -> None:
        _copy_fixture("jsonb_unpack_query.ts", temp_repo, _v6_dir(temp_repo))

        # atlas_fund_scorecard is in the mock migration
        _copy_mock_migration(temp_repo)

        result = run_audit(temp_repo)

        # "top_holdings" must not appear as a missing table
        missing_names = [r.table for r in result.missing]
        assert "top_holdings" not in missing_names
        assert result.ok is True

    def test_jsonb_array_elements_not_flagged(self, temp_repo: Path) -> None:
        _write_query(
            temp_repo,
            "array_elem.ts",
            """
            SELECT elem->>'isin' AS isin
            FROM atlas.atlas_fund_scorecard s
            CROSS JOIN LATERAL jsonb_array_elements(s.holdings_raw) AS elem
            WHERE s.snapshot_date = $1
            """,
        )
        _copy_mock_migration(temp_repo)

        result = run_audit(temp_repo)

        missing_names = [r.table for r in result.missing]
        assert "holdings_raw" not in missing_names
        assert "s" not in missing_names

    def test_known_view_atlas_stock_signal_unified_not_flagged(self, temp_repo: Path) -> None:
        """atlas_stock_signal_unified is a known VIEW — must not appear as missing."""

        _write_query(
            temp_repo,
            "view_query.ts",
            """
            SELECT u.symbol, ls.rs_state
            FROM atlas.atlas_universe_stocks u
            LEFT JOIN atlas.atlas_stock_signal_unified ls
              ON ls.instrument_id = u.instrument_id
            WHERE u.effective_to IS NULL
            """,
        )
        _copy_mock_migration(temp_repo)

        result = run_audit(temp_repo)

        missing_names = [r.table for r in result.missing]
        assert "atlas_stock_signal_unified" not in missing_names
        assert result.ok is True


# ---------------------------------------------------------------------------
# Integration smoke — run against real repo
# ---------------------------------------------------------------------------


class TestRealRepoSmoke:
    """Smoke test: run the audit against the actual atlas-os repo.

    This test verifies the audit exits cleanly on the real codebase.
    It does NOT assert ok=True because the real repo may have known
    issues tracked in data-source-map.md. It just asserts no crash.
    """

    def test_real_repo_audit_does_not_crash(self) -> None:
        # Should not raise
        result = run_audit(REPO_ROOT)

        # tables_found must be non-empty (at least 5 tables)
        assert len(result.tables_found) >= 5

        # migration_tables must be non-empty
        assert len(result.migration_tables) >= 10

    def test_real_repo_atlas_universe_snapshot_not_in_v6_queries(self) -> None:
        """Verify autonomous resolution: atlas_universe_snapshot is gone from v6/*.ts."""

        result = run_audit(REPO_ROOT)

        deprecated_names = [r.table for r, _ in result.deprecated]
        assert "atlas_universe_snapshot" not in deprecated_names, (
            "atlas_universe_snapshot found in a v6 query file — "
            "must be replaced with atlas_universe_stocks (autonomous resolution 2026-05-26)"
        )

    def test_real_repo_atlas_ledger_public_not_in_v6_queries(self) -> None:
        """Verify autonomous resolution: atlas_ledger_public is gone from v6/*.ts."""

        result = run_audit(REPO_ROOT)

        deprecated_names = [r.table for r, _ in result.deprecated]
        assert "atlas_ledger_public" not in deprecated_names, (
            "atlas_ledger_public found in a v6 query file — "
            "must be renamed to atlas_ledger (migration 083)"
        )

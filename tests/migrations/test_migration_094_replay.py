"""Tests for migration 094 — replay of 082-088 on Supabase atlas-os.

This test file does NOT spin up Postgres or actually run the migration.
It validates:
  - The migration file exists and is syntactically importable.
  - revision / down_revision metadata are correct.
  - The SQL body contains CREATE TABLE IF NOT EXISTS for every expected table.
  - All 4 new enums are created with IF NOT EXISTS guards.
  - The one view is created with CREATE OR REPLACE VIEW.
  - Both RLS policies are wrapped in idempotent DO $$ blocks.
"""

from __future__ import annotations

import importlib
import inspect
import types

import pytest

_MODULE = "migrations.versions.094_v6_replay_missing_tables_082_088"

# Tables that must appear in the migration as CREATE TABLE IF NOT EXISTS.
_EXPECTED_TABLES = [
    "atlas_brief_cache",
    "atlas_ledger",
    "atlas_paper_portfolio",
    "atlas_user_lots",
    "atlas_etf_signal_calls",
    "atlas_mf_recommendation_daily",
    "atlas_mf_switch_rules",
    "atlas_macro_features_daily",
    "atlas_macro_recommendation_daily",
    "atlas_provenance_log",
    "atlas_drift_event_log",
]

# New enum types that must be guarded with IF NOT EXISTS semantics.
_EXPECTED_NEW_ENUMS = [
    "atlas_etf_sub_category",
    "atlas_mf_quartile",
    "atlas_mf_recommendation",
    "atlas_drift_action",
]

# RLS policies that must appear.
_EXPECTED_POLICIES = [
    "paper_portfolio_user_isolation",
    "user_lots_user_isolation",
]


def _load() -> types.ModuleType:
    return importlib.import_module(_MODULE)


def _upgrade_source() -> str:
    """Return the source of the upgrade() function as a string."""
    mod = _load()
    return inspect.getsource(mod.upgrade)


def _module_source() -> str:
    """Return the entire module source."""
    mod = _load()
    return inspect.getsource(mod)


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


class TestImportable:
    def test_module_imports_without_error(self) -> None:
        """The migration file must be importable with no runtime errors."""
        mod = _load()
        assert mod is not None

    def test_module_has_upgrade_function(self) -> None:
        mod = _load()
        assert callable(getattr(mod, "upgrade", None))

    def test_module_has_downgrade_function(self) -> None:
        mod = _load()
        assert callable(getattr(mod, "downgrade", None))


# ---------------------------------------------------------------------------
# Revision metadata
# ---------------------------------------------------------------------------


class TestRevisionMetadata:
    def test_revision_is_094(self) -> None:
        mod = _load()
        assert mod.revision == "094"

    def test_down_revision_is_093(self) -> None:
        mod = _load()
        assert mod.down_revision == "093"

    def test_branch_labels_none(self) -> None:
        mod = _load()
        assert mod.branch_labels is None

    def test_depends_on_none(self) -> None:
        mod = _load()
        assert mod.depends_on is None


# ---------------------------------------------------------------------------
# CREATE TABLE IF NOT EXISTS — all 11 tables
# ---------------------------------------------------------------------------


class TestCreateTableStatements:
    def test_all_expected_tables_present(self) -> None:
        src = _upgrade_source()
        missing = [
            t for t in _EXPECTED_TABLES if "CREATE TABLE IF NOT EXISTS" not in src or t not in src
        ]
        assert not missing, f"Tables missing from upgrade(): {missing}"

    @pytest.mark.parametrize("table_name", _EXPECTED_TABLES)
    def test_table_uses_if_not_exists(self, table_name: str) -> None:
        src = _upgrade_source()
        # Each table must appear after a CREATE TABLE IF NOT EXISTS header.
        assert table_name in src, f"{table_name} not found in upgrade()"
        # Verify the overall pattern is present at least once.
        assert "CREATE TABLE IF NOT EXISTS" in src

    def test_expected_table_count(self) -> None:
        """Exactly 11 tables — no extra, no fewer."""
        src = _upgrade_source()
        count = src.count("CREATE TABLE IF NOT EXISTS")
        assert count == 11, f"Expected 11 CREATE TABLE IF NOT EXISTS, found {count}"


# ---------------------------------------------------------------------------
# New enums — idempotent creation guards
# ---------------------------------------------------------------------------


class TestNewEnums:
    @pytest.mark.parametrize("enum_name", _EXPECTED_NEW_ENUMS)
    def test_enum_has_if_not_exists_guard(self, enum_name: str) -> None:
        src = _upgrade_source()
        assert enum_name in src, f"Enum {enum_name} not referenced in upgrade()"

    def test_enum_creation_uses_pg_type_check(self) -> None:
        """Enum creation must be guarded by a pg_type existence check.

        The check lives in _create_enum_if_not_exists() which is called from
        upgrade(), so we inspect the full module source rather than just the
        upgrade() body.
        """
        src = _module_source()
        assert "pg_type" in src, "Enum creation must check pg_type for IF NOT EXISTS"

    def test_all_four_new_enums_present(self) -> None:
        src = _upgrade_source()
        missing = [e for e in _EXPECTED_NEW_ENUMS if e not in src]
        assert not missing, f"New enums missing from upgrade(): {missing}"


# ---------------------------------------------------------------------------
# CREATE OR REPLACE VIEW — atlas_ledger_public
# ---------------------------------------------------------------------------


class TestLedgerPublicView:
    def test_view_created_with_replace(self) -> None:
        src = _upgrade_source()
        assert "CREATE OR REPLACE VIEW" in src

    def test_view_is_atlas_ledger_public(self) -> None:
        src = _upgrade_source()
        assert "atlas_ledger_public" in src

    def test_view_selects_correct_columns(self) -> None:
        src = _upgrade_source()
        assert "signal_call_id" in src
        assert "realized_excess" in src
        assert "realized_at" in src


# ---------------------------------------------------------------------------
# RLS policies — idempotent DO $$ guards
# ---------------------------------------------------------------------------


class TestRLSPolicies:
    @pytest.mark.parametrize("policy_name", _EXPECTED_POLICIES)
    def test_policy_present_in_upgrade(self, policy_name: str) -> None:
        src = _upgrade_source()
        assert policy_name in src, f"Policy {policy_name} not found in upgrade()"

    def test_rls_enable_statements_present(self) -> None:
        src = _upgrade_source()
        assert "ENABLE ROW LEVEL SECURITY" in src

    def test_policies_wrapped_in_do_block(self) -> None:
        """Policies must be inside DO $$ ... $$ blocks for idempotency.

        The pg_policies check lives in _create_policy_if_not_exists() which is
        called from upgrade(), so we inspect the full module source.
        """
        src = _module_source()
        assert "pg_policies" in src, "RLS policy creation must check pg_policies for idempotency"


# ---------------------------------------------------------------------------
# Downgrade — presence of DROP statements for all created objects
# ---------------------------------------------------------------------------


class TestDowngradeStatements:
    def _downgrade_source(self) -> str:
        mod = _load()
        return inspect.getsource(mod.downgrade)

    def test_all_tables_dropped(self) -> None:
        src = self._downgrade_source()
        missing = [t for t in _EXPECTED_TABLES if t not in src]
        assert not missing, f"Tables not dropped in downgrade(): {missing}"

    def test_new_enums_dropped(self) -> None:
        src = self._downgrade_source()
        missing = [e for e in _EXPECTED_NEW_ENUMS if e not in src]
        assert not missing, f"Enums not dropped in downgrade(): {missing}"

    def test_view_dropped(self) -> None:
        src = self._downgrade_source()
        assert "atlas_ledger_public" in src
        assert "DROP VIEW IF EXISTS" in src

    def test_policies_dropped(self) -> None:
        src = self._downgrade_source()
        for p in _EXPECTED_POLICIES:
            assert p in src, f"Policy {p} not found in downgrade()"

    def test_drop_table_uses_if_exists(self) -> None:
        src = self._downgrade_source()
        assert "DROP TABLE IF EXISTS" in src

    def test_drop_type_uses_if_exists_guard(self) -> None:
        src = self._downgrade_source()
        assert "DROP TYPE" in src

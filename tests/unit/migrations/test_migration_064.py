"""Tests for migration 064 — tv_alert_registry, tv_signal_reports, atlas_signal_alerts.

Unit assertions (always run, no DB required)
--------------------------------------------
Patch ``alembic.op.*`` via unittest.mock, call ``upgrade()`` / ``downgrade()``,
and inspect which table names and SQL fragments were emitted.  These tests fail
fast if a future edit accidentally drops a table, renames an index, or changes
the drop-order in downgrade().

Integration tests (require ATLAS_DB_URL)
-----------------------------------------
Decorated with ``@pytest.mark.skipif`` so they are skipped on Mac where
psycopg2 is broken.  On EC2 they verify the tables actually exist.
"""

from __future__ import annotations

import importlib
import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIGRATION_MODULE = "migrations.versions.064_tv_signal_reports"
_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="needs ATLAS_DB_URL — integration tests run on EC2 only",
)


def _load_migration():  # type: ignore[return]
    """Import the migration module fresh (handles repeated imports gracefully)."""
    return importlib.import_module(_MIGRATION_MODULE)


# ---------------------------------------------------------------------------
# Unit assertions — always run, no database needed
# ---------------------------------------------------------------------------


class TestUpgrade:
    """Assert that upgrade() creates all 3 tables and the dedup unique index."""

    def _run_upgrade(self) -> tuple[MagicMock, MagicMock, MagicMock]:
        """Run upgrade() with mocked alembic.op functions.

        Returns (mock_create_table, mock_create_index, mock_execute).
        """
        mod = _load_migration()
        with (
            patch("alembic.op.create_table") as mock_ct,
            patch("alembic.op.create_index") as mock_ci,
            patch("alembic.op.execute") as mock_ex,
        ):
            mod.upgrade()
        return mock_ct, mock_ci, mock_ex

    # --- create_table assertions -------------------------------------------

    def test_upgrade_creates_tv_alert_registry(self) -> None:
        mock_ct, _, _ = self._run_upgrade()
        created_names = [c.args[0] for c in mock_ct.call_args_list]
        assert "tv_alert_registry" in created_names, (
            f"upgrade() must call op.create_table('tv_alert_registry'). "
            f"Tables created: {created_names}"
        )

    def test_upgrade_creates_tv_signal_reports(self) -> None:
        mock_ct, _, _ = self._run_upgrade()
        created_names = [c.args[0] for c in mock_ct.call_args_list]
        assert "tv_signal_reports" in created_names, (
            f"upgrade() must call op.create_table('tv_signal_reports'). "
            f"Tables created: {created_names}"
        )

    def test_upgrade_creates_atlas_signal_alerts(self) -> None:
        mock_ct, _, _ = self._run_upgrade()
        created_names = [c.args[0] for c in mock_ct.call_args_list]
        assert "atlas_signal_alerts" in created_names, (
            f"upgrade() must call op.create_table('atlas_signal_alerts'). "
            f"Tables created: {created_names}"
        )

    def test_upgrade_creates_exactly_three_tables(self) -> None:
        mock_ct, _, _ = self._run_upgrade()
        created_names = [c.args[0] for c in mock_ct.call_args_list]
        assert len(created_names) == 3, (
            f"upgrade() must create exactly 3 tables, got {len(created_names)}: {created_names}"
        )

    def test_upgrade_creates_tables_in_dependency_order(self) -> None:
        """tv_alert_registry and tv_signal_reports must come before atlas_signal_alerts
        because atlas_signal_alerts has a FK to tv_signal_reports."""
        mock_ct, _, _ = self._run_upgrade()
        created_names = [c.args[0] for c in mock_ct.call_args_list]
        idx_reports = created_names.index("tv_signal_reports")
        idx_alerts = created_names.index("atlas_signal_alerts")
        assert idx_reports < idx_alerts, (
            "tv_signal_reports must be created before atlas_signal_alerts "
            f"(FK dependency). Order seen: {created_names}"
        )

    # --- create_index assertions -------------------------------------------

    def test_upgrade_creates_ticker_index_on_registry(self) -> None:
        _, mock_ci, _ = self._run_upgrade()
        index_names = [c.args[0] for c in mock_ci.call_args_list]
        assert "idx_tv_alert_registry_ticker" in index_names, (
            f"upgrade() must create idx_tv_alert_registry_ticker. Indexes: {index_names}"
        )

    def test_upgrade_creates_ticker_index_on_signal_reports(self) -> None:
        _, mock_ci, _ = self._run_upgrade()
        index_names = [c.args[0] for c in mock_ci.call_args_list]
        assert "idx_tv_signal_reports_ticker" in index_names, (
            f"upgrade() must create idx_tv_signal_reports_ticker. Indexes: {index_names}"
        )

    def test_upgrade_creates_triggered_at_index(self) -> None:
        _, mock_ci, _ = self._run_upgrade()
        index_names = [c.args[0] for c in mock_ci.call_args_list]
        assert "idx_tv_signal_reports_triggered_at" in index_names, (
            f"upgrade() must create idx_tv_signal_reports_triggered_at. Indexes: {index_names}"
        )

    # --- dedup UNIQUE index (via op.execute) --------------------------------

    def test_upgrade_creates_dedup_unique_index(self) -> None:
        _, _, mock_ex = self._run_upgrade()
        executed_sql = "\n".join(str(c.args[0]) for c in mock_ex.call_args_list if c.args)
        assert "idx_tv_signal_dedup" in executed_sql, (
            "upgrade() must create UNIQUE INDEX idx_tv_signal_dedup via op.execute(). "
            f"SQL emitted: {executed_sql!r}"
        )

    def test_upgrade_dedup_index_covers_correct_columns(self) -> None:
        """Dedup index must cover ticker, condition_code, chart_type, date_trunc(hour)."""
        _, _, mock_ex = self._run_upgrade()
        executed_sql = "\n".join(str(c.args[0]) for c in mock_ex.call_args_list if c.args)
        for fragment in ("ticker", "condition_code", "chart_type", "date_trunc"):
            assert fragment in executed_sql, (
                f"Dedup UNIQUE index SQL must reference '{fragment}'. SQL emitted: {executed_sql!r}"
            )

    def test_upgrade_dedup_index_uses_hour_truncation(self) -> None:
        """The dedup window must be per-hour (prevents duplicate TV webhook retries)."""
        _, _, mock_ex = self._run_upgrade()
        executed_sql = "\n".join(str(c.args[0]) for c in mock_ex.call_args_list if c.args)
        assert "hour" in executed_sql.lower(), (
            f"Dedup index must truncate triggered_at to 'hour'. SQL emitted: {executed_sql!r}"
        )


class TestDowngrade:
    """Assert that downgrade() drops all 3 tables in the correct FK-safe order."""

    def _run_downgrade(self) -> MagicMock:
        """Run downgrade() with mocked alembic.op.drop_table.

        Returns mock_drop_table.
        """
        mod = _load_migration()
        with patch("alembic.op.drop_table") as mock_dt:
            mod.downgrade()
        return mock_dt

    def test_downgrade_drops_atlas_signal_alerts(self) -> None:
        mock_dt = self._run_downgrade()
        dropped_names = [c.args[0] for c in mock_dt.call_args_list]
        assert "atlas_signal_alerts" in dropped_names, (
            f"downgrade() must call op.drop_table('atlas_signal_alerts'). Dropped: {dropped_names}"
        )

    def test_downgrade_drops_tv_signal_reports(self) -> None:
        mock_dt = self._run_downgrade()
        dropped_names = [c.args[0] for c in mock_dt.call_args_list]
        assert "tv_signal_reports" in dropped_names, (
            f"downgrade() must call op.drop_table('tv_signal_reports'). Dropped: {dropped_names}"
        )

    def test_downgrade_drops_tv_alert_registry(self) -> None:
        mock_dt = self._run_downgrade()
        dropped_names = [c.args[0] for c in mock_dt.call_args_list]
        assert "tv_alert_registry" in dropped_names, (
            f"downgrade() must call op.drop_table('tv_alert_registry'). Dropped: {dropped_names}"
        )

    def test_downgrade_drops_exactly_three_tables(self) -> None:
        mock_dt = self._run_downgrade()
        dropped_names = [c.args[0] for c in mock_dt.call_args_list]
        assert len(dropped_names) == 3, (
            f"downgrade() must drop exactly 3 tables, got {len(dropped_names)}: {dropped_names}"
        )

    def test_downgrade_drops_alerts_before_reports(self) -> None:
        """atlas_signal_alerts (FK child) must be dropped before tv_signal_reports (FK parent)."""
        mock_dt = self._run_downgrade()
        dropped_names = [c.args[0] for c in mock_dt.call_args_list]
        idx_alerts = dropped_names.index("atlas_signal_alerts")
        idx_reports = dropped_names.index("tv_signal_reports")
        assert idx_alerts < idx_reports, (
            "atlas_signal_alerts must be dropped before tv_signal_reports "
            f"(FK constraint). Drop order seen: {dropped_names}"
        )

    def test_downgrade_drops_reports_before_registry(self) -> None:
        """tv_signal_reports must be dropped before tv_alert_registry."""
        mock_dt = self._run_downgrade()
        dropped_names = [c.args[0] for c in mock_dt.call_args_list]
        idx_reports = dropped_names.index("tv_signal_reports")
        idx_registry = dropped_names.index("tv_alert_registry")
        assert idx_reports < idx_registry, (
            "tv_signal_reports must be dropped before tv_alert_registry. "
            f"Drop order seen: {dropped_names}"
        )


# ---------------------------------------------------------------------------
# Metadata assertions — always run
# ---------------------------------------------------------------------------


class TestMigrationMetadata:
    """Verify the migration module has correct revision metadata."""

    def test_revision_id(self) -> None:
        mod = _load_migration()
        assert mod.revision == "064", f"Expected revision='064', got {mod.revision!r}"

    def test_down_revision(self) -> None:
        mod = _load_migration()
        assert mod.down_revision == "063", (
            f"Expected down_revision='063', got {mod.down_revision!r}"
        )

    def test_branch_labels_none(self) -> None:
        mod = _load_migration()
        assert mod.branch_labels is None

    def test_depends_on_none(self) -> None:
        mod = _load_migration()
        assert mod.depends_on is None


# ---------------------------------------------------------------------------
# Integration tests — skipped unless ATLAS_DB_URL is set
# ---------------------------------------------------------------------------

import sqlalchemy as sa  # noqa: E402 — after local helpers


@_SKIP_INTEGRATION
class TestMigration064Integration:
    """Live integration tests — verify the 3 tables exist after the migration is applied."""

    def _engine(self) -> sa.Engine:
        url = os.environ["ATLAS_DB_URL"]
        return sa.create_engine(url, pool_pre_ping=True)

    def test_tv_alert_registry_exists(self) -> None:
        engine = self._engine()
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'tv_alert_registry'"
                )
            )
            assert result.fetchone() is not None, "Table tv_alert_registry not found in DB"

    def test_tv_signal_reports_exists(self) -> None:
        engine = self._engine()
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'tv_signal_reports'"
                )
            )
            assert result.fetchone() is not None, "Table tv_signal_reports not found in DB"

    def test_atlas_signal_alerts_exists(self) -> None:
        engine = self._engine()
        with engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'atlas_signal_alerts'"
                )
            )
            assert result.fetchone() is not None, "Table atlas_signal_alerts not found in DB"

    def test_dedup_index_exists(self) -> None:
        engine = self._engine()
        with engine.connect() as conn:
            result = conn.execute(
                sa.text("SELECT 1 FROM pg_indexes WHERE indexname = 'idx_tv_signal_dedup'")
            )
            assert result.fetchone() is not None, "Dedup index idx_tv_signal_dedup not found in DB"

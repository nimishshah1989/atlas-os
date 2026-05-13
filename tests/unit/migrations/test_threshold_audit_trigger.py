"""Tests for migration 023 — atlas_thresholds AFTER UPDATE audit trigger.

Unit assertions (always run, no DB required)
--------------------------------------------
Patch ``alembic.op.execute`` via unittest.mock, call ``upgrade()``, and
inspect the SQL strings emitted.  These tests fail fast if a future edit
accidentally drops the trigger guard or renames the function.

Integration tests (require ATLAS_DB_URL)
-----------------------------------------
Decorated with ``@pytest.mark.skipif`` so they are skipped on Mac where
psycopg2 is broken.  On EC2 .214 (where psycopg2 works against the Supabase
pooler) they exercise the live trigger.

Each integration test uses a fresh, randomly-named threshold key that is
deleted in teardown — production thresholds are never mutated permanently.
"""

from __future__ import annotations

import importlib
import os
import uuid
from collections.abc import Generator
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIGRATION_MODULE = "migrations.versions.023_threshold_audit_trigger"
_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="needs ATLAS_DB_URL — integration tests run on EC2 only",
)


def _load_migration():  # type: ignore[return]
    """Import the migration module fresh (handles repeated imports gracefully)."""
    return importlib.import_module(_MIGRATION_MODULE)


def _captured_sql_strings(mock_execute: MagicMock) -> list[str]:
    """Return the raw SQL text from every op.execute(sa.text(...)) call."""
    result: list[str] = []
    for c in mock_execute.call_args_list:
        arg = c.args[0] if c.args else None
        if arg is None:
            continue
        # sa.text returns a TextClause whose string repr is the SQL.
        result.append(str(arg))
    return result


# ---------------------------------------------------------------------------
# Unit assertions — always run, no database needed
# ---------------------------------------------------------------------------


class TestUpgradeSQLContent:
    """Assert that upgrade() emits SQL containing all required elements."""

    def _run_upgrade_and_collect(self) -> list[str]:
        mod = _load_migration()
        with patch("alembic.op.execute") as mock_exec:
            mod.upgrade()
        return _captured_sql_strings(mock_exec)

    def test_upgrade_emits_trigger_function_name(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "atlas.fn_threshold_audit" in combined
        ), "upgrade() SQL must reference the audit function atlas.fn_threshold_audit"

    def test_upgrade_emits_trigger_name(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "trg_threshold_audit" in combined
        ), "upgrade() SQL must reference the trigger trg_threshold_audit"

    def test_upgrade_emits_current_setting_call(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert "current_setting('atlas.change_reason', true)" in combined, (
            "upgrade() SQL must use current_setting('atlas.change_reason', true)"
            " — the 'true' argument is required so an unset GUC returns NULL"
            " rather than raising"
        )

    def test_upgrade_emits_distinct_guard(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "IS DISTINCT FROM" in combined
        ), "upgrade() SQL must use IS DISTINCT FROM to guard against no-op updates"

    def test_upgrade_emits_threshold_value_guard(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "threshold_value" in combined
        ), "upgrade() SQL must reference threshold_value in the IS DISTINCT FROM guard"

    def test_upgrade_emits_three_statements(self) -> None:
        mod = _load_migration()
        with patch("alembic.op.execute") as mock_exec:
            mod.upgrade()
        # CREATE FUNCTION + DROP TRIGGER + CREATE TRIGGER
        assert (
            mock_exec.call_count == 3
        ), f"upgrade() should emit 3 op.execute() calls, got {mock_exec.call_count}"

    def test_downgrade_emits_two_statements(self) -> None:
        mod = _load_migration()
        with patch("alembic.op.execute") as mock_exec:
            mod.downgrade()
        assert (
            mock_exec.call_count == 2
        ), f"downgrade() should emit 2 op.execute() calls, got {mock_exec.call_count}"

    def test_downgrade_emits_drop_trigger(self) -> None:
        mod = _load_migration()
        with patch("alembic.op.execute") as mock_exec:
            mod.downgrade()
        sqls = _captured_sql_strings(mock_exec)
        combined = "\n".join(sqls)
        assert (
            "DROP TRIGGER IF EXISTS trg_threshold_audit" in combined
        ), "downgrade() SQL must drop the trigger safely"

    def test_downgrade_emits_drop_function(self) -> None:
        mod = _load_migration()
        with patch("alembic.op.execute") as mock_exec:
            mod.downgrade()
        sqls = _captured_sql_strings(mock_exec)
        combined = "\n".join(sqls)
        assert (
            "DROP FUNCTION IF EXISTS atlas.fn_threshold_audit" in combined
        ), "downgrade() SQL must drop the function safely"


# ---------------------------------------------------------------------------
# Integration tests — skipped unless ATLAS_DB_URL is set
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_engine() -> sa.Engine:
    """Create a SQLAlchemy engine from ATLAS_DB_URL."""
    url = os.environ["ATLAS_DB_URL"]
    return sa.create_engine(url, pool_pre_ping=True)


@pytest.fixture()
def test_threshold_key(db_engine: sa.Engine) -> Generator[str, None, None]:
    """Insert a throwaway threshold row; delete it after the test."""
    key = f"_M13_TEST_{uuid.uuid4().hex[:12].upper()}"
    with db_engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO atlas.atlas_thresholds (
                    threshold_key, threshold_value, category, description,
                    min_allowed, max_allowed, default_value,
                    last_modified_by, is_active
                ) VALUES (
                    :key, 10.0, 'test', 'M13 integration test threshold',
                    0.0, 100.0, 10.0, 'test_setup', TRUE
                )
            """),
            {"key": key},
        )
    yield key
    # Teardown: remove history rows first (FK), then the threshold itself.
    with db_engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM atlas.atlas_threshold_history WHERE threshold_key = :key"),
            {"key": key},
        )
        conn.execute(
            sa.text("DELETE FROM atlas.atlas_thresholds WHERE threshold_key = :key"),
            {"key": key},
        )


def _latest_history_row(conn: sa.Connection, key: str) -> sa.engine.Row | None:  # type: ignore[type-arg]
    result = conn.execute(
        sa.text("""
            SELECT old_value, new_value, changed_by, change_reason
            FROM atlas.atlas_threshold_history
            WHERE threshold_key = :key
            ORDER BY changed_at DESC
            LIMIT 1
        """),
        {"key": key},
    )
    return result.fetchone()


def _count_history_rows(conn: sa.Connection, key: str) -> int:
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM atlas.atlas_threshold_history WHERE threshold_key = :key"),
        {"key": key},
    )
    row = result.fetchone()
    return int(row[0]) if row else 0


@_SKIP_INTEGRATION
class TestTriggerIntegration:
    """Live integration tests against a real Postgres instance."""

    def test_trigger_logs_audit_when_value_changes_with_reason_set(
        self,
        db_engine: sa.Engine,
        test_threshold_key: str,
    ) -> None:
        """AFTER UPDATE with GUC set → history row with matching values and reason."""
        with db_engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL atlas.change_reason = 'unit test reason'"))
            conn.execute(
                sa.text("""
                    UPDATE atlas.atlas_thresholds
                    SET threshold_value = 20.0, last_modified_by = 'test_user'
                    WHERE threshold_key = :key
                """),
                {"key": test_threshold_key},
            )

        with db_engine.connect() as conn:
            row = _latest_history_row(conn, test_threshold_key)

        assert row is not None, "Expected a history row after UPDATE"
        assert Decimal(str(row.old_value)) == Decimal(
            "10.0"
        ), f"old_value mismatch: {row.old_value}"
        assert Decimal(str(row.new_value)) == Decimal(
            "20.0"
        ), f"new_value mismatch: {row.new_value}"
        assert (
            row.change_reason == "unit test reason"
        ), f"change_reason mismatch: {row.change_reason!r}"

    def test_trigger_logs_audit_with_null_reason_when_guc_unset(
        self,
        db_engine: sa.Engine,
        test_threshold_key: str,
    ) -> None:
        """AFTER UPDATE without GUC → history row exists but change_reason IS NULL."""
        # First reset the test key to a known value using a separate connection.
        with db_engine.begin() as conn:
            conn.execute(
                sa.text("""
                    UPDATE atlas.atlas_thresholds
                    SET threshold_value = 30.0, last_modified_by = 'test_user'
                    WHERE threshold_key = :key
                """),
                {"key": test_threshold_key},
            )
            # No SET LOCAL for atlas.change_reason — GUC is unset.

        with db_engine.connect() as conn:
            row = _latest_history_row(conn, test_threshold_key)

        assert row is not None, "Expected a history row after UPDATE"
        assert (
            row.change_reason is None
        ), f"change_reason should be NULL when GUC is unset, got {row.change_reason!r}"

    def test_trigger_logs_audit_with_empty_reason_when_guc_empty_string(
        self,
        db_engine: sa.Engine,
        test_threshold_key: str,
    ) -> None:
        """AFTER UPDATE with GUC set to '' → change_reason is empty string (not NULL)."""
        with db_engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL atlas.change_reason = ''"))
            conn.execute(
                sa.text("""
                    UPDATE atlas.atlas_thresholds
                    SET threshold_value = 40.0, last_modified_by = 'test_user'
                    WHERE threshold_key = :key
                """),
                {"key": test_threshold_key},
            )

        with db_engine.connect() as conn:
            row = _latest_history_row(conn, test_threshold_key)

        assert row is not None, "Expected a history row after UPDATE"
        assert (
            row.change_reason == ""
        ), f"change_reason should be '' when GUC is empty string, got {row.change_reason!r}"

    def test_trigger_does_not_log_when_value_unchanged(
        self,
        db_engine: sa.Engine,
        test_threshold_key: str,
    ) -> None:
        """UPDATE that sets threshold_value to its current value → no new history row."""
        # Read current value.
        with db_engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    "SELECT threshold_value FROM atlas.atlas_thresholds WHERE threshold_key = :key"
                ),
                {"key": test_threshold_key},
            )
            current_value = result.scalar()

        before_count: int
        with db_engine.connect() as conn:
            before_count = _count_history_rows(conn, test_threshold_key)

        # UPDATE to the same value — trigger guard (IS DISTINCT FROM) should skip INSERT.
        with db_engine.begin() as conn:
            conn.execute(
                sa.text("""
                    UPDATE atlas.atlas_thresholds
                    SET threshold_value = :val, last_modified_by = 'test_user'
                    WHERE threshold_key = :key
                """),
                {"val": current_value, "key": test_threshold_key},
            )

        with db_engine.connect() as conn:
            after_count = _count_history_rows(conn, test_threshold_key)

        assert after_count == before_count, (
            f"No new history row expected when value is unchanged. "
            f"Before={before_count}, After={after_count}"
        )

    def test_trigger_does_not_fire_on_insert(
        self,
        db_engine: sa.Engine,
    ) -> None:
        """INSERT into atlas_thresholds → no history row created (trigger is AFTER UPDATE)."""
        insert_key = f"_M13_INSERT_TEST_{uuid.uuid4().hex[:10].upper()}"
        try:
            with db_engine.begin() as conn:
                conn.execute(
                    sa.text("""
                        INSERT INTO atlas.atlas_thresholds (
                            threshold_key, threshold_value, category, description,
                            min_allowed, max_allowed, default_value,
                            last_modified_by, is_active
                        ) VALUES (
                            :key, 5.0, 'test', 'M13 insert-only test threshold',
                            0.0, 100.0, 5.0, 'test_insert', TRUE
                        )
                    """),
                    {"key": insert_key},
                )

            with db_engine.connect() as conn:
                count = _count_history_rows(conn, insert_key)

            assert count == 0, f"Expected 0 history rows after INSERT, got {count}"
        finally:
            with db_engine.begin() as conn:
                conn.execute(
                    sa.text("DELETE FROM atlas.atlas_threshold_history WHERE threshold_key = :key"),
                    {"key": insert_key},
                )
                conn.execute(
                    sa.text("DELETE FROM atlas.atlas_thresholds WHERE threshold_key = :key"),
                    {"key": insert_key},
                )

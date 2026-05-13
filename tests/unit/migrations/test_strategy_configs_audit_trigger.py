"""Tests for migration 025 — strategy_configs audit trigger.

Unit assertions (always run, no DB required)
--------------------------------------------
Patch ``alembic.op.execute`` via unittest.mock, call ``upgrade()`` /
``downgrade()``, and inspect the SQL strings emitted. These tests fail fast if
a future edit accidentally drops the trigger guard or renames the function.

Integration tests (require ATLAS_DB_URL)
-----------------------------------------
Decorated with ``@pytest.mark.skipif`` so they are skipped on Mac where
psycopg2 is broken. On EC2 .214 they exercise the live trigger.

Each integration test uses a throwaway strategy_id (UUID) that is deleted in
teardown — production strategy_configs rows are never mutated permanently.
"""

from __future__ import annotations

import importlib
import os
import uuid
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIGRATION_MODULE = "migrations.versions.025_strategy_configs_audit"
_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="needs ATLAS_DB_URL — integration tests run on EC2 only",
)


def _load_migration():  # type: ignore[return]
    """Import the migration module fresh (handles repeated imports gracefully)."""
    return importlib.import_module(_MIGRATION_MODULE)


def _captured_sql_strings(mock_execute: MagicMock) -> list[str]:
    """Return raw SQL text + bound-param values from every op.execute call.

    Two shapes captured:
    - op.execute(sa.text(SQL))
    - op.execute(sa.text(SQL).bindparams(...))
    - op.execute(sa.text(SQL), {params})
    """
    result: list[str] = []
    for c in mock_execute.call_args_list:
        arg = c.args[0] if c.args else None
        if arg is None:
            continue
        result.append(str(arg))
        # Two-arg form: dict in second position
        if len(c.args) >= 2 and isinstance(c.args[1], dict):
            for v in c.args[1].values():
                if isinstance(v, str):
                    result.append(v)
        # bindparams form: TextClause carries _bindparams attribute
        bindparams = getattr(arg, "_bindparams", None)
        if isinstance(bindparams, dict):
            for bp in bindparams.values():
                v = getattr(bp, "value", None)
                if isinstance(v, str):
                    result.append(v)
    return result


# ---------------------------------------------------------------------------
# Unit assertions — always run, no database needed
# ---------------------------------------------------------------------------


class TestUpgradeSQLContent:
    """Assert that upgrade() and downgrade() emit SQL with all required elements."""

    def _run_upgrade_and_collect(self) -> list[str]:
        mod = _load_migration()
        with patch("alembic.op.execute") as mock_exec:
            mod.upgrade()
        return _captured_sql_strings(mock_exec)

    def _run_downgrade_and_collect(self) -> list[str]:
        mod = _load_migration()
        with patch("alembic.op.execute") as mock_exec:
            mod.downgrade()
        return _captured_sql_strings(mock_exec)

    # --- upgrade assertions ------------------------------------------------

    def test_upgrade_adds_is_fm_authored_column(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "is_fm_authored" in combined
        ), "upgrade() SQL must add is_fm_authored column to strategy_configs"
        assert "BOOLEAN" in combined, "is_fm_authored must be BOOLEAN type"

    def test_upgrade_adds_created_by_column(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "created_by" in combined
        ), "upgrade() SQL must add created_by column to strategy_configs"

    def test_upgrade_creates_history_table(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "atlas_strategy_history" in combined
        ), "upgrade() SQL must create atlas.atlas_strategy_history table"

    def test_upgrade_emits_audit_function(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "atlas.fn_strategy_audit" in combined
        ), "upgrade() SQL must reference audit function atlas.fn_strategy_audit"
        assert "current_setting('atlas.change_reason', true)" in combined, (
            "upgrade() SQL must use current_setting('atlas.change_reason', true) "
            "— the ', true' second arg is required so an unset GUC returns NULL "
            "rather than raising"
        )

    def test_upgrade_emits_trigger_after_update(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "CREATE TRIGGER trg_strategy_audit" in combined
        ), "upgrade() SQL must create trigger trg_strategy_audit"
        assert "AFTER UPDATE" in combined, "upgrade() SQL must specify AFTER UPDATE on the trigger"

    def test_upgrade_emits_distinct_guard(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "IS DISTINCT FROM" in combined
        ), "upgrade() SQL must use IS DISTINCT FROM to guard against no-op updates"

    def test_upgrade_guards_both_config_and_is_active(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        # The trigger function must check both config and is_active columns
        assert "config" in combined, "trigger function must guard on config column"
        assert "is_active" in combined, "trigger function must guard on is_active column"

    # --- downgrade assertions ----------------------------------------------

    def test_downgrade_emits_drop_trigger(self) -> None:
        sqls = self._run_downgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "DROP TRIGGER IF EXISTS trg_strategy_audit" in combined
        ), "downgrade() SQL must drop trigger trg_strategy_audit safely"

    def test_downgrade_emits_drop_function(self) -> None:
        sqls = self._run_downgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "DROP FUNCTION IF EXISTS atlas.fn_strategy_audit" in combined
        ), "downgrade() SQL must drop function atlas.fn_strategy_audit safely"

    def test_downgrade_drops_history_table(self) -> None:
        sqls = self._run_downgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "DROP TABLE IF EXISTS atlas.atlas_strategy_history" in combined
        ), "downgrade() SQL must drop atlas.atlas_strategy_history table"

    def test_downgrade_drops_added_columns(self) -> None:
        sqls = self._run_downgrade_and_collect()
        combined = "\n".join(sqls)
        assert (
            "DROP COLUMN" in combined
        ), "downgrade() must DROP COLUMN for is_fm_authored and created_by"
        assert "is_fm_authored" in combined, "downgrade() must drop is_fm_authored column"


# ---------------------------------------------------------------------------
# Integration tests — skipped unless ATLAS_DB_URL is set
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_engine() -> sa.Engine:
    """Create a SQLAlchemy engine from ATLAS_DB_URL."""
    url = os.environ["ATLAS_DB_URL"]
    return sa.create_engine(url, pool_pre_ping=True)


@pytest.fixture()
def test_strategy(db_engine: sa.Engine) -> Generator[str, None, None]:
    """Insert a throwaway strategy_configs row; delete it + history after the test."""
    sid = str(uuid.uuid4())
    with db_engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO atlas.strategy_configs
                  (id, name, tier, archetype, variant, config, is_active, is_fm_authored)
                VALUES
                  (:id, :name, 'fm', 'fm_authored', 'custom',
                   '{"rs_state_filter": ["Leader"]}'::jsonb,
                   TRUE, TRUE)
            """),
            {"id": sid, "name": f"_M15_TEST_{sid[:8]}"},
        )
    yield sid
    with db_engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM atlas.atlas_strategy_history WHERE strategy_id = :id"),
            {"id": sid},
        )
        conn.execute(
            sa.text("DELETE FROM atlas.strategy_configs WHERE id = :id"),
            {"id": sid},
        )


def _latest_history_row(conn: sa.Connection, strategy_id: str) -> sa.engine.Row | None:  # type: ignore[type-arg]
    result = conn.execute(
        sa.text("""
            SELECT old_config, new_config, old_is_active, new_is_active, change_reason
            FROM atlas.atlas_strategy_history
            WHERE strategy_id = :id
            ORDER BY changed_at DESC
            LIMIT 1
        """),
        {"id": strategy_id},
    )
    return result.fetchone()


def _count_history_rows(conn: sa.Connection, strategy_id: str) -> int:
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM atlas.atlas_strategy_history WHERE strategy_id = :id"),
        {"id": strategy_id},
    )
    row = result.fetchone()
    return int(row[0]) if row else 0


@_SKIP_INTEGRATION
class TestStrategyAuditTriggerIntegration:
    """Live integration tests against a real Postgres instance."""

    def test_trigger_fires_on_config_change_with_reason(
        self,
        db_engine: sa.Engine,
        test_strategy: str,
    ) -> None:
        """AFTER UPDATE on config with GUC set → history row with correct values."""
        with db_engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL atlas.change_reason = 'M15 test reason'"))
            conn.execute(
                sa.text("""
                    UPDATE atlas.strategy_configs
                    SET config = '{"rs_state_filter": ["Leader", "Strong"]}'::jsonb
                    WHERE id = :id
                """),
                {"id": test_strategy},
            )

        with db_engine.connect() as conn:
            row = _latest_history_row(conn, test_strategy)

        assert row is not None, "Expected a history row after config UPDATE"
        assert (
            row.change_reason == "M15 test reason"
        ), f"change_reason mismatch: {row.change_reason!r}"

    def test_trigger_does_not_fire_when_config_unchanged(
        self,
        db_engine: sa.Engine,
        test_strategy: str,
    ) -> None:
        """UPDATE that sets config to same value → no new history row."""
        with db_engine.connect() as conn:
            before_count = _count_history_rows(conn, test_strategy)
            current_config = conn.execute(
                sa.text("SELECT config FROM atlas.strategy_configs WHERE id = :id"),
                {"id": test_strategy},
            ).scalar()

        with db_engine.begin() as conn:
            conn.execute(
                sa.text("""
                    UPDATE atlas.strategy_configs
                    SET config = :cfg::jsonb
                    WHERE id = :id
                """),
                {"cfg": current_config, "id": test_strategy},
            )

        with db_engine.connect() as conn:
            after_count = _count_history_rows(conn, test_strategy)

        assert after_count == before_count, (
            f"No new history row expected when config unchanged. "
            f"Before={before_count}, After={after_count}"
        )

    def test_trigger_does_not_fire_on_insert(
        self,
        db_engine: sa.Engine,
    ) -> None:
        """INSERT into strategy_configs → no history row (trigger is AFTER UPDATE)."""
        new_id = str(uuid.uuid4())
        try:
            with db_engine.begin() as conn:
                conn.execute(
                    sa.text("""
                        INSERT INTO atlas.strategy_configs
                          (id, name, tier, archetype, variant, config, is_active, is_fm_authored)
                        VALUES
                          (:id, :name, 'fm', 'fm_authored', 'custom',
                           '{}'::jsonb, TRUE, TRUE)
                    """),
                    {"id": new_id, "name": f"_M15_INSERT_{new_id[:8]}"},
                )

            with db_engine.connect() as conn:
                count = _count_history_rows(conn, new_id)

            assert count == 0, f"Expected 0 history rows after INSERT, got {count}"
        finally:
            with db_engine.begin() as conn:
                conn.execute(
                    sa.text("DELETE FROM atlas.atlas_strategy_history WHERE strategy_id = :id"),
                    {"id": new_id},
                )
                conn.execute(
                    sa.text("DELETE FROM atlas.strategy_configs WHERE id = :id"),
                    {"id": new_id},
                )

    def test_trigger_captures_null_reason_when_guc_unset(
        self,
        db_engine: sa.Engine,
        test_strategy: str,
    ) -> None:
        """AFTER UPDATE without GUC → history row exists but change_reason IS NULL or ''."""
        with db_engine.begin() as conn:
            conn.execute(
                sa.text("""
                    UPDATE atlas.strategy_configs
                    SET config = '{"rs_state_filter": ["Emerging"]}'::jsonb
                    WHERE id = :id
                """),
                {"id": test_strategy},
            )

        with db_engine.connect() as conn:
            row = _latest_history_row(conn, test_strategy)

        assert row is not None, "Expected a history row after UPDATE"
        assert (
            row.change_reason is None or row.change_reason == ""
        ), f"change_reason should be NULL or '' when GUC is unset, got {row.change_reason!r}"

    def test_trigger_fires_on_is_active_change(
        self,
        db_engine: sa.Engine,
        test_strategy: str,
    ) -> None:
        """AFTER UPDATE toggling is_active → history row created."""
        with db_engine.connect() as conn:
            before_count = _count_history_rows(conn, test_strategy)

        with db_engine.begin() as conn:
            conn.execute(
                sa.text("""
                    UPDATE atlas.strategy_configs
                    SET is_active = FALSE
                    WHERE id = :id
                """),
                {"id": test_strategy},
            )

        with db_engine.connect() as conn:
            after_count = _count_history_rows(conn, test_strategy)

        assert after_count == before_count + 1, (
            f"Expected 1 new history row after is_active toggle. "
            f"Before={before_count}, After={after_count}"
        )

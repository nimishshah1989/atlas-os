"""Tests for migration 024 — atlas_decision_policy AFTER UPDATE audit trigger.

Unit assertions (always run, no DB required)
--------------------------------------------
Patch ``alembic.op.execute`` via unittest.mock, call ``upgrade()`` /
``downgrade()``, and inspect the SQL strings emitted.  These tests fail fast if
a future edit accidentally drops the trigger guard or renames the function.

Integration tests (require ATLAS_DB_URL)
-----------------------------------------
Decorated with ``@pytest.mark.skipif`` so they are skipped on Mac where
psycopg2 is broken.  On EC2 .214 (where psycopg2 works against the Supabase
pooler) they exercise the live trigger.

Each integration test uses a fresh, randomly-named policy key (UUID-suffixed)
that is deleted in teardown — production policy rows are never mutated
permanently.
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

_MIGRATION_MODULE = "migrations.versions.024_create_decision_policy"
_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="needs ATLAS_DB_URL — integration tests run on EC2 only",
)

# All 12 seed policy keys expected in the migration
_ALL_SEED_KEYS: tuple[str, ...] = (
    "strength_gate_stock",
    "direction_gate_stock",
    "risk_gate_stock",
    "volume_gate_stock",
    "sector_gate_stock",
    "market_gate",
    "strength_gate_etf",
    "direction_gate_etf",
    "nav_strong_states_fund",
    "nav_positive_states_fund",
    "risk_multipliers_stock",
    "market_multipliers",
)


def _load_migration():  # type: ignore[return]
    """Import the migration module fresh (handles repeated imports gracefully)."""
    return importlib.import_module(_MIGRATION_MODULE)


def _captured_sql_strings(mock_execute: MagicMock) -> list[str]:
    """Return the raw SQL text + bound-param values from every op.execute call.

    Two shapes captured:
    - op.execute(sa.text(SQL)) — appends str(textclause)
    - op.execute(sa.text(SQL).bindparams(...)) — appends str(textclause) AND
      any string values from the bindparams (so seed keys are searchable).
    - op.execute(sa.text(SQL), {params}) — legacy two-arg shape; also captures.
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
                # BindParameter objects have a .value attr
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

    def test_upgrade_emits_create_atlas_decision_policy_table(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert "CREATE TABLE IF NOT EXISTS atlas.atlas_decision_policy" in combined, (
            "upgrade() SQL must contain CREATE TABLE IF NOT EXISTS atlas.atlas_decision_policy"
        )

    def test_upgrade_emits_create_atlas_decision_policy_history_table(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert "CREATE TABLE IF NOT EXISTS atlas.atlas_decision_policy_history" in combined, (
            "upgrade() SQL must contain"
            " CREATE TABLE IF NOT EXISTS atlas.atlas_decision_policy_history"
        )

    def test_upgrade_emits_audit_function(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert "atlas.fn_decision_policy_audit" in combined, (
            "upgrade() SQL must reference audit function atlas.fn_decision_policy_audit"
        )
        assert "current_setting('atlas.change_reason', true)" in combined, (
            "upgrade() SQL must use current_setting('atlas.change_reason', true)"
            " — the ', true' second arg is required so an unset GUC returns NULL"
            " rather than raising"
        )

    def test_upgrade_emits_trigger_after_update(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert "CREATE TRIGGER trg_decision_policy_audit" in combined, (
            "upgrade() SQL must create trigger trg_decision_policy_audit"
        )
        assert "AFTER UPDATE" in combined, "upgrade() SQL must specify AFTER UPDATE on the trigger"

    def test_upgrade_emits_distinct_guard(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        assert "IS DISTINCT FROM" in combined, (
            "upgrade() SQL must use IS DISTINCT FROM to guard against no-op updates"
        )

    def test_upgrade_emits_seed_rows(self) -> None:
        sqls = self._run_upgrade_and_collect()
        combined = "\n".join(sqls)
        for key in _ALL_SEED_KEYS:
            assert key in combined, f"upgrade() SQL must include seed row for policy_key '{key}'"

    # --- downgrade assertions ----------------------------------------------

    def test_downgrade_emits_drop_trigger(self) -> None:
        sqls = self._run_downgrade_and_collect()
        combined = "\n".join(sqls)
        assert "DROP TRIGGER IF EXISTS trg_decision_policy_audit" in combined, (
            "downgrade() SQL must drop trigger trg_decision_policy_audit safely"
        )

    def test_downgrade_emits_drop_function(self) -> None:
        sqls = self._run_downgrade_and_collect()
        combined = "\n".join(sqls)
        assert "DROP FUNCTION IF EXISTS atlas.fn_decision_policy_audit" in combined, (
            "downgrade() SQL must drop function atlas.fn_decision_policy_audit safely"
        )

    def test_downgrade_emits_drop_tables(self) -> None:
        sqls = self._run_downgrade_and_collect()
        combined = "\n".join(sqls)
        assert "DROP TABLE IF EXISTS atlas.atlas_decision_policy_history" in combined, (
            "downgrade() SQL must drop atlas_decision_policy_history"
        )
        assert "DROP TABLE IF EXISTS atlas.atlas_decision_policy" in combined, (
            "downgrade() SQL must drop atlas_decision_policy"
        )


# ---------------------------------------------------------------------------
# Integration tests — skipped unless ATLAS_DB_URL is set
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_engine() -> sa.Engine:
    """Create a SQLAlchemy engine from ATLAS_DB_URL."""
    url = os.environ["ATLAS_DB_URL"]
    return sa.create_engine(url, pool_pre_ping=True)


@pytest.fixture()
def test_policy_key(db_engine: sa.Engine) -> Generator[str, None, None]:
    """Insert a throwaway policy row; delete it (and its history) after the test."""
    key = f"_M14_TEST_{uuid.uuid4().hex[:12].upper()}"
    with db_engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO atlas.atlas_decision_policy (
                    policy_key, policy_kind, policy_value, description,
                    last_modified_by, is_active
                ) VALUES (
                    :key, 'gate_states', '["StateA","StateB"]'::jsonb,
                    'M14 integration test policy', 'test_setup', TRUE
                )
            """),
            {"key": key},
        )
    yield key
    # Teardown: remove history rows first (FK), then the policy row.
    with db_engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM atlas.atlas_decision_policy_history WHERE policy_key = :key"),
            {"key": key},
        )
        conn.execute(
            sa.text("DELETE FROM atlas.atlas_decision_policy WHERE policy_key = :key"),
            {"key": key},
        )


def _latest_policy_history_row(conn: sa.Connection, key: str) -> sa.engine.Row | None:  # type: ignore[type-arg]
    result = conn.execute(
        sa.text("""
            SELECT old_value, new_value, changed_by, change_reason
            FROM atlas.atlas_decision_policy_history
            WHERE policy_key = :key
            ORDER BY changed_at DESC
            LIMIT 1
        """),
        {"key": key},
    )
    return result.fetchone()


def _count_policy_history_rows(conn: sa.Connection, key: str) -> int:
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM atlas.atlas_decision_policy_history WHERE policy_key = :key"),
        {"key": key},
    )
    row = result.fetchone()
    return int(row[0]) if row else 0


@_SKIP_INTEGRATION
class TestPolicyTriggerIntegration:
    """Live integration tests against a real Postgres instance."""

    def test_trigger_logs_audit_when_policy_value_changes_with_reason_set(
        self,
        db_engine: sa.Engine,
        test_policy_key: str,
    ) -> None:
        """AFTER UPDATE with GUC set → history row with correct old/new values and reason."""
        with db_engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL atlas.change_reason = 'M14 unit test reason'"))
            conn.execute(
                sa.text("""
                    UPDATE atlas.atlas_decision_policy
                    SET policy_value = '["StateA","StateB","StateC"]'::jsonb,
                        last_modified_by = 'test_user'
                    WHERE policy_key = :key
                """),
                {"key": test_policy_key},
            )

        with db_engine.connect() as conn:
            row = _latest_policy_history_row(conn, test_policy_key)

        assert row is not None, "Expected a history row after UPDATE"
        import json

        assert json.loads(row.old_value) == [
            "StateA",
            "StateB",
        ], f"old_value mismatch: {row.old_value}"
        assert json.loads(row.new_value) == [
            "StateA",
            "StateB",
            "StateC",
        ], f"new_value mismatch: {row.new_value}"
        assert row.change_reason == "M14 unit test reason", (
            f"change_reason mismatch: {row.change_reason!r}"
        )

    def test_trigger_logs_audit_with_null_reason_when_guc_unset(
        self,
        db_engine: sa.Engine,
        test_policy_key: str,
    ) -> None:
        """AFTER UPDATE without GUC → history row exists but change_reason IS NULL or ''."""
        with db_engine.begin() as conn:
            conn.execute(
                sa.text("""
                    UPDATE atlas.atlas_decision_policy
                    SET policy_value = '["StateA"]'::jsonb,
                        last_modified_by = 'test_user'
                    WHERE policy_key = :key
                """),
                {"key": test_policy_key},
            )
            # No SET LOCAL for atlas.change_reason — GUC is intentionally unset.

        with db_engine.connect() as conn:
            row = _latest_policy_history_row(conn, test_policy_key)

        assert row is not None, "Expected a history row after UPDATE"
        # Per M13's experience: current_setting(name, true) may return '' or NULL
        # depending on whether the GUC was bound earlier in the session.
        assert row.change_reason is None or row.change_reason == "", (
            f"change_reason should be NULL or '' when GUC is unset, got {row.change_reason!r}"
        )

    def test_trigger_does_not_log_when_value_unchanged(
        self,
        db_engine: sa.Engine,
        test_policy_key: str,
    ) -> None:
        """UPDATE that sets policy_value to its current value → no new history row."""
        with db_engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    "SELECT policy_value FROM atlas.atlas_decision_policy WHERE policy_key = :key"
                ),
                {"key": test_policy_key},
            )
            current_value = result.scalar()

        with db_engine.connect() as conn:
            before_count = _count_policy_history_rows(conn, test_policy_key)

        # UPDATE to the same value — IS DISTINCT FROM guard should skip INSERT.
        with db_engine.begin() as conn:
            conn.execute(
                sa.text("""
                    UPDATE atlas.atlas_decision_policy
                    SET policy_value = CAST(:val AS jsonb),
                        last_modified_by = 'test_user'
                    WHERE policy_key = :key
                """),
                {"val": current_value, "key": test_policy_key},
            )

        with db_engine.connect() as conn:
            after_count = _count_policy_history_rows(conn, test_policy_key)

        assert after_count == before_count, (
            f"No new history row expected when policy_value is unchanged. "
            f"Before={before_count}, After={after_count}"
        )

    def test_trigger_does_not_fire_on_insert(
        self,
        db_engine: sa.Engine,
    ) -> None:
        """INSERT into atlas_decision_policy → no history row (trigger is AFTER UPDATE)."""
        insert_key = f"_M14_INSERT_TEST_{uuid.uuid4().hex[:10].upper()}"
        try:
            with db_engine.begin() as conn:
                conn.execute(
                    sa.text("""
                        INSERT INTO atlas.atlas_decision_policy (
                            policy_key, policy_kind, policy_value, description,
                            last_modified_by, is_active
                        ) VALUES (
                            :key, 'gate_states', '["X"]'::jsonb,
                            'M14 insert-only test policy', 'test_insert', TRUE
                        )
                    """),
                    {"key": insert_key},
                )

            with db_engine.connect() as conn:
                count = _count_policy_history_rows(conn, insert_key)

            assert count == 0, f"Expected 0 history rows after INSERT, got {count}"
        finally:
            with db_engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "DELETE FROM atlas.atlas_decision_policy_history WHERE policy_key = :key"
                    ),
                    {"key": insert_key},
                )
                conn.execute(
                    sa.text("DELETE FROM atlas.atlas_decision_policy WHERE policy_key = :key"),
                    {"key": insert_key},
                )

    def test_seed_rows_present_after_migration(
        self,
        db_engine: sa.Engine,
    ) -> None:
        """All 12 expected seed policy_keys must exist in atlas.atlas_decision_policy."""
        with db_engine.connect() as conn:
            result = conn.execute(
                sa.text(
                    "SELECT policy_key FROM atlas.atlas_decision_policy"
                    " WHERE policy_key = ANY(:keys)"
                ),
                {"keys": list(_ALL_SEED_KEYS)},
            )
            found_keys = {row[0] for row in result.fetchall()}

        missing = set(_ALL_SEED_KEYS) - found_keys
        assert not missing, f"Missing seed rows in atlas_decision_policy: {sorted(missing)}"

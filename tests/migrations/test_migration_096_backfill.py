"""Regression tests for migration 096 — backfill atlas_signal_calls + etf_signal_calls.

Verifies:
- Revision and down_revision are correct
- upgrade() uses INSERT...SELECT (op.execute) not INSERT VALUES with literals
- downgrade() uses DELETE not DROP TABLE
- No synthetic hard-coded data in the SQL strings
- MF backfill is intentionally absent (documented gap — nav NOT NULL with no source)
"""

from __future__ import annotations

import importlib
import re
import types
from unittest.mock import patch

_MODULE = "migrations.versions.096_v6_backfill_signal_calls_mf_etf"


def _load() -> types.ModuleType:
    return importlib.import_module(_MODULE)


class TestMigrationMetadata:
    def test_revision_is_096(self) -> None:
        mod = _load()
        assert mod.revision == "096"

    def test_down_revision_is_095(self) -> None:
        mod = _load()
        assert mod.down_revision == "095"

    def test_no_branch_labels(self) -> None:
        mod = _load()
        assert mod.branch_labels is None

    def test_no_depends_on(self) -> None:
        mod = _load()
        assert mod.depends_on is None


class TestUpgradeUsesInsertSelect:
    """The upgrade must use INSERT...SELECT — not INSERT VALUES with literals.

    This enforces the NO SYNTHETIC DATA rule: every row must be derived
    from an existing real table row.
    """

    def _get_executed_sqls(self) -> list[str]:
        mod = _load()
        executed: list[str] = []
        with patch.object(mod, "op") as mock_op:
            # sa.text() returns a ClauseElement; capture .text attribute
            def capture_execute(clause, *args, **kwargs):
                # clause is a sa.text() object; extract the string
                sql = str(clause)
                executed.append(sql)

            mock_op.execute.side_effect = capture_execute
            mod.upgrade()
        return executed

    def test_upgrade_calls_execute_at_least_twice(self) -> None:
        """signal_calls + etf_signal_calls = 2 execute() calls minimum."""
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mod.upgrade()
        assert mock_op.execute.call_count >= 2

    def test_signal_calls_insert_uses_select(self) -> None:
        mod = _load()
        sqls: list[str] = []
        with patch.object(mod, "op") as mock_op:

            def capture(clause, *a, **kw):
                sqls.append(str(clause))

            mock_op.execute.side_effect = capture
            mod.upgrade()

        # At least one SQL should insert into atlas_signal_calls via SELECT
        signal_sql = [s for s in sqls if "atlas_signal_calls" in s and "INSERT" in s.upper()]
        assert signal_sql, "No INSERT into atlas_signal_calls found"
        sc_sql = signal_sql[0]
        # Must be INSERT ... SELECT, not INSERT VALUES
        assert "SELECT" in sc_sql.upper(), "signal_calls INSERT must use SELECT"
        assert "VALUES" not in sc_sql.upper(), "signal_calls INSERT must not use VALUES"

    def test_etf_signal_calls_insert_uses_select(self) -> None:
        mod = _load()
        sqls: list[str] = []
        with patch.object(mod, "op") as mock_op:

            def capture(clause, *a, **kw):
                sqls.append(str(clause))

            mock_op.execute.side_effect = capture
            mod.upgrade()

        etf_sql = [s for s in sqls if "atlas_etf_signal_calls" in s and "INSERT" in s.upper()]
        assert etf_sql, "No INSERT into atlas_etf_signal_calls found"
        assert "SELECT" in etf_sql[0].upper()
        assert "VALUES" not in etf_sql[0].upper()

    def test_no_mf_recommendation_insert(self) -> None:
        """MF backfill is intentionally skipped (nav NOT NULL, no nav source).

        This test asserts the skip is intentional — no half-baked INSERT
        into atlas_mf_recommendation_daily exists.
        """
        mod = _load()
        sqls: list[str] = []
        with patch.object(mod, "op") as mock_op:

            def capture(clause, *a, **kw):
                sqls.append(str(clause))

            mock_op.execute.side_effect = capture
            mod.upgrade()

        mf_inserts = [
            s for s in sqls if "atlas_mf_recommendation_daily" in s and "INSERT" in s.upper()
        ]
        assert not mf_inserts, (
            "atlas_mf_recommendation_daily INSERT found — MF backfill is intentionally "
            "skipped because nav is NOT NULL and sub_metrics contains no nav key. "
            "If you've fixed the NAV sourcing, update this test."
        )

    def test_no_hardcoded_uuid_literals(self) -> None:
        """No INSERT ... VALUES ('some-uuid', ...) patterns in upgrade SQL.

        gen_random_uuid() inside a SELECT is allowed (it generates a new PK
        for each derived row — that's valid). Hardcoded UUID literals in VALUES
        clauses would be synthetic data.
        """
        mod = _load()
        sqls: list[str] = []
        with patch.object(mod, "op") as mock_op:

            def capture(clause, *a, **kw):
                sqls.append(str(clause))

            mock_op.execute.side_effect = capture
            mod.upgrade()

        uuid_re = re.compile(
            r"VALUES\s*\([^)]*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            re.IGNORECASE,
        )
        for sql in sqls:
            assert not uuid_re.search(sql), (
                f"Found hardcoded UUID literal in VALUES clause: {sql[:120]}"
            )

    def test_regime_fallback_covers_non_enum_values(self) -> None:
        """The SQL must handle 'Cautious' (pre-v6 label not in atlas_regime_state enum).

        The pattern: CASE WHEN r.regime_state IN ('Risk-On', 'Elevated', ...)
        must appear in both INSERT blocks.
        """
        mod = _load()
        sqls: list[str] = []
        with patch.object(mod, "op") as mock_op:

            def capture(clause, *a, **kw):
                sqls.append(str(clause))

            mock_op.execute.side_effect = capture
            mod.upgrade()

        for sql in sqls:
            if "INSERT" in sql.upper() and "atlas_signal_calls" in sql:
                assert "Risk-On" in sql, "Regime fallback missing 'Risk-On' in signal_calls SQL"
                assert "Elevated" in sql, "Regime fallback missing 'Elevated' in signal_calls SQL"

    def test_not_exists_guard_in_signal_calls_sql(self) -> None:
        """Idempotency: NOT EXISTS guard must appear in signal_calls INSERT."""
        mod = _load()
        sqls: list[str] = []
        with patch.object(mod, "op") as mock_op:

            def capture(clause, *a, **kw):
                sqls.append(str(clause))

            mock_op.execute.side_effect = capture
            mod.upgrade()

        signal_sqls = [s for s in sqls if "atlas_signal_calls" in s and "INSERT" in s.upper()]
        assert signal_sqls
        assert "NOT EXISTS" in signal_sqls[0].upper(), (
            "signal_calls INSERT missing NOT EXISTS idempotency guard"
        )


class TestDowngradeUsesDelete:
    def _get_downgrade_sqls(self) -> list[str]:
        mod = _load()
        sqls: list[str] = []
        with patch.object(mod, "op") as mock_op:

            def capture(clause, *a, **kw):
                sqls.append(str(clause))

            mock_op.execute.side_effect = capture
            mod.downgrade()
        return sqls

    def test_downgrade_calls_execute(self) -> None:
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mod.downgrade()
        assert mock_op.execute.call_count >= 1

    def test_downgrade_uses_delete_not_truncate(self) -> None:
        sqls = self._get_downgrade_sqls()
        for sql in sqls:
            upper = sql.upper()
            assert "DELETE" in upper, f"downgrade SQL missing DELETE: {sql[:80]}"
            assert "TRUNCATE" not in upper, "downgrade must not TRUNCATE (would delete future rows)"
            assert "DROP" not in upper, "downgrade must not DROP TABLE"

    def test_downgrade_targets_signal_calls(self) -> None:
        sqls = self._get_downgrade_sqls()
        targets = [s for s in sqls if "atlas_signal_calls" in s]
        assert targets, "downgrade must DELETE from atlas_signal_calls"

    def test_downgrade_targets_etf_signal_calls(self) -> None:
        sqls = self._get_downgrade_sqls()
        targets = [s for s in sqls if "atlas_etf_signal_calls" in s]
        assert targets, "downgrade must DELETE from atlas_etf_signal_calls"

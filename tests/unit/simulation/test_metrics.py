"""Unit tests for atlas.simulation.core.metrics.backfill_daily_returns.

Tests use SQLite in-memory DB via a minimal table structure that matches
the relevant columns of atlas.strategy_paper_performance. No Supabase required.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DDL = """
    CREATE TABLE IF NOT EXISTS strategy_paper_performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_id TEXT NOT NULL,
        date DATE NOT NULL,
        total_value REAL NOT NULL,
        daily_return REAL NOT NULL DEFAULT 0.0,
        regime TEXT NOT NULL DEFAULT 'Constructive',
        positions_count INTEGER NOT NULL DEFAULT 0,
        UNIQUE(strategy_id, date)
    );
"""

_INSERT = """
    INSERT INTO strategy_paper_performance
        (strategy_id, date, total_value, daily_return, regime, positions_count)
    VALUES (:sid, :date, :val, :ret, :regime, :cnt)
    ON CONFLICT (strategy_id, date) DO NOTHING
"""

_UPDATE_SQL = """
    UPDATE strategy_paper_performance
    SET daily_return = (
        total_value / (
            SELECT prev.total_value
            FROM strategy_paper_performance AS prev
            WHERE prev.strategy_id = strategy_paper_performance.strategy_id
              AND prev.date = (
                  SELECT MAX(d.date)
                  FROM strategy_paper_performance AS d
                  WHERE d.date < :today
              )
              AND prev.total_value > 0
        )
    ) - 1
    WHERE date = :today
      AND EXISTS (
          SELECT 1
          FROM strategy_paper_performance AS prev2
          WHERE prev2.strategy_id = strategy_paper_performance.strategy_id
            AND prev2.date = (
                SELECT MAX(d2.date)
                FROM strategy_paper_performance AS d2
                WHERE d2.date < :today
            )
            AND prev2.total_value > 0
      )
"""


_SELECT_RETURN_BY_SID = (
    "SELECT daily_return FROM strategy_paper_performance " "WHERE strategy_id='A' AND date=:d"
)

_SELECT_RETURN_ALL = (
    "SELECT strategy_id, daily_return FROM strategy_paper_performance "
    "WHERE date=:d ORDER BY strategy_id"
)


def _make_in_memory_engine():
    """SQLite in-memory engine with no schema prefix."""
    eng = create_engine("sqlite:///:memory:", future=True)
    with eng.connect() as conn:
        conn.execute(text(_DDL))
        conn.commit()
    return eng


# ---------------------------------------------------------------------------
# Tests for the SQL logic (schema-agnostic, inline re-implementation)
# ---------------------------------------------------------------------------


class TestBackfillDailyReturnsSQL:
    """Validate the UPDATE logic directly on SQLite to verify correctness."""

    def _run_update(self, engine, today: date) -> int:
        with engine.connect() as conn:
            result = conn.execute(text(_UPDATE_SQL), {"today": today})
            conn.commit()
        return result.rowcount if result.rowcount is not None else 0

    def test_basic_return_computed_correctly(self):
        eng = _make_in_memory_engine()
        yesterday = date(2026, 5, 7)
        today = date(2026, 5, 8)
        with eng.connect() as conn:
            conn.execute(
                text(_INSERT),
                {
                    "sid": "A",
                    "date": yesterday,
                    "val": 10_000_000.0,
                    "ret": 0.0,
                    "regime": "Constructive",
                    "cnt": 5,
                },
            )
            conn.execute(
                text(_INSERT),
                {
                    "sid": "A",
                    "date": today,
                    "val": 10_500_000.0,
                    "ret": 0.0,
                    "regime": "Constructive",
                    "cnt": 5,
                },
            )
            conn.commit()

        updated = self._run_update(eng, today)
        assert updated == 1

        with eng.connect() as conn:
            ret = conn.execute(
                text(_SELECT_RETURN_BY_SID),
                {"d": today},
            ).scalar()

        # (10_500_000 / 10_000_000) - 1 = 0.05
        assert ret == pytest.approx(0.05, abs=1e-8)

    def test_multiple_strategies_all_updated(self):
        eng = _make_in_memory_engine()
        yesterday = date(2026, 5, 7)
        today = date(2026, 5, 8)
        with eng.connect() as conn:
            for sid, prev, curr in [
                ("A", 10_000_000.0, 10_200_000.0),
                ("B", 5_000_000.0, 4_900_000.0),
            ]:
                conn.execute(
                    text(_INSERT),
                    {
                        "sid": sid,
                        "date": yesterday,
                        "val": prev,
                        "ret": 0.0,
                        "regime": "C",
                        "cnt": 0,
                    },
                )
                conn.execute(
                    text(_INSERT),
                    {"sid": sid, "date": today, "val": curr, "ret": 0.0, "regime": "C", "cnt": 0},
                )
            conn.commit()

        updated = self._run_update(eng, today)
        assert updated == 2

        with eng.connect() as conn:
            rows = conn.execute(
                text(_SELECT_RETURN_ALL),
                {"d": today},
            ).fetchall()

        ret_map = {r[0]: r[1] for r in rows}
        assert ret_map["A"] == pytest.approx(0.02, abs=1e-8)
        assert ret_map["B"] == pytest.approx(-0.02, abs=1e-8)

    def test_no_previous_day_leaves_rows_unchanged(self):
        """If no prior date exists, nothing should be updated."""
        eng = _make_in_memory_engine()
        today = date(2026, 5, 8)
        with eng.connect() as conn:
            conn.execute(
                text(_INSERT),
                {
                    "sid": "A",
                    "date": today,
                    "val": 10_000_000.0,
                    "ret": 0.0,
                    "regime": "C",
                    "cnt": 0,
                },
            )
            conn.commit()

        updated = self._run_update(eng, today)
        assert updated == 0

    def test_zero_prev_value_skipped(self):
        """Rows with prev_value = 0 must not be updated (division by zero guard)."""
        eng = _make_in_memory_engine()
        yesterday = date(2026, 5, 7)
        today = date(2026, 5, 8)
        with eng.connect() as conn:
            conn.execute(
                text(_INSERT),
                {"sid": "A", "date": yesterday, "val": 0.0, "ret": 0.0, "regime": "C", "cnt": 0},
            )
            conn.execute(
                text(_INSERT),
                {
                    "sid": "A",
                    "date": today,
                    "val": 10_000_000.0,
                    "ret": 0.0,
                    "regime": "C",
                    "cnt": 0,
                },
            )
            conn.commit()

        updated = self._run_update(eng, today)
        assert updated == 0

        with eng.connect() as conn:
            ret = conn.execute(
                text(_SELECT_RETURN_BY_SID),
                {"d": today},
            ).scalar()
        assert ret == 0.0  # unchanged sentinel

    def test_no_today_rows_returns_zero(self):
        """If there are no rows for :today, rowcount should be 0."""
        eng = _make_in_memory_engine()
        yesterday = date(2026, 5, 7)
        future = date(2026, 5, 9)
        with eng.connect() as conn:
            conn.execute(
                text(_INSERT),
                {
                    "sid": "A",
                    "date": yesterday,
                    "val": 10_000_000.0,
                    "ret": 0.0,
                    "regime": "C",
                    "cnt": 0,
                },
            )
            conn.commit()

        updated = self._run_update(eng, future)
        assert updated == 0


# ---------------------------------------------------------------------------
# Tests for backfill_daily_returns() function interface (mocked engine)
# ---------------------------------------------------------------------------


class TestBackfillDailyReturnsInterface:
    """Verify the function signature and return value under a mock engine."""

    def test_returns_rowcount_integer(self):
        from atlas.simulation.core.metrics import backfill_daily_returns

        mock_result = MagicMock()
        mock_result.rowcount = 7

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = lambda _: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("atlas.simulation.core.metrics.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = backfill_daily_returns(mock_engine, date(2026, 5, 8))

        assert result == 7
        assert isinstance(result, int)

    def test_returns_zero_when_rowcount_none(self):
        from atlas.simulation.core.metrics import backfill_daily_returns

        mock_result = MagicMock()
        mock_result.rowcount = None

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = lambda _: mock_conn
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with patch("atlas.simulation.core.metrics.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = backfill_daily_returns(mock_engine, date(2026, 5, 8))

        assert result == 0

    def test_commit_called_once(self):
        from atlas.simulation.core.metrics import backfill_daily_returns

        mock_result = MagicMock()
        mock_result.rowcount = 3

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result

        with patch("atlas.simulation.core.metrics.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            backfill_daily_returns(MagicMock(), date(2026, 5, 8))

        mock_conn.commit.assert_called_once()

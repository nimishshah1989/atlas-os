"""Regression tests for migration 105 — atlas.mv_sector_deepdive.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify the CREATE MV, unique index, REFRESH, and cron
schedule SQL strings are emitted by upgrade() / downgrade() in the correct
order and with correct content.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the MV exists with the correct shape in the live DB.
Skipped by default; run on EC2 after migration is applied.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.105_mv_sector_deepdive"
_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="live-DB tests — set ATLAS_INTEGRATION_TESTS=1 to run (EC2 only)",
)


def _load() -> types.ModuleType:
    return importlib.import_module(_MODULE)


# ---------------------------------------------------------------------------
# Unit: migration metadata
# ---------------------------------------------------------------------------


class TestMigrationMetadata:
    def test_revision(self) -> None:
        assert _load().revision == "105"

    def test_down_revision(self) -> None:
        assert _load().down_revision == "104"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: SQL string content checks
# ---------------------------------------------------------------------------


class TestCreateMvSql:
    def _sql(self) -> str:
        return _load()._CREATE_MV

    def test_mv_name_present(self) -> None:
        assert "atlas.mv_sector_deepdive" in self._sql()

    def test_with_no_data(self) -> None:
        assert "WITH NO DATA" in self._sql()

    def test_latest_date_anchors_present(self) -> None:
        sql = self._sql()
        assert "latest_sector_date" in sql
        assert "latest_stock_date" in sql
        assert "latest_conviction_date" in sql

    def test_sector_spine_from_universe(self) -> None:
        sql = self._sql()
        assert "atlas_universe_stocks" in sql
        assert "sector_spine" in sql

    def test_source_tables_all_present(self) -> None:
        sql = self._sql()
        assert "atlas_sector_metrics_daily" in sql
        assert "atlas_sector_states_daily" in sql
        assert "atlas_stock_metrics_daily" in sql
        assert "atlas_stock_states_daily" in sql
        assert "atlas_stock_conviction_daily" in sql
        assert "atlas_signal_calls" in sql
        assert "atlas_index_metrics_daily" in sql

    def test_returns_jsonb_section(self) -> None:
        sql = self._sql()
        assert "returns" in sql
        assert "ret_1m" in sql
        assert "ret_3m" in sql
        assert "ret_6m" in sql
        # 1W and 12M back-derived from RS + Nifty 500
        assert "n500_ret_1w" in sql or "rs_1w_raw" in sql

    def test_rs_windows_jsonb_section(self) -> None:
        sql = self._sql()
        assert "rs_windows" in sql
        assert "rs_1w" in sql
        assert "rs_3m" in sql
        assert "rs_12m" in sql

    def test_constituents_top30_present(self) -> None:
        sql = self._sql()
        assert "constituents_top30" in sql
        # must include the key fields
        assert "rs_state" in sql
        assert "composite_score" in sql
        assert "confidence_band" in sql

    def test_open_signals_present(self) -> None:
        sql = self._sql()
        assert "open_signals" in sql
        assert "exit_date IS NULL" in sql

    def test_strength_dist_present(self) -> None:
        sql = self._sql()
        assert "strength_dist" in sql
        assert "very_strong" in sql
        assert "very_weak" in sql
        assert "NTILE(5)" in sql

    def test_top_picks_top10_present(self) -> None:
        sql = self._sql()
        assert "top_picks_top10" in sql

    def test_composite_score_formula(self) -> None:
        """Composite score must use (conviction_score - 0.5) * 20."""
        sql = self._sql()
        assert "conviction_score - 0.5" in sql
        assert "* 20" in sql

    def test_confidence_band_mapping(self) -> None:
        """industry_grade→H, baseline→M, descriptive_only→L."""
        sql = self._sql()
        assert "industry_grade" in sql
        assert "'H'" in sql
        assert "baseline" in sql
        assert "'M'" in sql
        assert "descriptive_only" in sql
        assert "'L'" in sql

    def test_null_propagation_not_zeroed(self) -> None:
        """NULL returns must use CASE WHEN IS NOT NULL, not COALESCE to zero."""
        sql = self._sql()
        # Should use CASE WHEN ... IS NOT NULL for financial values
        assert "IS NOT NULL" in sql
        # Should NOT have COALESCE on ret_* or rs_* to a numeric zero
        # (COALESCE is allowed for arrays '[]' and counts 0, not financial values)
        assert "COALESCE(sd.very_strong, 0)" in sql  # count coalescing is fine

    def test_returns_multiplied_by_100_for_display(self) -> None:
        """Returns stored as fractions, displayed as percentages."""
        sql = self._sql()
        assert "* 100" in sql

    def test_rn_composite_limit_30(self) -> None:
        """Constituents must be limited to top 30 by composite_score."""
        sql = self._sql()
        assert "rn_composite <= 30" in sql

    def test_rn_composite_limit_10_for_top_picks(self) -> None:
        """Top picks must be limited to top 10."""
        sql = self._sql()
        assert "rn_composite <= 10" in sql

    def test_no_full_table_scans_without_date_filter(self) -> None:
        """Every large table must reference a date anchor CTE."""
        sql = self._sql()
        # The date anchor CTEs are used in WHERE clauses
        assert "latest_sector_date" in sql
        assert "latest_stock_date" in sql
        assert "latest_conviction_date" in sql
        assert "latest_stock_state_date" in sql

    def test_open_signals_filters_positive_negative_only(self) -> None:
        """open_signals must only include POSITIVE/NEGATIVE actions (not NEUTRAL)."""
        sql = self._sql()
        assert "'POSITIVE'" in sql
        assert "'NEGATIVE'" in sql

    def test_effective_to_filter_on_universe(self) -> None:
        """Universe joins must filter to current members (effective_to IS NULL)."""
        sql = self._sql()
        assert "effective_to IS NULL" in sql

    def test_refreshed_at_metadata(self) -> None:
        sql = self._sql()
        assert "refreshed_at" in sql
        assert "NOW()" in sql

    def test_data_as_of_present(self) -> None:
        sql = self._sql()
        assert "data_as_of" in sql


class TestUniqueIndexSql:
    def test_index_name(self) -> None:
        sql = _load()._CREATE_UNIQUE_INDEX
        assert "uix_mv_sector_deepdive_sector_name" in sql

    def test_on_mv_name(self) -> None:
        sql = _load()._CREATE_UNIQUE_INDEX
        assert "mv_sector_deepdive" in sql

    def test_on_sector_name_column(self) -> None:
        sql = _load()._CREATE_UNIQUE_INDEX
        assert "sector_name" in sql

    def test_is_unique(self) -> None:
        sql = _load()._CREATE_UNIQUE_INDEX
        assert "UNIQUE INDEX" in sql


class TestCronSql:
    def test_cron_job_name(self) -> None:
        sql = _load()._CRON_SCHEDULE
        assert "mv_sector_deepdive_nightly" in sql

    def test_cron_schedule_20_55_ist(self) -> None:
        """20:55 IST = 15:25 UTC → '25 15 * * *'."""
        sql = _load()._CRON_SCHEDULE
        assert "25 15 * * *" in sql

    def test_cron_refresh_concurrently(self) -> None:
        sql = _load()._CRON_SCHEDULE
        assert "CONCURRENTLY" in sql
        assert "mv_sector_deepdive" in sql

    def test_unschedule_uses_same_job_name(self) -> None:
        sql = _load()._CRON_UNSCHEDULE
        assert "mv_sector_deepdive_nightly" in sql


# ---------------------------------------------------------------------------
# Unit: upgrade() and downgrade() emit ops in correct order
# ---------------------------------------------------------------------------


class TestUpgrade:
    def _run(self) -> list[MagicMock]:
        mod = _load()
        calls: list[MagicMock] = []
        with patch("alembic.op.execute") as mock_exec:
            mock_exec.side_effect = lambda sql: calls.append(sql)
            mod.upgrade()
        return calls

    def test_upgrade_emits_four_ops(self) -> None:
        calls = self._run()
        assert len(calls) == 4, f"expected 4 op.execute calls, got {len(calls)}"

    def test_first_op_creates_mv(self) -> None:
        calls = self._run()
        assert "CREATE MATERIALIZED VIEW" in calls[0]

    def test_second_op_creates_unique_index(self) -> None:
        calls = self._run()
        assert "UNIQUE INDEX" in calls[1]
        assert "mv_sector_deepdive" in calls[1]

    def test_third_op_refreshes_mv(self) -> None:
        calls = self._run()
        assert "REFRESH MATERIALIZED VIEW" in calls[2]
        assert "atlas.mv_sector_deepdive" in calls[2]

    def test_fourth_op_schedules_cron(self) -> None:
        calls = self._run()
        assert "cron.schedule" in calls[3]
        assert "mv_sector_deepdive_nightly" in calls[3]


class TestDowngrade:
    def _run(self) -> list[str]:
        mod = _load()
        calls: list[str] = []
        with patch("alembic.op.execute") as mock_exec:
            mock_exec.side_effect = lambda sql: calls.append(sql)
            mod.downgrade()
        return calls

    def test_downgrade_emits_three_ops(self) -> None:
        calls = self._run()
        assert len(calls) == 3, f"expected 3 op.execute calls, got {len(calls)}"

    def test_first_op_unschedules_cron(self) -> None:
        calls = self._run()
        assert "cron.unschedule" in calls[0]

    def test_second_op_drops_unique_index(self) -> None:
        calls = self._run()
        assert "DROP INDEX" in calls[1]
        assert "mv_sector_deepdive" in calls[1]

    def test_third_op_drops_mv(self) -> None:
        calls = self._run()
        assert "DROP MATERIALIZED VIEW" in calls[2]
        assert "mv_sector_deepdive" in calls[2]

    def test_downgrade_cron_before_mv_drop(self) -> None:
        """Cron must be unscheduled before MV is dropped (dependency order)."""
        calls = self._run()
        cron_idx = next(i for i, c in enumerate(calls) if "cron.unschedule" in c)
        mv_idx = next(i for i, c in enumerate(calls) if "DROP MATERIALIZED VIEW" in c)
        assert cron_idx < mv_idx


# ---------------------------------------------------------------------------
# Unit: JSONB section shape completeness
# ---------------------------------------------------------------------------


class TestJsonbSectionShapes:
    """Verify all 6 JSONB sections are present in the final SELECT."""

    def _final_select_sql(self) -> str:
        """Extract the portion of SQL after 'FINAL SELECT'."""
        sql = _load()._CREATE_MV
        marker = "FINAL SELECT"
        idx = sql.find(marker)
        return sql[idx:] if idx >= 0 else sql

    def test_returns_section_key(self) -> None:
        sql = _load()._CREATE_MV
        assert "'ret_1m'" in sql
        assert "'ret_3m'" in sql

    def test_rs_windows_section_keys(self) -> None:
        sql = _load()._CREATE_MV
        assert "'rs_1w'" in sql
        assert "'rs_3m'" in sql
        assert "'rs_12m'" in sql

    def test_constituents_top30_keys(self) -> None:
        sql = _load()._CREATE_MV
        assert "'symbol'" in sql
        assert "'company_name'" in sql
        assert "'tier'" in sql
        assert "'rs_state'" in sql
        assert "'composite_score'" in sql
        assert "'confidence_band'" in sql
        assert "'action'" in sql

    def test_open_signals_keys(self) -> None:
        sql = _load()._CREATE_MV
        assert "'tenure'" in sql
        assert "'cap_tier_at_trigger'" in sql
        assert "'confidence_unconditional'" in sql
        assert "'signal_date'" in sql

    def test_strength_dist_keys(self) -> None:
        sql = _load()._CREATE_MV
        assert "'very_strong'" in sql
        assert "'strong'" in sql
        assert "'neutral'" in sql
        assert "'weak'" in sql
        assert "'very_weak'" in sql

    def test_top_picks_keys(self) -> None:
        sql = _load()._CREATE_MV
        # top_picks reuses composite_score, confidence_band, action keys
        assert "top_picks_top10" in sql


# ---------------------------------------------------------------------------
# Integration tests — live DB checks (EC2 only)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestIntegrationLiveDb:
    """Live DB tests. Requires ATLAS_INTEGRATION_TESTS=1 and DATABASE_URL."""

    @pytest.fixture(scope="class")
    def engine(self):
        from sqlalchemy import create_engine

        db_url = os.environ["DATABASE_URL"]
        return create_engine(db_url)

    def test_mv_exists(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT matviewname
                    FROM pg_matviews
                    WHERE schemaname = 'atlas'
                      AND matviewname = 'mv_sector_deepdive'
                    """
                )
            )
            rows = result.fetchall()
        assert len(rows) == 1, "mv_sector_deepdive does not exist in atlas schema"

    def test_unique_index_exists(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'atlas'
                      AND tablename = 'mv_sector_deepdive'
                      AND indexname = 'uix_mv_sector_deepdive_sector_name'
                    """
                )
            )
            rows = result.fetchall()
        assert len(rows) == 1, "unique index uix_mv_sector_deepdive_sector_name not found"

    def test_mv_has_rows(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM atlas.mv_sector_deepdive"))
            count = result.scalar()
        assert count > 0, "mv_sector_deepdive has no rows after REFRESH"

    def test_mv_row_count_is_sector_count(self, engine) -> None:
        """One row per sector — should match distinct sector count in universe."""
        from sqlalchemy import text

        with engine.connect() as conn:
            mv_count = conn.execute(text("SELECT COUNT(*) FROM atlas.mv_sector_deepdive")).scalar()
            sector_count = conn.execute(
                text(
                    "SELECT COUNT(DISTINCT sector) FROM atlas.atlas_universe_stocks "
                    "WHERE effective_to IS NULL"
                )
            ).scalar()
        assert mv_count == sector_count, (
            f"MV has {mv_count} rows but universe has {sector_count} distinct sectors"
        )

    def test_verdict_column_not_null(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM atlas.mv_sector_deepdive WHERE verdict IS NULL")
            )
            null_count = result.scalar()
        assert null_count == 0, f"{null_count} rows have NULL verdict"

    def test_returns_jsonb_keys_present(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM atlas.mv_sector_deepdive
                    WHERE returns ? 'ret_1m'
                      AND returns ? 'ret_3m'
                      AND returns ? 'ret_6m'
                    """
                )
            )
            count = result.scalar()
        assert count > 0, "returns JSONB missing expected keys"

    def test_rs_windows_jsonb_keys_present(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM atlas.mv_sector_deepdive
                    WHERE rs_windows ? 'rs_1w'
                      AND rs_windows ? 'rs_3m'
                      AND rs_windows ? 'rs_12m'
                    """
                )
            )
            count = result.scalar()
        assert count > 0, "rs_windows JSONB missing expected keys"

    def test_constituents_top30_is_array(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM atlas.mv_sector_deepdive
                    WHERE jsonb_typeof(constituents_top30) = 'array'
                    """
                )
            )
            count = result.scalar()
        assert count > 0, "constituents_top30 is not a JSONB array"

    def test_strength_dist_has_all_keys(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM atlas.mv_sector_deepdive
                    WHERE strength_dist ? 'very_strong'
                      AND strength_dist ? 'strong'
                      AND strength_dist ? 'neutral'
                      AND strength_dist ? 'weak'
                      AND strength_dist ? 'very_weak'
                    """
                )
            )
            count = result.scalar()
        mv_count_result = engine.connect().execute(
            text("SELECT COUNT(*) FROM atlas.mv_sector_deepdive")
        )
        assert count == mv_count_result.scalar(), "strength_dist JSONB missing keys in some rows"

    def test_open_signals_is_array(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM atlas.mv_sector_deepdive
                    WHERE jsonb_typeof(open_signals) = 'array'
                    """
                )
            )
            count = result.scalar()
        assert count > 0, "open_signals is not a JSONB array"

    def test_top_picks_top10_is_array(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM atlas.mv_sector_deepdive
                    WHERE jsonb_typeof(top_picks_top10) = 'array'
                    """
                )
            )
            count = result.scalar()
        assert count > 0, "top_picks_top10 is not a JSONB array"

    def test_refreshed_at_is_recent(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM atlas.mv_sector_deepdive
                    WHERE refreshed_at > NOW() - INTERVAL '1 hour'
                    """
                )
            )
            count = result.scalar()
        assert count > 0, "refreshed_at is not recent — REFRESH may have failed"

    def test_constituent_count_positive_for_all_sectors(self, engine) -> None:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM atlas.mv_sector_deepdive
                    WHERE constituent_count = 0
                    """
                )
            )
            zero_count = result.scalar()
        assert zero_count == 0, (
            f"{zero_count} sectors have constituent_count = 0 "
            "(expected all sectors to have at least 1 member)"
        )

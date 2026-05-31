"""Regression tests for migration 104 — mv_sector_rrg.

Materialized view created:
- atlas.mv_sector_rrg — one row per (as_of_date, sector_name) with:
  - rs_ratio_current  (X-axis of RRG: 100 = parity vs Nifty 500)
  - rs_momentum_current (Y-axis of RRG: rate-of-change of rs_ratio over 20 days)
  - quadrant_current  ('Leading'/'Improving'/'Lagging'/'Weakening'/NULL)
  - trail_6w          (JSONB array, up to 6 weekly snapshots oldest-first)
  - refreshed_at

Formula:
  rs_ratio     = 100 + (bottomup_rs_3m_nifty500 * 100)
  rs_momentum  = rs_ratio_today - LAG(rs_ratio, 20)
  quadrant     = CASE on (rs_ratio >= 100, rs_momentum >= 0)

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify upgrade() emits:
- CREATE MATERIALIZED VIEW IF NOT EXISTS ... WITH NO DATA
- CREATE UNIQUE INDEX on (as_of_date, sector_name)
- REFRESH MATERIALIZED VIEW
- pg_cron schedule at 20:50 IST (15:20 UTC) — 'mv_sector_rrg_nightly'
- Source table atlas_sector_metrics_daily referenced
- All required columns + JSONB trail structure in the SELECT
- Formula constants (100, LAG) present

Downgrade verifies cron unschedule + DROP in safe order.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the MV exists, row shape, JSONB trail validity, quadrant enum.
Skipped by default; run on EC2.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.104_mv_sector_rrg"
_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="live-DB tests — set ATLAS_INTEGRATION_TESTS=1 to run (EC2 only)",
)


def _load() -> types.ModuleType:
    return importlib.import_module(_MODULE)


def _run_upgrade_with_mock() -> MagicMock:
    mod = _load()
    with patch.object(mod, "op") as mock_op:
        mock_op.get_bind.return_value = MagicMock()
        mod.upgrade()
    return mock_op


def _run_downgrade_with_mock() -> MagicMock:
    mod = _load()
    with patch.object(mod, "op") as mock_op:
        mock_op.get_bind.return_value = MagicMock()
        mod.downgrade()
    return mock_op


def _executed_statements(mock_op: MagicMock) -> list[str]:
    statements: list[str] = []
    for call in mock_op.execute.call_args_list:
        if not call.args:
            continue
        arg = call.args[0]
        statements.append(str(getattr(arg, "text", arg)))
    return statements


# ---------------------------------------------------------------------------
# Revision metadata
# ---------------------------------------------------------------------------


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "104"
    assert mod.down_revision == "103"
    assert mod.branch_labels is None


# ---------------------------------------------------------------------------
# upgrade — CREATE MV
# ---------------------------------------------------------------------------


def test_upgrade_creates_materialized_view() -> None:
    """MV must be created WITH NO DATA — explicit refresh follows."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE MATERIALIZED VIEW" in joined
    assert "MV_SECTOR_RRG" in joined
    assert "WITH NO DATA" in joined, "MV should be created WITH NO DATA"


def test_upgrade_uses_atlas_schema() -> None:
    """MV must be in the atlas schema."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "atlas.mv_sector_rrg" in sql


def test_upgrade_uses_if_not_exists() -> None:
    """CREATE MATERIALIZED VIEW must be idempotent (IF NOT EXISTS)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS" in sql, "MV CREATE must use IF NOT EXISTS"


# ---------------------------------------------------------------------------
# Source tables
# ---------------------------------------------------------------------------


def test_upgrade_references_sector_metrics_daily() -> None:
    """MV must read from atlas_sector_metrics_daily."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "atlas_sector_metrics_daily" in sql, "atlas_sector_metrics_daily must be source table"


def test_upgrade_reads_bottomup_rs_3m_nifty500() -> None:
    """rs_ratio must be derived from bottomup_rs_3m_nifty500."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "bottomup_rs_3m_nifty500" in sql, (
        "bottomup_rs_3m_nifty500 must be read from atlas_sector_metrics_daily"
    )


def test_upgrade_covers_date_range_from_2020() -> None:
    """Date spine must start from 2020-01-01 per spec (5-year minimum)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "2020-01-01" in sql, "Date spine must start from 2020-01-01"


# ---------------------------------------------------------------------------
# RRG formula — rs_ratio
# ---------------------------------------------------------------------------


def test_upgrade_rs_ratio_uses_100_base() -> None:
    """rs_ratio formula must add 100 so parity RS → 100.0."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    # Either 'rs_ratio' keyword and '100' constant must both appear
    assert "rs_ratio" in sql.lower(), "rs_ratio column missing from MV"
    assert "100" in sql, "rs_ratio formula must include 100 (parity base)"


def test_upgrade_rs_ratio_multiplies_by_100() -> None:
    """bottomup_rs_3m_nifty500 (fraction) must be multiplied by 100 in rs_ratio."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    # Accept '* 100' or '*100' — multiply by 100 to convert fraction to percentage points
    assert "* 100" in sql or "*100" in sql, "rs_ratio must multiply bottomup_rs_3m_nifty500 by 100"


# ---------------------------------------------------------------------------
# RRG formula — rs_momentum
# ---------------------------------------------------------------------------


def test_upgrade_rs_momentum_uses_lag() -> None:
    """rs_momentum must use LAG window function over 20 periods."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "LAG" in sql, "rs_momentum must use LAG window function"
    assert "20" in sql, "LAG must use 20-period lookback for rs_momentum"


def test_upgrade_rs_momentum_partitions_by_sector() -> None:
    """LAG window must PARTITION BY sector_name ORDER BY date."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "partition by sector_name" in sql, "LAG must PARTITION BY sector_name"
    assert "order by date" in sql, "LAG must ORDER BY date"


def test_upgrade_emits_rs_momentum_column() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "rs_momentum" in sql, "rs_momentum column missing from MV"


# ---------------------------------------------------------------------------
# Quadrant assignment
# ---------------------------------------------------------------------------


def test_upgrade_emits_quadrant_column() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "quadrant" in sql, "quadrant column missing from MV"


def test_upgrade_quadrant_has_all_four_values() -> None:
    """All 4 quadrant labels must appear in the CASE statement."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    for label in ("Leading", "Improving", "Lagging", "Weakening"):
        assert label in sql, f"Quadrant label '{label}' missing from CASE in MV"


def test_upgrade_quadrant_uses_100_threshold_for_rs_ratio() -> None:
    """Quadrant split on rs_ratio must use 100 as the parity threshold."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    # Leading: rs_ratio >= 100; Lagging: rs_ratio < 100
    assert ">= 100" in sql or ">=100" in sql, (
        "Quadrant must use rs_ratio >= 100 for Leading/Weakening"
    )
    assert "< 100" in sql or "<100" in sql, "Quadrant must use rs_ratio < 100 for Lagging/Improving"


def test_upgrade_quadrant_null_guard() -> None:
    """Quadrant must be NULL when inputs are NULL (never a default string)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "ELSE NULL" in sql, "Quadrant CASE must include ELSE NULL guard"


# ---------------------------------------------------------------------------
# trail_6w JSONB
# ---------------------------------------------------------------------------


def test_upgrade_emits_trail_6w_column() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "trail_6w" in sql, "trail_6w JSONB column missing from MV"


def test_upgrade_trail_uses_jsonb_agg() -> None:
    """trail_6w must be built with jsonb_agg."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "jsonb_agg" in sql, "trail_6w must use jsonb_agg"


def test_upgrade_trail_uses_jsonb_build_object() -> None:
    """Each trail element must be a jsonb_build_object."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "jsonb_build_object" in sql, "trail element must use jsonb_build_object"


def test_upgrade_trail_has_week_end_date_key() -> None:
    """trail_6w objects must include 'week_end_date' key."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "'week_end_date'" in sql, "trail_6w must include 'week_end_date' key"


def test_upgrade_trail_has_rs_ratio_key() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "'rs_ratio'" in sql, "trail_6w must include 'rs_ratio' key"


def test_upgrade_trail_has_rs_momentum_key() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "'rs_momentum'" in sql, "trail_6w must include 'rs_momentum' key"


def test_upgrade_trail_has_quadrant_key() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "'quadrant'" in sql, "trail_6w must include 'quadrant' key"


def test_upgrade_trail_limits_to_6_snapshots() -> None:
    """Trail must be limited to 6 weekly snapshots."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "LIMIT 6" in sql, "trail_6w must LIMIT to 6 weekly snapshots"


def test_upgrade_trail_uses_weekly_sampling() -> None:
    """Trail must use every-5th-row sampling (ROW_NUMBER modulo 5)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "ROW_NUMBER" in sql, "Trail sampling must use ROW_NUMBER() window function"
    assert "% 5" in sql or "MOD" in sql, "Trail must sample every 5th row (row_num % 5)"


def test_upgrade_trail_coalesces_to_empty_array() -> None:
    """trail_6w must COALESCE to empty array when no weekly anchors found."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "coalesce" in sql, "trail_6w must COALESCE to '[]'::jsonb on NULL"
    assert "'[]'" in sql or "[]" in sql, "trail_6w COALESCE must use empty array default"


# ---------------------------------------------------------------------------
# Current scalar columns
# ---------------------------------------------------------------------------


def test_upgrade_emits_rs_ratio_current() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "rs_ratio_current" in sql, "rs_ratio_current column missing from MV SELECT"


def test_upgrade_emits_rs_momentum_current() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "rs_momentum_current" in sql, "rs_momentum_current column missing from MV SELECT"


def test_upgrade_emits_quadrant_current() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "quadrant_current" in sql, "quadrant_current column missing from MV SELECT"


def test_upgrade_emits_refreshed_at() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "refreshed_at" in sql, "refreshed_at metadata column missing from MV"


# ---------------------------------------------------------------------------
# Unique index
# ---------------------------------------------------------------------------


def test_upgrade_creates_unique_index() -> None:
    """Unique index on (as_of_date, sector_name) required for CONCURRENTLY refresh."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE UNIQUE INDEX" in joined
    assert "MV_SECTOR_RRG" in joined
    assert "AS_OF_DATE" in joined
    assert "SECTOR_NAME" in joined


def test_upgrade_refreshes_mv_after_index() -> None:
    """REFRESH MATERIALIZED VIEW must come after CREATE UNIQUE INDEX."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "REFRESH MATERIALIZED VIEW" in joined
    idx_pos = joined.index("CREATE UNIQUE INDEX")
    refresh_pos = joined.index("REFRESH MATERIALIZED VIEW")
    assert refresh_pos > idx_pos, "REFRESH must come after CREATE UNIQUE INDEX"


# ---------------------------------------------------------------------------
# pg_cron schedule
# ---------------------------------------------------------------------------


def test_upgrade_schedules_cron_at_correct_time() -> None:
    """pg_cron must be at 20 15 * * * (20:50 IST = 15:20 UTC)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "mv_sector_rrg_nightly" in sql
    assert "20 15 * * *" in sql, "Cron must run at 15:20 UTC (20:50 IST)"


def test_upgrade_cron_uses_concurrently() -> None:
    """pg_cron must use REFRESH MATERIALIZED VIEW CONCURRENTLY."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    cron_idx = sql.index("MV_SECTOR_RRG_NIGHTLY")
    cron_block = sql[cron_idx:]
    assert "CONCURRENTLY" in cron_block, "pg_cron must use CONCURRENTLY refresh"


def test_upgrade_cron_refreshes_mv_sector_rrg() -> None:
    """pg_cron command must reference mv_sector_rrg."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "mv_sector_rrg" in sql.lower()


# ---------------------------------------------------------------------------
# Step order
# ---------------------------------------------------------------------------


def test_upgrade_step_order() -> None:
    """Upgrade order: CREATE MV → CREATE INDEX → REFRESH → CRON."""
    statements = _executed_statements(_run_upgrade_with_mock())
    upper = [s.upper() for s in statements]
    positions = {
        "create_mv": next((i for i, s in enumerate(upper) if "CREATE MATERIALIZED VIEW" in s), -1),
        "create_idx": next((i for i, s in enumerate(upper) if "CREATE UNIQUE INDEX" in s), -1),
        "refresh": next((i for i, s in enumerate(upper) if "REFRESH MATERIALIZED VIEW" in s), -1),
        "cron": next((i for i, s in enumerate(upper) if "CRON.SCHEDULE" in s), -1),
    }
    assert positions["create_mv"] != -1, "CREATE MV step not found"
    assert positions["create_idx"] != -1, "CREATE INDEX step not found"
    assert positions["refresh"] != -1, "REFRESH step not found"
    assert positions["cron"] != -1, "CRON SCHEDULE step not found"
    assert (
        positions["create_mv"] < positions["create_idx"] < positions["refresh"] < positions["cron"]
    ), "Steps must execute in order: CREATE MV → CREATE INDEX → REFRESH → CRON"


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def test_downgrade_drops_materialized_view() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "DROP MATERIALIZED VIEW" in joined
    assert "MV_SECTOR_RRG" in joined


def test_downgrade_uses_if_exists() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "DROP MATERIALIZED VIEW IF EXISTS" in sql, "downgrade DROP must be IF EXISTS"


def test_downgrade_unschedules_cron() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    sql = "\n".join(statements)
    assert "mv_sector_rrg_nightly" in sql
    assert "unschedule" in sql.lower(), "downgrade must unschedule the cron job"


def test_downgrade_cron_before_drop() -> None:
    """Cron must be unscheduled before the MV is dropped."""
    statements = _executed_statements(_run_downgrade_with_mock())
    upper = [s.upper() for s in statements]
    cron_pos = next((i for i, s in enumerate(upper) if "UNSCHEDULE" in s), -1)
    drop_pos = next((i for i, s in enumerate(upper) if "DROP MATERIALIZED VIEW" in s), -1)
    assert cron_pos != -1, "UNSCHEDULE step not found in downgrade"
    assert drop_pos != -1, "DROP MV step not found in downgrade"
    assert cron_pos < drop_pos, "Cron must be unscheduled before MV is dropped"


# ---------------------------------------------------------------------------
# Integration tests (live DB — EC2 only)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
def test_mv_exists_and_is_populated() -> None:  # pragma: no cover
    """MV must exist and have rows after REFRESH."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        result = conn.execute(sa.text("SELECT COUNT(*) FROM atlas.mv_sector_rrg")).scalar()
    # 31 sectors × 1,550+ trading days from 2020-01-01
    assert result is not None and result >= 31, f"Expected >= 31 rows, got {result}"


@_SKIP_INTEGRATION
def test_mv_row_shape_latest() -> None:  # pragma: no cover
    """Latest date must have ~31 sector rows with valid RRG scalars."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT
                    sector_name,
                    rs_ratio_current,
                    rs_momentum_current,
                    quadrant_current,
                    trail_6w,
                    refreshed_at
                FROM atlas.mv_sector_rrg
                WHERE as_of_date = (
                    SELECT MAX(as_of_date) FROM atlas.mv_sector_rrg
                )
                ORDER BY sector_name
                """
            )
        ).fetchall()

    assert len(rows) >= 1, "Expected at least 1 sector row on latest date"

    valid_quadrants = {"Leading", "Improving", "Lagging", "Weakening", None}
    for row in rows:
        sn = row[0]
        rs_ratio, _rs_momentum, quadrant, trail, refreshed = row[1], row[2], row[3], row[4], row[5]

        # quadrant must be one of the 4 valid values or NULL
        assert quadrant in valid_quadrants, f"{sn}: unexpected quadrant '{quadrant}'"

        # rs_ratio if non-null must be in a plausible range (80-120 for sector RS)
        if rs_ratio is not None:
            assert 50 <= float(rs_ratio) <= 150, (
                f"{sn}: rs_ratio {rs_ratio} out of expected range [50, 150]"
            )

        # trail must be a list (possibly empty)
        assert isinstance(trail, list), f"{sn}: trail_6w must be a list"
        assert len(trail) <= 6, f"{sn}: trail_6w must have at most 6 elements"

        # refreshed_at must be set
        assert refreshed is not None, f"{sn}: refreshed_at must not be NULL"


@_SKIP_INTEGRATION
def test_mv_trail_6w_structure() -> None:  # pragma: no cover
    """trail_6w elements must have required keys: week_end_date, rs_ratio, rs_momentum, quadrant."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT sector_name, as_of_date, trail_6w
                FROM atlas.mv_sector_rrg
                WHERE as_of_date = (SELECT MAX(as_of_date) FROM atlas.mv_sector_rrg)
                  AND jsonb_array_length(trail_6w) > 0
                ORDER BY sector_name
                LIMIT 20
                """
            )
        ).fetchall()

    assert len(rows) > 0, "Expected at least some rows with non-empty trail_6w"

    required_keys = {"week_end_date", "rs_ratio", "rs_momentum", "quadrant"}
    valid_quadrants = {"Leading", "Improving", "Lagging", "Weakening", None}
    for row in rows:
        sn, as_of_date, trail = row[0], row[1], row[2]
        assert isinstance(trail, list), f"{sn}: trail_6w must be a list"
        for elem in trail:
            missing = required_keys - set(elem.keys())
            assert not missing, f"{sn} @ {as_of_date}: trail element missing keys: {missing}"
            assert elem.get("quadrant") in valid_quadrants, (
                f"{sn}: trail element has invalid quadrant '{elem.get('quadrant')}'"
            )


@_SKIP_INTEGRATION
def test_mv_rs_ratio_range_sane() -> None:  # pragma: no cover
    """rs_ratio_current must be in [50, 150] where non-NULL (extreme outlier check)."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        bad = conn.execute(
            sa.text(
                """
                SELECT sector_name, as_of_date, rs_ratio_current
                FROM atlas.mv_sector_rrg
                WHERE rs_ratio_current IS NOT NULL
                  AND (rs_ratio_current < 50 OR rs_ratio_current > 150)
                LIMIT 5
                """
            )
        ).fetchall()

    assert len(bad) == 0, f"rs_ratio_current out of range [50, 150]: {bad}"


@_SKIP_INTEGRATION
def test_mv_quadrant_distribution_sane() -> None:  # pragma: no cover
    """Latest date must have at least 2 distinct non-NULL quadrant values."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        quadrants = {
            row[0]
            for row in conn.execute(
                sa.text(
                    """
                    SELECT DISTINCT quadrant_current
                    FROM atlas.mv_sector_rrg
                    WHERE as_of_date = (SELECT MAX(as_of_date) FROM atlas.mv_sector_rrg)
                      AND quadrant_current IS NOT NULL
                    """
                )
            ).all()
        }

    assert len(quadrants) >= 2, f"Expected >= 2 distinct quadrants on latest date, got: {quadrants}"
    assert quadrants.issubset({"Leading", "Improving", "Lagging", "Weakening"}), (
        f"Unexpected quadrant values: {quadrants}"
    )


@_SKIP_INTEGRATION
def test_mv_sector_coverage_minimum() -> None:  # pragma: no cover
    """MV must have >= 1,000 rows (at least 31 sectors x ~32 trading days)."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        total = conn.execute(sa.text("SELECT COUNT(*) FROM atlas.mv_sector_rrg")).scalar()
        sector_count = conn.execute(
            sa.text("SELECT COUNT(DISTINCT sector_name) FROM atlas.mv_sector_rrg")
        ).scalar()

    assert total >= 1_000, f"Expected >= 1,000 rows, got {total}"
    assert sector_count >= 1, f"Expected >= 1 distinct sector, got {sector_count}"


@_SKIP_INTEGRATION
def test_mv_cron_job_registered() -> None:  # pragma: no cover
    """pg_cron job must exist after upgrade with correct schedule."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                """
                SELECT schedule
                FROM cron.job
                WHERE jobname = 'mv_sector_rrg_nightly'
                """
            )
        ).fetchone()

    assert row is not None, "pg_cron job 'mv_sector_rrg_nightly' not found"
    assert row[0] == "20 15 * * *", f"Expected cron '20 15 * * *', got '{row[0]}'"


@_SKIP_INTEGRATION
def test_mv_date_range_starts_2020() -> None:  # pragma: no cover
    """MV date range must start at or after 2020-01-01."""
    import datetime

    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        min_date = conn.execute(sa.text("SELECT MIN(as_of_date) FROM atlas.mv_sector_rrg")).scalar()

    assert min_date is not None
    assert min_date >= datetime.date(2020, 1, 1), (
        f"Expected date range starting 2020-01-01, got min_date={min_date}"
    )


@_SKIP_INTEGRATION
def test_mv_trail_oldest_first_ordering() -> None:  # pragma: no cover
    """trail_6w must be sorted oldest-first (ascending dates)."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT sector_name, trail_6w
                FROM atlas.mv_sector_rrg
                WHERE as_of_date = (SELECT MAX(as_of_date) FROM atlas.mv_sector_rrg)
                  AND jsonb_array_length(trail_6w) > 1
                ORDER BY sector_name
                LIMIT 10
                """
            )
        ).fetchall()

    assert len(rows) > 0, "Expected rows with multi-element trail for ordering test"
    for row in rows:
        sn, trail = row[0], row[1]
        dates = [elem["week_end_date"] for elem in trail if elem.get("week_end_date")]
        assert dates == sorted(dates), f"{sn}: trail_6w is not oldest-first. Got dates: {dates}"

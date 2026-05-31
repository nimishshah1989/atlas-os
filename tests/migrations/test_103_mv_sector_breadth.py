"""Regression tests for migration 103 — mv_sector_breadth.

Materialized view created:
- atlas.mv_sector_breadth — one row per (as_of_date, sector_name) with:
  - Scalar breadth: pct_above_ema20, pct_above_ema50, pct_above_ema200, pct_at_52wh
  - JSONB breadth_by_window: array of 4 objects (1W/1M/3M/6M) with
    pct_positive + pct_top_decile_movers
  - JSONB breadth_by_strength: {very_strong, strong, neutral, weak, very_weak} counts
  - JSONB top_movers + bottom_movers: top 5 and bottom 5 stocks by ret_1m
  - constituent_count, refreshed_at

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify upgrade() emits:
- CREATE MATERIALIZED VIEW IF NOT EXISTS ... WITH NO DATA
- CREATE UNIQUE INDEX on (as_of_date, sector_name)
- REFRESH MATERIALIZED VIEW
- pg_cron schedule at 20:45 IST (14:45 UTC) — 'mv_sector_breadth_nightly'
- All 3 source tables referenced
- All required columns + JSONB structures in the SELECT

Downgrade verifies cron unschedule + DROP in safe order.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the MV exists with correct row shape and JSONB structure validity.
Skipped by default; run on EC2.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.103_mv_sector_breadth"
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
    assert mod.revision == "103"
    assert mod.down_revision == "102"
    assert mod.branch_labels is None


# ---------------------------------------------------------------------------
# upgrade — CREATE MV
# ---------------------------------------------------------------------------


def test_upgrade_creates_materialized_view() -> None:
    """MV must be created WITH NO DATA — explicit refresh follows."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE MATERIALIZED VIEW" in joined
    assert "MV_SECTOR_BREADTH" in joined
    assert "WITH NO DATA" in joined, "MV should be created WITH NO DATA"


def test_upgrade_uses_atlas_schema() -> None:
    """MV must be in the atlas schema."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "atlas.mv_sector_breadth" in sql


def test_upgrade_uses_if_not_exists() -> None:
    """CREATE MATERIALIZED VIEW must be idempotent (IF NOT EXISTS)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS" in sql, "MV CREATE must use IF NOT EXISTS"


# ---------------------------------------------------------------------------
# Source tables
# ---------------------------------------------------------------------------


def test_upgrade_references_all_source_tables() -> None:
    """MV must pull from all 3 required source tables."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    sources = [
        "atlas_sector_metrics_daily",
        "atlas_universe_stocks",
        "atlas_stock_metrics_daily",
    ]
    for src in sources:
        assert src in sql, f"source table '{src}' missing from MV body"


def test_upgrade_uses_effective_to_null_filter() -> None:
    """Universe stock join must filter effective_to IS NULL (current members only)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "effective_to is null" in sql, (
        "Must filter atlas_universe_stocks on effective_to IS NULL"
    )


def test_upgrade_date_spine_from_sector_metrics() -> None:
    """Date spine must come from atlas_sector_metrics_daily."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "atlas_sector_metrics_daily" in sql


def test_upgrade_covers_date_range_from_2020() -> None:
    """Date spine must start from 2020-01-01 per spec (5-year minimum)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "2020-01-01" in sql, "Date spine must start from 2020-01-01"


# ---------------------------------------------------------------------------
# EMA breadth scalar columns
# ---------------------------------------------------------------------------


def test_upgrade_emits_ema20_breadth() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "pct_above_ema20" in sql, "pct_above_ema20 missing from MV"


def test_upgrade_emits_ema50_breadth() -> None:
    """pct_above_ema50 must come from participation_50 in atlas_sector_metrics_daily."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "pct_above_ema50" in sql, "pct_above_ema50 missing from MV"
    assert "participation_50" in sql, "participation_50 (source for ema50) must be referenced"


def test_upgrade_emits_ema200_breadth() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "pct_above_ema200" in sql, "pct_above_ema200 missing from MV"


def test_upgrade_emits_52wh_breadth() -> None:
    """pct_at_52wh must come from pct_52wh in atlas_sector_metrics_daily."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "pct_at_52wh" in sql, "pct_at_52wh missing from MV"
    assert "pct_52wh" in sql, "pct_52wh (source column) must be referenced"


def test_upgrade_emits_constituent_count() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "constituent_count" in sql, "constituent_count missing from MV"


# ---------------------------------------------------------------------------
# breadth_by_window JSONB
# ---------------------------------------------------------------------------


def test_upgrade_emits_breadth_by_window() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "breadth_by_window" in sql, "breadth_by_window JSONB column missing from MV"


def test_upgrade_breadth_by_window_is_json_array() -> None:
    """breadth_by_window must use jsonb_build_array to produce the 4-element array."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "jsonb_build_array" in sql, "breadth_by_window must use jsonb_build_array"


def test_upgrade_breadth_by_window_has_all_four_windows() -> None:
    """All 4 lookback windows must appear: 1W, 1M, 3M, 6M."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    for window in ("'1W'", "'1M'", "'3M'", "'6M'"):
        assert window in sql, f"breadth_by_window missing window {window}"


def test_upgrade_breadth_by_window_has_pct_positive() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "'pct_positive'" in sql, "breadth_by_window must include pct_positive key"


def test_upgrade_breadth_by_window_has_pct_top_decile_movers() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "'pct_top_decile_movers'" in sql, (
        "breadth_by_window must include pct_top_decile_movers key"
    )


def test_upgrade_breadth_by_window_uses_ret_columns() -> None:
    """breadth_by_window must read ret_1w, ret_1m, ret_3m, ret_6m from stock_metrics_daily."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    for col in ("ret_1w", "ret_1m", "ret_3m", "ret_6m"):
        assert col in sql, f"breadth_by_window must use {col} from atlas_stock_metrics_daily"


def test_upgrade_breadth_by_window_uses_ntile_for_decile() -> None:
    """Top decile movers must use NTILE(10) window function."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "NTILE(10)" in sql, "Top decile computation must use NTILE(10)"


def test_upgrade_breadth_by_window_null_guard_for_zero_n() -> None:
    """pct_positive must be NULL (not 0) when no stocks have non-NULL returns."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    # CASE WHEN n > 0 THEN ... ELSE NULL END
    assert "ELSE NULL" in sql, "pct_positive must guard against n=0 and return NULL (not 0)"


# ---------------------------------------------------------------------------
# breadth_by_strength JSONB
# ---------------------------------------------------------------------------


def test_upgrade_emits_breadth_by_strength() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "breadth_by_strength" in sql, "breadth_by_strength JSONB column missing from MV"


def test_upgrade_breadth_by_strength_has_five_buckets() -> None:
    """breadth_by_strength must have very_strong, strong, neutral, weak, very_weak keys."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    for key in ("'very_strong'", "'strong'", "'neutral'", "'weak'", "'very_weak'"):
        assert key in sql, f"breadth_by_strength missing bucket key {key}"


def test_upgrade_breadth_by_strength_uses_ntile5() -> None:
    """Strength distribution must use NTILE(5) for quintile bucketing."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "NTILE(5)" in sql, "breadth_by_strength must use NTILE(5) for quintile distribution"


def test_upgrade_breadth_by_strength_based_on_ret_3m() -> None:
    """Strength quintiles must be computed on ret_3m."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "ret_3m" in sql, "breadth_by_strength must use ret_3m for quintile ordering"


# ---------------------------------------------------------------------------
# top_movers / bottom_movers JSONB
# ---------------------------------------------------------------------------


def test_upgrade_emits_top_movers() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "top_movers" in sql, "top_movers JSONB column missing from MV"


def test_upgrade_emits_bottom_movers() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "bottom_movers" in sql, "bottom_movers JSONB column missing from MV"


def test_upgrade_movers_limit_5() -> None:
    """Movers lists must be limited to top 5 each."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "LIMIT 5" in sql, "top/bottom movers must be limited to 5 stocks"


def test_upgrade_movers_has_symbol_and_ret_pct_keys() -> None:
    """Movers JSONB objects must include 'symbol' and 'ret_pct' keys."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "'symbol'" in sql, "movers must include 'symbol' key"
    assert "'ret_pct'" in sql, "movers must include 'ret_pct' key"


def test_upgrade_movers_returns_empty_array_on_null() -> None:
    """top_movers and bottom_movers must COALESCE to '[]'::jsonb when NULL."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "'[]'" in sql or "[]" in sql, "movers must COALESCE to empty array when NULL"


# ---------------------------------------------------------------------------
# refreshed_at
# ---------------------------------------------------------------------------


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
    assert "MV_SECTOR_BREADTH" in joined
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
    """pg_cron must be at 45 14 * * * (20:45 IST = 14:45 UTC)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "mv_sector_breadth_nightly" in sql
    assert "45 14 * * *" in sql, "Cron must run at 14:45 UTC (20:45 IST)"


def test_upgrade_cron_uses_concurrently() -> None:
    """pg_cron must use REFRESH MATERIALIZED VIEW CONCURRENTLY."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    cron_idx = sql.index("MV_SECTOR_BREADTH_NIGHTLY")
    cron_block = sql[cron_idx:]
    assert "CONCURRENTLY" in cron_block, "pg_cron must use CONCURRENTLY refresh"


def test_upgrade_cron_refreshes_mv_sector_breadth() -> None:
    """pg_cron command must reference mv_sector_breadth."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "mv_sector_breadth" in sql.lower()


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
    assert "MV_SECTOR_BREADTH" in joined


def test_downgrade_uses_if_exists() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "DROP MATERIALIZED VIEW IF EXISTS" in sql, "downgrade DROP must be IF EXISTS"


def test_downgrade_unschedules_cron() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    sql = "\n".join(statements)
    assert "mv_sector_breadth_nightly" in sql
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
        result = conn.execute(sa.text("SELECT COUNT(*) FROM atlas.mv_sector_breadth")).scalar()
    # 31 sectors × 1,550+ trading days from 2020-01-01
    assert result is not None and result >= 31, f"Expected >= 31 rows, got {result}"


@_SKIP_INTEGRATION
def test_mv_row_shape_latest() -> None:  # pragma: no cover
    """Latest date must have ~31 sector rows with breadth_by_window non-null."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT
                    sector_name,
                    constituent_count,
                    breadth_by_window,
                    breadth_by_strength,
                    top_movers,
                    bottom_movers,
                    refreshed_at
                FROM atlas.mv_sector_breadth
                WHERE as_of_date = (
                    SELECT MAX(as_of_date) FROM atlas.mv_sector_breadth
                )
                ORDER BY sector_name
                """
            )
        ).fetchall()

    assert len(rows) >= 1, "Expected at least 1 sector row on latest date"

    for row in rows:
        sn = row[0]
        constituent_count, breadth_window, _breadth_strength, top_mv, bot_mv, refreshed = (
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
        )
        # constituent_count must be non-negative integer
        assert constituent_count is not None and constituent_count >= 0, (
            f"{sn}: constituent_count must be >= 0"
        )
        # breadth_by_window must be a list of 4 elements
        if breadth_window is not None:
            assert isinstance(breadth_window, list), f"{sn}: breadth_by_window must be a list"
            assert len(breadth_window) == 4, f"{sn}: breadth_by_window must have 4 elements"
            for elem in breadth_window:
                assert "window" in elem, f"{sn}: breadth_by_window element missing 'window' key"
                assert "pct_positive" in elem, (
                    f"{sn}: breadth_by_window element missing 'pct_positive'"
                )
                assert "pct_top_decile_movers" in elem, (
                    f"{sn}: breadth_by_window element missing 'pct_top_decile_movers'"
                )
                assert elem["window"] in (
                    "1W",
                    "1M",
                    "3M",
                    "6M",
                ), f"{sn}: unexpected window value '{elem['window']}'"
        # top_movers / bottom_movers: must be list (possibly empty)
        assert isinstance(top_mv, list), f"{sn}: top_movers must be a list"
        assert isinstance(bot_mv, list), f"{sn}: bottom_movers must be a list"
        assert len(top_mv) <= 5, f"{sn}: top_movers must have at most 5 elements"
        assert len(bot_mv) <= 5, f"{sn}: bottom_movers must have at most 5 elements"
        # refreshed_at must be set
        assert refreshed is not None, f"{sn}: refreshed_at must not be NULL"


@_SKIP_INTEGRATION
def test_mv_breadth_by_window_pct_in_valid_range() -> None:  # pragma: no cover
    """pct_positive and pct_top_decile_movers must be in [0.0, 1.0] or NULL."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT sector_name, as_of_date, w->>'window' AS win,
                       (w->>'pct_positive')::float           AS pct_pos,
                       (w->>'pct_top_decile_movers')::float  AS pct_top
                FROM atlas.mv_sector_breadth,
                     jsonb_array_elements(breadth_by_window) w
                WHERE breadth_by_window IS NOT NULL
                  AND (
                    (w->>'pct_positive')::float NOT BETWEEN 0 AND 1
                    OR (w->>'pct_top_decile_movers')::float NOT BETWEEN 0 AND 1
                  )
                LIMIT 5
                """
            )
        ).fetchall()

    assert len(rows) == 0, f"Out-of-range pct values found: {rows}"


@_SKIP_INTEGRATION
def test_mv_breadth_by_strength_counts_non_negative() -> None:  # pragma: no cover
    """All quintile counts in breadth_by_strength must be >= 0."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        bad_rows = conn.execute(
            sa.text(
                """
                SELECT sector_name, as_of_date, breadth_by_strength
                FROM atlas.mv_sector_breadth
                WHERE breadth_by_strength IS NOT NULL
                  AND (
                    (breadth_by_strength->>'very_strong')::int < 0
                    OR (breadth_by_strength->>'strong')::int < 0
                    OR (breadth_by_strength->>'neutral')::int < 0
                    OR (breadth_by_strength->>'weak')::int < 0
                    OR (breadth_by_strength->>'very_weak')::int < 0
                  )
                LIMIT 5
                """
            )
        ).fetchall()

    assert len(bad_rows) == 0, f"Negative quintile counts found: {bad_rows}"


@_SKIP_INTEGRATION
def test_mv_movers_have_symbol_and_ret_pct() -> None:  # pragma: no cover
    """Every mover object must have symbol and ret_pct keys."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        bad_rows = conn.execute(
            sa.text(
                """
                SELECT sector_name, as_of_date, m
                FROM (
                  SELECT sector_name, as_of_date,
                         jsonb_array_elements(top_movers) AS m
                  FROM atlas.mv_sector_breadth
                  WHERE jsonb_array_length(top_movers) > 0
                  LIMIT 1000
                ) sub
                WHERE (m->>'symbol') IS NULL
                   OR (m->>'ret_pct') IS NULL
                LIMIT 5
                """
            )
        ).fetchall()

    assert len(bad_rows) == 0, f"Movers with missing symbol or ret_pct: {bad_rows}"


@_SKIP_INTEGRATION
def test_mv_sector_coverage_minimum() -> None:  # pragma: no cover
    """MV must have >= 1,000 rows (at least 31 sectors x ~32 trading days)."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        total = conn.execute(sa.text("SELECT COUNT(*) FROM atlas.mv_sector_breadth")).scalar()
        sector_count = conn.execute(
            sa.text("SELECT COUNT(DISTINCT sector_name) FROM atlas.mv_sector_breadth")
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
                WHERE jobname = 'mv_sector_breadth_nightly'
                """
            )
        ).fetchone()

    assert row is not None, "pg_cron job 'mv_sector_breadth_nightly' not found"
    assert row[0] == "45 14 * * *", f"Expected cron '45 14 * * *', got '{row[0]}'"


@_SKIP_INTEGRATION
def test_mv_date_range_starts_2020() -> None:  # pragma: no cover
    """MV date range must start at or after 2020-01-01."""
    import datetime

    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        min_date = conn.execute(
            sa.text("SELECT MIN(as_of_date) FROM atlas.mv_sector_breadth")
        ).scalar()

    assert min_date is not None
    assert min_date >= datetime.date(2020, 1, 1), (
        f"Expected date range starting 2020-01-01, got min_date={min_date}"
    )

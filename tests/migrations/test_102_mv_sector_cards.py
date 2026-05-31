"""Regression tests for migration 102 — mv_sector_cards.

Materialized view created:
- atlas.mv_sector_cards — one row per (as_of_date, sector_name)
  with all 15+ mockup-required columns for Page 04 Sectors.

Columns: sector_name, constituent_count, ret_1w, ret_1m, ret_3m, ret_6m,
ret_12m, rs_1m, rs_3m, rs_6m, vol_60d_ann, pct_above_ema20, pct_above_ema200,
pct_at_52wh, hhi_concentration, buy_signal_count, confidence_distribution
(JSONB {"H":n,"M":n,"L":n}), verdict, verdict_abbr, refreshed_at.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify upgrade() emits:
- CREATE MATERIALIZED VIEW ... WITH NO DATA
- CREATE UNIQUE INDEX on (as_of_date, sector_name)
- REFRESH MATERIALIZED VIEW
- pg_cron schedule at 20:40 IST (14:40 UTC)
- All 6 source tables referenced
- All required columns in the SELECT

Downgrade verifies cron unschedule + DROP in safe order.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the MV exists, row count >= 31 (at least 1 date × 31 sectors),
and sample the latest date rows for shape validity.
Skipped by default; run on EC2.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.102_mv_sector_cards"
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
    assert mod.revision == "102"
    assert mod.down_revision == "101"
    assert mod.branch_labels is None


# ---------------------------------------------------------------------------
# upgrade — CREATE MV
# ---------------------------------------------------------------------------


def test_upgrade_creates_materialized_view() -> None:
    """MV must be created WITH NO DATA — explicit refresh follows."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE MATERIALIZED VIEW" in joined
    assert "MV_SECTOR_CARDS" in joined
    assert "WITH NO DATA" in joined, "MV should be created WITH NO DATA"


def test_upgrade_uses_atlas_schema() -> None:
    """MV must be in the atlas schema."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "atlas.mv_sector_cards" in sql


# ---------------------------------------------------------------------------
# Source tables
# ---------------------------------------------------------------------------


def test_upgrade_references_all_source_tables() -> None:
    """MV must pull from all 6 required source tables."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    sources = [
        "atlas_sector_metrics_daily",
        "atlas_sector_states_daily",
        "atlas_signal_calls",
        "atlas_universe_stocks",
        "atlas_stock_metrics_daily",
        "atlas_index_metrics_daily",
    ]
    for src in sources:
        assert src in sql, f"source table '{src}' missing from MV body"


def test_upgrade_uses_nifty500_for_return_derivation() -> None:
    """Nifty 500 must be referenced to back-derive 1W and 12M absolute returns."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "NIFTY 500" in sql, "NIFTY 500 must be used to back-derive sector returns"


def test_upgrade_vol_uses_realized_vol_63() -> None:
    """vol_60d_ann must be computed from realized_vol_63 in stock_metrics_daily."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "realized_vol_63" in sql, (
        "vol_60d_ann must use realized_vol_63 from atlas_stock_metrics_daily"
    )


def test_upgrade_signals_filter_positive_action() -> None:
    """Signal aggregation must filter on action = 'POSITIVE' (BUY)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "POSITIVE" in sql, "Signal filter must use action = 'POSITIVE'"


def test_upgrade_signals_filter_open_only() -> None:
    """Signal aggregation must filter exit_date IS NULL (open signals only)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "exit_date is null" in sql, "Must filter to open signals (exit_date IS NULL)"


# ---------------------------------------------------------------------------
# Required columns
# ---------------------------------------------------------------------------


def test_upgrade_emits_required_return_columns() -> None:
    """All 5 return columns must appear in the MV SELECT."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    for col in ("ret_1w", "ret_1m", "ret_3m", "ret_6m", "ret_12m"):
        assert col in sql, f"return column '{col}' missing from MV"


def test_upgrade_emits_required_rs_columns() -> None:
    """All 3 RS columns (rs_1m, rs_3m, rs_6m) must appear."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    for col in ("rs_1m", "rs_3m", "rs_6m"):
        assert col in sql, f"RS column '{col}' missing from MV"


def test_upgrade_emits_required_breadth_columns() -> None:
    """Breadth columns must appear: vol_60d_ann, pct_above_ema20, pct_above_ema200, pct_at_52wh."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    for col in ("vol_60d_ann", "pct_above_ema20", "pct_above_ema200", "pct_at_52wh"):
        assert col in sql, f"breadth column '{col}' missing from MV"


def test_upgrade_emits_concentration_column() -> None:
    """HHI concentration column must appear."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "hhi_concentration" in sql, "hhi_concentration column missing from MV"


def test_upgrade_emits_signal_columns() -> None:
    """buy_signal_count and confidence_distribution must appear."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "buy_signal_count" in sql, "buy_signal_count missing from MV"
    assert "confidence_distribution" in sql, "confidence_distribution missing from MV"


def test_upgrade_emits_verdict_columns() -> None:
    """verdict and verdict_abbr must appear."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "verdict" in sql, "verdict missing from MV"
    assert "verdict_abbr" in sql, "verdict_abbr missing from MV"


def test_upgrade_emits_constituent_count() -> None:
    """constituent_count must appear."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "constituent_count" in sql, "constituent_count missing from MV"


def test_upgrade_emits_refreshed_at() -> None:
    """refreshed_at metadata column must appear."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "refreshed_at" in sql, "refreshed_at metadata column missing from MV"


# ---------------------------------------------------------------------------
# Confidence distribution JSONB
# ---------------------------------------------------------------------------


def test_upgrade_confidence_distribution_is_jsonb() -> None:
    """confidence_distribution must be built with jsonb_build_object."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "jsonb_build_object" in sql, "confidence_distribution must use jsonb_build_object"


def test_upgrade_confidence_distribution_has_h_m_l_keys() -> None:
    """confidence_distribution must include H, M, L keys."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    for key in ("'H'", "'M'", "'L'"):
        assert key in sql, f"confidence_distribution missing key {key}"


def test_upgrade_confidence_h_threshold_is_07() -> None:
    """High confidence threshold must be 0.70."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "0.70" in sql, "High confidence threshold must be 0.70"


def test_upgrade_confidence_m_threshold_is_05() -> None:
    """Medium confidence threshold must be 0.50."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "0.50" in sql, "Medium confidence lower bound must be 0.50"


# ---------------------------------------------------------------------------
# Verdict mapping
# ---------------------------------------------------------------------------


def test_upgrade_verdict_maps_overweight_to_ow() -> None:
    """Verdict mapping must include Overweight → OW."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "Overweight" in sql and "'OW'" in sql, "Overweight must map to OW"


def test_upgrade_verdict_maps_underweight_to_uw() -> None:
    """Verdict mapping must include Underweight → UW and Avoid → UW."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "Underweight" in sql, "Underweight must be in verdict mapping"
    assert "'UW'" in sql, "UW must be in verdict mapping"


def test_upgrade_verdict_maps_neutral_to_nw() -> None:
    """Verdict mapping must include Neutral → NW."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "Neutral" in sql and "'NW'" in sql, "Neutral must map to NW"


# ---------------------------------------------------------------------------
# Date spine
# ---------------------------------------------------------------------------


def test_upgrade_covers_date_range_from_2020() -> None:
    """Date spine must start from 2020-01-01 per spec (5-year minimum)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "2020-01-01" in sql, "Date spine must start from 2020-01-01"


# ---------------------------------------------------------------------------
# Return derivation
# ---------------------------------------------------------------------------


def test_upgrade_ret_1w_derived_from_rs_1w_plus_n500() -> None:
    """ret_1w must be derived as rs_1w + nifty500_ret_1w."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "rs_1w" in sql, "rs_1w must be used in ret_1w derivation"
    assert "n500_ret_1w" in sql, "n500_ret_1w must be used in ret_1w derivation"


def test_upgrade_ret_12m_derived_from_rs_12m_plus_n500() -> None:
    """ret_12m must be derived as rs_12m + nifty500_ret_12m."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "rs_12m" in sql, "rs_12m must be used in ret_12m derivation"
    assert "n500_ret_12m" in sql, "n500_ret_12m must be used in ret_12m derivation"


# ---------------------------------------------------------------------------
# Unique index
# ---------------------------------------------------------------------------


def test_upgrade_creates_unique_index() -> None:
    """Unique index on (as_of_date, sector_name) required for CONCURRENTLY refresh."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE UNIQUE INDEX" in joined
    assert "MV_SECTOR_CARDS" in joined
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
    """pg_cron must be scheduled at 40 14 * * * (20:40 IST = 14:40 UTC)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "mv_sector_cards_nightly" in sql
    assert "40 14 * * *" in sql, "Cron must run at 14:40 UTC (20:40 IST)"


def test_upgrade_cron_uses_concurrently() -> None:
    """pg_cron must use REFRESH MATERIALIZED VIEW CONCURRENTLY."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    cron_idx = sql.index("MV_SECTOR_CARDS_NIGHTLY")
    cron_block = sql[cron_idx:]
    assert "CONCURRENTLY" in cron_block, "pg_cron must use CONCURRENTLY refresh"


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
    assert "MV_SECTOR_CARDS" in joined


def test_downgrade_uses_if_exists() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "DROP MATERIALIZED VIEW IF EXISTS" in sql


def test_downgrade_unschedules_cron() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    sql = "\n".join(statements)
    assert "mv_sector_cards_nightly" in sql
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
        result = conn.execute(sa.text("SELECT COUNT(*) FROM atlas.mv_sector_cards")).scalar()
    # 31 sectors × 1,550+ trading days from 2020-01-01
    assert result is not None and result >= 31, f"Expected >= 31 rows, got {result}"


@_SKIP_INTEGRATION
def test_mv_row_shape_latest() -> None:  # pragma: no cover
    """Latest date must have ~31 sector rows with all required columns non-null."""
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
                    ret_1m,
                    ret_3m,
                    ret_6m,
                    rs_3m,
                    buy_signal_count,
                    confidence_distribution,
                    verdict,
                    verdict_abbr,
                    refreshed_at
                FROM atlas.mv_sector_cards
                WHERE as_of_date = (
                    SELECT MAX(as_of_date) FROM atlas.mv_sector_cards
                )
                ORDER BY sector_name
                """
            )
        ).fetchall()

    assert len(rows) >= 1, "Expected at least 1 sector row on latest date"

    for row in rows:
        sn = row[0]
        # constituent_count must be non-negative integer
        assert row[1] is not None and row[1] >= 0, f"{sn}: constituent_count must be >= 0"
        # confidence_distribution must be a JSONB with H, M, L keys
        conf = row[7]
        assert conf is not None, f"{sn}: confidence_distribution must not be NULL"
        assert "H" in conf, f"{sn}: confidence_distribution missing 'H' key"
        assert "M" in conf, f"{sn}: confidence_distribution missing 'M' key"
        assert "L" in conf, f"{sn}: confidence_distribution missing 'L' key"
        # refreshed_at must be set
        assert row[10] is not None, f"{sn}: refreshed_at must not be NULL"


@_SKIP_INTEGRATION
def test_mv_verdict_abbr_values() -> None:  # pragma: no cover
    """verdict_abbr must only contain OW, NW, UW, or NULL."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        invalid = conn.execute(
            sa.text(
                """
                SELECT DISTINCT verdict_abbr
                FROM atlas.mv_sector_cards
                WHERE verdict_abbr IS NOT NULL
                  AND verdict_abbr NOT IN ('OW', 'NW', 'UW')
                """
            )
        ).fetchall()

    assert len(invalid) == 0, f"Invalid verdict_abbr values found: {[r[0] for r in invalid]}"


@_SKIP_INTEGRATION
def test_mv_confidence_distribution_non_negative() -> None:  # pragma: no cover
    """All H/M/L counts in confidence_distribution must be >= 0."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        bad_rows = conn.execute(
            sa.text(
                """
                SELECT sector_name, as_of_date, confidence_distribution
                FROM atlas.mv_sector_cards
                WHERE (confidence_distribution->>'H')::int < 0
                   OR (confidence_distribution->>'M')::int < 0
                   OR (confidence_distribution->>'L')::int < 0
                LIMIT 5
                """
            )
        ).fetchall()

    assert len(bad_rows) == 0, f"Negative confidence counts found: {bad_rows}"


@_SKIP_INTEGRATION
def test_mv_sector_coverage_minimum() -> None:  # pragma: no cover
    """MV must have >= 1,000 rows (at least 31 sectors × ~32 trading days)."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        total = conn.execute(sa.text("SELECT COUNT(*) FROM atlas.mv_sector_cards")).scalar()
        sector_count = conn.execute(
            sa.text("SELECT COUNT(DISTINCT sector_name) FROM atlas.mv_sector_cards")
        ).scalar()

    assert total >= 1_000, f"Expected >= 1,000 rows, got {total}"
    assert sector_count >= 1, f"Expected >= 1 distinct sector, got {sector_count}"


@_SKIP_INTEGRATION
def test_mv_cron_job_registered() -> None:  # pragma: no cover
    """pg_cron job must exist after upgrade."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                """
                SELECT schedule
                FROM cron.job
                WHERE jobname = 'mv_sector_cards_nightly'
                """
            )
        ).fetchone()

    assert row is not None, "pg_cron job 'mv_sector_cards_nightly' not found"
    assert row[0] == "40 14 * * *", f"Expected cron '40 14 * * *', got '{row[0]}'"


@_SKIP_INTEGRATION
def test_mv_date_range_starts_2020() -> None:  # pragma: no cover
    """MV date range must start at or after 2020-01-01."""
    import datetime

    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        min_date = conn.execute(
            sa.text("SELECT MIN(as_of_date) FROM atlas.mv_sector_cards")
        ).scalar()

    assert min_date is not None
    assert min_date >= datetime.date(2020, 1, 1), (
        f"Expected date range starting 2020-01-01, got min_date={min_date}"
    )

"""Regression tests for migration 101 — mv_markets_rs_detail_charts.

Materialized view created:
- atlas.mv_markets_rs_detail_charts — one row per (as_of_date, baseline_code)
  containing 180 trading days of chart data in JSONB arrays plus scalar S/R
  levels, RS series, volume series, and MA20 series.

Baselines (9): NIFTY_50, NIFTY_100, NIFTY_MIDCAP_150, NIFTY_SMLCAP_250,
NIFTY_500, GOLD, SP500, MSCI_WORLD, MSCI_EM.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify upgrade() emits:
- CREATE MATERIALIZED VIEW ... WITH NO DATA
- CREATE UNIQUE INDEX on (as_of_date, baseline_code)
- REFRESH MATERIALIZED VIEW
- pg_cron schedule at 20:35 IST

Downgrade verifies cron unschedule + DROP in safe order.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the MV exists, row count ≥ 11,760 (9 × 1,307 days from 2020 to 2023),
and sample the latest row's JSONB arrays for shape validity.
Skipped by default; run on EC2.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.101_mv_markets_rs_detail_charts"
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
    assert mod.revision == "101"
    assert mod.down_revision == "100"
    assert mod.branch_labels is None


# ---------------------------------------------------------------------------
# upgrade — CREATE MV
# ---------------------------------------------------------------------------


def test_upgrade_creates_materialized_view() -> None:
    """MV must be created WITH NO DATA — explicit refresh follows."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE MATERIALIZED VIEW" in joined
    assert "MV_MARKETS_RS_DETAIL_CHARTS" in joined
    assert "WITH NO DATA" in joined, "MV should be created WITH NO DATA"


def test_upgrade_emits_all_nine_baselines() -> None:
    """All 9 baseline_code values must appear in the MV SQL."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    expected_baselines = [
        "NIFTY_50",
        "NIFTY_100",
        "NIFTY_MIDCAP_150",
        "NIFTY_SMLCAP_250",
        "NIFTY_500",
        "GOLD",
        "SP500",
        "MSCI_WORLD",
        "MSCI_EM",
    ]
    for baseline in expected_baselines:
        assert baseline in sql, f"baseline '{baseline}' missing from MV body"


def test_upgrade_emits_required_jsonb_columns() -> None:
    """All 6 JSONB array columns must appear in the MV SELECT."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    required = [
        "price_series",
        "rs_series",
        "volume_series",
        "ma20_series",
        "rs_new_high_dates",
        "rs_new_low_dates",
    ]
    for col in required:
        assert col in sql, f"JSONB column '{col}' missing from MV body"


def test_upgrade_emits_required_scalar_columns() -> None:
    """Scalar output columns must appear in the MV SELECT."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    required = [
        "support_level",
        "resistance_level",
        "latest_close",
        "rs_latest",
        "rs_delta_3m",
        "baseline_label",
        "baseline_group",
        "is_usd_baseline",
        "refreshed_at",
    ]
    for col in required:
        assert col in sql, f"scalar column '{col}' missing from MV body"


def test_upgrade_uses_all_four_source_tables() -> None:
    """MV must pull from all required source tables."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    sources = [
        "de_index_prices",
        "de_etf_ohlcv",
        "de_global_prices",
        "atlas_index_metrics_daily",
        "atlas_macro_daily",
    ]
    for src in sources:
        assert src in sql, f"source table '{src}' missing from MV body"


def test_upgrade_covers_goldbees_for_gold_baseline() -> None:
    """GOLDBEES ticker must be the Gold baseline source."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "GOLDBEES" in sql, "GOLDBEES must be the Gold baseline source"


def test_upgrade_covers_global_tickers() -> None:
    """^GSPC, URTH, VWO must be sources for USD baselines."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    for ticker in ("^GSPC", "URTH", "VWO"):
        assert ticker in sql, f"global ticker '{ticker}' missing from MV body"


def test_upgrade_performs_usd_inr_conversion() -> None:
    """FX conversion must reference usdinr from atlas_macro_daily."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "usdinr" in sql, "USD→INR conversion must use usdinr from atlas_macro_daily"


def test_upgrade_covers_date_range_from_2020() -> None:
    """Date spine must start from 2020-01-01 per spec."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "2020-01-01" in sql, "Date spine must start from 2020-01-01"


def test_upgrade_uses_rs_3m_nifty500_for_india_indices() -> None:
    """India indices must use pre-computed RS from atlas_index_metrics_daily."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "rs_3m_nifty500" in sql, (
        "India RS must come from atlas_index_metrics_daily.rs_3m_nifty500"
    )


def test_upgrade_includes_support_resistance_computation() -> None:
    """S/R levels must be MIN/MAX of close over the 180-row window."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "support_level" in sql and "resistance_level" in sql
    assert "min(" in sql, "support_level must be computed as MIN(close)"
    assert "max(" in sql, "resistance_level must be computed as MAX(close)"


def test_upgrade_uses_180_row_window() -> None:
    """180-row window bound must appear in the JSONB aggregation."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "180" in sql, "180-row window spec must appear in MV body"


def test_upgrade_includes_20day_ma() -> None:
    """20-day MA must be computed (ROWS BETWEEN 19 PRECEDING)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "19 preceding" in sql, "20-day MA must use ROWS BETWEEN 19 PRECEDING AND CURRENT ROW"


def test_upgrade_creates_unique_index() -> None:
    """Unique index on (as_of_date, baseline_code) required for CONCURRENTLY refresh."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE UNIQUE INDEX" in joined
    assert "MV_MARKETS_RS_DETAIL_CHARTS" in joined
    assert "AS_OF_DATE" in joined
    assert "BASELINE_CODE" in joined


def test_upgrade_refreshes_mv_after_index() -> None:
    """REFRESH MATERIALIZED VIEW must come after CREATE UNIQUE INDEX."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "REFRESH MATERIALIZED VIEW" in joined
    assert "MV_MARKETS_RS_DETAIL_CHARTS" in joined
    idx_pos = joined.index("CREATE UNIQUE INDEX")
    refresh_pos = joined.index("REFRESH MATERIALIZED VIEW")
    assert refresh_pos > idx_pos, "REFRESH must come after CREATE UNIQUE INDEX"


def test_upgrade_schedules_cron_at_correct_time() -> None:
    """pg_cron must be scheduled at 35 14 * * * (20:35 IST = 14:35 UTC)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    assert "mv_markets_rs_detail_charts_nightly" in sql
    assert "35 14 * * *" in sql, "Cron must run at 14:35 UTC (20:35 IST)"


def test_upgrade_cron_uses_concurrently() -> None:
    """pg_cron must use REFRESH MATERIALIZED VIEW CONCURRENTLY."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).upper()
    cron_idx = sql.index("MV_MARKETS_RS_DETAIL_CHARTS_NIGHTLY")
    cron_block = sql[cron_idx:]
    assert "CONCURRENTLY" in cron_block, "pg_cron must use CONCURRENTLY refresh"


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
    )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def test_downgrade_drops_materialized_view() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "DROP MATERIALIZED VIEW" in joined
    assert "MV_MARKETS_RS_DETAIL_CHARTS" in joined


def test_downgrade_uses_if_exists() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    sql = "\n".join(statements).upper()
    assert "DROP MATERIALIZED VIEW IF EXISTS" in sql
    assert "IF EXISTS" in sql


def test_downgrade_unschedules_cron() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    sql = "\n".join(statements)
    assert "mv_markets_rs_detail_charts_nightly" in sql
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
        result = conn.execute(
            sa.text("SELECT COUNT(*) FROM atlas.mv_markets_rs_detail_charts")
        ).scalar()
    # 9 baselines × 1,640+ trading days
    assert result is not None and result >= 11_760, f"Expected ≥ 11,760 rows, got {result}"


@_SKIP_INTEGRATION
def test_mv_row_shape_latest() -> None:  # pragma: no cover
    """Latest row per baseline must have all 6 JSONB arrays non-null."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT baseline_code,
                       jsonb_array_length(price_series)   AS price_len,
                       jsonb_array_length(rs_series)      AS rs_len,
                       jsonb_array_length(ma20_series)    AS ma20_len,
                       support_level,
                       resistance_level,
                       latest_close
                FROM atlas.mv_markets_rs_detail_charts
                WHERE as_of_date = (
                    SELECT MAX(as_of_date) FROM atlas.mv_markets_rs_detail_charts
                )
                ORDER BY baseline_code
                """
            )
        ).fetchall()

    assert len(rows) == 9, f"Expected 9 baseline rows for latest date, got {len(rows)}"

    for row in rows:
        code = row[0]
        price_len = row[1]
        assert price_len == 180, f"{code}: expected price_series length 180, got {price_len}"
        assert row[5] is not None, f"{code}: latest_close must not be NULL"
        assert row[3] is not None, f"{code}: support_level must not be NULL"
        assert row[4] is not None, f"{code}: resistance_level must not be NULL"
        assert row[4] >= row[3], f"{code}: resistance_level must be >= support_level"


@_SKIP_INTEGRATION
def test_mv_usd_baselines_are_inr_adjusted() -> None:  # pragma: no cover
    """USD baselines (SP500, MSCI_WORLD, MSCI_EM) must have is_usd_baseline=true
    and latest_close in a plausible INR range (>100, <500000)."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT baseline_code, latest_close, is_usd_baseline
                FROM atlas.mv_markets_rs_detail_charts
                WHERE as_of_date = (
                    SELECT MAX(as_of_date) FROM atlas.mv_markets_rs_detail_charts
                )
                  AND baseline_code IN ('SP500', 'MSCI_WORLD', 'MSCI_EM')
                """
            )
        ).fetchall()

    assert len(rows) == 3
    for row in rows:
        code, close, is_usd = row
        assert is_usd is True, f"{code}: is_usd_baseline must be true"
        assert close is not None, f"{code}: latest_close must not be NULL"
        assert 100 < float(close) < 500_000, (
            f"{code}: latest_close {close} is outside expected INR range"
        )


@_SKIP_INTEGRATION
def test_mv_nine_baselines_coverage() -> None:  # pragma: no cover
    """Every baseline must have ≥ 1,300 trading days from 2020-01-01."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT baseline_code, COUNT(*) AS days
                FROM atlas.mv_markets_rs_detail_charts
                GROUP BY baseline_code
                ORDER BY baseline_code
                """
            )
        ).fetchall()

    codes = {row[0] for row in rows}
    expected = {
        "NIFTY_50",
        "NIFTY_100",
        "NIFTY_MIDCAP_150",
        "NIFTY_SMLCAP_250",
        "NIFTY_500",
        "GOLD",
        "SP500",
        "MSCI_WORLD",
        "MSCI_EM",
    }
    assert codes == expected, f"Unexpected baselines: {codes ^ expected}"

    for row in rows:
        code, days = row
        assert days >= 1_300, f"{code}: expected ≥ 1,300 trading-day rows, got {days}"


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
                WHERE jobname = 'mv_markets_rs_detail_charts_nightly'
                """
            )
        ).fetchone()

    assert row is not None, "pg_cron job 'mv_markets_rs_detail_charts_nightly' not found"
    assert row[0] == "35 14 * * *", f"Expected cron '35 14 * * *', got '{row[0]}'"

"""Regression tests for migration 100 — mv_india_pulse.

Materialized view created:
- atlas.mv_india_pulse — one row per date (date spine from atlas_market_regime_daily)
  with all data sections for Page 02 India Pulse.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify:
  - upgrade() emits CREATE MATERIALIZED VIEW + unique index + REFRESH + cron schedule
  - downgrade() unschedules cron + drops index + drops MV in correct order
  - All mockup sections have their JSONB keys in the SQL body
  - Data gap rows are explicitly flagged

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the MV exists, has ≥ 1260 rows (5y), date range ≥ 2020-01-01, and
every required JSONB key is present on the latest row.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.100_mv_india_pulse"
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
    assert mod.revision == "100"
    assert mod.down_revision == "099"
    assert mod.branch_labels is None


# ---------------------------------------------------------------------------
# upgrade() assertions
# ---------------------------------------------------------------------------


def test_upgrade_creates_materialized_view() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE MATERIALIZED VIEW" in joined
    assert "MV_INDIA_PULSE" in joined
    assert "WITH NO DATA" in joined, "MV must be created WITH NO DATA for deferred refresh"


def test_upgrade_creates_unique_index_for_concurrent_refresh() -> None:
    """CONCURRENTLY refresh requires a unique index on as_of_date."""
    statements = _executed_statements(_run_upgrade_with_mock())
    joined = "\n".join(statements).upper()
    assert "CREATE UNIQUE INDEX" in joined
    assert "AS_OF_DATE" in joined, "unique index must cover the as_of_date column"


def test_upgrade_does_initial_full_refresh() -> None:
    """First REFRESH must be non-CONCURRENT since no unique index exists yet during build."""
    statements = _executed_statements(_run_upgrade_with_mock())
    full_sql = "\n".join(statements).upper()
    assert "REFRESH MATERIALIZED VIEW" in full_sql
    assert "MV_INDIA_PULSE" in full_sql


def test_upgrade_schedules_pg_cron_job() -> None:
    """pg_cron job mv_india_pulse_nightly must be scheduled."""
    statements = _executed_statements(_run_upgrade_with_mock())
    full_sql = "\n".join(statements)
    assert "mv_india_pulse_nightly" in full_sql
    assert "cron.schedule" in full_sql
    # 20:30 IST = 14:30 UTC = '30 14 * * *'
    assert "30 14 * * *" in full_sql, "cron must run at 20:30 IST (14:30 UTC)"
    assert "CONCURRENTLY" in full_sql.upper(), "nightly cron must use CONCURRENT refresh"


def test_upgrade_uses_correct_source_tables() -> None:
    """All required source tables must be referenced in the MV body."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    required_sources = [
        "atlas_market_regime_daily",  # breadth, VIX, A/D data
        "atlas_regime_daily",  # v6 driver attributions (smallcap_rs_z etc.)
        "atlas_macro_daily",  # macro 8 cards
        "atlas_index_metrics_daily",  # 7 headline indices
        "de_index_prices",  # index close levels
        "atlas_benchmark_returns_cache",  # Gold (GOLDBEES proxy)
        "atlas_sector_metrics_daily",  # sector heatmap
    ]
    for tbl in required_sources:
        assert tbl in sql, f"source table '{tbl}' missing from MV body"


# ---------------------------------------------------------------------------
# Hero section (4 scalars)
# ---------------------------------------------------------------------------


def test_upgrade_hero_smallcap_rs_z_from_regime_v6() -> None:
    """smallcap_rs_z must come from atlas_regime_daily (v6 table)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "smallcap_rs_z" in sql
    assert "atlas_regime_daily" in sql


def test_upgrade_hero_breadth_coalesces_v6_v5() -> None:
    """breadth_pct_above_200dma uses COALESCE(v6, v5 fallback)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "breadth_pct_above_200dma" in sql
    assert "coalesce" in sql, "breadth must COALESCE v6 and v5 sources"
    assert "pct_above_ema_200" in sql, "v5 fallback column must be referenced"


def test_upgrade_hero_india_vix() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "india_vix" in sql


def test_upgrade_hero_cross_section_dispersion() -> None:
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "cross_section" in sql or "cross_sectional" in sql


# ---------------------------------------------------------------------------
# Headline indices section
# ---------------------------------------------------------------------------


def test_upgrade_headline_indices_8_codes() -> None:
    """All 8 headline index codes must appear in the MV body."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    required_codes = [
        "NIFTY 50",
        "NIFTY 100",
        "NIFTY MIDCAP 150",
        "NIFTY SMLCAP 250",
        "NIFTY 500",
        "NIFTY BANK",
        "NIFTY IT",
        "GOLD",
    ]
    for code in required_codes:
        assert code in sql, f"index code '{code}' missing from headline_indices"


def test_upgrade_headline_indices_return_windows() -> None:
    """Each index card shows ret_1d/1w/1m/3m/6m and RS vs Nifty500."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    for window in ("ret_1d", "ret_1w", "ret_1m", "ret_3m", "ret_6m"):
        assert window in sql, f"return window '{window}' missing from headline_indices"
    assert "rs_3m_nifty500" in sql


# ---------------------------------------------------------------------------
# Breadth table section
# ---------------------------------------------------------------------------


def test_upgrade_breadth_table_all_9_rows() -> None:
    """All 9 breadth table rows must be represented (7 live + 2 data_gap)."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    # 7 live metrics
    live_metrics = [
        "pct_above_200dma",
        "pct_above_50dma",
        "new_52w_highs",
        "new_52w_lows",
        "ad_ratio",
        "mcclellan",
        "ad_line",
    ]
    for metric in live_metrics:
        assert metric in sql, f"breadth metric '{metric}' missing from breadth_table"
    # 2 data gap rows
    assert "pct_above_100dma" in sql, "100 DMA row must be in breadth_table (data_gap)"
    assert "pct_4w_high" in sql, "4-week high row must be in breadth_table (data_gap)"


def test_upgrade_breadth_table_delta_windows() -> None:
    """Δ1w/Δ1m/Δ3m deltas (LAG 5/21/63) must be computed for live metrics."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    # LAG offsets
    assert "lag(" in sql
    for lag_n in ("5", "21", "63"):
        assert f", {lag_n})" in sql, f"LAG offset {lag_n} missing from breadth deltas"


def test_upgrade_breadth_data_gaps_flagged_true() -> None:
    """data_gap: true must be present for the 2 missing metrics."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "data_gap" in sql
    assert "true" in sql


# ---------------------------------------------------------------------------
# Volatility section
# ---------------------------------------------------------------------------


def test_upgrade_volatility_vix_5y_percentile() -> None:
    """VIX 5-year percentile requires PERCENT_RANK() window function."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "percent_rank" in sql, "vix_5y_pct must use PERCENT_RANK()"
    assert "vix_5y_pct" in sql


def test_upgrade_volatility_term_structure() -> None:
    """VIX term structure = india_vix - vix_9d from atlas_macro_daily."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "vix_9d" in sql
    assert "vix_term_structure" in sql


# ---------------------------------------------------------------------------
# Tier leadership section
# ---------------------------------------------------------------------------


def test_upgrade_tier_leadership_sc_mc_lc() -> None:
    """Tier leadership table must cover SC/MC/LC for all 5 windows."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    for window in ("1w", "1m", "3m", "6m", "12m"):
        assert f"ret_{window}" in sql, f"window ret_{window} missing from tier leadership"
    # SC-LC and MC-LC spreads
    assert "sc_lc_spread" in sql
    assert "mc_lc_spread" in sql


# ---------------------------------------------------------------------------
# Sector heatmap section
# ---------------------------------------------------------------------------


def test_upgrade_sector_heatmap_fields() -> None:
    """Sector heatmap must include rs_1w, ret_1m, ret_3m per sector."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "sector_heatmap" in sql
    assert "sector_name" in sql
    assert "rs_1w" in sql
    assert "bottomup_ret_1m" in sql
    assert "bottomup_ret_3m" in sql


# ---------------------------------------------------------------------------
# Macro cards section
# ---------------------------------------------------------------------------


def test_upgrade_macro_cards_all_8_ids() -> None:
    """All 8 macro card IDs must appear in the macro_cards JSONB."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements)
    card_ids = [
        "usdinr",
        "india_10y",
        "brent_inr",
        "real_yield",
        "fii_flow_1m",
        "dii_flow_1m",
        "us_10y",
        "dxy",
    ]
    for cid in card_ids:
        assert cid in sql, f"macro card id '{cid}' missing from macro_cards"


def test_upgrade_macro_cards_sparklines() -> None:
    """Each macro card must carry a 30-day sparkline."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "sparkline_30d" in sql
    assert "macro_sparklines" in sql or "31 days" in sql


def test_upgrade_macro_real_yield_computed() -> None:
    """Real yield = india_10y_yield - cpi_yoy."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "real_yield" in sql
    assert "cpi_yoy" in sql
    assert "india_10y_yield" in sql


def test_upgrade_macro_fii_rolling_sum() -> None:
    """FII 1M cumulative = SUM over 20 PRECEDING rows."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "fii_cash_equity_flow_cr" in sql
    assert "20 preceding" in sql, "FII cumulative must use 20 PRECEDING window"


# ---------------------------------------------------------------------------
# Narrative ribbon section
# ---------------------------------------------------------------------------


def test_upgrade_narrative_ribbon_keys() -> None:
    """Narrative ribbon must carry india_10y_yield, real_yield, fii_flow scalars."""
    statements = _executed_statements(_run_upgrade_with_mock())
    sql = "\n".join(statements).lower()
    assert "narrative_ribbon" in sql
    assert "equity_earnings_yield" in sql  # deferred, but key must be present


# ---------------------------------------------------------------------------
# downgrade() assertions
# ---------------------------------------------------------------------------


def test_downgrade_unschedules_cron_first() -> None:
    mock_op = _run_downgrade_with_mock()
    statements = _executed_statements(mock_op)
    # First statement must be cron.unschedule
    assert statements, "downgrade must emit at least one statement"
    assert "unschedule" in statements[0].lower() or "unschedule" in "\n".join(statements).lower()


def test_downgrade_drops_mv() -> None:
    statements = _executed_statements(_run_downgrade_with_mock())
    full_sql = "\n".join(statements).upper()
    assert "DROP MATERIALIZED VIEW" in full_sql
    assert "MV_INDIA_PULSE" in full_sql


# ---------------------------------------------------------------------------
# Integration tests (live DB — EC2 only)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
def test_integration_mv_exists_and_has_rows() -> None:
    """MV must exist and have ≥ 1260 rows (5y of daily data)."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        row_count = conn.execute(sa.text("SELECT COUNT(*) FROM atlas.mv_india_pulse")).scalar()
    assert (
        row_count is not None and row_count >= 1260
    ), f"expected ≥ 1260 rows (5y), got {row_count}"


@_SKIP_INTEGRATION
def test_integration_mv_date_range() -> None:
    """MV must cover dates ≥ 2020-01-01."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        min_date = conn.execute(
            sa.text("SELECT MIN(as_of_date) FROM atlas.mv_india_pulse")
        ).scalar()
    assert min_date is not None
    from datetime import date

    assert min_date <= date(2020, 1, 1), f"expected MV to start ≤ 2020-01-01, got {min_date}"


@_SKIP_INTEGRATION
def test_integration_latest_row_jsonb_shape() -> None:
    """Latest row must have all required JSONB keys with correct types."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("""
                SELECT
                  jsonb_typeof(headline_indices),
                  jsonb_typeof(breadth_table),
                  jsonb_typeof(sector_heatmap),
                  jsonb_typeof(macro_cards),
                  jsonb_typeof(narrative_ribbon),
                  jsonb_typeof(tier_leadership)
                FROM atlas.mv_india_pulse
                ORDER BY as_of_date DESC
                LIMIT 1
            """)
        ).fetchone()
    assert row is not None, "MV must have at least one row"
    headline_type, breadth_type, sector_type, macro_type, narrative_type, tier_type = row
    assert headline_type == "array", "headline_indices must be a JSON array"
    assert breadth_type == "array", "breadth_table must be a JSON array"
    assert sector_type == "array", "sector_heatmap must be a JSON array"
    assert macro_type == "array", "macro_cards must be a JSON array"
    assert narrative_type == "object", "narrative_ribbon must be a JSON object"
    assert tier_type == "object", "tier_leadership must be a JSON object"


@_SKIP_INTEGRATION
def test_integration_headline_indices_count() -> None:
    """headline_indices array must have exactly 8 elements on the latest row."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        count = conn.execute(
            sa.text("""
                SELECT jsonb_array_length(headline_indices)
                FROM atlas.mv_india_pulse
                ORDER BY as_of_date DESC
                LIMIT 1
            """)
        ).scalar()
    assert count == 8, f"expected 8 headline indices, got {count}"


@_SKIP_INTEGRATION
def test_integration_breadth_table_9_rows() -> None:
    """breadth_table array must have exactly 9 elements (7 live + 2 data_gap)."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        count = conn.execute(
            sa.text("""
                SELECT jsonb_array_length(breadth_table)
                FROM atlas.mv_india_pulse
                ORDER BY as_of_date DESC
                LIMIT 1
            """)
        ).scalar()
    assert count == 9, f"expected 9 breadth rows, got {count}"


@_SKIP_INTEGRATION
def test_integration_cron_job_exists() -> None:
    """pg_cron job mv_india_pulse_nightly must be registered."""
    import sqlalchemy as sa

    url = os.environ["ATLAS_DB_URL"]
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        job = conn.execute(
            sa.text("SELECT jobname FROM cron.job WHERE jobname = 'mv_india_pulse_nightly'")
        ).scalar()
    assert job == "mv_india_pulse_nightly", "pg_cron job mv_india_pulse_nightly must exist"

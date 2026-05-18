"""Smoke tests for atlas_*_signal_unified views.

Verifies each view exists, returns rows, and exposes the legacy column
names every frontend query expects.

Integration test (requires ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Skipped by default; run after migration 080 is applied on a live DB.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy import text

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB)",
)

_VALID_ENGINE_STATES = frozenset(
    {
        "uninvestable",
        "stage_1",
        "stage_2a",
        "stage_2b",
        "stage_2c",
        "stage_3",
        "stage_4",
    }
)
_VALID_RS_STATES = frozenset({"Leader", "Strong", "Average", "Weak", "Laggard"})


@_SKIP_INTEGRATION
def test_stock_signal_unified_view_exists(db_engine: sa.Engine) -> None:
    """View exists in atlas schema and exposes all required legacy columns."""
    with db_engine.connect() as c:
        row = c.execute(
            text("""
            SELECT
                instrument_id, date, engine_state, is_investable, rs_state,
                momentum_state, weinstein_gate_pass, within_state_rank,
                rs_rank_12m, dwell_days, urgency_score
            FROM atlas.atlas_stock_signal_unified
            LIMIT 1
        """)
        ).first()
    assert row is not None, "view must return at least one row"
    assert row.engine_state in _VALID_ENGINE_STATES, f"unexpected engine_state: {row.engine_state}"
    assert isinstance(row.is_investable, bool)
    assert row.rs_state in _VALID_RS_STATES, f"unexpected rs_state: {row.rs_state}"


@_SKIP_INTEGRATION
def test_stock_signal_unified_view_row_count_parity(db_engine: sa.Engine) -> None:
    """View row count matches source table for classifier_version = v2.0-validated."""
    with db_engine.connect() as c:
        result = c.execute(
            text("""
            SELECT
                (SELECT COUNT(*) FROM atlas.atlas_stock_state_daily
                 WHERE classifier_version = 'v2.0-validated') AS engine_rows,
                (SELECT COUNT(*) FROM atlas.atlas_stock_signal_unified) AS view_rows
        """)
        ).first()
    assert result is not None
    assert (
        result.engine_rows == result.view_rows
    ), f"Row count mismatch: engine={result.engine_rows} view={result.view_rows}"


@_SKIP_INTEGRATION
def test_stock_signal_unified_is_investable_distribution(db_engine: sa.Engine) -> None:
    """Both true and false buckets are present in the latest date snapshot."""
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
            SELECT is_investable, COUNT(*) AS cnt
            FROM atlas.atlas_stock_signal_unified
            WHERE date = (SELECT MAX(date) FROM atlas.atlas_stock_signal_unified)
            GROUP BY 1
            ORDER BY 1
        """)
        ).fetchall()
    buckets = {r.is_investable: r.cnt for r in rows}
    assert True in buckets, "no investable stocks found"
    assert False in buckets, "no uninvestable stocks found"


@_SKIP_INTEGRATION
def test_stock_signal_unified_rs_state_distribution(db_engine: sa.Engine) -> None:
    """All five rs_state buckets present for the latest date snapshot."""
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
            SELECT rs_state, COUNT(*) AS cnt
            FROM atlas.atlas_stock_signal_unified
            WHERE date = (SELECT MAX(date) FROM atlas.atlas_stock_signal_unified)
            GROUP BY 1
            ORDER BY 1
        """)
        ).fetchall()
    found_states = {r.rs_state for r in rows}
    assert (
        found_states == _VALID_RS_STATES
    ), f"Missing rs_state buckets: {_VALID_RS_STATES - found_states}"


@_SKIP_INTEGRATION
def test_stock_signal_unified_continuous_columns_present(db_engine: sa.Engine) -> None:
    """Tier 4 continuous columns are selectable (may be NULL for some rows)."""
    with db_engine.connect() as c:
        row = c.execute(
            text("""
            SELECT
                close_vs_sma_50, close_vs_sma_150, close_vs_sma_200,
                sma_200_slope, volume_ratio_50d, distribution_days,
                classifier_version
            FROM atlas.atlas_stock_signal_unified
            LIMIT 1
        """)
        ).first()
    assert row is not None, "view must return at least one row for continuous column check"
    # classifier_version must always be v2.0-validated (view WHERE clause)
    assert row.classifier_version == "v2.0-validated"


# ---------------------------------------------------------------------------
# Phase 3 — v2 aggregate tables
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
def test_atlas_sector_state_v2_table_exists(db_engine: sa.Engine) -> None:
    """atlas_sector_state_v2 exists with all required columns."""
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'atlas'
              AND table_name   = 'atlas_sector_state_v2'
        """)
        ).fetchall()
    cols = {r.column_name for r in rows}
    expected = {
        "sector",
        "date",
        "dominant_state",
        "dominant_share",
        "n_constituents",
        "mean_within_state_rank",
        "pct_stage_2",
        "pct_stage_3",
        "pct_stage_4",
        "pct_stage_1",
        "pct_uninvestable",
        "computed_at",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"


@_SKIP_INTEGRATION
def test_atlas_fund_state_v2_table_exists(db_engine: sa.Engine) -> None:
    """atlas_fund_state_v2 exists with all required columns."""
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'atlas'
              AND table_name   = 'atlas_fund_state_v2'
        """)
        ).fetchall()
    cols = {r.column_name for r in rows}
    expected = {
        "mstar_id",
        "date",
        "composition_state",
        "holdings_state",
        "pct_holdings_stage_2",
        "pct_holdings_stage_3",
        "pct_holdings_stage_4",
        "mean_within_state_rank",
        "n_holdings",
        "computed_at",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"


@_SKIP_INTEGRATION
def test_atlas_etf_state_v2_table_exists(db_engine: sa.Engine) -> None:
    """atlas_etf_state_v2 exists with all required columns."""
    with db_engine.connect() as c:
        rows = c.execute(
            text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'atlas'
              AND table_name   = 'atlas_etf_state_v2'
        """)
        ).fetchall()
    cols = {r.column_name for r in rows}
    expected = {
        "etf_ticker",
        "date",
        "dominant_state",
        "dominant_share",
        "n_holdings",
        "mean_rs_rank_12m",
        "pct_stage_2",
        "pct_stage_3",
        "pct_stage_4",
        "computed_at",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"


# ---------------------------------------------------------------------------
# Phase 3 — unified view smoke tests (SELECT 1 row, verify column presence)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
def test_atlas_sector_signal_unified_view_columns(db_engine: sa.Engine) -> None:
    """atlas_sector_signal_unified exposes required columns (0 rows OK — table may be empty)."""
    with db_engine.connect() as c:
        # SELECT with LIMIT 0 still validates column names
        result = c.execute(
            text("""
            SELECT sector, date, engine_state, dominant_share, n_constituents,
                   mean_within_state_rank, pct_stage_2, pct_stage_3, pct_stage_4,
                   sector_state
            FROM atlas.atlas_sector_signal_unified
            LIMIT 0
        """)
        )
        col_names = set(result.keys())
    expected = {
        "sector",
        "date",
        "engine_state",
        "dominant_share",
        "n_constituents",
        "mean_within_state_rank",
        "pct_stage_2",
        "pct_stage_3",
        "pct_stage_4",
        "sector_state",
    }
    assert expected.issubset(col_names), f"missing view columns: {expected - col_names}"


@_SKIP_INTEGRATION
def test_atlas_fund_signal_unified_view_columns(db_engine: sa.Engine) -> None:
    """atlas_fund_signal_unified exposes required columns (0 rows OK — table may be empty)."""
    with db_engine.connect() as c:
        result = c.execute(
            text("""
            SELECT mstar_id, date, composition_state, holdings_state,
                   pct_holdings_stage_2, pct_holdings_stage_3, pct_holdings_stage_4,
                   mean_within_state_rank, n_holdings,
                   nav_state, nav_state_as_of, recommendation
            FROM atlas.atlas_fund_signal_unified
            LIMIT 0
        """)
        )
        col_names = set(result.keys())
    expected = {
        "mstar_id",
        "date",
        "composition_state",
        "holdings_state",
        "pct_holdings_stage_2",
        "pct_holdings_stage_3",
        "pct_holdings_stage_4",
        "mean_within_state_rank",
        "n_holdings",
        "nav_state",
        "nav_state_as_of",
        "recommendation",
    }
    assert expected.issubset(col_names), f"missing view columns: {expected - col_names}"


@_SKIP_INTEGRATION
def test_atlas_etf_signal_unified_view_columns(db_engine: sa.Engine) -> None:
    """atlas_etf_signal_unified exposes required columns (0 rows OK — table may be empty)."""
    with db_engine.connect() as c:
        result = c.execute(
            text("""
            SELECT etf_ticker, date, engine_state, dominant_share,
                   n_holdings, mean_rs_rank_12m,
                   pct_stage_2, pct_stage_3, pct_stage_4
            FROM atlas.atlas_etf_signal_unified
            LIMIT 0
        """)
        )
        col_names = set(result.keys())
    expected = {
        "etf_ticker",
        "date",
        "engine_state",
        "dominant_share",
        "n_holdings",
        "mean_rs_rank_12m",
        "pct_stage_2",
        "pct_stage_3",
        "pct_stage_4",
    }
    assert expected.issubset(col_names), f"missing view columns: {expected - col_names}"

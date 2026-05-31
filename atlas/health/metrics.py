"""Metric catalog for daily health monitoring.

Each metric describes one observable quantity for one atlas.* table on a
given trading date. Computed nightly by scripts/health_check_daily.py.
Most metrics are NUMERIC (rates, counts); a few are CATEGORICAL strings
(regime_state_today). Categorical metrics use a dedicated encoding for
storage so the rest of the pipeline only sees numerics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session


@dataclass(frozen=True)
class MetricDef:
    table: str  # e.g. "atlas_stock_decisions_daily"
    name: str  # e.g. "pct_investable"
    sql: str  # SELECT returning a single column 'v' for the given date
    is_categorical: bool = False
    severity_critical: bool = False  # categorical: change-of-value triggers critical


# --------------------------------------------------------------------------- #
# Catalog                                                                      #
# --------------------------------------------------------------------------- #

# Use %(d)s for the bound trading date.
CATALOG: tuple[MetricDef, ...] = (
    # ----- atlas_market_regime_daily ----------------------------------------
    MetricDef(
        "atlas_market_regime_daily",
        "regime_state_today",
        "SELECT regime_state AS v FROM atlas.atlas_market_regime_daily WHERE date = %(d)s",
        is_categorical=True,
        severity_critical=True,
    ),
    MetricDef(
        "atlas_market_regime_daily",
        "pct_above_ema_50",
        "SELECT pct_above_ema_50 AS v FROM atlas.atlas_market_regime_daily WHERE date = %(d)s",
    ),
    MetricDef(
        "atlas_market_regime_daily",
        "india_vix",
        "SELECT india_vix AS v FROM atlas.atlas_market_regime_daily WHERE date = %(d)s",
    ),
    MetricDef(
        "atlas_market_regime_daily",
        "ad_ratio",
        "SELECT ad_ratio AS v FROM atlas.atlas_market_regime_daily WHERE date = %(d)s",
    ),
    # ----- atlas_sector_states_daily ----------------------------------------
    MetricDef(
        "atlas_sector_states_daily",
        "count_overweight",
        "SELECT COUNT(*) AS v FROM atlas.atlas_sector_states_daily "
        "WHERE date = %(d)s AND sector_state = 'Overweight'",
    ),
    MetricDef(
        "atlas_sector_states_daily",
        "count_neutral",
        "SELECT COUNT(*) AS v FROM atlas.atlas_sector_states_daily "
        "WHERE date = %(d)s AND sector_state = 'Neutral'",
    ),
    MetricDef(
        "atlas_sector_states_daily",
        "count_avoid",
        "SELECT COUNT(*) AS v FROM atlas.atlas_sector_states_daily "
        "WHERE date = %(d)s AND sector_state = 'Avoid'",
    ),
    # ----- atlas_stock_decisions_daily --------------------------------------
    MetricDef(
        "atlas_stock_decisions_daily",
        "row_count",
        "SELECT COUNT(*) AS v FROM atlas.atlas_stock_decisions_daily WHERE date = %(d)s",
    ),
    MetricDef(
        "atlas_stock_decisions_daily",
        "pct_investable",
        "SELECT AVG(CASE WHEN is_investable THEN 1.0 ELSE 0.0 END) AS v "
        "FROM atlas.atlas_stock_decisions_daily WHERE date = %(d)s",
    ),
    MetricDef(
        "atlas_stock_decisions_daily",
        "pct_market_gate",
        "SELECT AVG(CASE WHEN market_gate THEN 1.0 ELSE 0.0 END) AS v "
        "FROM atlas.atlas_stock_decisions_daily WHERE date = %(d)s",
    ),
    MetricDef(
        "atlas_stock_decisions_daily",
        "pct_strength_gate",
        "SELECT AVG(CASE WHEN strength_gate THEN 1.0 ELSE 0.0 END) AS v "
        "FROM atlas.atlas_stock_decisions_daily WHERE date = %(d)s",
    ),
    MetricDef(
        "atlas_stock_decisions_daily",
        "pct_volume_gate",
        "SELECT AVG(CASE WHEN volume_gate THEN 1.0 ELSE 0.0 END) AS v "
        "FROM atlas.atlas_stock_decisions_daily WHERE date = %(d)s",
    ),
    MetricDef(
        "atlas_stock_decisions_daily",
        "count_breakout_triggers",
        "SELECT COUNT(*) AS v FROM atlas.atlas_stock_decisions_daily "
        "WHERE date = %(d)s AND breakout_trigger = TRUE",
    ),
    MetricDef(
        "atlas_stock_decisions_daily",
        "mean_position_size_pct",
        "SELECT AVG(position_size_pct) AS v FROM atlas.atlas_stock_decisions_daily "
        "WHERE date = %(d)s AND position_size_pct IS NOT NULL",
    ),
    # ----- atlas_etf_decisions_daily ----------------------------------------
    MetricDef(
        "atlas_etf_decisions_daily",
        "row_count",
        "SELECT COUNT(*) AS v FROM atlas.atlas_etf_decisions_daily WHERE date = %(d)s",
    ),
    MetricDef(
        "atlas_etf_decisions_daily",
        "pct_investable",
        "SELECT AVG(CASE WHEN is_investable THEN 1.0 ELSE 0.0 END) AS v "
        "FROM atlas.atlas_etf_decisions_daily WHERE date = %(d)s",
    ),
    MetricDef(
        "atlas_etf_decisions_daily",
        "count_breakout_triggers",
        "SELECT COUNT(*) AS v FROM atlas.atlas_etf_decisions_daily "
        "WHERE date = %(d)s AND breakout_trigger = TRUE",
    ),
    # ----- atlas_fund_decisions_daily ---------------------------------------
    MetricDef(
        "atlas_fund_decisions_daily",
        "count_recommended",
        "SELECT COUNT(*) AS v FROM atlas.atlas_fund_decisions_daily "
        "WHERE date = %(d)s AND recommendation = 'Recommended'",
    ),
    MetricDef(
        "atlas_fund_decisions_daily",
        "count_hold",
        "SELECT COUNT(*) AS v FROM atlas.atlas_fund_decisions_daily "
        "WHERE date = %(d)s AND recommendation = 'Hold'",
    ),
    MetricDef(
        "atlas_fund_decisions_daily",
        "count_reduce",
        "SELECT COUNT(*) AS v FROM atlas.atlas_fund_decisions_daily "
        "WHERE date = %(d)s AND recommendation = 'Reduce'",
    ),
    MetricDef(
        "atlas_fund_decisions_daily",
        "count_exit",
        "SELECT COUNT(*) AS v FROM atlas.atlas_fund_decisions_daily "
        "WHERE date = %(d)s AND recommendation = 'Exit'",
    ),
    MetricDef(
        "atlas_fund_decisions_daily",
        "pct_with_entry_trigger",
        "SELECT AVG(CASE WHEN entry_trigger THEN 1.0 ELSE 0.0 END) AS v "
        "FROM atlas.atlas_fund_decisions_daily WHERE date = %(d)s",
    ),
    # ----- atlas_fund_metrics_daily -----------------------------------------
    MetricDef(
        "atlas_fund_metrics_daily",
        "row_count",
        "SELECT COUNT(*) AS v FROM atlas.atlas_fund_metrics_daily WHERE nav_date = %(d)s",
    ),
    MetricDef(
        "atlas_fund_metrics_daily",
        "pct_null_nav_state",
        "SELECT AVG(CASE WHEN nav_state IS NULL THEN 1.0 ELSE 0.0 END) AS v "
        "FROM atlas.atlas_fund_metrics_daily WHERE nav_date = %(d)s",
    ),
    MetricDef(
        "atlas_fund_metrics_daily",
        "mean_rs_pctile_3m",
        "SELECT AVG(rs_pctile_3m) AS v FROM atlas.atlas_fund_metrics_daily "
        "WHERE nav_date = %(d)s AND rs_pctile_3m IS NOT NULL",
    ),
    # ----- atlas_stock_metrics_daily ----------------------------------------
    MetricDef(
        "atlas_stock_metrics_daily",
        "row_count",
        "SELECT COUNT(*) AS v FROM atlas.atlas_stock_metrics_daily WHERE date = %(d)s",
    ),
    # ----- atlas_etf_metrics_daily ------------------------------------------
    MetricDef(
        "atlas_etf_metrics_daily",
        "row_count",
        "SELECT COUNT(*) AS v FROM atlas.atlas_etf_metrics_daily WHERE date = %(d)s",
    ),
)


def compute_metric(engine: Engine, mdef: MetricDef, target_date: date) -> object | None:
    """Run the metric SQL for ``target_date``. Returns scalar or None."""
    with open_compute_session(engine) as conn:
        rows = pd.read_sql(mdef.sql, conn, params={"d": target_date})
    if rows.empty:
        return None
    val = rows.iloc[0]["v"]
    if pd.isna(val):
        return None
    return val


__all__ = ["CATALOG", "MetricDef", "compute_metric"]

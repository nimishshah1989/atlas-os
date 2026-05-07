"""create indexes

Revision ID: 008
Revises: 007
Create Date: 2026-05-06 00:00:07.000000

Indexes per ``docs/02_DATABASE_SCHEMA.md`` Section 7. Three patterns:

- ``(instrument_id, date)`` PK is already created by table DDL; no
  additional index needed.
- ``(date, instrument_id)`` secondary — for date-cross-section queries
  ("give me all stocks on this date"). 100x speedup at v0 scale.
- Partial indexes for common filters: investable today, entry triggers,
  exit triggers, active universe rows.

All ``CREATE INDEX IF NOT EXISTS`` for idempotence.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


_INDEXES = (
    # Universe — partial indexes on currently-active rows
    "CREATE INDEX IF NOT EXISTS idx_universe_stocks_tier ON atlas.atlas_universe_stocks (tier) WHERE effective_to IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_universe_stocks_sector ON atlas.atlas_universe_stocks (sector) WHERE effective_to IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_universe_stocks_active ON atlas.atlas_universe_stocks (instrument_id) WHERE effective_to IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_universe_etfs_theme ON atlas.atlas_universe_etfs (theme) WHERE effective_to IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_universe_etfs_active ON atlas.atlas_universe_etfs (ticker) WHERE effective_to IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_universe_indices_role ON atlas.atlas_universe_indices (role) WHERE effective_to IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_universe_indices_active ON atlas.atlas_universe_indices (index_code) WHERE effective_to IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_universe_funds_category ON atlas.atlas_universe_funds (category_name) WHERE effective_to IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_universe_funds_active ON atlas.atlas_universe_funds (mstar_id) WHERE effective_to IS NULL",

    # Stock metrics
    "CREATE INDEX IF NOT EXISTS idx_stock_metrics_date ON atlas.atlas_stock_metrics_daily (date, instrument_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_metrics_run ON atlas.atlas_stock_metrics_daily (compute_run_id)",

    # ETF metrics
    "CREATE INDEX IF NOT EXISTS idx_etf_metrics_date ON atlas.atlas_etf_metrics_daily (date, ticker)",
    "CREATE INDEX IF NOT EXISTS idx_etf_metrics_run ON atlas.atlas_etf_metrics_daily (compute_run_id)",

    # Index metrics
    "CREATE INDEX IF NOT EXISTS idx_index_metrics_date ON atlas.atlas_index_metrics_daily (date, index_code)",
    "CREATE INDEX IF NOT EXISTS idx_index_metrics_run ON atlas.atlas_index_metrics_daily (compute_run_id)",

    # Sector metrics
    "CREATE INDEX IF NOT EXISTS idx_sector_metrics_date ON atlas.atlas_sector_metrics_daily (date, sector_name)",

    # Market regime
    "CREATE INDEX IF NOT EXISTS idx_market_regime_state ON atlas.atlas_market_regime_daily (regime_state, date)",

    # Fund metrics + lens
    "CREATE INDEX IF NOT EXISTS idx_fund_metrics_date ON atlas.atlas_fund_metrics_daily (nav_date, mstar_id)",
    "CREATE INDEX IF NOT EXISTS idx_fund_lens_date ON atlas.atlas_fund_lens_monthly (as_of_date, mstar_id)",

    # Stock states
    "CREATE INDEX IF NOT EXISTS idx_stock_states_date ON atlas.atlas_stock_states_daily (date, instrument_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_states_rs ON atlas.atlas_stock_states_daily (date, rs_state)",
    "CREATE INDEX IF NOT EXISTS idx_stock_states_sector ON atlas.atlas_stock_states_daily (date, sector)",
    "CREATE INDEX IF NOT EXISTS idx_stock_states_run ON atlas.atlas_stock_states_daily (compute_run_id)",

    # ETF states
    "CREATE INDEX IF NOT EXISTS idx_etf_states_date ON atlas.atlas_etf_states_daily (date, ticker)",
    "CREATE INDEX IF NOT EXISTS idx_etf_states_rs ON atlas.atlas_etf_states_daily (date, rs_state)",

    # Sector states
    "CREATE INDEX IF NOT EXISTS idx_sector_states_date ON atlas.atlas_sector_states_daily (date, sector_name)",

    # Fund states
    "CREATE INDEX IF NOT EXISTS idx_fund_states_date ON atlas.atlas_fund_states_daily (date, mstar_id)",
    "CREATE INDEX IF NOT EXISTS idx_fund_states_nav ON atlas.atlas_fund_states_daily (date, nav_state)",

    # Stock decisions
    "CREATE INDEX IF NOT EXISTS idx_stock_decisions_investable ON atlas.atlas_stock_decisions_daily (date, is_investable) WHERE is_investable = TRUE",
    "CREATE INDEX IF NOT EXISTS idx_stock_decisions_entry ON atlas.atlas_stock_decisions_daily (date) WHERE transition_trigger = TRUE OR breakout_trigger = TRUE",
    "CREATE INDEX IF NOT EXISTS idx_stock_decisions_exit ON atlas.atlas_stock_decisions_daily (date) WHERE exit_market_riskoff = TRUE OR exit_sector_avoid = TRUE OR exit_rs_deteriorate = TRUE OR exit_momentum_collapse = TRUE OR exit_volume_distrib = TRUE OR exit_stop_loss = TRUE",

    # ETF decisions
    "CREATE INDEX IF NOT EXISTS idx_etf_decisions_investable ON atlas.atlas_etf_decisions_daily (date, is_investable) WHERE is_investable = TRUE",

    # Fund decisions
    "CREATE INDEX IF NOT EXISTS idx_fund_decisions_recommended ON atlas.atlas_fund_decisions_daily (date, recommendation)",
    "CREATE INDEX IF NOT EXISTS idx_fund_decisions_transitions ON atlas.atlas_fund_decisions_daily (date) WHERE entry_trigger OR exit_trigger OR reduce_trigger OR add_trigger",

    # Operational
    "CREATE INDEX IF NOT EXISTS idx_run_log_date ON atlas.atlas_run_log (business_date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_run_log_status ON atlas.atlas_run_log (status, business_date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_validation_run ON atlas.atlas_validation_results (compute_run_id)",
    "CREATE INDEX IF NOT EXISTS idx_validation_failures ON atlas.atlas_validation_results (compute_run_id) WHERE passed = FALSE",
    "CREATE INDEX IF NOT EXISTS idx_benchmark_cache_date ON atlas.atlas_benchmark_returns_cache (date, benchmark_code)",
    "CREATE INDEX IF NOT EXISTS idx_thresholds_category ON atlas.atlas_thresholds (category) WHERE is_active = TRUE",
    "CREATE INDEX IF NOT EXISTS idx_threshold_history_key ON atlas.atlas_threshold_history (threshold_key, changed_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_threshold_history_reclassify ON atlas.atlas_threshold_history (reclassify_run_id) WHERE reclassify_run_id IS NOT NULL",

    # Quarantine — by run id
    "CREATE INDEX IF NOT EXISTS idx_stock_quarantine_run ON atlas.atlas_stock_metrics_quarantine (compute_run_id)",
    "CREATE INDEX IF NOT EXISTS idx_etf_quarantine_run ON atlas.atlas_etf_metrics_quarantine (compute_run_id)",
    "CREATE INDEX IF NOT EXISTS idx_index_quarantine_run ON atlas.atlas_index_metrics_quarantine (compute_run_id)",
    "CREATE INDEX IF NOT EXISTS idx_sector_quarantine_run ON atlas.atlas_sector_metrics_quarantine (compute_run_id)",
    "CREATE INDEX IF NOT EXISTS idx_fund_quarantine_run ON atlas.atlas_fund_metrics_quarantine (compute_run_id)",
)


def upgrade() -> None:
    for stmt in _INDEXES:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    # Indexes drop with their parent tables; explicit drops are not required.
    pass

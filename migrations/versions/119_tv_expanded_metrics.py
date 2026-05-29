"""Add expanded TV screener columns: oscillators, MAs, returns, fundamentals.

Revision ID: 119
Revises: 118
Create Date: 2026-05-29
"""

from alembic import op

revision = "119"
down_revision = "118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE atlas.tv_metrics
            ADD COLUMN IF NOT EXISTS macd_signal     NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS macd_hist       NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS stoch_k         NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS stoch_d         NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS adx             NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS adx_plus_di     NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS adx_minus_di    NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS cci_20          NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS williams_r      NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS mfi             NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS ao              NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS uo              NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS momentum        NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS roc             NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS bb_lower        NUMERIC(16,4),
            ADD COLUMN IF NOT EXISTS bb_upper        NUMERIC(16,4),
            ADD COLUMN IF NOT EXISTS bb_width        NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS vwap            NUMERIC(16,4),
            ADD COLUMN IF NOT EXISTS sma_20          NUMERIC(16,4),
            ADD COLUMN IF NOT EXISTS sma_50          NUMERIC(16,4),
            ADD COLUMN IF NOT EXISTS sma_200         NUMERIC(16,4),
            ADD COLUMN IF NOT EXISTS perf_1w         NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS perf_1m         NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS perf_3m         NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS perf_6m         NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS perf_ytd        NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS perf_1y         NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS perf_5y         NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS volatility_d    NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS volatility_w    NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS volatility_m    NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS beta_1y         NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS rel_volume_10d  NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS avg_volume_30d  BIGINT,
            ADD COLUMN IF NOT EXISTS avg_volume_60d  BIGINT,
            ADD COLUMN IF NOT EXISTS eps_diluted_ttm NUMERIC(16,4),
            ADD COLUMN IF NOT EXISTS eps_growth_yoy  NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS revenue_ttm     NUMERIC(20,2),
            ADD COLUMN IF NOT EXISTS revenue_growth_yoy NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS market_cap      NUMERIC(20,2),
            ADD COLUMN IF NOT EXISTS enterprise_value NUMERIC(20,2),
            ADD COLUMN IF NOT EXISTS gross_margin    NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS operating_margin NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS net_margin      NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS dividend_yield  NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS payout_ratio    NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS book_value_per_share NUMERIC(16,4),
            ADD COLUMN IF NOT EXISTS current_ratio   NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS quick_ratio     NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS roa             NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS roic            NUMERIC(10,4),
            ADD COLUMN IF NOT EXISTS ev_ebitda       NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS ev_sales        NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS price_fcf       NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS peg_ratio       NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS analyst_rating  NUMERIC(6,4),
            ADD COLUMN IF NOT EXISTS shares_outstanding NUMERIC(20,2),
            ADD COLUMN IF NOT EXISTS float_shares    NUMERIC(20,2)
    """)


def downgrade() -> None:
    cols = [
        "macd_signal", "macd_hist", "stoch_k", "stoch_d", "adx", "adx_plus_di", "adx_minus_di",
        "cci_20", "williams_r", "mfi", "ao", "uo", "momentum", "roc",
        "bb_lower", "bb_upper", "bb_width",
        "vwap", "sma_20", "sma_50", "sma_200",
        "perf_1w", "perf_1m", "perf_3m", "perf_6m", "perf_ytd", "perf_1y", "perf_5y",
        "volatility_d", "volatility_w", "volatility_m", "beta_1y",
        "rel_volume_10d", "avg_volume_30d", "avg_volume_60d",
        "eps_diluted_ttm", "eps_growth_yoy", "revenue_ttm", "revenue_growth_yoy",
        "market_cap", "enterprise_value",
        "gross_margin", "operating_margin", "net_margin",
        "dividend_yield", "payout_ratio", "book_value_per_share",
        "current_ratio", "quick_ratio", "roa", "roic",
        "ev_ebitda", "ev_sales", "price_fcf", "peg_ratio", "analyst_rating",
        "shares_outstanding", "float_shares",
    ]
    for c in cols:
        op.execute(f"ALTER TABLE atlas.tv_metrics DROP COLUMN IF EXISTS {c}")

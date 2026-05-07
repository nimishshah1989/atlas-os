"""create metrics tables

Revision ID: 004
Revises: 003
Create Date: 2026-05-06 00:00:03.000000

Layer 3 metric tables per ``docs/02_DATABASE_SCHEMA.md`` Section 3.
Stock + ETF + Index + Sector + Market Regime + Fund (daily + monthly).

The widest table is ``atlas_stock_metrics_daily`` (~50 columns of raw
primitive values). ``ema_50_stock`` and ``atr_21`` are baked in from M1
to avoid a re-run when M3 / M5 need them — see ``prds/00_INFRA_DECISIONS.md``
sections 5 and 6.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stock metrics
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_stock_metrics_daily (
            instrument_id          UUID            NOT NULL,
            date                   DATE            NOT NULL,

            -- Returns (decimal, not percent — e.g. 0.05 = 5%)
            ret_1d                 NUMERIC(10,4),
            ret_1w                 NUMERIC(10,4),
            ret_1m                 NUMERIC(10,4),
            ret_3m                 NUMERIC(10,4),
            ret_6m                 NUMERIC(10,4),
            ret_12m                NUMERIC(10,4),
            ret_12m_1m             NUMERIC(10,4),

            -- Relative Strength against tier benchmark
            rs_1w_tier             NUMERIC(10,4),
            rs_1m_tier             NUMERIC(10,4),
            rs_3m_tier             NUMERIC(10,4),
            rs_6m_tier             NUMERIC(10,4),
            rs_12m_tier            NUMERIC(10,4),

            -- RS against Nifty 500
            rs_1w_nifty500         NUMERIC(10,4),
            rs_1m_nifty500         NUMERIC(10,4),
            rs_3m_nifty500         NUMERIC(10,4),

            -- Within-tier RS percentile rank (0.0–1.0)
            rs_pctile_1w           NUMERIC(10,4),
            rs_pctile_1m           NUMERIC(10,4),
            rs_pctile_3m           NUMERIC(10,4),

            -- RS Momentum components (Bhaven's EMA-ratio approach)
            ema_10_stock           NUMERIC(18,4),
            ema_20_stock           NUMERIC(18,4),
            ema_50_stock           NUMERIC(18,4),
            ema_10_benchmark       NUMERIC(18,4),
            ema_20_benchmark       NUMERIC(18,4),
            ema_10_ratio           NUMERIC(10,4),
            ema_20_ratio           NUMERIC(10,4),
            ema_10_at_20d_high     BOOLEAN,
            ema_10_at_20d_low      BOOLEAN,

            -- Risk components
            extension_pct          NUMERIC(10,4),
            ema_200_stock          NUMERIC(18,4),
            vol_ratio_63           NUMERIC(10,4),
            realized_vol_63        NUMERIC(10,4),
            drawdown_ratio_252     NUMERIC(10,4),
            max_drawdown_252       NUMERIC(10,4),
            atr_21                 NUMERIC(18,4),

            -- Volume components
            volume_expansion       NUMERIC(10,4),
            avg_volume_20          BIGINT,
            avg_volume_252         BIGINT,
            effort_ratio_63        NUMERIC(10,4),

            -- Weinstein gate
            above_30w_ma           BOOLEAN,
            ma_30w_slope_4w        NUMERIC(10,4),
            weinstein_gate_pass    BOOLEAN,

            -- Stage-1 base detection
            stage1_base_qualifies  BOOLEAN,

            -- Numéraire variant — Gold-denominated RS values
            rs_1w_tier_gold        NUMERIC(10,4),
            rs_1m_tier_gold        NUMERIC(10,4),
            rs_3m_tier_gold        NUMERIC(10,4),

            -- Audit
            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (instrument_id, date)
        )
    """))

    # ETF metrics
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_etf_metrics_daily (
            ticker                 VARCHAR(32)     NOT NULL,
            date                   DATE            NOT NULL,

            -- Returns
            ret_1d                 NUMERIC(10,4),
            ret_1w                 NUMERIC(10,4),
            ret_1m                 NUMERIC(10,4),
            ret_3m                 NUMERIC(10,4),
            ret_6m                 NUMERIC(10,4),
            ret_12m                NUMERIC(10,4),

            -- Relative Strength
            rs_1w_benchmark        NUMERIC(10,4),
            rs_1m_benchmark        NUMERIC(10,4),
            rs_3m_benchmark        NUMERIC(10,4),
            rs_pctile_1w           NUMERIC(10,4),
            rs_pctile_1m           NUMERIC(10,4),
            rs_pctile_3m           NUMERIC(10,4),

            -- RS Momentum
            ema_10_etf             NUMERIC(18,4),
            ema_20_etf             NUMERIC(18,4),
            ema_10_benchmark       NUMERIC(18,4),
            ema_20_benchmark       NUMERIC(18,4),
            ema_10_ratio           NUMERIC(10,4),
            ema_20_ratio           NUMERIC(10,4),
            ema_10_at_20d_high     BOOLEAN,
            ema_10_at_20d_low      BOOLEAN,

            -- Risk
            extension_pct          NUMERIC(10,4),
            ema_200_etf            NUMERIC(18,4),
            vol_ratio_63           NUMERIC(10,4),
            realized_vol_63        NUMERIC(10,4),
            drawdown_ratio_252     NUMERIC(10,4),

            -- Volume (computed but informational)
            volume_expansion       NUMERIC(10,4),
            effort_ratio_63        NUMERIC(10,4),

            -- Weinstein gate
            above_30w_ma           BOOLEAN,
            weinstein_gate_pass    BOOLEAN,

            -- Numéraire variant
            rs_1w_benchmark_gold   NUMERIC(10,4),
            rs_1m_benchmark_gold   NUMERIC(10,4),
            rs_3m_benchmark_gold   NUMERIC(10,4),

            -- Audit
            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ticker, date)
        )
    """))

    # Index metrics
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_index_metrics_daily (
            index_code             VARCHAR(32)     NOT NULL,
            date                   DATE            NOT NULL,

            ret_1d                 NUMERIC(10,4),
            ret_1w                 NUMERIC(10,4),
            ret_1m                 NUMERIC(10,4),
            ret_3m                 NUMERIC(10,4),
            ret_6m                 NUMERIC(10,4),
            ret_12m                NUMERIC(10,4),

            rs_1w_nifty500         NUMERIC(10,4),
            rs_1m_nifty500         NUMERIC(10,4),
            rs_3m_nifty500         NUMERIC(10,4),

            ema_10_index           NUMERIC(18,4),
            ema_20_index           NUMERIC(18,4),
            ema_10_ratio_nifty500  NUMERIC(10,4),
            ema_20_ratio_nifty500  NUMERIC(10,4),

            realized_vol_63        NUMERIC(10,4),
            realized_vol_5d        NUMERIC(10,4),
            vol_252_median         NUMERIC(10,4),

            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (index_code, date)
        )
    """))

    # Sector metrics
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_sector_metrics_daily (
            sector_name            VARCHAR(64)     NOT NULL,
            date                   DATE            NOT NULL,

            -- Bottom-up
            bottomup_ret_1m        NUMERIC(10,4),
            bottomup_ret_3m        NUMERIC(10,4),
            bottomup_ret_6m        NUMERIC(10,4),
            bottomup_rs_3m_nifty500 NUMERIC(10,4),
            bottomup_ema_10_ratio  NUMERIC(10,4),
            bottomup_ema_20_ratio  NUMERIC(10,4),

            -- Top-down
            topdown_index_code     VARCHAR(32),
            topdown_ret_1m         NUMERIC(10,4),
            topdown_ret_3m         NUMERIC(10,4),
            topdown_rs_3m_nifty500 NUMERIC(10,4),

            -- Breadth
            constituent_count      INTEGER,
            participation_50       NUMERIC(10,4),
            participation_rs       NUMERIC(10,4),
            leadership_concentration NUMERIC(10,4),

            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (sector_name, date)
        )
    """))

    # Market regime
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_market_regime_daily (
            date                   DATE            NOT NULL PRIMARY KEY,

            -- Trend
            nifty500_close         NUMERIC(18,4),
            nifty500_ema_50        NUMERIC(18,4),
            nifty500_ema_200       NUMERIC(18,4),
            nifty500_above_ema_50  BOOLEAN,
            nifty500_above_ema_200 BOOLEAN,
            nifty500_ema_50_slope  NUMERIC(10,4),
            nifty500_ema_200_slope NUMERIC(10,4),

            -- MA breadth
            pct_above_ema_20       NUMERIC(10,4),
            pct_above_ema_50       NUMERIC(10,4),
            pct_above_ema_200      NUMERIC(10,4),

            -- A/D breadth
            advances_count         INTEGER,
            declines_count         INTEGER,
            unchanged_count        INTEGER,
            ad_ratio               NUMERIC(10,4),
            ad_line                NUMERIC(18,4),
            ad_line_slope_21       NUMERIC(10,4),
            mcclellan_oscillator   NUMERIC(10,4),
            mcclellan_summation    NUMERIC(18,4),

            -- New highs/lows
            new_52w_highs          INTEGER,
            new_52w_lows           INTEGER,
            net_new_highs          INTEGER,
            new_high_low_ratio     NUMERIC(10,4),

            -- Strength breadth
            pct_in_strong_states   NUMERIC(10,4),
            pct_weinstein_pass     NUMERIC(10,4),

            -- Vol inputs
            india_vix              NUMERIC(10,4),
            realized_vol_5d_nifty500 NUMERIC(10,4),
            vol_252_median_nifty500 NUMERIC(10,4),

            -- Computed regime
            regime_state           VARCHAR(32)     NOT NULL,
            deployment_multiplier  NUMERIC(10,4)   NOT NULL,

            -- Dislocation
            dislocation_active     BOOLEAN         NOT NULL DEFAULT FALSE,
            dislocation_started    DATE,

            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_market_regime_state CHECK (regime_state IN (
                'Risk-On', 'Constructive', 'Cautious', 'Risk-Off', 'DISLOCATION_SUSPENDED'
            )),
            CONSTRAINT chk_market_regime_multiplier CHECK (
                deployment_multiplier IN (1.0, 0.7, 0.4, 0.0)
            )
        )
    """))

    # Fund metrics (daily — Lens 1 inputs)
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_fund_metrics_daily (
            mstar_id               VARCHAR(32)     NOT NULL,
            nav_date               DATE            NOT NULL,

            nav                    NUMERIC(18,4),
            ret_1m                 NUMERIC(10,4),
            ret_3m                 NUMERIC(10,4),
            ret_6m                 NUMERIC(10,4),
            ret_12m                NUMERIC(10,4),

            rs_1m_category         NUMERIC(10,4),
            rs_3m_category         NUMERIC(10,4),
            rs_6m_category         NUMERIC(10,4),
            rs_pctile_1m           NUMERIC(10,4),
            rs_pctile_3m           NUMERIC(10,4),
            rs_pctile_6m           NUMERIC(10,4),

            realized_vol_63        NUMERIC(10,4),
            drawdown_ratio_252     NUMERIC(10,4),

            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (mstar_id, nav_date)
        )
    """))

    # Fund lens monthly (Lens 2 + Lens 3)
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_fund_lens_monthly (
            mstar_id               VARCHAR(32)     NOT NULL,
            as_of_date             DATE            NOT NULL,

            aligned_aum_pct        NUMERIC(10,4),
            avoid_aum_pct          NUMERIC(10,4),
            sector_concentration   NUMERIC(10,4),

            strong_aum_pct         NUMERIC(10,4),
            weak_aum_pct           NUMERIC(10,4),
            unknown_aum_pct        NUMERIC(10,4),
            holdings_concentration NUMERIC(10,4),

            last_disclosed_date    DATE,

            compute_run_id         UUID            NOT NULL,
            created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (mstar_id, as_of_date)
        )
    """))


def downgrade() -> None:
    for tbl in (
        "atlas_fund_lens_monthly",
        "atlas_fund_metrics_daily",
        "atlas_market_regime_daily",
        "atlas_sector_metrics_daily",
        "atlas_index_metrics_daily",
        "atlas_etf_metrics_daily",
        "atlas_stock_metrics_daily",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS atlas.{tbl}"))

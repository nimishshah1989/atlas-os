"""Create us_atlas schema with all 16 tables for US Atlas universe.

Tables mirror the India (atlas) schema but with US-specific columns:
- instruments: GICS sector, in_sp500 flag instead of BSE classification
- atlas_stock_metrics_daily: 4-benchmark RS columns (ACWI, VT, EEM, GOLD)
- atlas_stock_rs_states / atlas_etf_rs_states: normalized 20-row-per-day RS state table
- atlas_market_regime_daily: generic column names (benchmark_close, vix_level)

No cross-schema foreign keys. Alembic version tracked in us_atlas.alembic_version.
"""

from alembic import op

revision = "055"
down_revision = "054"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS us_atlas")

    # ------------------------------------------------------------------
    # instruments — S&P 500 stocks + curated ETFs master list
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.instruments (
            ticker              VARCHAR(20)     PRIMARY KEY,
            name                TEXT            NOT NULL,
            instrument_type     VARCHAR(20)     NOT NULL,   -- 'stock', 'etf', 'index'
            asset_class         VARCHAR(50),                -- 'equity', 'commodity', 'broad'
            gics_sector         VARCHAR(100),               -- GICS level-1 sector
            gics_industry       VARCHAR(100),               -- GICS level-2 industry
            etf_category        VARCHAR(100),               -- 'Sector ETF', 'Commodity ETF', etc.
            issuer              VARCHAR(50),
            aum_usd             BIGINT,
            avg_volume_30d      BIGINT,
            inception_date      DATE,
            in_sp500            BOOLEAN         NOT NULL DEFAULT FALSE,
            universe_eligible   BOOLEAN         NOT NULL DEFAULT TRUE,
            is_developed_market BOOLEAN         NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """)

    # ------------------------------------------------------------------
    # stock_ohlcv — daily OHLCV for all US instruments
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.stock_ohlcv (
            ticker      VARCHAR(20)     NOT NULL,
            date        DATE            NOT NULL,
            open        NUMERIC(14, 4),
            high        NUMERIC(14, 4),
            low         NUMERIC(14, 4),
            close       NUMERIC(14, 4)  NOT NULL,
            volume      BIGINT,
            PRIMARY KEY (ticker, date)
        )
    """)
    op.execute("CREATE INDEX ix_us_stock_ohlcv_date ON us_atlas.stock_ohlcv (date)")

    # ------------------------------------------------------------------
    # atlas_benchmark_master — SPY, ACWI, VT, EEM, GLD, ^SPX, ^VIX
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_benchmark_master (
            benchmark_code      VARCHAR(30)     PRIMARY KEY,
            benchmark_type      VARCHAR(30)     NOT NULL,   -- 'etf', 'index', 'vix'
            source_table        VARCHAR(60)     NOT NULL,   -- 'us_atlas.stock_ohlcv'
            source_identifier   VARCHAR(30)     NOT NULL,   -- ticker or index code
            description         TEXT,
            is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """)

    # ------------------------------------------------------------------
    # atlas_benchmark_returns_cache — pre-computed returns per benchmark per date
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_benchmark_returns_cache (
            benchmark_code  VARCHAR(30)     NOT NULL,
            date            DATE            NOT NULL,
            close           NUMERIC(14, 4),
            ret_1d          NUMERIC(10, 8),
            ret_1w          NUMERIC(10, 8),
            ret_1m          NUMERIC(10, 8),
            ret_3m          NUMERIC(10, 8),
            ret_6m          NUMERIC(10, 8),
            ret_12m         NUMERIC(10, 8),
            ret_12m_1m      NUMERIC(10, 8),
            ema_10          NUMERIC(14, 4),
            ema_20          NUMERIC(14, 4),
            realized_vol_63 NUMERIC(10, 8),
            PRIMARY KEY (benchmark_code, date)
        )
    """)

    # ------------------------------------------------------------------
    # atlas_universe_stocks + atlas_universe_etfs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_universe_stocks (
            ticker          VARCHAR(20)     PRIMARY KEY,
            tier            VARCHAR(20),    -- 'Large', 'Mid', 'Small'
            in_sp500        BOOLEAN         NOT NULL DEFAULT FALSE,
            gics_sector     VARCHAR(100),
            is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
            locked_at       DATE,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE us_atlas.atlas_universe_etfs (
            ticker          VARCHAR(20)     PRIMARY KEY,
            etf_category    VARCHAR(100),   -- 'Sector ETF', 'Commodity ETF', 'Country ETF', etc.
            linked_sector   VARCHAR(100),   -- GICS sector for Sector ETFs
            is_benchmark    BOOLEAN         NOT NULL DEFAULT FALSE,
            is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
            locked_at       DATE,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """)

    # ------------------------------------------------------------------
    # atlas_thresholds — US-calibrated threshold values
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_thresholds (
            threshold_key           VARCHAR(64)     PRIMARY KEY,
            threshold_value         NUMERIC(18, 6)  NOT NULL,
            category                VARCHAR(32)     NOT NULL,
            description             TEXT            NOT NULL,
            methodology_section     VARCHAR(16),
            units                   VARCHAR(16),
            min_allowed             NUMERIC(18, 6)  NOT NULL,
            max_allowed             NUMERIC(18, 6)  NOT NULL,
            default_value           NUMERIC(18, 6)  NOT NULL,
            last_modified_by        VARCHAR(64)     NOT NULL DEFAULT 'system',
            last_modified_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            is_active               BOOLEAN         NOT NULL DEFAULT TRUE
        )
    """)

    # ------------------------------------------------------------------
    # atlas_run_log
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_run_log (
            id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            run_type        VARCHAR(30)     NOT NULL,
            universe        VARCHAR(20)     NOT NULL DEFAULT 'us',
            status          VARCHAR(20)     NOT NULL DEFAULT 'running',
            started_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            finished_at     TIMESTAMPTZ,
            rows_written    INTEGER,
            error_message   TEXT,
            metadata        JSONB
        )
    """)

    # ------------------------------------------------------------------
    # atlas_stock_metrics_daily — Layer 2: raw computed metrics
    # 40 RS columns (4 benchmarks × 5 timeframes × raw + pctile)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_stock_metrics_daily (
            instrument_id   UUID            NOT NULL,
            ticker          VARCHAR(20)     NOT NULL,
            date            DATE            NOT NULL,

            -- Core returns
            ret_1d          NUMERIC(10, 8),
            ret_1w          NUMERIC(10, 8),
            ret_1m          NUMERIC(10, 8),
            ret_3m          NUMERIC(10, 8),
            ret_6m          NUMERIC(10, 8),
            ret_12m         NUMERIC(10, 8),
            ret_12m_1m      NUMERIC(10, 8),

            -- EMAs
            ema_10_stock    NUMERIC(14, 4),
            ema_20_stock    NUMERIC(14, 4),
            ema_50_stock    NUMERIC(14, 4),
            ema_200_stock   NUMERIC(14, 4),
            ema_10_ratio    NUMERIC(10, 8),
            ema_20_ratio    NUMERIC(10, 8),

            -- Risk metrics
            realized_vol_63     NUMERIC(10, 8),
            vol_ratio_63        NUMERIC(10, 8),
            max_drawdown_252    NUMERIC(10, 8),
            extension_pct       NUMERIC(10, 8),
            atr_21              NUMERIC(14, 4),
            above_30w_ma        BOOLEAN,

            -- Volume
            avg_volume_20       NUMERIC(20, 2),
            avg_volume_252      NUMERIC(20, 2),
            volume_expansion    NUMERIC(10, 4),

            -- RS vs ACWI (iShares MSCI ACWI ETF — MSCI World proxy)
            rs_1w_acwi          NUMERIC(10, 8),
            rs_1m_acwi          NUMERIC(10, 8),
            rs_3m_acwi          NUMERIC(10, 8),
            rs_6m_acwi          NUMERIC(10, 8),
            rs_12m_acwi         NUMERIC(10, 8),
            rs_pctile_1w_acwi   NUMERIC(6, 4),
            rs_pctile_1m_acwi   NUMERIC(6, 4),
            rs_pctile_3m_acwi   NUMERIC(6, 4),
            rs_pctile_6m_acwi   NUMERIC(6, 4),
            rs_pctile_12m_acwi  NUMERIC(6, 4),

            -- RS vs VT (Vanguard Total World)
            rs_1w_vt            NUMERIC(10, 8),
            rs_1m_vt            NUMERIC(10, 8),
            rs_3m_vt            NUMERIC(10, 8),
            rs_6m_vt            NUMERIC(10, 8),
            rs_12m_vt           NUMERIC(10, 8),
            rs_pctile_1w_vt     NUMERIC(6, 4),
            rs_pctile_1m_vt     NUMERIC(6, 4),
            rs_pctile_3m_vt     NUMERIC(6, 4),
            rs_pctile_6m_vt     NUMERIC(6, 4),
            rs_pctile_12m_vt    NUMERIC(6, 4),

            -- RS vs EEM (iShares Emerging Markets)
            rs_1w_eem           NUMERIC(10, 8),
            rs_1m_eem           NUMERIC(10, 8),
            rs_3m_eem           NUMERIC(10, 8),
            rs_6m_eem           NUMERIC(10, 8),
            rs_12m_eem          NUMERIC(10, 8),
            rs_pctile_1w_eem    NUMERIC(6, 4),
            rs_pctile_1m_eem    NUMERIC(6, 4),
            rs_pctile_3m_eem    NUMERIC(6, 4),
            rs_pctile_6m_eem    NUMERIC(6, 4),
            rs_pctile_12m_eem   NUMERIC(6, 4),

            -- RS vs GOLD (GLD ETF)
            rs_1w_gold          NUMERIC(10, 8),
            rs_1m_gold          NUMERIC(10, 8),
            rs_3m_gold          NUMERIC(10, 8),
            rs_6m_gold          NUMERIC(10, 8),
            rs_12m_gold         NUMERIC(10, 8),
            rs_pctile_1w_gold   NUMERIC(6, 4),
            rs_pctile_1m_gold   NUMERIC(6, 4),
            rs_pctile_3m_gold   NUMERIC(6, 4),
            rs_pctile_6m_gold   NUMERIC(6, 4),
            rs_pctile_12m_gold  NUMERIC(6, 4),

            -- Consensus RS score: count of (benchmark x timeframe) cells in top 40%
            rs_consensus_bullish    SMALLINT,   -- 0-20
            rs_consensus_bearish    SMALLINT,   -- 0-20

            created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

            PRIMARY KEY (ticker, date)
        )
    """)
    op.execute("CREATE INDEX ix_us_stock_metrics_date ON us_atlas.atlas_stock_metrics_daily (date)")
    op.execute("CREATE INDEX ix_us_stock_metrics_ticker ON us_atlas.atlas_stock_metrics_daily (ticker)")

    # ------------------------------------------------------------------
    # atlas_stock_rs_states — normalized RS state: 20 rows per stock per day
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_stock_rs_states (
            ticker      VARCHAR(20)     NOT NULL,
            date        DATE            NOT NULL,
            benchmark   VARCHAR(10)     NOT NULL,   -- 'acwi', 'vt', 'eem', 'gold'
            timeframe   VARCHAR(5)      NOT NULL,   -- '1w', '1m', '3m', '6m', '12m'
            rs_value    NUMERIC(10, 8),
            rs_pctile   NUMERIC(6, 4),
            rs_state    VARCHAR(15),                -- 'Overweight', 'Neutral', 'Underweight'
            PRIMARY KEY (ticker, date, benchmark, timeframe)
        )
    """)
    op.execute("""
        CREATE INDEX ix_us_stock_rs_states_date_bench_tf
        ON us_atlas.atlas_stock_rs_states (date, benchmark, timeframe, rs_state)
    """)

    # ------------------------------------------------------------------
    # atlas_stock_states_daily — Layer 3: non-RS classified states
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_stock_states_daily (
            ticker                  VARCHAR(20)     NOT NULL,
            date                    DATE            NOT NULL,
            momentum_state          VARCHAR(30),    -- 'Rising', 'Falling', 'Neutral'
            risk_state              VARCHAR(30),    -- 'Low', 'Elevated', 'High'
            volume_state            VARCHAR(30),
            history_gate_pass       BOOLEAN,
            liquidity_gate_pass     BOOLEAN,
            weinstein_gate_pass     BOOLEAN,
            stage1_base_qualifies   BOOLEAN,
            above_30w_ma            BOOLEAN,
            gics_sector             VARCHAR(100),
            tier                    VARCHAR(20),
            created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ticker, date)
        )
    """)
    op.execute("CREATE INDEX ix_us_stock_states_date ON us_atlas.atlas_stock_states_daily (date)")

    # ------------------------------------------------------------------
    # atlas_etf_metrics_daily — same 40-RS-column structure for ETFs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_etf_metrics_daily (
            ticker              VARCHAR(20)     NOT NULL,
            date                DATE            NOT NULL,

            ret_1d              NUMERIC(10, 8),
            ret_1w              NUMERIC(10, 8),
            ret_1m              NUMERIC(10, 8),
            ret_3m              NUMERIC(10, 8),
            ret_6m              NUMERIC(10, 8),
            ret_12m             NUMERIC(10, 8),
            ret_12m_1m          NUMERIC(10, 8),

            ema_10_stock        NUMERIC(14, 4),
            ema_20_stock        NUMERIC(14, 4),
            ema_50_stock        NUMERIC(14, 4),
            ema_200_stock       NUMERIC(14, 4),
            ema_10_ratio        NUMERIC(10, 8),
            ema_20_ratio        NUMERIC(10, 8),

            realized_vol_63     NUMERIC(10, 8),
            vol_ratio_63        NUMERIC(10, 8),
            max_drawdown_252    NUMERIC(10, 8),
            extension_pct       NUMERIC(10, 8),
            atr_21              NUMERIC(14, 4),
            above_30w_ma        BOOLEAN,
            avg_volume_20       NUMERIC(20, 2),

            rs_1w_acwi          NUMERIC(10, 8),
            rs_1m_acwi          NUMERIC(10, 8),
            rs_3m_acwi          NUMERIC(10, 8),
            rs_6m_acwi          NUMERIC(10, 8),
            rs_12m_acwi         NUMERIC(10, 8),
            rs_pctile_1w_acwi   NUMERIC(6, 4),
            rs_pctile_1m_acwi   NUMERIC(6, 4),
            rs_pctile_3m_acwi   NUMERIC(6, 4),
            rs_pctile_6m_acwi   NUMERIC(6, 4),
            rs_pctile_12m_acwi  NUMERIC(6, 4),

            rs_1w_vt            NUMERIC(10, 8),
            rs_1m_vt            NUMERIC(10, 8),
            rs_3m_vt            NUMERIC(10, 8),
            rs_6m_vt            NUMERIC(10, 8),
            rs_12m_vt           NUMERIC(10, 8),
            rs_pctile_1w_vt     NUMERIC(6, 4),
            rs_pctile_1m_vt     NUMERIC(6, 4),
            rs_pctile_3m_vt     NUMERIC(6, 4),
            rs_pctile_6m_vt     NUMERIC(6, 4),
            rs_pctile_12m_vt    NUMERIC(6, 4),

            rs_1w_eem           NUMERIC(10, 8),
            rs_1m_eem           NUMERIC(10, 8),
            rs_3m_eem           NUMERIC(10, 8),
            rs_6m_eem           NUMERIC(10, 8),
            rs_12m_eem          NUMERIC(10, 8),
            rs_pctile_1w_eem    NUMERIC(6, 4),
            rs_pctile_1m_eem    NUMERIC(6, 4),
            rs_pctile_3m_eem    NUMERIC(6, 4),
            rs_pctile_6m_eem    NUMERIC(6, 4),
            rs_pctile_12m_eem   NUMERIC(6, 4),

            rs_1w_gold          NUMERIC(10, 8),
            rs_1m_gold          NUMERIC(10, 8),
            rs_3m_gold          NUMERIC(10, 8),
            rs_6m_gold          NUMERIC(10, 8),
            rs_12m_gold         NUMERIC(10, 8),
            rs_pctile_1w_gold   NUMERIC(6, 4),
            rs_pctile_1m_gold   NUMERIC(6, 4),
            rs_pctile_3m_gold   NUMERIC(6, 4),
            rs_pctile_6m_gold   NUMERIC(6, 4),
            rs_pctile_12m_gold  NUMERIC(6, 4),

            rs_consensus_bullish    SMALLINT,
            rs_consensus_bearish    SMALLINT,

            created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ticker, date)
        )
    """)
    op.execute("CREATE INDEX ix_us_etf_metrics_date ON us_atlas.atlas_etf_metrics_daily (date)")

    # ------------------------------------------------------------------
    # atlas_etf_rs_states — normalized RS state: 20 rows per ETF per day
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_etf_rs_states (
            ticker      VARCHAR(20)     NOT NULL,
            date        DATE            NOT NULL,
            benchmark   VARCHAR(10)     NOT NULL,
            timeframe   VARCHAR(5)      NOT NULL,
            rs_value    NUMERIC(10, 8),
            rs_pctile   NUMERIC(6, 4),
            rs_state    VARCHAR(15),
            rs_quintile SMALLINT,       -- 1-5 (1=best); consistent with global_atlas schema
            PRIMARY KEY (ticker, date, benchmark, timeframe)
        )
    """)
    op.execute("""
        CREATE INDEX ix_us_etf_rs_states_date_bench_tf
        ON us_atlas.atlas_etf_rs_states (date, benchmark, timeframe, rs_state)
    """)

    # ------------------------------------------------------------------
    # atlas_etf_states_daily — non-RS classified states for ETFs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_etf_states_daily (
            ticker              VARCHAR(20)     NOT NULL,
            date                DATE            NOT NULL,
            momentum_state      VARCHAR(30),
            risk_state          VARCHAR(30),
            history_gate_pass   BOOLEAN,
            liquidity_gate_pass BOOLEAN,
            weinstein_gate_pass BOOLEAN,
            etf_category        VARCHAR(100),
            linked_sector       VARCHAR(100),
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ticker, date)
        )
    """)
    op.execute("CREATE INDEX ix_us_etf_states_date ON us_atlas.atlas_etf_states_daily (date)")

    # ------------------------------------------------------------------
    # atlas_market_regime_daily — VT trend + breadth (same structure as global_atlas)
    # VIX and advance/decline line added in a later migration when ingest is built.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_market_regime_daily (
            date                    DATE        PRIMARY KEY,

            -- World benchmark trend (VT for US ETF universe — consistent with global_atlas)
            benchmark_close         NUMERIC(14, 4),
            benchmark_ema_50        NUMERIC(14, 4),
            benchmark_ema_200       NUMERIC(14, 4),
            benchmark_ema_50_slope  NUMERIC(10, 8),
            benchmark_ema_200_slope NUMERIC(10, 8),
            benchmark_above_ema_50  BOOLEAN,
            benchmark_above_ema_200 BOOLEAN,

            -- Realized vol regime (VT 5d realized vol vs 252d median — no VIX dependency)
            realized_vol_5d         NUMERIC(10, 8),
            vol_252_median          NUMERIC(10, 8),

            -- Breadth: % of universe ETFs above their own 200DMA / 50DMA
            pct_countries_above_200dma  NUMERIC(6, 4),
            pct_countries_above_50dma   NUMERIC(6, 4),

            -- Regime classification
            regime_state            VARCHAR(30),    -- 'Strong', 'Healthy', 'Caution', 'Weak'
            dislocation_flag        BOOLEAN         NOT NULL DEFAULT FALSE,

            created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """)

    # ------------------------------------------------------------------
    # atlas_breadth_daily — S&P 500 breadth indicators
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE us_atlas.atlas_breadth_daily (
            date                DATE        PRIMARY KEY,
            advances            INTEGER,
            declines            INTEGER,
            unchanged           INTEGER,
            ad_ratio            NUMERIC(8, 4),
            ad_line             NUMERIC(14, 4),
            mcclellan_oscillator    NUMERIC(10, 4),
            mcclellan_summation     NUMERIC(14, 4),
            new_highs_52w       INTEGER,
            new_lows_52w        INTEGER,
            pct_above_200dma    NUMERIC(6, 4),
            pct_above_50dma     NUMERIC(6, 4),
            pct_above_20dma     NUMERIC(6, 4),
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """)

    # ------------------------------------------------------------------
    # Seed benchmark master rows
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO us_atlas.atlas_benchmark_master
            (benchmark_code, benchmark_type, source_table, source_identifier, description)
        VALUES
            ('SPY',  'etf',   'us_atlas.stock_ohlcv', 'spy',  'SPDR S&P 500 ETF — primary US equity benchmark'),
            ('ACWI', 'etf',   'us_atlas.stock_ohlcv', 'acwi', 'iShares MSCI ACWI ETF — MSCI World proxy (2008-)'),
            ('VT',   'etf',   'us_atlas.stock_ohlcv', 'vt',   'Vanguard Total World Stock ETF (2008-)'),
            ('EEM',  'etf',   'us_atlas.stock_ohlcv', 'eem',  'iShares MSCI Emerging Markets ETF (2005-)'),
            ('GOLD', 'etf',   'us_atlas.stock_ohlcv', 'gld',  'SPDR Gold Shares — gold numéraire benchmark'),
            ('^SPX', 'index', 'us_atlas.stock_ohlcv', '^spx', 'S&P 500 Index — regime benchmark'),
            ('^VIX', 'vix',   'us_atlas.stock_ohlcv', '^vix', 'CBOE Volatility Index — fetched via Stooq API')
    """)

    # ------------------------------------------------------------------
    # Seed US-calibrated thresholds
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO us_atlas.atlas_thresholds
            (threshold_key, threshold_value, category, description, units, min_allowed, max_allowed, default_value)
        VALUES
            -- RS state cutoffs (same percentile logic as India — self-calibrating)
            ('rs_overweight_pctile',  0.70, 'rs', 'RS percentile above which state = Overweight', 'ratio', 0.50, 0.90, 0.70),
            ('rs_underweight_pctile', 0.30, 'rs', 'RS percentile below which state = Underweight', 'ratio', 0.10, 0.50, 0.30),

            -- Consensus RS conviction tiers (count of bullish cells out of 20)
            ('rs_consensus_t1_min', 16, 'rs', 'Minimum bullish cell count for T1 conviction', 'count', 14, 20, 16),
            ('rs_consensus_t2_min', 12, 'rs', 'Minimum bullish cell count for T2 conviction', 'count', 10, 16, 12),
            ('rs_consensus_t3_min',  8, 'rs', 'Minimum bullish cell count for T3 conviction', 'count',  6, 12,  8),
            ('rs_consensus_t4_min',  4, 'rs', 'Minimum bullish cell count for T4 conviction', 'count',  2,  8,  4),

            -- VIX regime thresholds (CBOE VIX — calibrated from 10yr history)
            -- Historical: median ~17, 70th pctile ~22, 90th pctile ~30
            ('vix_risk_on_max',    20.0, 'regime', 'VIX below this = Risk-On state',   'vix_points', 15.0, 25.0, 20.0),
            ('vix_caution_max',    30.0, 'regime', 'VIX below this = Caution state',   'vix_points', 22.0, 35.0, 30.0),
            ('vix_high_fear_min',  30.0, 'regime', 'VIX above this = High-Fear state', 'vix_points', 25.0, 40.0, 30.0),

            -- Breadth regime thresholds
            ('breadth_healthy_min',  0.55, 'regime', '% S&P 500 above 200DMA for healthy market', 'ratio', 0.40, 0.70, 0.55),
            ('breadth_caution_min',  0.40, 'regime', '% S&P 500 above 200DMA for caution zone',   'ratio', 0.25, 0.55, 0.40),

            -- Dislocation: 5d realized vol vs 252d median
            ('dislocation_vol_multiplier', 2.0, 'regime', 'Vol spike multiplier for dislocation override', 'ratio', 1.5, 3.0, 2.0),

            -- Momentum state (EMA ratio — same as India, dimensionless)
            ('ema10_ratio_rising_min',  1.01, 'momentum', 'EMA10/EMA20 ratio for Rising state',  'ratio', 1.00, 1.05, 1.01),
            ('ema20_ratio_falling_max', 0.99, 'momentum', 'EMA10/EMA20 ratio for Falling state', 'ratio', 0.95, 1.00, 0.99),

            -- History gate
            ('history_gate_min_days', 252, 'gate', 'Minimum trading days of history required', 'days', 126, 504, 252),

            -- Liquidity gate
            ('liquidity_gate_min_avg_vol', 500000, 'gate', 'Minimum 20-day avg volume for US stocks', 'shares', 100000, 5000000, 500000)
    """)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS us_atlas CASCADE")

"""Create global_atlas schema with 10 tables for Global Macro universe.

30 country ETFs (US-listed) tracked against 4 benchmarks (ACWI, VT, EEM, GOLD).
RS labels are quintile-based (Q1-Q5) because 30 instruments is too small for
meaningful percentile distinctions.

No stocks, no sector taxonomy, no funds. Only ETFs + regime.
VIX not used — regime derives volatility state from VT realized vol.

EEM RS column is populated for all 30 countries but the UI suppresses it
for developed-market countries (is_developed_market = TRUE).
"""

from alembic import op

revision = "056"
down_revision = "055"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS global_atlas")

    # ------------------------------------------------------------------
    # instruments — 30 country ETFs master list
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE global_atlas.instruments (
            ticker              VARCHAR(20)     PRIMARY KEY,
            name                TEXT            NOT NULL,
            country             VARCHAR(60)     NOT NULL,
            country_iso2        VARCHAR(2),
            region              VARCHAR(40)     NOT NULL,   -- 'Americas', 'Europe Developed', etc.
            is_developed_market BOOLEAN         NOT NULL DEFAULT FALSE,
            issuer              VARCHAR(50),
            aum_usd             BIGINT,
            inception_date      DATE,
            universe_eligible   BOOLEAN         NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """)

    # ------------------------------------------------------------------
    # stock_ohlcv — daily OHLCV for all 30 country ETFs + benchmarks
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE global_atlas.stock_ohlcv (
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
    op.execute("CREATE INDEX ix_global_ohlcv_date ON global_atlas.stock_ohlcv (date)")

    # ------------------------------------------------------------------
    # atlas_benchmark_master
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE global_atlas.atlas_benchmark_master (
            benchmark_code      VARCHAR(30)     PRIMARY KEY,
            benchmark_type      VARCHAR(30)     NOT NULL,
            source_table        VARCHAR(60)     NOT NULL,
            source_identifier   VARCHAR(30)     NOT NULL,
            description         TEXT,
            is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """)

    # ------------------------------------------------------------------
    # atlas_benchmark_returns_cache
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE global_atlas.atlas_benchmark_returns_cache (
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
    # atlas_universe_etfs — the 30 country ETFs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE global_atlas.atlas_universe_etfs (
            ticker          VARCHAR(20)     PRIMARY KEY,
            country         VARCHAR(60)     NOT NULL,
            region          VARCHAR(40)     NOT NULL,
            is_developed_market BOOLEAN     NOT NULL DEFAULT FALSE,
            is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
            locked_at       DATE,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        )
    """)

    # ------------------------------------------------------------------
    # atlas_thresholds — Global-calibrated thresholds
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE global_atlas.atlas_thresholds (
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
        CREATE TABLE global_atlas.atlas_run_log (
            id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            run_type        VARCHAR(30)     NOT NULL,
            universe        VARCHAR(20)     NOT NULL DEFAULT 'global',
            status          VARCHAR(20)     NOT NULL DEFAULT 'running',
            started_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            finished_at     TIMESTAMPTZ,
            rows_written    INTEGER,
            error_message   TEXT,
            metadata        JSONB
        )
    """)

    # ------------------------------------------------------------------
    # atlas_etf_metrics_daily — 40 RS columns for 30 country ETFs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE global_atlas.atlas_etf_metrics_daily (
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
            max_drawdown_252    NUMERIC(10, 8),
            above_30w_ma        BOOLEAN,

            -- RS vs ACWI
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

            -- RS vs VT
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

            -- RS vs EEM (populated for all; UI suppresses for DM countries)
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

            -- RS vs GOLD
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

            -- Consensus
            rs_consensus_bullish    SMALLINT,
            rs_consensus_bearish    SMALLINT,

            created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ticker, date)
        )
    """)
    op.execute("CREATE INDEX ix_global_etf_metrics_date ON global_atlas.atlas_etf_metrics_daily (date)")

    # ------------------------------------------------------------------
    # atlas_etf_rs_states — 20 rows per country ETF per day
    # This is the PRIMARY query target for Global Pulse Country Rankings.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE global_atlas.atlas_etf_rs_states (
            ticker      VARCHAR(20)     NOT NULL,
            date        DATE            NOT NULL,
            benchmark   VARCHAR(10)     NOT NULL,   -- 'acwi', 'vt', 'eem', 'gold'
            timeframe   VARCHAR(5)      NOT NULL,   -- '1w', '1m', '3m', '6m', '12m'
            rs_value    NUMERIC(10, 8),
            rs_pctile   NUMERIC(6, 4),
            rs_state    VARCHAR(15),                -- 'Q1', 'Q2', 'Q3', 'Q4', 'Q5'
            rs_quintile SMALLINT,                   -- 1-5 (1=best)
            PRIMARY KEY (ticker, date, benchmark, timeframe)
        )
    """)
    op.execute("""
        CREATE INDEX ix_global_etf_rs_states_date_bench
        ON global_atlas.atlas_etf_rs_states (date, benchmark, timeframe, rs_quintile)
    """)

    # ------------------------------------------------------------------
    # atlas_market_regime_daily — VT trend + realized vol regime
    # No VIX for Global; volatility state derived from VT realized vol.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE global_atlas.atlas_market_regime_daily (
            date                    DATE        PRIMARY KEY,

            -- VT as world benchmark
            benchmark_close         NUMERIC(14, 4),
            benchmark_ema_50        NUMERIC(14, 4),
            benchmark_ema_200       NUMERIC(14, 4),
            benchmark_ema_50_slope  NUMERIC(10, 8),
            benchmark_ema_200_slope NUMERIC(10, 8),
            benchmark_above_ema_50  BOOLEAN,
            benchmark_above_ema_200 BOOLEAN,

            -- Realized vol regime (no VIX; VT 5d realized vol vs 252d median)
            realized_vol_5d         NUMERIC(10, 8),
            vol_252_median          NUMERIC(10, 8),

            -- Global breadth: % of 30 country ETFs above their own 200DMA
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
    # Seed benchmark master rows
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO global_atlas.atlas_benchmark_master
            (benchmark_code, benchmark_type, source_table, source_identifier, description)
        VALUES
            ('VT',   'etf', 'global_atlas.stock_ohlcv', 'vt',   'Vanguard Total World Stock ETF — primary world benchmark'),
            ('ACWI', 'etf', 'global_atlas.stock_ohlcv', 'acwi', 'iShares MSCI ACWI ETF — MSCI World proxy'),
            ('EEM',  'etf', 'global_atlas.stock_ohlcv', 'eem',  'iShares MSCI Emerging Markets ETF'),
            ('GOLD', 'etf', 'global_atlas.stock_ohlcv', 'gld',  'SPDR Gold Shares — gold numéraire benchmark')
    """)

    # ------------------------------------------------------------------
    # Seed Global-calibrated thresholds
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO global_atlas.atlas_thresholds
            (threshold_key, threshold_value, category, description, units, min_allowed, max_allowed, default_value)
        VALUES
            -- Quintile boundaries (equal-split of 30 instruments)
            ('rs_q1_min_pctile', 0.80, 'rs', 'Top 20% = Q1 (Overweight)', 'ratio', 0.70, 0.90, 0.80),
            ('rs_q2_min_pctile', 0.60, 'rs', 'Top 20-40% = Q2',           'ratio', 0.50, 0.80, 0.60),
            ('rs_q4_max_pctile', 0.40, 'rs', 'Bottom 40-60% = Q4',        'ratio', 0.20, 0.50, 0.40),
            ('rs_q5_max_pctile', 0.20, 'rs', 'Bottom 20% = Q5 (Underweight)', 'ratio', 0.10, 0.30, 0.20),

            -- Consensus thresholds (same structure as US but 20 cells)
            ('rs_consensus_t1_min', 16, 'rs', 'Min bullish cell count for top conviction', 'count', 14, 20, 16),
            ('rs_consensus_t2_min', 12, 'rs', 'Min bullish cell count for T2',             'count', 10, 16, 12),

            -- Global regime thresholds (VT realized vol, no VIX)
            ('breadth_healthy_min',       0.60, 'regime', '% countries above 200DMA for healthy global market', 'ratio', 0.40, 0.80, 0.60),
            ('breadth_caution_min',       0.40, 'regime', '% countries above 200DMA for caution zone',          'ratio', 0.20, 0.60, 0.40),
            ('dislocation_vol_multiplier', 2.0, 'regime', 'VT vol spike multiplier for dislocation override',   'ratio', 1.5,  3.0,  2.0),

            -- History gate (shorter OK — country ETFs have clean history since 2008)
            ('history_gate_min_days', 252, 'gate', 'Minimum trading days required for country ETF', 'days', 126, 504, 252)
    """)

    # ------------------------------------------------------------------
    # Seed the 30 country ETF universe
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO global_atlas.atlas_universe_etfs
            (ticker, country, region, is_developed_market)
        VALUES
            -- Americas
            ('spy',  'United States',   'Americas',          TRUE),
            ('ewc',  'Canada',          'Americas',          TRUE),
            ('ewz',  'Brazil',          'Americas',          FALSE),
            ('eww',  'Mexico',          'Americas',          FALSE),
            ('ech',  'Chile',           'Americas',          FALSE),
            -- Europe Developed
            ('ewg',  'Germany',         'Europe Developed',  TRUE),
            ('ewu',  'United Kingdom',  'Europe Developed',  TRUE),
            ('ewq',  'France',          'Europe Developed',  TRUE),
            ('ewn',  'Netherlands',     'Europe Developed',  TRUE),
            ('ewi',  'Italy',           'Europe Developed',  TRUE),
            ('ewp',  'Spain',           'Europe Developed',  TRUE),
            ('ewd',  'Sweden',          'Europe Developed',  TRUE),
            -- Asia-Pacific Developed
            ('ewj',  'Japan',           'Asia-Pacific DM',   TRUE),
            ('ewa',  'Australia',       'Asia-Pacific DM',   TRUE),
            ('ewh',  'Hong Kong',       'Asia-Pacific DM',   TRUE),
            ('ews',  'Singapore',       'Asia-Pacific DM',   TRUE),
            -- Asia Emerging
            ('inda', 'India',           'Asia Emerging',     FALSE),
            ('mchi', 'China',           'Asia Emerging',     FALSE),
            ('ewy',  'South Korea',     'Asia Emerging',     FALSE),
            ('ewt',  'Taiwan',          'Asia Emerging',     FALSE),
            ('ephe', 'Philippines',     'Asia Emerging',     FALSE),
            ('eido', 'Indonesia',       'Asia Emerging',     FALSE),
            ('thd',  'Thailand',        'Asia Emerging',     FALSE),
            ('vnm',  'Vietnam',         'Asia Emerging',     FALSE),
            -- Other Emerging
            ('eza',  'South Africa',    'Other Emerging',    FALSE),
            ('ksa',  'Saudi Arabia',    'Other Emerging',    FALSE),
            ('uae',  'UAE',             'Other Emerging',    FALSE),
            ('tur',  'Turkey',          'Other Emerging',    FALSE)
    """)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS global_atlas CASCADE")

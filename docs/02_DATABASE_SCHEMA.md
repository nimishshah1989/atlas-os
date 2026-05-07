# Atlas — Database Schema

**Document:** 02_DATABASE_SCHEMA
**Status:** v0
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**References:**
- `00_METHODOLOGY_LOCK.md` (defines what gets stored)
- `01_BACKEND_ARCHITECTURE.md` (defines naming/typing/indexing conventions)

---

## Purpose of This Document

Every Atlas table, every column, every type, every index, every constraint. This is the document Claude Code reads when writing CREATE TABLE migrations.

If a table is not defined here, it is not part of v0. If a column is not defined here, it is not part of v0. The schema is closed unless this document is updated through a methodology revision.

---

## 1. Schema Organization

All Atlas tables live in the `atlas` schema. Tables are organized into five categories:

| Category | Purpose | Refresh Cadence |
|---|---|---|
| Reference | Universe locks, masters, mappings | Quarterly (universe), one-time at M1 (others) |
| Computed Metrics | Numeric primitive values per instrument per date | Nightly |
| Computed States | Categorical state labels per instrument per date | Nightly |
| Decisions | Investability, entry, exit signals | Nightly |
| Operational | Run logs, quarantine, validation artifacts | Per nightly run |

Naming follows `01_BACKEND_ARCHITECTURE.md` Section 3.1.

---

## 2. Reference Tables (Layer 2)

Reference tables hold slow-changing master data. Locked at Atlas-M1 from current snapshots of JIP Data Core; refreshed quarterly for universe membership.

### 2.1 `atlas_universe_stocks`

Locked list of 750 stocks Atlas operates on, with tier classification.

```sql
CREATE TABLE atlas.atlas_universe_stocks (
    instrument_id          UUID            NOT NULL,
    symbol                 VARCHAR(32)     NOT NULL,
    company_name           VARCHAR(256),
    tier                   VARCHAR(8)      NOT NULL,           -- 'Large' | 'Mid' | 'Small' | 'Micro'
    sector                 VARCHAR(64)     NOT NULL,           -- from de_instrument.sector
    industry               VARCHAR(128),                       -- from de_instrument.industry
    in_nifty_50            BOOLEAN         NOT NULL DEFAULT FALSE,
    in_nifty_100           BOOLEAN         NOT NULL DEFAULT FALSE,
    in_nifty_500           BOOLEAN         NOT NULL DEFAULT FALSE,
    listing_date           DATE,
    effective_from         DATE            NOT NULL,
    effective_to           DATE,                               -- NULL = currently active
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (instrument_id, effective_from)
);

CREATE INDEX idx_universe_stocks_tier ON atlas.atlas_universe_stocks (tier) WHERE effective_to IS NULL;
CREATE INDEX idx_universe_stocks_sector ON atlas.atlas_universe_stocks (sector) WHERE effective_to IS NULL;
CREATE INDEX idx_universe_stocks_active ON atlas.atlas_universe_stocks (instrument_id) WHERE effective_to IS NULL;
```

**Notes:**
- Composite primary key allows membership history (slowly-changing dimension type 2)
- `effective_to IS NULL` means the row represents current membership
- Quarterly refresh closes old rows (sets `effective_to`) and inserts new rows
- v0 starts with all rows having `effective_from` = M1 lock date

### 2.2 `atlas_universe_etfs`

Locked list of 100 ETFs.

```sql
CREATE TABLE atlas.atlas_universe_etfs (
    ticker                 VARCHAR(32)     NOT NULL,
    isin                   VARCHAR(16),
    fund_house             VARCHAR(128),
    etf_name               VARCHAR(256),
    theme                  VARCHAR(16)     NOT NULL,           -- 'Broad' | 'Sectoral' | 'Thematic'
    linked_sector          VARCHAR(64),                        -- For Sectoral; references atlas_sector_master.sector_name
    linked_index           VARCHAR(32),                        -- Underlying index code if applicable
    asset_class            VARCHAR(32),                        -- 'Equity' | 'Gold' | 'Silver' | 'Debt' | 'International'
    inception_date         DATE,
    effective_from         DATE            NOT NULL,
    effective_to           DATE,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, effective_from)
);

CREATE INDEX idx_universe_etfs_theme ON atlas.atlas_universe_etfs (theme) WHERE effective_to IS NULL;
CREATE INDEX idx_universe_etfs_active ON atlas.atlas_universe_etfs (ticker) WHERE effective_to IS NULL;
```

### 2.3 `atlas_universe_indices`

Curated list of ~75 NSE indices.

```sql
CREATE TABLE atlas.atlas_universe_indices (
    index_code             VARCHAR(32)     NOT NULL,
    index_name             VARCHAR(128)    NOT NULL,
    role                   VARCHAR(16)     NOT NULL,           -- 'broad' | 'sectoral' | 'industry' | 'factor' | 'thematic'
    linked_sector          VARCHAR(64),                        -- For sectoral indices; references atlas_sector_master
    inception_date         DATE,
    effective_from         DATE            NOT NULL,
    effective_to           DATE,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (index_code, effective_from)
);

CREATE INDEX idx_universe_indices_role ON atlas.atlas_universe_indices (role) WHERE effective_to IS NULL;
CREATE INDEX idx_universe_indices_active ON atlas.atlas_universe_indices (index_code) WHERE effective_to IS NULL;
```

### 2.4 `atlas_universe_funds`

Locked list of ~400 mutual funds.

```sql
CREATE TABLE atlas.atlas_universe_funds (
    mstar_id               VARCHAR(32)     NOT NULL,
    scheme_name            VARCHAR(256)    NOT NULL,
    amc                    VARCHAR(128),
    broad_category         VARCHAR(32)     NOT NULL,           -- 'Equity'
    category_name          VARCHAR(64)     NOT NULL,           -- 'Large Cap' | 'Mid Cap' | etc.
    plan_type              VARCHAR(16)     NOT NULL DEFAULT 'Regular',
    option_type            VARCHAR(16)     NOT NULL DEFAULT 'Growth',
    benchmark_code         VARCHAR(32),                        -- references atlas_benchmark_master
    inception_date         DATE,
    effective_from         DATE            NOT NULL,
    effective_to           DATE,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (mstar_id, effective_from)
);

CREATE INDEX idx_universe_funds_category ON atlas.atlas_universe_funds (category_name) WHERE effective_to IS NULL;
CREATE INDEX idx_universe_funds_active ON atlas.atlas_universe_funds (mstar_id) WHERE effective_to IS NULL;
```

### 2.5 `atlas_sector_master`

The locked NSE sector taxonomy. Output of Atlas-M1 query against `de_instrument.sector`.

```sql
CREATE TABLE atlas.atlas_sector_master (
    sector_name            VARCHAR(64)     NOT NULL PRIMARY KEY,
    primary_nse_index      VARCHAR(32),                        -- e.g. 'NIFTY BANK' for Bank sector
    secondary_nse_indices  TEXT[],                             -- Array of additional related indices
    fallback_benchmark     VARCHAR(32)     NOT NULL DEFAULT 'NIFTY 500',
    notes                  TEXT,
    is_active              BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
```

**Notes:**
- Populated from `de_sector_mapping` in JIP Data Core during Atlas-M1
- Expected ~20 rows
- `primary_nse_index` is the top-down benchmark for that sector's state computation
- Sectors without a dedicated NSE sectoral index have NULL `primary_nse_index` and use `fallback_benchmark`

### 2.6 `atlas_benchmark_master`

The five user benchmarks plus the four tier benchmarks plus gold.

```sql
CREATE TABLE atlas.atlas_benchmark_master (
    benchmark_code         VARCHAR(32)     NOT NULL PRIMARY KEY,
    benchmark_name         VARCHAR(128)    NOT NULL,
    benchmark_type         VARCHAR(16)     NOT NULL,           -- 'user' | 'tier' | 'sector' | 'numeraire'
    source_table           VARCHAR(64)     NOT NULL,           -- e.g. 'de_index_prices', 'de_global_prices', 'de_etf_ohlcv'
    source_identifier      VARCHAR(64)     NOT NULL,           -- The identifier value to look up in source_table
    description            TEXT,
    is_active              BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
```

**Expected rows (~10):**

| benchmark_code | benchmark_type | source_table | source_identifier |
|---|---|---|---|
| NIFTY50 | user | de_index_prices | NIFTY 50 |
| NIFTY500 | user | de_index_prices | NIFTY 500 |
| MSCIWORLD | user | de_global_prices | URTH |
| SP500 | user | de_global_prices | ^GSPC |
| GOLD | user/numeraire | de_etf_ohlcv | GOLDBEES |
| NIFTY100 | tier | de_index_prices | NIFTY 100 |
| MIDCAP150 | tier | de_index_prices | NIFTY MIDCAP 150 |
| SMALLCAP250 | tier | de_index_prices | NIFTY SMALLCAP 250 |
| MICROCAP_CUSTOM | tier | atlas_index_metrics_daily | MICROCAP_CUSTOM |

The MICROCAP_CUSTOM is constructed by Atlas as an equal-weighted index of 250 microcap names.

### 2.7 `atlas_fund_category_benchmark_map`

Mapping of fund categories to category benchmarks for NAV state computation.

```sql
CREATE TABLE atlas.atlas_fund_category_benchmark_map (
    category_name          VARCHAR(64)     NOT NULL PRIMARY KEY,
    benchmark_code         VARCHAR(32)     NOT NULL REFERENCES atlas.atlas_benchmark_master(benchmark_code),
    notes                  TEXT,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
```

**Expected rows (8-10):**

| category_name | benchmark_code |
|---|---|
| Large Cap | NIFTY100 |
| Large & Midcap | NIFTY200 |
| Mid Cap | MIDCAP150 |
| Small Cap | SMALLCAP250 |
| Multi Cap | NIFTY500 |
| Flexi Cap | NIFTY500 |
| ELSS | NIFTY500 |
| Sectoral / Thematic | (per-fund mapping in atlas_universe_funds.benchmark_code) |

---

## 3. Computed Metrics Tables (Layer 3)

Numeric metric values per instrument per date. The "what we measured" tables.

### 3.1 `atlas_stock_metrics_daily`

Per stock per day, all primitive numeric values.

```sql
CREATE TABLE atlas.atlas_stock_metrics_daily (
    instrument_id          UUID            NOT NULL,
    date                   DATE            NOT NULL,
    
    -- Returns (decimal, not percent — e.g. 0.05 = 5%)
    ret_1d                 NUMERIC(10,4),
    ret_1w                 NUMERIC(10,4),
    ret_1m                 NUMERIC(10,4),
    ret_3m                 NUMERIC(10,4),
    ret_6m                 NUMERIC(10,4),
    ret_12m                NUMERIC(10,4),
    ret_12m_1m             NUMERIC(10,4),                      -- 12M skip-month variant
    
    -- Relative Strength against tier benchmark (decimal)
    rs_1w_tier             NUMERIC(10,4),
    rs_1m_tier             NUMERIC(10,4),
    rs_3m_tier             NUMERIC(10,4),
    rs_6m_tier             NUMERIC(10,4),
    rs_12m_tier            NUMERIC(10,4),
    
    -- RS against Nifty 500 (the broad-market reference)
    rs_1w_nifty500         NUMERIC(10,4),
    rs_1m_nifty500         NUMERIC(10,4),
    rs_3m_nifty500         NUMERIC(10,4),
    
    -- Tier-relative RS percentile rank (0.0–1.0)
    rs_pctile_1w           NUMERIC(10,4),
    rs_pctile_1m           NUMERIC(10,4),
    rs_pctile_3m           NUMERIC(10,4),
    
    -- RS Momentum components (Bhaven's EMA-ratio approach)
    ema_10_stock           NUMERIC(18,4),
    ema_20_stock           NUMERIC(18,4),
    ema_50_stock           NUMERIC(18,4),                      -- For pct_above_ema_50 breadth (methodology 11.1)
    ema_10_benchmark       NUMERIC(18,4),
    ema_20_benchmark       NUMERIC(18,4),
    ema_10_ratio           NUMERIC(10,4),                      -- ema_10_stock / ema_10_benchmark
    ema_20_ratio           NUMERIC(10,4),
    ema_10_at_20d_high     BOOLEAN,                            -- For Accelerating state
    ema_10_at_20d_low      BOOLEAN,                            -- For Collapsing state

    -- Risk components
    extension_pct          NUMERIC(10,4),                      -- (close - ema_200) / ema_200
    ema_200_stock          NUMERIC(18,4),
    vol_ratio_63           NUMERIC(10,4),
    realized_vol_63        NUMERIC(10,4),
    drawdown_ratio_252     NUMERIC(10,4),
    max_drawdown_252       NUMERIC(10,4),
    atr_21                 NUMERIC(18,4),                      -- 21-period ATR (methodology 13.4 exit trigger 6)
    
    -- Volume components
    volume_expansion       NUMERIC(10,4),                      -- avg_volume_20 / avg_volume_252
    avg_volume_20          BIGINT,
    avg_volume_252         BIGINT,
    effort_ratio_63        NUMERIC(10,4),
    
    -- Weinstein gate
    above_30w_ma           BOOLEAN,                            -- price > 30-week MA
    ma_30w_slope_4w        NUMERIC(10,4),                      -- 30-week MA slope, last 4 weeks (in σ units)
    weinstein_gate_pass    BOOLEAN,                            -- Both conditions for "strong" classification
    
    -- Stage-1 base detection
    stage1_base_qualifies  BOOLEAN,                            -- For Emerging classification eligibility
    
    -- Numéraire variant — Gold-denominated RS values
    rs_1w_tier_gold        NUMERIC(10,4),
    rs_1m_tier_gold        NUMERIC(10,4),
    rs_3m_tier_gold        NUMERIC(10,4),
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (instrument_id, date)
);

CREATE INDEX idx_stock_metrics_date ON atlas.atlas_stock_metrics_daily (date, instrument_id);
CREATE INDEX idx_stock_metrics_run ON atlas.atlas_stock_metrics_daily (compute_run_id);
```

**Notes:**
- 50+ columns; this is the widest computed table by design (raw primitive values)
- All numerics stored as decimals (not percentages)
- Bhaven's EMA-ratio momentum stored as raw EMAs plus the computed ratios for traceability
- Weinstein gate components stored separately so we can audit why a stock did/didn't pass
- Gold numéraire variant for the three classification windows; full INR variant always present
- `ema_50_stock` is required for the `pct_above_ema_50` breadth measure used by the
  market regime classifier (methodology 11.1). Stored at stock grain so M3 reads
  directly without recomputation.
- `atr_21` is the 21-period Average True Range, used by methodology 13.4 exit trigger
  6 (the per-position stop loss). Computed once per stock per day; the M5 decision
  engine reads it.

### 3.2 `atlas_etf_metrics_daily`

Same structure as `atlas_stock_metrics_daily` minus volume primitive details (volume is informational for ETFs).

```sql
CREATE TABLE atlas.atlas_etf_metrics_daily (
    ticker                 VARCHAR(32)     NOT NULL,
    date                   DATE            NOT NULL,
    
    -- Returns
    ret_1d                 NUMERIC(10,4),
    ret_1w                 NUMERIC(10,4),
    ret_1m                 NUMERIC(10,4),
    ret_3m                 NUMERIC(10,4),
    ret_6m                 NUMERIC(10,4),
    ret_12m                NUMERIC(10,4),
    
    -- Relative Strength (against theme-appropriate benchmark)
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
);

CREATE INDEX idx_etf_metrics_date ON atlas.atlas_etf_metrics_daily (date, ticker);
CREATE INDEX idx_etf_metrics_run ON atlas.atlas_etf_metrics_daily (compute_run_id);
```

### 3.3 `atlas_index_metrics_daily`

Index-level metrics. No states — indices aren't classified.

```sql
CREATE TABLE atlas.atlas_index_metrics_daily (
    index_code             VARCHAR(32)     NOT NULL,
    date                   DATE            NOT NULL,
    
    -- Returns
    ret_1d                 NUMERIC(10,4),
    ret_1w                 NUMERIC(10,4),
    ret_1m                 NUMERIC(10,4),
    ret_3m                 NUMERIC(10,4),
    ret_6m                 NUMERIC(10,4),
    ret_12m                NUMERIC(10,4),
    
    -- RS vs Nifty 500
    rs_1w_nifty500         NUMERIC(10,4),
    rs_1m_nifty500         NUMERIC(10,4),
    rs_3m_nifty500         NUMERIC(10,4),
    
    -- Momentum (for sector top-down state derivation)
    ema_10_index           NUMERIC(18,4),
    ema_20_index           NUMERIC(18,4),
    ema_10_ratio_nifty500  NUMERIC(10,4),
    ema_20_ratio_nifty500  NUMERIC(10,4),
    
    -- Volatility metrics
    realized_vol_63        NUMERIC(10,4),
    realized_vol_5d        NUMERIC(10,4),                      -- For dislocation override
    vol_252_median         NUMERIC(10,4),                      -- For dislocation override threshold
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (index_code, date)
);

CREATE INDEX idx_index_metrics_date ON atlas.atlas_index_metrics_daily (date, index_code);
CREATE INDEX idx_index_metrics_run ON atlas.atlas_index_metrics_daily (compute_run_id);
```

### 3.4 `atlas_sector_metrics_daily`

Sector aggregations — bottom-up plus top-down side-by-side.

```sql
CREATE TABLE atlas.atlas_sector_metrics_daily (
    sector_name            VARCHAR(64)     NOT NULL,
    date                   DATE            NOT NULL,
    
    -- Bottom-up aggregations (market-cap-weighted)
    bottomup_ret_1m        NUMERIC(10,4),
    bottomup_ret_3m        NUMERIC(10,4),
    bottomup_ret_6m        NUMERIC(10,4),
    bottomup_rs_3m_nifty500 NUMERIC(10,4),
    bottomup_ema_10_ratio  NUMERIC(10,4),
    bottomup_ema_20_ratio  NUMERIC(10,4),
    
    -- Top-down (NSE sectoral index, where available)
    topdown_index_code     VARCHAR(32),                        -- e.g. 'NIFTY BANK'; NULL if no index
    topdown_ret_1m         NUMERIC(10,4),
    topdown_ret_3m         NUMERIC(10,4),
    topdown_rs_3m_nifty500 NUMERIC(10,4),
    
    -- Breadth measures
    constituent_count      INTEGER,                            -- Stocks in sector (in our universe)
    participation_50       NUMERIC(10,4),                      -- % above 50-day MA
    participation_rs       NUMERIC(10,4),                      -- % in {Leader, Strong, Emerging}
    leadership_concentration NUMERIC(10,4),                    -- top 5 by RS_3M as % of sector market cap
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sector_name, date)
);

CREATE INDEX idx_sector_metrics_date ON atlas.atlas_sector_metrics_daily (date, sector_name);
```

### 3.5 `atlas_market_regime_daily`

One row per trading day. The market-level state. Captures four families of breadth measures (MA breadth, A/D breadth, new highs/lows, strength breadth) plus trend and volatility inputs.

```sql
CREATE TABLE atlas.atlas_market_regime_daily (
    date                   DATE            NOT NULL PRIMARY KEY,
    
    -- Trend inputs (using EMAs for consistency with Bhaven's anchor)
    nifty500_close         NUMERIC(18,4),
    nifty500_ema_50        NUMERIC(18,4),
    nifty500_ema_200       NUMERIC(18,4),
    nifty500_above_ema_50  BOOLEAN,
    nifty500_above_ema_200 BOOLEAN,
    nifty500_ema_50_slope  NUMERIC(10,4),                      -- 21-day slope (in σ units)
    nifty500_ema_200_slope NUMERIC(10,4),
    
    -- MA Breadth (Bhaven's primary anchor)
    pct_above_ema_20       NUMERIC(10,4),
    pct_above_ema_50       NUMERIC(10,4),
    pct_above_ema_200      NUMERIC(10,4),
    
    -- A/D Breadth
    advances_count         INTEGER,                            -- Stocks where close > prev close
    declines_count         INTEGER,                            -- Stocks where close < prev close
    unchanged_count        INTEGER,                            -- Stocks where close == prev close
    ad_ratio               NUMERIC(10,4),                      -- advances ÷ max(declines, 1)
    ad_line                NUMERIC(18,4),                      -- Cumulative net advances
    ad_line_slope_21       NUMERIC(10,4),                      -- 21-day slope of A/D line
    mcclellan_oscillator   NUMERIC(10,4),                      -- EMA(net_advances, 19) − EMA(net_advances, 39)
    mcclellan_summation    NUMERIC(18,4),                      -- Cumulative McClellan Oscillator
    
    -- New Highs/Lows Breadth
    new_52w_highs          INTEGER,                            -- Stocks at 252-day rolling high
    new_52w_lows           INTEGER,                            -- Stocks at 252-day rolling low
    net_new_highs          INTEGER,                            -- new_52w_highs − new_52w_lows
    new_high_low_ratio     NUMERIC(10,4),                      -- new_52w_highs ÷ max(new_52w_lows, 1)
    
    -- Strength Breadth (Atlas-specific)
    pct_in_strong_states   NUMERIC(10,4),                      -- % in {Leader, Strong, Emerging}
    pct_weinstein_pass     NUMERIC(10,4),                      -- % passing Weinstein gate
    
    -- Volatility inputs
    india_vix              NUMERIC(10,4),
    realized_vol_5d_nifty500 NUMERIC(10,4),
    vol_252_median_nifty500 NUMERIC(10,4),
    
    -- Computed regime state
    regime_state           VARCHAR(16)     NOT NULL,           -- 'Risk-On' | 'Constructive' | 'Cautious' | 'Risk-Off' | 'DISLOCATION_SUSPENDED'
    deployment_multiplier  NUMERIC(10,4)   NOT NULL,           -- 1.0 | 0.7 | 0.4 | 0.0
    
    -- Dislocation override
    dislocation_active     BOOLEAN         NOT NULL DEFAULT FALSE,
    dislocation_started    DATE,
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_market_regime_state ON atlas.atlas_market_regime_daily (regime_state, date);
```

**Notes:**
- Velocity (1M change, 3M change of any breadth measure) is computed on read via SQL window functions, not stored
- All technical indicators (EMAs, McClellan) computed using `pandas-ta` per architecture Section 5.5
- 28 columns total — comprehensive but no compute waste; each column maps directly to a methodology requirement

### 3.6 `atlas_fund_metrics_daily`

Daily-refreshed fund metrics (Lens 1 inputs).

```sql
CREATE TABLE atlas.atlas_fund_metrics_daily (
    mstar_id               VARCHAR(32)     NOT NULL,
    nav_date               DATE            NOT NULL,
    
    -- NAV-derived returns (Lens 1)
    nav                    NUMERIC(18,4),
    ret_1m                 NUMERIC(10,4),
    ret_3m                 NUMERIC(10,4),
    ret_6m                 NUMERIC(10,4),
    ret_12m                NUMERIC(10,4),
    
    -- RS against category benchmark
    rs_1m_category         NUMERIC(10,4),
    rs_3m_category         NUMERIC(10,4),
    rs_6m_category         NUMERIC(10,4),
    rs_pctile_1m           NUMERIC(10,4),
    rs_pctile_3m           NUMERIC(10,4),
    rs_pctile_6m           NUMERIC(10,4),
    
    -- Risk metrics (NAV-based)
    realized_vol_63        NUMERIC(10,4),
    drawdown_ratio_252     NUMERIC(10,4),
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (mstar_id, nav_date)
);

CREATE INDEX idx_fund_metrics_date ON atlas.atlas_fund_metrics_daily (nav_date, mstar_id);
```

### 3.7 `atlas_fund_lens_monthly`

Monthly-refreshed Lens 2 (composition) and Lens 3 (holdings) values.

```sql
CREATE TABLE atlas.atlas_fund_lens_monthly (
    mstar_id               VARCHAR(32)     NOT NULL,
    as_of_date             DATE            NOT NULL,           -- Holdings disclosure date
    
    -- Lens 2: Sector composition
    aligned_aum_pct        NUMERIC(10,4),                      -- AUM in {Overweight, Neutral} sectors
    avoid_aum_pct          NUMERIC(10,4),                      -- AUM in {Avoid} sectors
    sector_concentration   NUMERIC(10,4),                      -- Top 3 sectors as % of AUM
    
    -- Lens 3: Holdings quality
    strong_aum_pct         NUMERIC(10,4),                      -- AUM in {Leader, Strong, Emerging} stocks
    weak_aum_pct           NUMERIC(10,4),                      -- AUM in {Weak, Laggard} stocks
    unknown_aum_pct        NUMERIC(10,4),                      -- AUM in stocks outside our universe
    holdings_concentration NUMERIC(10,4),                      -- Top 10 holdings as % of AUM
    
    -- Lag tracking (Morningstar discloses with delay)
    last_disclosed_date    DATE,                               -- Actual disclosure publish date
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (mstar_id, as_of_date)
);

CREATE INDEX idx_fund_lens_date ON atlas.atlas_fund_lens_monthly (as_of_date, mstar_id);
```

---

## 4. Computed States Tables (Layer 3)

Categorical state labels per instrument per date. The "what we concluded" tables.

### 4.1 `atlas_stock_states_daily`

```sql
CREATE TABLE atlas.atlas_stock_states_daily (
    instrument_id          UUID            NOT NULL,
    date                   DATE            NOT NULL,
    
    -- The four primitive states
    rs_state               VARCHAR(16)     NOT NULL,           -- 'Leader' | 'Strong' | 'Consolidating' | 'Emerging' | 'Average' | 'Weak' | 'Laggard' | 'INSUFFICIENT_HISTORY' | 'ILLIQUID' | 'DISLOCATION_SUSPENDED'
    momentum_state         VARCHAR(16)     NOT NULL,           -- 'Accelerating' | 'Improving' | 'Flat' | 'Deteriorating' | 'Collapsing' | (suspended states)
    risk_state             VARCHAR(16)     NOT NULL,           -- 'Low' | 'Normal' | 'Elevated' | 'High' | 'Below Trend'
    volume_state           VARCHAR(16)     NOT NULL,           -- 'Accumulation' | 'Steady-Buying' | 'Neutral' | 'Distribution' | 'Heavy Distribution'
    
    -- Gates and qualifiers
    history_gate_pass      BOOLEAN         NOT NULL,
    liquidity_gate_pass    BOOLEAN         NOT NULL,
    weinstein_gate_pass    BOOLEAN         NOT NULL,
    stage1_base_qualifies  BOOLEAN         NOT NULL,
    
    -- Sector context (denormalized for query speed)
    sector                 VARCHAR(64),
    tier                   VARCHAR(8),
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (instrument_id, date)
);

CREATE INDEX idx_stock_states_date ON atlas.atlas_stock_states_daily (date, instrument_id);
CREATE INDEX idx_stock_states_rs ON atlas.atlas_stock_states_daily (date, rs_state);
CREATE INDEX idx_stock_states_sector ON atlas.atlas_stock_states_daily (date, sector);
CREATE INDEX idx_stock_states_run ON atlas.atlas_stock_states_daily (compute_run_id);
```

**Notes:**
- States stored as VARCHAR (not enum) — enums are painful to migrate when state set evolves
- Sector and tier denormalized from `atlas_universe_stocks` for fast filtering without joins
- Three special "suspended" states all instrument states can take: `INSUFFICIENT_HISTORY`, `ILLIQUID`, `DISLOCATION_SUSPENDED` — these supersede the primitive state values

### 4.2 `atlas_etf_states_daily`

```sql
CREATE TABLE atlas.atlas_etf_states_daily (
    ticker                 VARCHAR(32)     NOT NULL,
    date                   DATE            NOT NULL,
    
    -- Three primitive states (no volume state in decision tuple)
    rs_state               VARCHAR(16)     NOT NULL,
    momentum_state         VARCHAR(16)     NOT NULL,
    risk_state             VARCHAR(16)     NOT NULL,
    volume_state           VARCHAR(16),                        -- Stored but informational only
    
    -- Gates
    history_gate_pass      BOOLEAN         NOT NULL,
    liquidity_gate_pass    BOOLEAN         NOT NULL,
    weinstein_gate_pass    BOOLEAN         NOT NULL,
    
    -- ETF context
    theme                  VARCHAR(16),
    linked_sector          VARCHAR(64),
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, date)
);

CREATE INDEX idx_etf_states_date ON atlas.atlas_etf_states_daily (date, ticker);
CREATE INDEX idx_etf_states_rs ON atlas.atlas_etf_states_daily (date, rs_state);
```

### 4.3 `atlas_sector_states_daily`

```sql
CREATE TABLE atlas.atlas_sector_states_daily (
    sector_name            VARCHAR(64)     NOT NULL,
    date                   DATE            NOT NULL,
    
    -- Sector state
    sector_state           VARCHAR(16)     NOT NULL,           -- 'Overweight' | 'Neutral' | 'Underweight' | 'Avoid'
    
    -- Bottom-up vs top-down
    bottomup_state         VARCHAR(16),                        -- Bottom-up classified state
    topdown_state          VARCHAR(16),                        -- Top-down (NSE index) classified state
    divergence_flag        BOOLEAN         NOT NULL DEFAULT FALSE,
    
    -- Reasoning denormalized for UI
    bottomup_rs_state      VARCHAR(16),
    bottomup_momentum_state VARCHAR(16),
    participation_rs_pct   NUMERIC(10,4),
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sector_name, date)
);

CREATE INDEX idx_sector_states_date ON atlas.atlas_sector_states_daily (date, sector_name);
```

### 4.4 `atlas_fund_states_daily`

```sql
CREATE TABLE atlas.atlas_fund_states_daily (
    mstar_id               VARCHAR(32)     NOT NULL,
    date                   DATE            NOT NULL,
    
    -- Three lens states
    nav_state              VARCHAR(20)     NOT NULL,           -- 'Leader NAV' | 'Strong NAV' | 'Emerging NAV' | 'Average NAV' | 'Weak NAV' | 'Laggard NAV' | (suspended)
    composition_state      VARCHAR(16)     NOT NULL,           -- 'Aligned' | 'Mixed' | 'Misaligned'
    holdings_state         VARCHAR(20)     NOT NULL,           -- 'Strong-Holdings' | 'Decent' | 'Weak-Holdings'
    
    -- Lens 1 daily; Lens 2/3 monthly — track refresh dates
    nav_state_as_of        DATE            NOT NULL,
    composition_as_of      DATE,
    holdings_as_of         DATE,
    
    -- Fund context
    category_name          VARCHAR(64),
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (mstar_id, date)
);

CREATE INDEX idx_fund_states_date ON atlas.atlas_fund_states_daily (date, mstar_id);
CREATE INDEX idx_fund_states_nav ON atlas.atlas_fund_states_daily (date, nav_state);
```

---

## 5. Decisions Tables (Layer 3)

Investability, entry, and exit signals. The "what to do" tables.

### 5.1 `atlas_stock_decisions_daily`

```sql
CREATE TABLE atlas.atlas_stock_decisions_daily (
    instrument_id          UUID            NOT NULL,
    date                   DATE            NOT NULL,
    
    -- Investability
    is_investable          BOOLEAN         NOT NULL,
    
    -- Gate breakdown (for UI traceability — "why did/didn't this pass")
    strength_gate          BOOLEAN         NOT NULL,
    direction_gate         BOOLEAN         NOT NULL,
    risk_gate              BOOLEAN         NOT NULL,
    volume_gate            BOOLEAN         NOT NULL,
    sector_gate            BOOLEAN         NOT NULL,
    market_gate            BOOLEAN         NOT NULL,
    
    -- Entry triggers (only meaningful when is_investable = TRUE)
    transition_trigger     BOOLEAN         NOT NULL DEFAULT FALSE,
    breakout_trigger       BOOLEAN         NOT NULL DEFAULT FALSE,
    proximity_pass         BOOLEAN,                            -- Within 5% of 20-EMA
    
    -- Position sizing
    position_size_pct      NUMERIC(10,4),                      -- base_size × market_mult × risk_mult
    market_multiplier      NUMERIC(10,4),
    risk_multiplier        NUMERIC(10,4),
    
    -- Exit triggers (six independent flags)
    exit_market_riskoff    BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_sector_avoid      BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_rs_deteriorate    BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_momentum_collapse BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_volume_distrib    BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_stop_loss         BOOLEAN         NOT NULL DEFAULT FALSE,
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (instrument_id, date)
);

CREATE INDEX idx_stock_decisions_investable ON atlas.atlas_stock_decisions_daily (date, is_investable) WHERE is_investable = TRUE;
CREATE INDEX idx_stock_decisions_entry ON atlas.atlas_stock_decisions_daily (date) WHERE transition_trigger = TRUE OR breakout_trigger = TRUE;
CREATE INDEX idx_stock_decisions_exit ON atlas.atlas_stock_decisions_daily (date) 
    WHERE exit_market_riskoff = TRUE OR exit_sector_avoid = TRUE OR exit_rs_deteriorate = TRUE 
       OR exit_momentum_collapse = TRUE OR exit_volume_distrib = TRUE OR exit_stop_loss = TRUE;
```

**Notes:**
- Each gate stored as separate boolean — enables UI to show "5 of 6 gates pass; failing on momentum"
- Exit triggers are independent flags, not exclusive — multiple can fire simultaneously
- Partial indexes for common queries: investable today, entry today, exit today

### 5.2 `atlas_etf_decisions_daily`

Similar to stocks but with 5 gates instead of 6 (no volume gate) and 5 exit triggers (no volume distribution exit).

```sql
CREATE TABLE atlas.atlas_etf_decisions_daily (
    ticker                 VARCHAR(32)     NOT NULL,
    date                   DATE            NOT NULL,
    
    is_investable          BOOLEAN         NOT NULL,
    
    -- Gates (5 — no volume gate)
    strength_gate          BOOLEAN         NOT NULL,
    direction_gate         BOOLEAN         NOT NULL,
    risk_gate              BOOLEAN         NOT NULL,
    sector_gate            BOOLEAN         NOT NULL,           -- For Sectoral/Thematic; always TRUE for Broad
    market_gate            BOOLEAN         NOT NULL,
    
    -- Entry triggers
    transition_trigger     BOOLEAN         NOT NULL DEFAULT FALSE,
    breakout_trigger       BOOLEAN         NOT NULL DEFAULT FALSE,
    proximity_pass         BOOLEAN,
    
    -- Position sizing
    position_size_pct      NUMERIC(10,4),
    market_multiplier      NUMERIC(10,4),
    risk_multiplier        NUMERIC(10,4),
    
    -- Exit triggers (5 — no volume distribution)
    exit_market_riskoff    BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_sector_avoid      BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_rs_deteriorate    BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_momentum_collapse BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_stop_loss         BOOLEAN         NOT NULL DEFAULT FALSE,
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, date)
);

CREATE INDEX idx_etf_decisions_investable ON atlas.atlas_etf_decisions_daily (date, is_investable) WHERE is_investable = TRUE;
```

### 5.3 `atlas_fund_decisions_daily`

Funds are not tactical — different decision structure.

```sql
CREATE TABLE atlas.atlas_fund_decisions_daily (
    mstar_id               VARCHAR(32)     NOT NULL,
    date                   DATE            NOT NULL,
    
    -- Recommendation (enumerated)
    recommendation         VARCHAR(32)     NOT NULL,           -- 'Recommended' | 'Hold' | 'Reduce' | 'Exit'
    
    -- Investability
    is_investable          BOOLEAN         NOT NULL,
    
    -- Gate breakdown
    performance_gate       BOOLEAN         NOT NULL,           -- nav_state ∈ {Leader, Strong, Emerging}
    sectors_gate           BOOLEAN         NOT NULL,           -- composition_state ∈ {Aligned, Mixed}
    stocks_gate            BOOLEAN         NOT NULL,           -- holdings_state ∈ {Strong-Holdings, Decent}
    market_gate            BOOLEAN         NOT NULL,
    
    -- Exit triggers (4 — lens-level: detect movement of individual lens states)
    exit_market_riskoff    BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_composition_misaligned BOOLEAN    NOT NULL DEFAULT FALSE,
    exit_holdings_weak     BOOLEAN         NOT NULL DEFAULT FALSE,
    exit_nav_deteriorate   BOOLEAN         NOT NULL DEFAULT FALSE,
    
    -- Recommendation transition triggers (4 — fire when overall recommendation changes week-over-week)
    entry_trigger          BOOLEAN         NOT NULL DEFAULT FALSE,  -- recommendation became Recommended this week
    exit_trigger           BOOLEAN         NOT NULL DEFAULT FALSE,  -- recommendation became Exit this week
    reduce_trigger         BOOLEAN         NOT NULL DEFAULT FALSE,  -- recommendation became Reduce this week
    add_trigger            BOOLEAN         NOT NULL DEFAULT FALSE,  -- recommendation upgraded but not yet Recommended
    
    -- Transition tracking
    last_week_recommendation VARCHAR(32),                            -- Previous week's recommendation; NULL on first week
    weeks_in_current_state INTEGER,                                  -- Consecutive weeks current recommendation has held
    
    -- Audit
    compute_run_id         UUID            NOT NULL,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (mstar_id, date)
);

CREATE INDEX idx_fund_decisions_recommended ON atlas.atlas_fund_decisions_daily (date, recommendation);
CREATE INDEX idx_fund_decisions_transitions ON atlas.atlas_fund_decisions_daily (date) 
    WHERE entry_trigger OR exit_trigger OR reduce_trigger OR add_trigger;
```

---

## 6. Operational Tables

### 6.1 `atlas_run_log`

One row per nightly run. Tracks execution metadata.

```sql
CREATE TABLE atlas.atlas_run_log (
    compute_run_id         UUID            NOT NULL PRIMARY KEY,
    business_date          DATE            NOT NULL,
    started_at             TIMESTAMPTZ     NOT NULL,
    completed_at           TIMESTAMPTZ,
    status                 VARCHAR(16)     NOT NULL,           -- 'RUNNING' | 'SUCCESS' | 'FAILED' | 'PARTIAL'
    
    -- Stage timings (in seconds)
    stage1_pre_check_sec   INTEGER,
    stage2_reference_sec   INTEGER,
    stage3_stock_etf_sec   INTEGER,
    stage4_index_sec       INTEGER,
    stage5_sector_sec      INTEGER,
    stage6_regime_sec      INTEGER,
    stage7_funds_sec       INTEGER,
    stage8_decisions_sec   INTEGER,
    stage9_validation_sec  INTEGER,
    
    -- Volume metrics
    rows_written_total     INTEGER,
    rows_quarantined_total INTEGER,
    
    -- Validation
    tier1_pass             BOOLEAN,
    tier2_pass             BOOLEAN,
    tier3_pass             BOOLEAN,
    tier4_pass             BOOLEAN,
    
    -- Failure tracking
    failure_stage          VARCHAR(32),
    failure_message        TEXT,
    
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_run_log_date ON atlas.atlas_run_log (business_date DESC);
CREATE INDEX idx_run_log_status ON atlas.atlas_run_log (status, business_date DESC);
```

### 6.2 `atlas_validation_results`

Per-tier validation results, one row per check.

```sql
CREATE TABLE atlas.atlas_validation_results (
    id                     SERIAL          PRIMARY KEY,
    compute_run_id         UUID            NOT NULL REFERENCES atlas.atlas_run_log(compute_run_id),
    business_date          DATE            NOT NULL,
    tier                   SMALLINT        NOT NULL,           -- 1, 2, 3, 4, 5
    check_name             VARCHAR(128)    NOT NULL,
    instrument_id          UUID,                               -- NULL for non-instrument-specific checks
    expected_value         TEXT,
    actual_value           TEXT,
    passed                 BOOLEAN         NOT NULL,
    deviation_pct          NUMERIC(10,4),                      -- For numeric checks
    notes                  TEXT,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_validation_run ON atlas.atlas_validation_results (compute_run_id);
CREATE INDEX idx_validation_failures ON atlas.atlas_validation_results (compute_run_id) WHERE passed = FALSE;
```

### 6.3 Quarantine Tables

One per major scope. Same structure for each.

```sql
CREATE TABLE atlas.atlas_stock_metrics_quarantine (
    id                     SERIAL          PRIMARY KEY,
    instrument_id          UUID,
    date                   DATE,
    error_type             VARCHAR(64)     NOT NULL,
    error_message          TEXT,
    raw_input              JSONB,                              -- Original input for debugging
    compute_run_id         UUID,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stock_quarantine_run ON atlas.atlas_stock_metrics_quarantine (compute_run_id);

-- Same structure for:
-- atlas_etf_metrics_quarantine
-- atlas_index_metrics_quarantine
-- atlas_sector_metrics_quarantine
-- atlas_fund_metrics_quarantine
```

### 6.4 `atlas_benchmark_returns_cache`

Working table — materialized once per run, used for RS calculations. Truncated and rebuilt at the start of each pipeline run.

```sql
CREATE TABLE atlas.atlas_benchmark_returns_cache (
    benchmark_code         VARCHAR(32)     NOT NULL,
    date                   DATE            NOT NULL,
    close                  NUMERIC(18,4)   NOT NULL,
    ret_1d                 NUMERIC(10,4),
    ret_1w                 NUMERIC(10,4),
    ret_1m                 NUMERIC(10,4),
    ret_3m                 NUMERIC(10,4),
    ret_6m                 NUMERIC(10,4),
    ret_12m                NUMERIC(10,4),
    ret_12m_1m             NUMERIC(10,4),
    ema_10                 NUMERIC(18,4),
    ema_20                 NUMERIC(18,4),
    realized_vol_63        NUMERIC(10,4),
    PRIMARY KEY (benchmark_code, date)
);

CREATE INDEX idx_benchmark_cache_date ON atlas.atlas_benchmark_returns_cache (date, benchmark_code);
```

### 6.5 `atlas_thresholds`

Tunable thresholds that drive classification logic. Read at the start of every compute run; never hardcoded in code. Per `04_THRESHOLD_CATALOG.md`.

```sql
CREATE TABLE atlas.atlas_thresholds (
    threshold_key          VARCHAR(64)     NOT NULL PRIMARY KEY,
    threshold_value        NUMERIC(18,6)   NOT NULL,
    category               VARCHAR(32)     NOT NULL,           -- 'rs' | 'momentum' | 'risk' | 'volume' | 'gate' | 'sector' | 'regime' | 'fund' | 'decision'
    description            TEXT            NOT NULL,
    methodology_section    VARCHAR(16),                        -- e.g. '7.1', '11.4'
    units                  VARCHAR(16),                        -- 'percent' | 'ratio' | 'sigma' | 'days' | 'inr' | 'pctile'
    min_allowed            NUMERIC(18,6)   NOT NULL,
    max_allowed            NUMERIC(18,6)   NOT NULL,
    default_value          NUMERIC(18,6)   NOT NULL,
    last_modified_by       VARCHAR(64)     NOT NULL DEFAULT 'system',
    last_modified_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    is_active              BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    
    CONSTRAINT chk_threshold_in_range 
        CHECK (threshold_value >= min_allowed AND threshold_value <= max_allowed),
    CONSTRAINT chk_threshold_default_in_range 
        CHECK (default_value >= min_allowed AND default_value <= max_allowed)
);

CREATE INDEX idx_thresholds_category ON atlas.atlas_thresholds (category) WHERE is_active = TRUE;
```

**Notes:**
- 35 rows total at v0, populated at Atlas-M1 from `04_THRESHOLD_CATALOG.md`
- `threshold_value` uses `NUMERIC(18,6)` for sufficient precision across all threshold types (percentages, ratios, sigma values, integer counts)
- `min_allowed`/`max_allowed` enforced at DB level — fund manager cannot save values outside the allowed range
- `category` indexed for fast filtering in the UI (show all RS-related thresholds, etc.)

### 6.6 `atlas_threshold_history`

Audit log of every threshold change. Append-only — historical record never modified.

```sql
CREATE TABLE atlas.atlas_threshold_history (
    id                     SERIAL          PRIMARY KEY,
    threshold_key          VARCHAR(64)     NOT NULL REFERENCES atlas.atlas_thresholds(threshold_key),
    old_value              NUMERIC(18,6),                      -- NULL for initial seed
    new_value              NUMERIC(18,6)   NOT NULL,
    changed_by             VARCHAR(64)     NOT NULL,
    changed_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    change_reason          TEXT,
    triggered_reclassify   BOOLEAN         NOT NULL DEFAULT FALSE,
    reclassify_run_id      UUID,                               -- References atlas_run_log if a reclassify was triggered
    
    -- Audit fields
    user_ip                INET,
    user_agent             TEXT
);

CREATE INDEX idx_threshold_history_key ON atlas.atlas_threshold_history (threshold_key, changed_at DESC);
CREATE INDEX idx_threshold_history_reclassify ON atlas.atlas_threshold_history (reclassify_run_id) WHERE reclassify_run_id IS NOT NULL;
```

**Notes:**
- Append-only — never UPDATE or DELETE; preserves complete tuning history
- `old_value` is NULL only for the very first row per threshold_key (the M1 seed insert)
- `triggered_reclassify` distinguishes a saved threshold change (no reclassify yet) from one that was actually applied
- `reclassify_run_id` links back to `atlas_run_log` for the run that re-classified states with this new threshold

---

## 7. Index Strategy Summary

| Pattern | Purpose |
|---|---|
| `(instrument_id, date)` PK | Primary access pattern: "give me this stock's history" |
| `(date, instrument_id)` secondary | Cross-section queries: "give me all stocks on this date" |
| `(date, <state>)` partial | "find all Leaders today" |
| `(date, sector)` | Sector-filtered cross-sections |
| `(compute_run_id)` | Run-level rollback / re-query |

Total indexes per metric/state/decision table: 3–4. Storage cost: ~15% of table size. Query speedup at v0 scale: 100x+.

**No additional indexes added speculatively.** Indexes added in v1 only when query profiling shows a specific pattern needs it.

---

## 8. Constraints and Foreign Keys

### 8.1 Foreign Keys

Atlas uses foreign keys conservatively. Reference table FKs are enforced; metric/state/decision tables avoid FK overhead at write time.

| Source | Target | Enforced? |
|---|---|---|
| atlas_universe_funds.benchmark_code | atlas_benchmark_master.benchmark_code | Yes |
| atlas_fund_category_benchmark_map.benchmark_code | atlas_benchmark_master.benchmark_code | Yes |
| atlas_universe_etfs.linked_sector | atlas_sector_master.sector_name | Yes |
| atlas_universe_indices.linked_sector | atlas_sector_master.sector_name | Yes |
| atlas_validation_results.compute_run_id | atlas_run_log.compute_run_id | Yes |

For computed tables (Layer 3), `instrument_id` is NOT a foreign key to `atlas_universe_stocks` — the universe table uses composite PK with effective dates, and FK enforcement here would block daily writes during quarterly universe updates.

### 8.2 Check Constraints

```sql
-- Tier values must be one of the four allowed
ALTER TABLE atlas.atlas_universe_stocks 
    ADD CONSTRAINT chk_tier 
    CHECK (tier IN ('Large', 'Mid', 'Small', 'Micro'));

-- ETF theme values
ALTER TABLE atlas.atlas_universe_etfs 
    ADD CONSTRAINT chk_theme 
    CHECK (theme IN ('Broad', 'Sectoral', 'Thematic'));

-- Run status values
ALTER TABLE atlas.atlas_run_log 
    ADD CONSTRAINT chk_status 
    CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED', 'PARTIAL'));

-- Regime state values
ALTER TABLE atlas.atlas_market_regime_daily 
    ADD CONSTRAINT chk_regime_state 
    CHECK (regime_state IN ('Risk-On', 'Constructive', 'Cautious', 'Risk-Off', 'DISLOCATION_SUSPENDED'));

-- Deployment multiplier in valid range
ALTER TABLE atlas.atlas_market_regime_daily 
    ADD CONSTRAINT chk_deployment_mult 
    CHECK (deployment_multiplier IN (0.0, 0.4, 0.7, 1.0));

-- Sector state values
ALTER TABLE atlas.atlas_sector_states_daily 
    ADD CONSTRAINT chk_sector_state 
    CHECK (sector_state IN ('Overweight', 'Neutral', 'Underweight', 'Avoid'));
```

State values for primitives (rs_state, momentum_state, etc.) are NOT enforced via CHECK constraints — the set may evolve and CHECK constraints are painful to migrate. Validation Tier 3 catches invalid values.

---

## 9. Migration Files

Schema changes ship as numbered SQL migrations in `migrations/`. Forward-only.

```
migrations/
├── 001_create_atlas_schema.sql              (CREATE SCHEMA atlas)
├── 002_create_universe_tables.sql           (Section 2.1–2.4)
├── 003_create_master_tables.sql             (Section 2.5–2.7)
├── 004_create_metric_tables.sql             (Section 3)
├── 005_create_state_tables.sql              (Section 4)
├── 006_create_decision_tables.sql           (Section 5)
├── 007_create_operational_tables.sql        (Section 6.1–6.4)
├── 008_create_threshold_tables.sql          (Section 6.5–6.6 — atlas_thresholds, atlas_threshold_history)
├── 009_create_indexes.sql                   (All indexes from Sections 2–6)
├── 010_create_constraints.sql               (Section 8)
└── 011_grant_role_permissions.sql           (atlas_writer, atlas_reader, atlas_admin)
```

Each migration is idempotent (uses `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`).

---

## 10. Total Schema Footprint

**Tables: 30**

| Category | Count | Tables |
|---|---|---|
| Reference | 7 | universe_stocks, universe_etfs, universe_indices, universe_funds, sector_master, benchmark_master, fund_category_benchmark_map |
| Computed metrics | 7 | stock_metrics_daily, etf_metrics_daily, index_metrics_daily, sector_metrics_daily, market_regime_daily, fund_metrics_daily, fund_lens_monthly |
| Computed states | 4 | stock_states_daily, etf_states_daily, sector_states_daily, fund_states_daily |
| Decisions | 3 | stock_decisions_daily, etf_decisions_daily, fund_decisions_daily |
| Configuration | 2 | thresholds, threshold_history |
| Operational | 7 | run_log, validation_results, benchmark_returns_cache, stock_metrics_quarantine, etf_metrics_quarantine, sector_metrics_quarantine, fund_metrics_quarantine |

**Storage estimate:** ~3.7 GB at 12-year scope. Threshold tables add < 1 MB.

---

## 11. Open Questions

1. **Sector denormalization in stock states** — currently denormalize `sector` and `tier` into `atlas_stock_states_daily` for query speed. Tradeoff: staleness if universe membership changes mid-quarter. Rationale: universe changes are quarterly, denormalization saves a join on every UI query.

2. **JSONB for raw_input in quarantine tables** — flexible but harder to query. Acceptable tradeoff for v0; can normalize specific fields later if quarantine queries become common.

3. **Does the Microcap custom benchmark belong in `atlas_index_metrics_daily` or its own table?** Current design: store as a special `index_code = 'MICROCAP_CUSTOM'` row in `atlas_index_metrics_daily`. Cleaner than a separate table.

---

**Document version:** 1.0
**Last updated:** 2026-05-04
**Next review:** Atlas-M1 completion — verify actual table footprints match estimates

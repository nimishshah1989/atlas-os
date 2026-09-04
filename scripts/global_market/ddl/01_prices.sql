-- 01_prices.sql — atlas_global price spine + corporate actions + nightly technicals.
-- Tables: ohlcv_daily, corporate_actions, technical_daily.
-- Plan: "Schema `atlas_global` — core tables" (ohlcv_daily, technical_daily) and
--       "Methodology spec §A" (returns / trend / RS / risk / liquidity metrics land in
--       technical_daily — the plan names no separate risk table, so the §A risk group lives here).
-- Requires 00_core.sql (instrument_master). Idempotent; no DROP; no function bodies.

-- ohlcv_daily — ONE table for stocks and ETFs. Calendar = DISTINCT date WHERE instrument_id = SPY.
-- close_adj (split-only) drives charts + trend technicals; close_tr (splits + dividends) drives
-- every return / RS / risk metric. open/high/low_adj are split-only too: ATR-14, IBS and
-- Bollinger need split-consistent H/L (India carries the same three columns).
CREATE TABLE IF NOT EXISTS atlas_global.ohlcv_daily (
    instrument_id      uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    date               date          NOT NULL,
    open               numeric(18,6),
    high               numeric(18,6),
    low                numeric(18,6),
    close              numeric(18,6),
    volume             bigint,
    open_adj           numeric(18,6),
    high_adj           numeric(18,6),
    low_adj            numeric(18,6),
    close_adj          numeric(18,6),                       -- split-only
    close_tr           numeric(18,6),                       -- total return (splits + dividends)
    trade_count        bigint,
    vwap               numeric(18,6),
    source             text          NOT NULL,              -- alpaca | stooq_csv (never mixed per instrument-day without --override)
    adjustment_source  text,                                -- provenance of close_adj/close_tr, e.g. alpaca_split+all, stooq_detected_split
    ingested_at        timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT ohlcv_daily_pkey PRIMARY KEY (instrument_id, date),
    CONSTRAINT chk_ohlcv_daily_source CHECK (source IN ('alpaca', 'stooq_csv')),
    CONSTRAINT chk_ohlcv_daily_volume CHECK (volume IS NULL OR volume >= 0)
);
CREATE INDEX IF NOT EXISTS ix_ohlcv_daily_date
    ON atlas_global.ohlcv_daily (date);

-- corporate_actions — splits / dividends / spin-offs / mergers by ex-date. A row with
-- source = 'derived_from_adjustment' is a rule-#0 exception that needs the FM's approval and is
-- visible as such here rather than hidden in a bar ratio.
CREATE TABLE IF NOT EXISTS atlas_global.corporate_actions (
    instrument_id  uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    ex_date        date          NOT NULL,
    action_type    text          NOT NULL,                  -- Alpaca event type: forward_split | reverse_split | cash_dividend | stock_dividend | spin_off | merger | …
    ratio          numeric(20,10),                          -- new shares per old share (splits / stock dividends); NULL for cash
    cash_amount    numeric(18,6),                           -- USD per share (cash dividends); NULL otherwise
    source         text          NOT NULL,
    ingested_at    timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT corporate_actions_pkey PRIMARY KEY (instrument_id, ex_date, action_type),
    CONSTRAINT chk_corporate_actions_source CHECK (source IN ('alpaca', 'derived_from_adjustment')),
    CONSTRAINT chk_corporate_actions_ratio CHECK (ratio IS NULL OR ratio > 0)
);
CREATE INDEX IF NOT EXISTS ix_corporate_actions_ex_date
    ON atlas_global.corporate_actions (ex_date);

-- technical_daily — nightly per-instrument metrics (India technical_daily shape, US windows).
-- Trading-session windows: 1w=5, 1m=21, 3m=63, 6m=126, 12m=252, 24m=504, 36m=756.
-- EMAs / ATR / Bollinger / RSI on close_adj; ret_* / rs_* / risk on close_tr.
-- rs_* is the RELATIVE form (1+r_i)/(1+r_b) − 1 (ADR-0002); peer = GICS-sector ETF for stocks,
-- taxonomy peer-group median for ETFs. Precision follows India (ret/rs numeric(16,8)).
CREATE TABLE IF NOT EXISTS atlas_global.technical_daily (
    instrument_id        uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    asset_class          text          NOT NULL,
    symbol               text          NOT NULL,
    date                 date          NOT NULL,
    -- trend structure (close_adj)
    ema_10               numeric(18,6),
    ema_13               numeric(18,6),
    ema_21               numeric(18,6),
    ema_34               numeric(18,6),
    ema_50               numeric(18,6),
    ema_200              numeric(18,6),
    above_ema_10         boolean,
    above_ema_13         boolean,
    above_ema_21         boolean,
    above_ema_34         boolean,
    above_ema_50         boolean,
    above_ema_200        boolean,
    rsi_2                numeric(12,6),
    rsi_14               numeric(12,6),
    atr_14               numeric(18,6),
    atr_14_pct           numeric(12,8),                     -- ATR-14 / close_adj
    bb_width             numeric(12,8),
    vol_ratio_30d        numeric(12,6),                     -- today's volume / SMA-30 volume
    vol_ratio_60d        numeric(12,6),
    pos_52w              numeric(8,4),                      -- 0–100 position in the 52-week range
    ibs                  numeric(8,6),                      -- internal bar strength
    -- returns (close_tr)
    ret_1d               numeric(16,8),
    ret_1w               numeric(16,8),
    ret_1m               numeric(16,8),
    ret_3m               numeric(16,8),
    ret_6m               numeric(16,8),
    ret_12m              numeric(16,8),
    ret_24m              numeric(16,8),
    ret_36m              numeric(16,8),
    ret_ytd              numeric(16,8),
    -- relative strength vs SPY and vs peer group (close_tr, relative form)
    rs_1w_spy            numeric(16,8),
    rs_1m_spy            numeric(16,8),
    rs_3m_spy            numeric(16,8),
    rs_6m_spy            numeric(16,8),
    rs_12m_spy           numeric(16,8),
    rs_24m_spy           numeric(16,8),
    rs_1w_peer           numeric(16,8),
    rs_1m_peer           numeric(16,8),
    rs_3m_peer           numeric(16,8),
    rs_6m_peer           numeric(16,8),
    rs_12m_peer          numeric(16,8),
    rs_24m_peer          numeric(16,8),
    -- liquidity (volume × close; the 60d median is the universe floor input)
    adv_usd_20d_mean     numeric(20,4),
    adv_usd_60d_median   numeric(20,4),
    zero_volume_days_60d integer,
    -- risk (close_tr; empyrical-reloaded; rf = FRED DTB3)
    vol_20d_ann          numeric(12,8),
    vol_63d_ann          numeric(12,8),
    vol_252d_ann         numeric(12,8),
    downside_dev_63d     numeric(12,8),
    mdd_12m              numeric(12,8),                     -- max drawdown, negative fraction
    mdd_36m              numeric(12,8),
    beta_spy_252         numeric(12,8),
    corr_spy_252         numeric(12,8),
    sharpe_12m           numeric(12,6),
    sortino_12m          numeric(12,6),
    calmar_36m           numeric(12,6),
    compute_run_id       uuid,
    computed_at          timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT technical_daily_pkey PRIMARY KEY (instrument_id, date),
    CONSTRAINT chk_technical_daily_asset_class CHECK (asset_class IN ('stock', 'etf'))
);
CREATE INDEX IF NOT EXISTS ix_technical_daily_date
    ON atlas_global.technical_daily (date);
CREATE INDEX IF NOT EXISTS ix_technical_daily_class_date
    ON atlas_global.technical_daily (asset_class, date);

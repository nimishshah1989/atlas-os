-- Atlas clean data-foundation — STAGING schema.
-- Locked decision (docs/atlas-data-foundation.md §4): build on a clean staging
-- schema, validate to all-green, then cut over. NEVER mutate live de_*/atlas_*.
-- Decimal for money (numeric), tz-aware timestamps (timestamptz). Idempotent DDL.

create schema if not exists atlas_foundation;

-- ── Raw + adjusted stock OHLCV (NSE Bhavcopy sourced) ──────────────────────
create table if not exists atlas_foundation.ohlcv_stock (
    instrument_id uuid        not null,
    symbol        text        not null,
    date          date        not null,
    open          numeric(18,6),
    high          numeric(18,6),
    low           numeric(18,6),
    close         numeric(18,6),
    prev_close    numeric(18,6),
    open_adj      numeric(18,6),
    high_adj      numeric(18,6),
    low_adj       numeric(18,6),
    close_adj     numeric(18,6),
    adj_factor    numeric(20,10) not null default 1,
    volume        bigint,
    trades        integer,
    series        text,
    source        text        not null,
    ingested_at   timestamptz  not null default now(),
    primary key (instrument_id, date)
);
create index if not exists ix_fs_ohlcv_stock_symbol on atlas_foundation.ohlcv_stock (symbol, date);

-- ── ETF OHLCV ──────────────────────────────────────────────────────────────
create table if not exists atlas_foundation.ohlcv_etf (
    ticker      text not null,
    isin        text,
    date        date not null,
    open        numeric(18,6),
    high        numeric(18,6),
    low         numeric(18,6),
    close       numeric(18,6),
    close_adj   numeric(18,6),
    adj_factor  numeric(20,10) not null default 1,
    volume      bigint,
    source      text not null,
    ingested_at timestamptz not null default now(),
    primary key (ticker, date)
);

-- ── Index EOD prices ───────────────────────────────────────────────────────
create table if not exists atlas_foundation.index_prices (
    index_code  text not null,
    date        date not null,
    open        numeric(18,6),
    high        numeric(18,6),
    low         numeric(18,6),
    close       numeric(18,6),
    volume      bigint,
    source      text not null,
    ingested_at timestamptz not null default now(),
    primary key (index_code, date)
);

-- ── Corporate actions (drive deterministic back-adjustment) ────────────────
create table if not exists atlas_foundation.corp_action (
    instrument_id uuid not null,
    symbol        text not null,
    ex_date       date not null,
    action_type   text not null,            -- split | bonus | dividend | ...
    ratio         numeric(20,10) not null,  -- price multiplier on/after ex_date
    raw_text      text,
    source        text not null,
    ingested_at   timestamptz not null default now(),
    primary key (instrument_id, ex_date, action_type)
);

-- ── TA-Lib technicals (the metrics axis target) ───────────────────────────
create table if not exists atlas_foundation.technical_stock (
    instrument_id uuid not null,
    date          date not null,
    ema_21        numeric(18,6),
    ema_50        numeric(18,6),
    ema_200       numeric(18,6),
    rsi_14        numeric(12,6),
    ret_1d        numeric(16,8),
    ret_1w        numeric(16,8),
    ret_1m        numeric(16,8),
    ret_3m        numeric(16,8),
    ret_6m        numeric(16,8),
    ret_12m       numeric(16,8),
    rs_1d_n50     numeric(16,8),
    rs_1w_n50     numeric(16,8),
    rs_1m_n50     numeric(16,8),
    rs_3m_n50     numeric(16,8),
    rs_6m_n50     numeric(16,8),
    rs_12m_n50    numeric(16,8),
    rs_1d_n500    numeric(16,8),
    rs_1w_n500    numeric(16,8),
    rs_1m_n500    numeric(16,8),
    rs_3m_n500    numeric(16,8),
    rs_6m_n500    numeric(16,8),
    rs_12m_n500   numeric(16,8),
    above_ema_21  boolean,
    above_ema_50  boolean,
    above_ema_200 boolean,
    compute_run_id uuid,
    computed_at   timestamptz not null default now(),
    primary key (instrument_id, date)
);

-- ── Authoritative instrument master (the universe registry) ───────────────
create table if not exists atlas_foundation.instrument_master (
    instrument_id uuid not null,
    asset_class   text not null,            -- stock | etf | index
    symbol        text not null,            -- NSE tradingsymbol / index code
    name          text,
    isin          text,
    series        text,
    listing_date  date,
    kite_token    bigint,                   -- Kite instrument_token (null = not on Kite)
    exchange      text not null default 'NSE',
    is_active     boolean not null default true,
    source        text not null,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    primary key (instrument_id)
);
create unique index if not exists ux_fs_master_class_symbol
    on atlas_foundation.instrument_master (asset_class, symbol);
create index if not exists ix_fs_master_token
    on atlas_foundation.instrument_master (kite_token);

-- ── Per-instrument backfill progress (resumability) ───────────────────────
create table if not exists atlas_foundation.backfill_state (
    instrument_id uuid not null,
    asset_class   text not null,
    symbol        text not null,
    status        text not null,            -- pending | done | error | no_data
    rows_written  integer,
    first_date    date,
    last_date     date,
    error         text,
    updated_at    timestamptz not null default now(),
    primary key (instrument_id)
);

-- ── Corp-action events that are TRUE discontinuities (demerger whitelist) ──
-- The cleanliness jump-check skips these ex-dates: a demerger/spin-off price
-- drop is a real value separation, not a data error.
create table if not exists atlas_foundation.corp_action_event (
    symbol      text not null,
    ex_date     date not null,
    event_type  text not null,              -- demerger | spinoff | scheme | special
    note        text,
    source      text not null default 'manual',
    created_at  timestamptz not null default now(),
    primary key (symbol, ex_date, event_type)
);

-- ── Unified TA-Lib technicals for ALL instruments (stocks/ETFs/indices) ────
-- One technicals surface keyed by instrument_id (from instrument_master), so the
-- materialized-view layer reads a single table. RS is vs N50/N500 (meaningful for
-- stocks/ETFs; ~0 for the benchmark indices themselves).
create table if not exists atlas_foundation.technical_daily (
    instrument_id uuid not null,
    asset_class   text not null,
    symbol        text not null,
    date          date not null,
    ema_21 numeric(18,6), ema_50 numeric(18,6), ema_200 numeric(18,6),
    rsi_14 numeric(12,6),
    ret_1d numeric(16,8), ret_1w numeric(16,8), ret_1m numeric(16,8),
    ret_3m numeric(16,8), ret_6m numeric(16,8), ret_12m numeric(16,8),
    rs_1d_n50 numeric(16,8), rs_1w_n50 numeric(16,8), rs_1m_n50 numeric(16,8),
    rs_3m_n50 numeric(16,8), rs_6m_n50 numeric(16,8), rs_12m_n50 numeric(16,8),
    rs_1d_n500 numeric(16,8), rs_1w_n500 numeric(16,8), rs_1m_n500 numeric(16,8),
    rs_3m_n500 numeric(16,8), rs_6m_n500 numeric(16,8), rs_12m_n500 numeric(16,8),
    above_ema_21 boolean, above_ema_50 boolean, above_ema_200 boolean,
    compute_run_id uuid,
    computed_at timestamptz not null default now(),
    primary key (instrument_id, date)
);
create index if not exists ix_fs_tech_daily_class_date
    on atlas_foundation.technical_daily (asset_class, date);

-- ── Per-instrument compute progress (resumability) ────────────────────────
create table if not exists atlas_foundation.compute_state (
    instrument_id uuid not null,
    asset_class   text not null,
    symbol        text not null,
    status        text not null,            -- done | error | no_data
    rows_written  integer,
    last_date     date,
    error         text,
    updated_at    timestamptz not null default now(),
    primary key (instrument_id)
);

-- ── Ingest/compute provenance (loop heartbeat) ────────────────────────────
create table if not exists atlas_foundation.ingest_run (
    run_id      uuid not null default gen_random_uuid(),
    kind        text not null,        -- ingest_bhavcopy | compute_technicals | poc
    as_of_date  date,
    status      text not null,        -- ok | partial | error
    detail      jsonb,
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    primary key (run_id)
);

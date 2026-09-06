-- 00_core.sql — atlas_global schema + core tables.
-- Tables: instrument_master, symbol_alias, benchmark_master, macro_daily, index_membership,
--         atlas_thresholds, atlas_thresholds_audit, atlas_pipeline_runs, atlas_validator_results,
--         atlas_health_daily, ingest_state, provider_calls, app_user.
-- Plan: "Schema `atlas_global` — core tables" + "Non-negotiables" (every weight/threshold
--       lives in atlas_thresholds). Apply order 00 → 06 (scripts/global_market/apply_ddl.py).
-- Idempotent: every statement is CREATE … IF NOT EXISTS; no DROP, no function bodies (Phase 0).
-- Conventions: USD money = numeric; timestamps = timestamptz; dates = date; enums = CHECK.
-- India ops/threshold tables are mirrored column-for-column so load_thresholds(schema=...),
-- the admin thresholds panel and write_health_snapshot.py work unchanged; the only additions
-- are primary keys (India's clones carry none — upsert_df needs a conflict target).

CREATE SCHEMA IF NOT EXISTS atlas_global;

-- instrument_master — one row per US-listed stock / ETF, minted by build_identity.py (its
-- ONLY writer). instrument_id = uuid5 over a STABLE identity, never the bare symbol: US
-- tickers are recycled after delistings, and a recycled ticker is a NEW instrument that must
-- not inherit the dead one's bars (survivorship honesty). The key build_identity.py hashes is
-- "us:{asset_class}:{cik}:{symbol}" when the SEC identity is known (stocks: CIK; funds: CIK,
-- with series_id/class_id stored alongside) and "us:{asset_class}:{symbol}:{listing_date}"
-- otherwise. Hence symbol is unique among ACTIVE rows only (partial index below): the
-- delisted holder of a recycled symbol stays, is_active = false, with its history intact.
-- The registrant is the identity: a symbol whose CIK changes between weekly runs (another
-- registrant, none to one, one to none) is RECYCLED — old row deactivated, new uuid; with
-- no CIK on either side, a Tiingo listing start that jumps forward is the recycle signal.
-- A registrant that changes symbol (same CIK — funds: same CIK, series and class — with
-- exactly one listing before and after) is RENAMED: same uuid, new symbol, old spellings
-- closed in symbol_alias. source = 'manual' rows are never deactivated by the directory.
CREATE TABLE IF NOT EXISTS atlas_global.instrument_master (
    instrument_id    uuid        NOT NULL,
    asset_class      text        NOT NULL,
    symbol           text        NOT NULL,                  -- canonical form: BRK.B (aliases in symbol_alias)
    name             text,
    exchange         text,                                  -- NYSE | NASDAQ | NYSEARCA | BATS | …
    cik              text,                                  -- SEC CIK; text because leading zeros matter
    series_id        text,                                  -- SEC series id (funds), e.g. S000004310
    class_id         text,                                  -- SEC class id (share class)
    alpaca_asset_id  text,                                  -- provider-owned id, kept verbatim
    tradable         boolean,
    fractionable     boolean,
    listing_date     date,
    delisted_at      date,
    is_active        boolean     NOT NULL DEFAULT true,     -- delisted names keep their bars (survivorship honesty)
    sector_gics      text,                                  -- stocks: GICS sector by Select Sector SPDR membership — the ONE column written outside build_identity.py (ingest_index_membership.py), and written WITHOUT bumping updated_at (build_identity's freshness signal)
    sub_sector_id    text,                                  -- taxonomy_sector(id) level 2; no FK: taxonomy is created in 03_*
    source           text        NOT NULL,                  -- nasdaq_trader | stooq (archive-only, delisted) | alpaca | manual
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT instrument_master_pkey PRIMARY KEY (instrument_id),
    CONSTRAINT chk_instrument_master_asset_class CHECK (asset_class IN ('stock', 'etf'))
);
-- One ACTIVE instrument per symbol. build_identity.py never targets this index: it
-- deactivates the previous holder FIRST, in the same transaction, then inserts new rows by
-- the primary key and upserts renames / reactivations with ON CONFLICT (instrument_id) —
-- so the index is an assertion on the planner's bookkeeping, never a merge target.
-- Delisted rows may share a symbol with the live one.
CREATE UNIQUE INDEX IF NOT EXISTS ux_instrument_master_symbol_active
    ON atlas_global.instrument_master (symbol) WHERE is_active;
CREATE INDEX IF NOT EXISTS ix_instrument_master_symbol
    ON atlas_global.instrument_master (symbol);
CREATE INDEX IF NOT EXISTS ix_instrument_master_class_active
    ON atlas_global.instrument_master (asset_class, is_active);
CREATE INDEX IF NOT EXISTS ix_instrument_master_cik
    ON atlas_global.instrument_master (cik);

-- symbol_alias — how each source spells a symbol (AAPL.US, BRK-B vs BRK.B). A rename keeps
-- the uuid: the old spellings are closed (valid_to = the run date) and the new ones opened
-- on the SAME instrument_id — never a second instrument. A recycled ticker's open aliases
-- move to the new holder (closed on the old row, re-opened on the new one).
CREATE TABLE IF NOT EXISTS atlas_global.symbol_alias (
    source         text        NOT NULL,                    -- stooq | tiingo | sec | nasdaq_symbol | cqs | alpaca | manual
    source_symbol  text        NOT NULL,                    -- that source's own spelling: BRK-B.US, BRK-B, AGM-PD, AGM-D, AGMpD
    valid_from     date        NOT NULL,
    valid_to       date,                                    -- NULL = current
    instrument_id  uuid        NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    note           text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT symbol_alias_pkey PRIMARY KEY (source, source_symbol, valid_from)
);
CREATE INDEX IF NOT EXISTS ix_symbol_alias_instrument
    ON atlas_global.symbol_alias (instrument_id);

-- benchmark_master — benchmarks are ETFs with their own total-return bars in ohlcv_daily;
-- there is no separate benchmark-price table. SPY market, QQQ growth, IWM small, VXUS intl,
-- AGG bond, GLD gold, BIL cash.
CREATE TABLE IF NOT EXISTS atlas_global.benchmark_master (
    code           text        NOT NULL,
    instrument_id  uuid        NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    role           text        NOT NULL,
    name           text,
    is_active      boolean     NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT benchmark_master_pkey PRIMARY KEY (code),
    CONSTRAINT chk_benchmark_master_role
        CHECK (role IN ('market', 'growth', 'small', 'intl', 'bond', 'gold', 'cash'))
);

-- macro_daily — FRED series, one column per series (India's wide atlas_macro_daily shape, so the
-- adapted ingest_macro.py:_fred() maps series → column). Column = FRED series id, lower-cased.
CREATE TABLE IF NOT EXISTS atlas_global.macro_daily (
    date         date        NOT NULL,
    sp500        numeric(14,4),                             -- FRED SP500 (price index; SPY cross-check only)
    vixcls       numeric(10,4),                             -- CBOE VIX close
    dgs10        numeric(8,4),                              -- 10y Treasury constant maturity, percent p.a.
    dtb3         numeric(8,4),                              -- 3m T-bill secondary market, percent p.a. (risk-free)
    dtwexbgs     numeric(10,4),                             -- broad trade-weighted dollar index
    source       text        NOT NULL DEFAULT 'fred',
    ingested_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT macro_daily_pkey PRIMARY KEY (date)
);

-- index_membership — effective-dated membership (SSGA SPY daily holdings + fja05680/sp500
-- history). weight_frac = the latest observed index weight (a fraction, never percent); the daily weight
-- series itself lives in etf_holdings for SPY.
CREATE TABLE IF NOT EXISTS atlas_global.index_membership (
    index_code      text        NOT NULL,                   -- 'SP500'
    instrument_id   uuid        NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    effective_from  date        NOT NULL,
    effective_to    date,                                   -- NULL = current member; EXCLUSIVE end (the member is out on that date). On an ssga row it is the weekly OBSERVATION date — up to 7 sessions after the true change — and frozen once written; fja05680 rows are re-derived from the file on every --history run (a departure observed on one before the file caught up is provisional until then)
    weight_frac     numeric(12,8),
    source          text        NOT NULL,                   -- ssga | fja05680 (the values ingest_index_membership.py writes)
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT index_membership_pkey PRIMARY KEY (index_code, instrument_id, effective_from),
    CONSTRAINT chk_index_membership_weight
        CHECK (weight_frac IS NULL OR (weight_frac >= 0 AND weight_frac <= 1))
);
CREATE INDEX IF NOT EXISTS ix_index_membership_current
    ON atlas_global.index_membership (index_code, effective_to);

-- atlas_thresholds — India's 13 columns 1:1 (load_thresholds(schema="atlas_global") and the
-- admin panel read the same names) + PRIMARY KEY (threshold_key) so seeds can ON CONFLICT.
-- is_active carries NOT NULL DEFAULT true because load_thresholds() filters `WHERE is_active
-- = TRUE`: a hand-written insert that omits the column (the runbook tells the FM to write one
-- to set the liquidity floor) would otherwise land NULL and be INVISIBLE to every reader,
-- while the row plainly sits in the table. Found by making exactly that mistake, 2026-09-06.
CREATE TABLE IF NOT EXISTS atlas_global.atlas_thresholds (
    threshold_key        varchar(64)   NOT NULL,
    threshold_value      numeric(18,6),
    category             varchar(32),
    description          text,
    methodology_section  varchar(16),
    units                varchar(16),
    min_allowed          numeric(18,6),
    max_allowed          numeric(18,6),
    default_value        numeric(18,6),
    last_modified_by     varchar(64),
    last_modified_at     timestamptz,
    is_active            boolean       NOT NULL DEFAULT true,
    created_at           timestamptz,
    CONSTRAINT atlas_thresholds_pkey PRIMARY KEY (threshold_key)
);

-- atlas_thresholds_audit — every change to a threshold, with who/why as COLUMNS (the global
-- board runs on the transaction pooler, so SET LOCAL-style session audit is unavailable).
CREATE TABLE IF NOT EXISTS atlas_global.atlas_thresholds_audit (
    id             bigint        GENERATED ALWAYS AS IDENTITY,
    threshold_key  varchar(64)   NOT NULL,
    old_value      numeric(18,6),
    new_value      numeric(18,6),
    changed_by     varchar(64)   NOT NULL,                  -- app_user.email or script name
    change_reason  text,
    changed_at     timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT atlas_thresholds_audit_pkey PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_atlas_thresholds_audit_key
    ON atlas_global.atlas_thresholds_audit (threshold_key, changed_at);

-- atlas_pipeline_runs — India shape 1:1 (+ PK on run_id; write_health_snapshot mints a fresh
-- uuid per row).
CREATE TABLE IF NOT EXISTS atlas_global.atlas_pipeline_runs (
    run_id         uuid          NOT NULL,
    script_name    varchar(64)   NOT NULL,
    milestone      varchar(8),
    phase          varchar(32),
    started_at     timestamptz   NOT NULL,
    ended_at       timestamptz,
    status         varchar(16)   NOT NULL,
    rows_written   bigint,
    error_message  text,
    host           varchar(64),
    git_sha        varchar(40),
    created_at     timestamptz   NOT NULL DEFAULT now(),
    updated_at     timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT atlas_pipeline_runs_pkey PRIMARY KEY (run_id),
    CONSTRAINT chk_pipeline_runs_status
        CHECK (status IN ('queued', 'running', 'success', 'failed'))
);
CREATE INDEX IF NOT EXISTS ix_atlas_pipeline_runs_started
    ON atlas_global.atlas_pipeline_runs (started_at);

-- atlas_validator_results — India shape 1:1 (+ PK).
CREATE TABLE IF NOT EXISTS atlas_global.atlas_validator_results (
    run_id           uuid          NOT NULL,
    validator        varchar(16)   NOT NULL,
    ran_at           timestamptz   NOT NULL,
    total_checks     integer       NOT NULL,
    failures         integer       NOT NULL,
    status           varchar(8)    NOT NULL,
    failure_summary  jsonb,
    host             varchar(64),
    git_sha          varchar(40),
    CONSTRAINT atlas_validator_results_pkey PRIMARY KEY (run_id, validator),
    CONSTRAINT chk_validator_results_status CHECK (status IN ('PASS', 'FAIL'))
);
CREATE INDEX IF NOT EXISTS ix_atlas_validator_results_ran_at
    ON atlas_global.atlas_validator_results (ran_at);

-- atlas_health_daily — India shape 1:1 (+ PK; the writer deletes a (data_date, metric) slice
-- then inserts one row per tracked table, so the key is unique by construction).
CREATE TABLE IF NOT EXISTS atlas_global.atlas_health_daily (
    data_date         date          NOT NULL,
    table_name        varchar(64)   NOT NULL,
    metric_name       varchar(64)   NOT NULL,
    value_today       numeric,
    value_prior_day   numeric,
    rolling_14d_avg   numeric,
    rolling_14d_std   numeric,
    pct_change_dod    numeric,
    z_score           numeric,
    is_anomaly        boolean       NOT NULL DEFAULT false,
    severity          varchar(8),
    notes             text,
    computed_at       timestamptz   NOT NULL,
    CONSTRAINT atlas_health_daily_pkey PRIMARY KEY (data_date, table_name, metric_name),
    CONSTRAINT chk_health_severity
        CHECK (severity IS NULL OR severity IN ('info', 'warn', 'critical'))
);

-- ingest_state — per-source watermarks / cursors (last EDGAR index processed, last Alpaca
-- page token, …). One jsonb value per (source, key).
CREATE TABLE IF NOT EXISTS atlas_global.ingest_state (
    source      text        NOT NULL,
    key         text        NOT NULL,
    value       jsonb       NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ingest_state_pkey PRIMARY KEY (source, key)
);

-- provider_calls — free-tier budget is a monitored metric: calls per (day, provider, endpoint).
CREATE TABLE IF NOT EXISTS atlas_global.provider_calls (
    run_date    date        NOT NULL,
    provider    text        NOT NULL,                       -- alpaca | edgar | fred | issuer | nasdaq_trader | tiingo | finra
    endpoint    text        NOT NULL,
    calls       integer     NOT NULL DEFAULT 0,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT provider_calls_pkey PRIMARY KEY (run_date, provider, endpoint),
    CONSTRAINT chk_provider_calls_calls CHECK (calls >= 0)
);

-- app_user — invite-only allowlist for the global board (Supabase Auth identity is matched on
-- email; auth_user_id is filled on first sign-in). Emails are stored lower-cased.
CREATE TABLE IF NOT EXISTS atlas_global.app_user (
    email          text        NOT NULL,
    role           text        NOT NULL,
    display_name   text,
    auth_user_id   uuid,                                    -- Supabase Auth user id once known
    is_active      boolean     NOT NULL DEFAULT true,
    invited_by     text,
    invited_at     timestamptz NOT NULL DEFAULT now(),
    last_login_at  timestamptz,
    CONSTRAINT app_user_pkey PRIMARY KEY (email),
    CONSTRAINT ux_app_user_auth_user_id UNIQUE (auth_user_id),
    CONSTRAINT chk_app_user_role CHECK (role IN ('fm', 'analyst', 'client')),
    CONSTRAINT chk_app_user_email_lower CHECK (email = lower(email))
);

-- 06_baskets.sql — atlas_global basket product tables (M2, created now so the shapes are locked).
-- Tables: basket_master, basket_constituents, basket_trades, basket_nav_daily.
-- Plan: "Schema `atlas_global` — core tables" (M2 line) and "Later milestones — M2 Baskets".
-- basket_trades / basket_nav_daily mirror India's portfolio_trades / portfolio_nav_daily so
-- atlas.portfolio.engine.replay can be reused with a fractional quantum (qty numeric(18,6)).
-- Requires 00_core.sql, 03_classification.sql (country). Idempotent; no DROP; no function bodies.
--
-- DEFERRED TO PHASE 4 (no $$ function bodies in Phase 0):
--   * trigger enforcing Σ target_weight_frac = 1 per (basket_id, version) on basket_constituents;
--   * trigger refusing a non-basket_eligible ETF anywhere, and a non-country_pure ETF in a
--     kind = 'country' basket (the plan's "enforced by a DB trigger, not only the UI").

-- basket_master — kind etf | country | stock; weights are fixed per version and drift until the
-- next version (buy-and-hold on close_tr, no daily-rebalance fiction).
CREATE TABLE IF NOT EXISTS atlas_global.basket_master (
    basket_id        uuid          NOT NULL DEFAULT gen_random_uuid(),
    name             text          NOT NULL,
    kind             text          NOT NULL,
    description      text,
    benchmark_code   text          REFERENCES atlas_global.benchmark_master (code),
    country_iso2     char(2)       REFERENCES atlas_global.country (iso2),   -- required for kind = 'country'
    status           text          NOT NULL DEFAULT 'draft',
    current_version  integer       NOT NULL DEFAULT 1,
    initial_capital  numeric(18,2),                         -- USD; the replay's starting cash
    inception_date   date,
    created_by       text          NOT NULL,                -- app_user.email or 'system'
    created_at       timestamptz   NOT NULL DEFAULT now(),
    updated_at       timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT basket_master_pkey PRIMARY KEY (basket_id),
    CONSTRAINT chk_basket_master_kind CHECK (kind IN ('etf', 'country', 'stock')),
    CONSTRAINT chk_basket_master_status CHECK (status IN ('draft', 'active', 'archived')),
    CONSTRAINT chk_basket_master_country CHECK (kind <> 'country' OR country_iso2 IS NOT NULL),
    CONSTRAINT chk_basket_master_initial_capital
        CHECK (initial_capital IS NULL OR initial_capital > 0)
);

-- basket_constituents — target weights per (basket, version), fractions summing to 1.
-- Σ = 1 is enforced by a deferred trigger in Phase 4 (see header) — no trigger now.
CREATE TABLE IF NOT EXISTS atlas_global.basket_constituents (
    basket_id           uuid          NOT NULL REFERENCES atlas_global.basket_master (basket_id),
    version             integer       NOT NULL,
    instrument_id       uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    target_weight_frac  numeric(12,8) NOT NULL,
    effective_from      date          NOT NULL,
    created_at          timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT basket_constituents_pkey PRIMARY KEY (basket_id, version, instrument_id),
    CONSTRAINT chk_basket_constituents_weight
        CHECK (target_weight_frac > 0 AND target_weight_frac <= 1)
);
CREATE INDEX IF NOT EXISTS ix_basket_constituents_instrument
    ON atlas_global.basket_constituents (instrument_id);

-- basket_trades — India portfolio_trades shape; instrument_key → instrument_id (uuid),
-- qty numeric(18,6) for fractional shares, reasons adapted to baskets (rebalance replaces desk).
CREATE TABLE IF NOT EXISTS atlas_global.basket_trades (
    trade_id             bigint        GENERATED ALWAYS AS IDENTITY,
    basket_id            uuid          NOT NULL REFERENCES atlas_global.basket_master (basket_id),
    run_type             text          NOT NULL DEFAULT 'live',
    trade_date           date          NOT NULL,
    asset_class          text          NOT NULL,
    instrument_id        uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    symbol               text          NOT NULL,
    side                 text          NOT NULL,
    qty                  numeric(18,6) NOT NULL,
    price                numeric(18,6) NOT NULL,
    value                numeric(18,2) NOT NULL,
    reason               text          NOT NULL,
    run_id               uuid,
    created_at           timestamptz   NOT NULL DEFAULT now(),
    cost                 numeric(18,2),
    realized_pnl         numeric(18,2),
    holding_days         integer,
    tax_bucket           text,                              -- short_term | long_term (US), NULL until lots are tracked
    tax                  numeric(18,2),
    rationale            text,
    composite_at_signal  numeric(20,4),
    version              integer,                           -- basket version that produced the trade
    CONSTRAINT basket_trades_pkey PRIMARY KEY (trade_id),
    CONSTRAINT chk_basket_trades_run_type CHECK (run_type IN ('live', 'backtest', 'backtest_raw')),
    CONSTRAINT chk_basket_trades_asset_class CHECK (asset_class IN ('stock', 'etf')),
    CONSTRAINT chk_basket_trades_side CHECK (side IN ('buy', 'sell')),
    CONSTRAINT chk_basket_trades_qty CHECK (qty > 0),
    CONSTRAINT chk_basket_trades_price CHECK (price > 0),
    CONSTRAINT chk_basket_trades_reason
        CHECK (reason IN ('inception', 'rebalance', 'signal', 'manual', 'stop'))
);
CREATE INDEX IF NOT EXISTS ix_basket_trades
    ON atlas_global.basket_trades (basket_id, run_type, trade_date);

-- basket_nav_daily — India portfolio_nav_daily shape 1:1 (USD, cents).
CREATE TABLE IF NOT EXISTS atlas_global.basket_nav_daily (
    basket_id     uuid          NOT NULL REFERENCES atlas_global.basket_master (basket_id),
    run_type      text          NOT NULL DEFAULT 'live',
    date          date          NOT NULL,
    nav           numeric(18,2) NOT NULL,
    cash          numeric(18,2) NOT NULL,
    invested      numeric(18,2) NOT NULL,
    n_positions   integer       NOT NULL,
    run_id        uuid,
    computed_at   timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT basket_nav_daily_pkey PRIMARY KEY (basket_id, run_type, date),
    CONSTRAINT chk_basket_nav_daily_run_type CHECK (run_type IN ('live', 'backtest', 'backtest_raw'))
);
CREATE INDEX IF NOT EXISTS ix_basket_nav_daily_date
    ON atlas_global.basket_nav_daily (date);

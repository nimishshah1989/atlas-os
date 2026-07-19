-- Portfolio module tables (see docs/adr + plan: feat/portfolio-module).
-- Applied via: python3 -c "import _db; _db.exec_script(open('portfolio_ddl.sql').read())"
-- Holdings are DERIVED from portfolio_trades (no positions table — avoids dual writes).
-- Backtest and live paper-track share tables via run_type.

CREATE TABLE IF NOT EXISTS atlas_foundation.portfolio_master (
    portfolio_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name             text NOT NULL UNIQUE,
    kind             text NOT NULL CHECK (kind IN ('strategy', 'basket')),
    strategy_key     text,
    params           jsonb NOT NULL DEFAULT '{}',
    asset_classes    text[] NOT NULL DEFAULT '{stock}',
    initial_capital  numeric(18,2) NOT NULL CHECK (initial_capital > 0),
    max_position_pct numeric(6,4) NOT NULL CHECK (max_position_pct > 0 AND max_position_pct <= 1),
    inception_date   date NOT NULL,
    status           text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (kind = 'basket' OR strategy_key IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS atlas_foundation.portfolio_trades (
    trade_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id   uuid NOT NULL REFERENCES atlas_foundation.portfolio_master(portfolio_id),
    run_type       text NOT NULL DEFAULT 'live' CHECK (run_type IN ('live', 'backtest')),
    trade_date     date NOT NULL,
    asset_class    text NOT NULL CHECK (asset_class IN ('stock', 'etf', 'fund')),
    instrument_key text NOT NULL,
    symbol         text NOT NULL,
    side           text NOT NULL CHECK (side IN ('buy', 'sell')),
    qty            numeric(18,4) NOT NULL CHECK (qty > 0),
    price          numeric(18,6) NOT NULL CHECK (price > 0),
    value          numeric(18,2) NOT NULL,
    reason         text NOT NULL CHECK (reason IN ('inception', 'signal', 'manual')),
    run_id         uuid,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_portfolio_trades
    ON atlas_foundation.portfolio_trades (portfolio_id, run_type, trade_date);

CREATE TABLE IF NOT EXISTS atlas_foundation.portfolio_nav_daily (
    portfolio_id uuid NOT NULL REFERENCES atlas_foundation.portfolio_master(portfolio_id),
    run_type     text NOT NULL DEFAULT 'live' CHECK (run_type IN ('live', 'backtest')),
    date         date NOT NULL,
    nav          numeric(18,2) NOT NULL,
    cash         numeric(18,2) NOT NULL,
    invested     numeric(18,2) NOT NULL,
    n_positions  integer NOT NULL,
    run_id       uuid,
    computed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (portfolio_id, run_type, date)
);

-- Methodology defaults (editable from /admin/thresholds). Per-portfolio identity
-- (EMA pairs etc.) lives in portfolio_master.params, NOT here.
INSERT INTO atlas_foundation.atlas_thresholds
    (threshold_key, threshold_value, category, description, units,
     min_allowed, max_allowed, default_value, is_active)
SELECT 'portfolio_default_capital', 1000000, 'portfolio',
       'Default initial capital for a new portfolio', 'INR',
       100000, 100000000, 1000000, TRUE
WHERE NOT EXISTS (SELECT 1 FROM atlas_foundation.atlas_thresholds
                  WHERE threshold_key = 'portfolio_default_capital');

INSERT INTO atlas_foundation.atlas_thresholds
    (threshold_key, threshold_value, category, description, units,
     min_allowed, max_allowed, default_value, is_active)
SELECT 'portfolio_max_position_pct', 0.08, 'portfolio',
       'Default max position size as a fraction of portfolio value (slots = floor(1/pct))',
       'fraction', 0.01, 0.25, 0.08, TRUE
WHERE NOT EXISTS (SELECT 1 FROM atlas_foundation.atlas_thresholds
                  WHERE threshold_key = 'portfolio_max_position_pct');

-- ── Execution costs + Indian capital-gains tax (2026-07, feature b) ────────
-- Trade ledger columns: cost = total execution charges (STT/stamp/txn/GST) at the
-- booked rate; sells additionally carry FIFO-derived realized P&L and tax fields.
ALTER TABLE atlas_foundation.portfolio_trades ADD COLUMN IF NOT EXISTS cost numeric(18,2);
ALTER TABLE atlas_foundation.portfolio_trades ADD COLUMN IF NOT EXISTS realized_pnl numeric(18,2);
ALTER TABLE atlas_foundation.portfolio_trades ADD COLUMN IF NOT EXISTS holding_days integer;
ALTER TABLE atlas_foundation.portfolio_trades ADD COLUMN IF NOT EXISTS tax_bucket text;
ALTER TABLE atlas_foundation.portfolio_trades ADD COLUMN IF NOT EXISTS tax numeric(18,2);

-- Cost rates per asset class and side (fractions of trade value; editable knobs).
-- Seeds approximate NSE delivery economics: STT 0.1% both sides (stocks), stamp
-- 0.015% buy, exchange+SEBI+GST ~0.0035%; ETFs: stamp 0.015% buy, STT 0.001% sell;
-- MFs: stamp 0.005% buy, STT 0.001% equity redemption.
INSERT INTO atlas_foundation.atlas_thresholds
    (threshold_key, threshold_value, category, description, units, min_allowed, max_allowed, default_value, is_active)
SELECT k, v, 'portfolio', d, 'fraction', 0, 0.02, v, TRUE
FROM (VALUES
    ('portfolio_cost_stock_buy_pct',  0.00118, 'Equity delivery BUY cost: STT 0.1% + stamp 0.015% + txn/SEBI/GST'),
    ('portfolio_cost_stock_sell_pct', 0.00103, 'Equity delivery SELL cost: STT 0.1% + txn/SEBI/GST'),
    ('portfolio_cost_etf_buy_pct',    0.00019, 'ETF BUY cost: stamp 0.015% + txn/GST'),
    ('portfolio_cost_etf_sell_pct',   0.00005, 'ETF SELL cost: STT 0.001% + txn/GST'),
    ('portfolio_cost_fund_buy_pct',   0.00005, 'MF BUY cost: stamp duty 0.005%'),
    ('portfolio_cost_fund_sell_pct',  0.00001, 'Equity MF redemption STT 0.001%')
) AS s(k, v, d)
WHERE NOT EXISTS (SELECT 1 FROM atlas_foundation.atlas_thresholds t WHERE t.threshold_key = s.k);

-- Capital-gains tax knobs (equity/equity-MF, FY2026 law). LTCG exemption is per
-- financial year and applied PER PORTFOLIO here (approximation — the real 1.25L
-- exemption is per taxpayer across all holdings).
INSERT INTO atlas_foundation.atlas_thresholds
    (threshold_key, threshold_value, category, description, units, min_allowed, max_allowed, default_value, is_active)
SELECT k, v, 'portfolio', d, u, lo, hi, v, TRUE
FROM (VALUES
    ('portfolio_tax_stcg_pct',          0.20,   'STCG rate on equity/equity-MF (held < LTCG threshold)', 'fraction', 0::numeric, 0.5::numeric),
    ('portfolio_tax_ltcg_pct',          0.125,  'LTCG rate on equity/equity-MF above the FY exemption',  'fraction', 0, 0.5),
    ('portfolio_tax_ltcg_exemption_inr', 125000, 'LTCG exemption per financial year (per portfolio)',    'INR',      0, 1000000),
    ('portfolio_tax_ltcg_days',          365,    'Holding days threshold for LTCG on listed equity/MF',  'days',     180, 1100)
) AS s(k, v, d, u, lo, hi)
WHERE NOT EXISTS (SELECT 1 FROM atlas_foundation.atlas_thresholds t WHERE t.threshold_key = s.k);

-- ── Portfolio origin (kanban categories, 2026-07 feature f) ────────────────
-- rule-based = kind 'strategy' + origin 'fm' · system-generated = origin 'system'
-- (Phase 3 expert agent) · FM basket = kind 'basket'.
ALTER TABLE atlas_foundation.portfolio_master
    ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'fm'
    CHECK (origin IN ('fm', 'system'));

-- ── System-generated portfolios: policy journal + evolve knobs (feature a) ──
-- Every evaluation/change the walk-forward champion/challenger makes is journaled
-- with full evidence — the "learning log" rendered on the portfolio deepdive.
CREATE TABLE IF NOT EXISTS atlas_foundation.portfolio_policy_journal (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id uuid NOT NULL REFERENCES atlas_foundation.portfolio_master(portfolio_id),
    ts           timestamptz NOT NULL DEFAULT now(),
    kind         text NOT NULL CHECK (kind IN ('evaluation', 'change')),
    old_params   jsonb,
    new_params   jsonb,
    evidence     jsonb NOT NULL
);

INSERT INTO atlas_foundation.atlas_thresholds
    (threshold_key, threshold_value, category, description, units, min_allowed, max_allowed, default_value, is_active)
SELECT k, v, 'portfolio', d, u, lo, hi, v, TRUE
FROM (VALUES
    ('portfolio_evolve_train_years',      3,  'Walk-forward TRAIN window for system-portfolio policy search', 'years',  1::numeric, 5::numeric),
    ('portfolio_evolve_val_months',       12, 'Out-of-sample VALIDATION window (never trained on)',           'months', 6, 24),
    ('portfolio_evolve_min_improve_pp',   2,  'Challenger must beat champion by this many pp of excess return on validation', 'pp', 0, 10),
    ('portfolio_evolve_min_days_change',  28, 'Minimum days between policy changes (anti noise-chasing)',     'days',   7, 120),
    ('portfolio_evolve_min_trades',       5,  'Minimum train-window trades for a candidate to be considered', 'trades', 1, 50)
) AS s(k, v, d, u, lo, hi)
WHERE NOT EXISTS (SELECT 1 FROM atlas_foundation.atlas_thresholds t WHERE t.threshold_key = s.k);

-- ── Atlas Desk B1: per-cycle journal + desk knobs (spec 2026-07-04) ─────────
-- One row per desk per nightly cycle: the inputs digest, every agent's raw
-- output, what was actually booked, and any rejections — the desk's audit trail
-- and (in B2) its learning substrate.
CREATE TABLE IF NOT EXISTS atlas_foundation.desk_journal (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id uuid NOT NULL REFERENCES atlas_foundation.portfolio_master(portfolio_id),
    cycle_date   date NOT NULL,
    ts           timestamptz NOT NULL DEFAULT now(),
    scout        jsonb,
    risk         jsonb,
    pm           jsonb,
    applied      jsonb NOT NULL DEFAULT '[]',
    errors       jsonb NOT NULL DEFAULT '[]',
    inputs_digest jsonb
);
CREATE INDEX IF NOT EXISTS ix_desk_journal ON atlas_foundation.desk_journal (portfolio_id, cycle_date);

INSERT INTO atlas_foundation.atlas_thresholds
    (threshold_key, threshold_value, category, description, units, min_allowed, max_allowed, default_value, is_active)
SELECT k, v, 'portfolio', d, u, lo, hi, v, TRUE
FROM (VALUES
    ('desk_max_orders_per_cycle', 5,  'Hard cap on desk orders booked per nightly cycle', 'orders', 1::numeric, 12::numeric),
    ('desk_sector_cap',           3,  'Hard cap on desk holdings per sector',             'names',  1, 6),
    ('desk_watchlist_size',       40, 'Top-N by composite fed to the desk agents',        'names',  10, 100)
) AS s(k, v, d, u, lo, hi)
WHERE NOT EXISTS (SELECT 1 FROM atlas_foundation.atlas_thresholds t WHERE t.threshold_key = s.k);

-- ── Atlas Desk B2: outcome stamps + distilled lessons (spec 2026-07-04) ─────
-- Outcomes: what actually happened after each desk decision — booked orders get
-- T+5/T+20/T+60 marks; deferred/vetoed proposals get the opportunity cost of the
-- road not taken. The reflection agent learns ONLY from these forward stamps.
CREATE TABLE IF NOT EXISTS atlas_foundation.desk_outcomes (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id uuid NOT NULL REFERENCES atlas_foundation.portfolio_master(portfolio_id),
    kind         text NOT NULL CHECK (kind IN ('order', 'rejected')),
    symbol       text NOT NULL,
    side         text,
    decision_date date NOT NULL,
    t5_pct       numeric(10,4),
    t20_pct      numeric(10,4),
    t60_pct      numeric(10,4),
    stamped_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, kind, symbol, decision_date)
);

-- Lessons: the desk's distilled memory. Confidence is EARNED — the weekly
-- reflection raises it when later outcomes confirm a lesson and decays it when
-- they don't, so bad lessons die instead of compounding.
CREATE TABLE IF NOT EXISTS atlas_foundation.desk_lessons (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id uuid NOT NULL REFERENCES atlas_foundation.portfolio_master(portfolio_id),
    ts           timestamptz NOT NULL DEFAULT now(),
    lesson       text NOT NULL,
    tags         jsonb NOT NULL DEFAULT '{}',
    confidence   numeric(4,3) NOT NULL DEFAULT 0.5,
    active       boolean NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS ix_desk_lessons ON atlas_foundation.desk_lessons (portfolio_id, active);

-- ── MF exit load (2026-07, fund cap portfolios) ────────────────────────────
-- Equity-MF redemption load: charged on the redeemed value when a fund lot is
-- sold within the load window. Deducted from proceeds (reduces cash) AND folded
-- into the trade cost so the FIFO capital-gains basis nets it too — a transfer
-- expense. Distinct from STT (portfolio_cost_fund_sell_pct), which always applies.
INSERT INTO atlas_foundation.atlas_thresholds
    (threshold_key, threshold_value, category, description, units, min_allowed, max_allowed, default_value, is_active)
SELECT k, v, 'portfolio', d, u, lo, hi, v, TRUE
FROM (VALUES
    ('portfolio_exit_load_fund_pct',  0.01, 'Equity-MF exit load on redemptions within the load window', 'fraction', 0::numeric, 0.05::numeric),
    ('portfolio_exit_load_fund_days', 365,  'Holding days below which the fund exit load applies',       'days',     0, 1100)
) AS s(k, v, d, u, lo, hi)
WHERE NOT EXISTS (SELECT 1 FROM atlas_foundation.atlas_thresholds t WHERE t.threshold_key = s.k);

-- ── Desk v2 wave 1 (2026-07): trade plans + human approval queue ───────────
-- EXECUTION TRADER agent sets stop/target per buy (grounded in real levels,
-- geometry + R:R re-checked in code). Desks with params.approval='true' queue
-- orders here instead of auto-booking; approval books via the audited
-- book_trade path at next settlement; unapproved cards auto-expire.
ALTER TABLE atlas_foundation.desk_journal ADD COLUMN IF NOT EXISTS trader jsonb;
ALTER TABLE atlas_foundation.desk_journal ADD COLUMN IF NOT EXISTS queued jsonb NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS atlas_foundation.desk_pending_orders (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id   uuid NOT NULL REFERENCES atlas_foundation.portfolio_master(portfolio_id),
    cycle_date     date NOT NULL,
    symbol         text NOT NULL,
    side           text NOT NULL CHECK (side IN ('buy', 'sell')),
    instrument_key text NOT NULL,
    thesis         text NOT NULL,
    invalidation   text NOT NULL,
    entry_ref      numeric(14, 2),
    stop           numeric(14, 2),
    target         numeric(14, 2),
    rr             numeric(6, 2),
    plan_basis     text,
    status         text NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'approved', 'rejected', 'expired', 'booked', 'failed')),
    decided_at     timestamptz,
    decided_by     text,
    booked_at      timestamptz,
    note           text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, symbol, cycle_date)
);
CREATE INDEX IF NOT EXISTS ix_desk_pending ON atlas_foundation.desk_pending_orders (status, cycle_date);

INSERT INTO atlas_foundation.atlas_thresholds
    (threshold_key, threshold_value, category, description, units, min_allowed, max_allowed, default_value, is_active)
SELECT k, v, 'portfolio', d, u, lo, hi, v, TRUE
FROM (VALUES
    ('desk_min_rr',               1.5, 'Minimum reward-to-risk for a desk buy trade plan', 'ratio', 1::numeric, 5::numeric),
    ('desk_pending_expiry_days',  3,   'Sessions before an unapproved desk order expires', 'days',  1, 10)
) AS s(k, v, d, u, lo, hi)
WHERE NOT EXISTS (SELECT 1 FROM atlas_foundation.atlas_thresholds t WHERE t.threshold_key = s.k);

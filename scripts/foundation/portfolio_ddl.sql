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

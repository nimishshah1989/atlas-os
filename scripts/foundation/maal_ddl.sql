-- MaaL Process (Multi Asset Alpha - Leaders): the three real model portfolios,
-- sourced from the clients.jslwealth.in (CPP) database.
--
-- Applied via: python3 -c "import _db; _db.exec_script(open('maal_ddl.sql').read())"
--
-- This script ADDS tables. It alters nothing that already exists — deliberately.
-- portfolio_trades is written by the engine's nightly mark, and widening a live
-- table another writer owns is a bigger blast radius than this change needs.

-- ── The three books ──────────────────────────────────────────────────────────
-- Registered in portfolio_master so the EXISTING /portfolios pages render them
-- with no new UI. kind='basket' because there is no engine strategy behind them
-- (the kind='strategy' CHECK would demand a strategy_key); origin='fm' because the
-- FM does run these books — the CPP provenance lives in params, which is jsonb and
-- needs no CHECK migration.
--
-- initial_capital is a CHECK-satisfying placeholder, not a real number: the corpus
-- moves, and the true value arrives nightly from cpp_nav_series into
-- portfolio_nav_daily. max_position_pct likewise satisfies (> 0 AND <= 1) and is
-- unused for these books — the real cap lives in atlas_thresholds.
INSERT INTO atlas_foundation.portfolio_master
    (name, kind, strategy_key, params, asset_classes,
     initial_capital, max_position_pct, inception_date, status, origin)
VALUES
    ('MaaL Leaders', 'basket', NULL,
     '{"source":"cpp","client_code":"BJ53","maal_code":"leaders"}'::jsonb,
     ARRAY['stock','etf'], 100000, 0.25, DATE '2020-09-28', 'active', 'fm'),
    ('MaaL IND11', 'basket', NULL,
     '{"source":"cpp","client_code":"BJ53IND","maal_code":"ind11"}'::jsonb,
     ARRAY['stock','etf'], 100000, 0.25, DATE '2026-05-09', 'active', 'fm'),
    ('MaaL Passive', 'basket', NULL,
     '{"source":"cpp","client_code":"JR100PASS","maal_code":"passive"}'::jsonb,
     ARRAY['stock','etf'], 100000, 0.25, DATE '2021-08-02', 'active', 'fm')
ON CONFLICT (name) DO UPDATE SET params = EXCLUDED.params;

-- ── Dated position snapshot ──────────────────────────────────────────────────
-- cpp_holdings is current-state only (UNIQUE on client+portfolio+symbol), so
-- "what did BJ53 hold last Friday" does not exist anywhere unless Atlas records
-- it. One row per position per day; nothing is ever overwritten, so the series IS
-- the change log — yesterday vs today is a query, not a second table to keep in sync.
CREATE TABLE IF NOT EXISTS atlas_foundation.maal_holding_snapshot (
    -- TWO dates, and the difference between them matters.
    --   as_of        = the day WE looked (the sync run date).
    --   source_as_of = the day the DATA is from (cpp_nav_series.nav_date).
    -- CPP positions only move when a backoffice file is uploaded, so these drift
    -- apart routinely — verified 2026-07-31, when BJ53's newest transaction was
    -- 2026-07-29. Stamping a book "Monday" when it is really Thursday's positions
    -- is how the desk sells a name that was already sold. The board and the PDF
    -- render source_as_of; as_of exists so a DEAD sync ("we never looked") is
    -- distinguishable from a quiet one ("we looked, nothing changed").
    as_of          date NOT NULL,
    source_as_of   date NOT NULL,
    maal_code      text NOT NULL CHECK (maal_code IN ('leaders', 'passive', 'ind11')),
    isin           text NOT NULL,
    source_symbol  text NOT NULL,
    -- Resolved Atlas key ("stock:SYMBOL" / "etf:SYMBOL"); NULL when the ISIN is not
    -- in instrument_master. NULL is loud, never silently dropped — see the gate.
    instrument_key text,
    -- 'EQUITY' or 'CASH', straight from CPP. CASH is how liquid ETFs (LIQUIDBEES,
    -- LIQUIDCASE, LIQUIDETF) are already tagged there, so no symbol list is needed.
    asset_class    text NOT NULL,
    quantity       numeric(18,4) NOT NULL,
    avg_cost       numeric(18,4) NOT NULL,
    synced_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of, maal_code, isin)
);

CREATE INDEX IF NOT EXISTS ix_maal_snapshot_latest
    ON atlas_foundation.maal_holding_snapshot (maal_code, as_of DESC);

-- ── Trade idempotency ────────────────────────────────────────────────────────
-- portfolio_trades has no natural key, so a re-run would duplicate every trade.
-- The idempotency key lives in its OWN table rather than as a column on
-- portfolio_trades, for two reasons:
--   1. portfolio_trades is written by the engine's nightly mark. Adding a column
--      to a live table another writer owns widens the blast radius of this change
--      for no benefit — a link table touches nothing that already exists.
--   2. ALTER on a production table is a different risk tier than CREATE, and this
--      change does not need that tier.
-- The cost is one join on insert, over a few thousand rows. Irrelevant here.
CREATE TABLE IF NOT EXISTS atlas_foundation.maal_trade_link (
    source_txn_id bigint PRIMARY KEY,          -- cpp_transactions.id
    trade_id      bigint NOT NULL UNIQUE
                  REFERENCES atlas_foundation.portfolio_trades(trade_id) ON DELETE CASCADE,
    linked_at     timestamptz NOT NULL DEFAULT now()
);

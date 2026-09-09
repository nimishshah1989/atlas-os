-- 02_etf.sql — atlas_global ETF facts, shares/flow input, holdings, look-through exposures.
-- Tables: etf_meta, etf_shares_daily, etf_holdings, etf_exposure_daily.
-- Plan: "Schema `atlas_global` — core tables" (etf_meta … etf_exposure_daily) and
--       "Classification engine" L0/L1 (facts + exposures).
-- Requires 00_core.sql. Idempotent; no DROP; no function bodies.
-- Weight scale: weight_frac is a FRACTION, always (the name carries the unit). Gate later:
-- Σ|weight_frac| ∈ [0.9, 1.1] for non-leveraged ETFs.

-- etf_meta — structure & cost facts with a *_source column beside every number that could
-- come from an unofficial fill, so provenance is visible on the card.
CREATE TABLE IF NOT EXISTS atlas_global.etf_meta (
    instrument_id        uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    issuer               text,                              -- iShares | SPDR | Vanguard | Invesco | …
    family               text,                              -- issuer product family / brand line
    inception_date       date,
    expense_ratio        numeric(8,6),                      -- fraction (0.0009 = 9 bp)
    expense_source       text,                              -- issuer_list | nport | yfinance_unofficial
    aum_usd              numeric,
    aum_as_of            date,
    aum_source           text,
    shares_outstanding   bigint,
    shares_as_of         date,
    shares_source        text,                              -- issuer_csv | nport
    index_tracked        text,
    is_active_mgmt       boolean,
    leveraged_factor     numeric(6,2),                      -- 1 = unleveraged, 2 / 3 = 2x / 3x; negative for inverse
    is_inverse           boolean,
    is_currency_hedged   boolean,
    derivatives_share    numeric(8,6),                      -- fraction of NAV in derivatives (N-PORT)
    description          text,                              -- issuer / prospectus objective text (L0 fact for the LLM pass)
    source               text,
    updated_at           timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT etf_meta_pkey PRIMARY KEY (instrument_id),
    CONSTRAINT chk_etf_meta_aum_source
        CHECK (aum_source IS NULL OR aum_source IN ('nport', 'issuer_list', 'yfinance_unofficial')),
    CONSTRAINT chk_etf_meta_expense_ratio
        CHECK (expense_ratio IS NULL OR (expense_ratio >= 0 AND expense_ratio < 1))
);

-- etf_shares_daily — shares outstanding / NAV series (issuer daily files). Flow-lens input:
-- Δ shares 21d / 63d = creations proxy.
CREATE TABLE IF NOT EXISTS atlas_global.etf_shares_daily (
    instrument_id       uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    date                date          NOT NULL,
    shares_outstanding  bigint,
    nav_usd             numeric(18,6),
    aum_usd             numeric,                            -- issuer-reported net assets that day
    source              text          NOT NULL,
    ingested_at         timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT etf_shares_daily_pkey PRIMARY KEY (instrument_id, date),
    CONSTRAINT chk_etf_shares_daily_source CHECK (source IN ('issuer_csv', 'nport'))
);
CREATE INDEX IF NOT EXISTS ix_etf_shares_daily_date
    ON atlas_global.etf_shares_daily (date);

-- etf_holdings — append-only snapshots; readers take max(as_of_date) ≤ lens date.
-- holding_key = the source's own row identity (CUSIP, ticker or name — whatever the file gives);
-- holding_instrument_id is set when the holding maps to a scored instrument.
CREATE TABLE IF NOT EXISTS atlas_global.etf_holdings (
    instrument_id          uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    as_of_date             date          NOT NULL,
    holding_key            text          NOT NULL,
    holding_instrument_id  uuid          REFERENCES atlas_global.instrument_master (instrument_id),
    holding_name           text,
    holding_ticker         text,
    cusip                  text,
    weight_frac            numeric(12,8),
    market_value_usd       numeric,
    balance                numeric,                         -- shares / notional held (N-PORT balance)
    country_iso2           char(2),
    asset_category         text,                            -- N-PORT asset category / issuer sector column
    source                 text          NOT NULL,
    ingested_at            timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT etf_holdings_pkey PRIMARY KEY (instrument_id, as_of_date, holding_key),
    CONSTRAINT chk_etf_holdings_weight_frac
        CHECK (weight_frac IS NULL OR (weight_frac >= -10 AND weight_frac <= 10)),
    CONSTRAINT chk_etf_holdings_source CHECK (source IN ('issuer_csv', 'nport'))
);
CREATE INDEX IF NOT EXISTS ix_etf_holdings_as_of_date
    ON atlas_global.etf_holdings (as_of_date);
CREATE INDEX IF NOT EXISTS ix_etf_holdings_holding_instrument
    ON atlas_global.etf_holdings (holding_instrument_id);

-- etf_exposure_daily — L1 exposures computed from ONE holdings snapshot (pure exposures.py).
-- Keyed by the snapshot (instrument_id, as_of_date) rather than the lens date: exposures only
-- change when holdings change (build_exposures --changed), and readers take the latest
-- as_of_date ≤ lens date exactly as they do for etf_holdings. Vectors are jsonb of fractions.
CREATE TABLE IF NOT EXISTS atlas_global.etf_exposure_daily (
    instrument_id         uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    as_of_date            date          NOT NULL,
    country_vec           jsonb,                            -- {"US": 0.62, "JP": 0.08, …}
    sector_vec            jsonb,                            -- {"information_technology": 0.31, …}
    asset_vec             jsonb,                            -- {"equity": 0.99, "cash": 0.01, …}
    top_country           char(2),
    top_country_w         numeric(12,8),
    equity_w              numeric(12,8),
    n_holdings            integer,
    top10_w               numeric(12,8),
    hhi                   numeric(12,8),
    lookthrough_scored_w  numeric(12,8),                    -- weight in scored S&P 500 stocks (quality-lens gate)
    sum_abs_weight        numeric(12,8),                    -- Σ|weight_frac| of the snapshot (the [0.9, 1.1] gate input)
    holdings_source       text,
    compute_run_id        uuid,
    computed_at           timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT etf_exposure_daily_pkey PRIMARY KEY (instrument_id, as_of_date)
);
CREATE INDEX IF NOT EXISTS ix_etf_exposure_daily_as_of_date
    ON atlas_global.etf_exposure_daily (as_of_date);

-- ── what Form N-PORT turned out to carry (ingest_nport.py) ────────────────────────────────
-- Added rather than folded into the CREATEs above: both paths converge on the same tables,
-- and a database created before this producer landed is upgraded by exactly these lines.

-- etf_holdings: four columns without which a row cannot be read back correctly.
--   isin   — the ONLY identifier on 176 of EWJ's 182 holdings (Japanese equities have no
--            CUSIP). Without it a non-US holding can never be resolved to an instrument.
--   units  — N-PORT's NS | PA | NC | OU. `balance` is 4,027,521 SHARES or 4,027,521 DOLLARS
--            of principal depending on this column; a number that cannot be interpreted is
--            worse than no number.
--   payoff_profile      — Long | Short. Two rows of equal |weight| are opposite exposures.
--   derivative_category — FUT | SWP | FWD | … when the line is a derivative. Look-through
--            must not read a swap's MARK as an equity position.
ALTER TABLE atlas_global.etf_holdings ADD COLUMN IF NOT EXISTS isin                text;
ALTER TABLE atlas_global.etf_holdings ADD COLUMN IF NOT EXISTS units               text;
ALTER TABLE atlas_global.etf_holdings ADD COLUMN IF NOT EXISTS payoff_profile      text;
ALTER TABLE atlas_global.etf_holdings ADD COLUMN IF NOT EXISTS derivative_category text;
CREATE INDEX IF NOT EXISTS ix_etf_holdings_isin ON atlas_global.etf_holdings (isin);

-- etf_meta: the series-level facts, stored under their true names.
-- One N-PORT filing covers one SERIES, and `net_assets` is the series'. VOO is one of FOUR
-- share classes of the Vanguard 500 Index Fund, so that fund's $1.67tn is NOT VOO's AUM, and
-- N-PORT carries no class-level assets at all. Writing it into aum_usd would be a wrong
-- number on a card (rule #0), so the series figure lives here under its own name and
-- ingest_nport.py copies it into aum_usd ONLY when series_class_count = 1.
ALTER TABLE atlas_global.etf_meta
    ADD COLUMN IF NOT EXISTS series_net_assets_usd numeric;
ALTER TABLE atlas_global.etf_meta
    ADD COLUMN IF NOT EXISTS series_class_count    integer;
-- Σ|notionalAmt| ÷ net assets. The ONLY structural evidence of gearing in the form: a swap's
-- pctVal is its mark, not its notional, so TQQQ (three times) sums to 101.26% of net assets
-- against IVV's 100.12% — the weights cannot tell them apart, and this can (TQQQ 2.70,
-- IVV 0.0016, measured on the fixtures).
ALTER TABLE atlas_global.etf_meta
    ADD COLUMN IF NOT EXISTS derivative_notional_share numeric;

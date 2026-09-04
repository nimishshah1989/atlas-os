-- 04_fundamentals_events.sql — atlas_global point-in-time fundamentals + stock event feeds.
-- Tables: stock_financials_pit, filings_8k, insider_form4, holders_13f_q, short_interest.
-- Plan: "Schema `atlas_global` — core tables" (stock_financials_pit, filings_8k, insider_form4,
--       holders_13f_q, short_interest), "Methodology spec §A" (fundamentals, events) and
--       "Non-negotiables" (point-in-time discipline: availability = the actual EDGAR filed date).
-- Requires 00_core.sql. Idempotent; no DROP; no function bodies.
-- All amounts are USD as reported (numeric, unrounded); per-share values numeric(18,6).

-- stock_financials_pit — one row per (instrument, period_end, form, filed). `filed` is the PIT key:
-- as-of loaders take rows with filed ≤ as_of only. Restated figures arrive as a NEW row with a
-- later filed date; the original is never overwritten.
CREATE TABLE IF NOT EXISTS atlas_global.stock_financials_pit (
    instrument_id         uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    period_end            date          NOT NULL,
    form                  text          NOT NULL,
    filed                 date          NOT NULL,
    fiscal_year           integer,
    fiscal_period         text,                             -- FY | Q1 | Q2 | Q3 | Q4
    period_start          date,
    accession_no          text,
    -- income statement (period, as reported)
    revenue               numeric,
    gross_profit          numeric,
    operating_income      numeric,                          -- EBIT
    net_income            numeric,
    eps_diluted           numeric(18,6),
    shares_diluted        numeric,
    dep_amort             numeric,                          -- D&A → EBITDA = operating_income + dep_amort
    interest_expense      numeric,
    -- balance sheet (period end)
    equity                numeric,
    total_assets          numeric,
    total_debt            numeric,
    cash                  numeric,
    current_assets        numeric,
    current_liabilities   numeric,
    -- cash flow (period)
    operating_cash_flow   numeric,
    capex                 numeric,                          -- FCF = operating_cash_flow − capex
    dividends_paid        numeric,
    is_financial_co       boolean,                          -- balance-sheet sub-score skipped when true
    source                text          NOT NULL DEFAULT 'edgar_xbrl',
    ingested_at           timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT stock_financials_pit_pkey PRIMARY KEY (instrument_id, period_end, form, filed),
    CONSTRAINT chk_stock_financials_pit_form
        CHECK (form IN ('10-K', '10-Q', '10-K/A', '10-Q/A', '20-F', '40-F')),
    CONSTRAINT chk_stock_financials_pit_fiscal_period
        CHECK (fiscal_period IS NULL OR fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4'))
);
CREATE INDEX IF NOT EXISTS ix_stock_financials_pit_filed
    ON atlas_global.stock_financials_pit (filed);
CREATE INDEX IF NOT EXISTS ix_stock_financials_pit_instrument_filed
    ON atlas_global.stock_financials_pit (instrument_id, filed);

-- filings_8k — one row per (8-K accession, instrument); dual-class issuers (GOOGL/GOOG) share a
-- CIK, so the same accession maps to two instruments. items = the 8-K item codes ('2.02', '5.02', …).
CREATE TABLE IF NOT EXISTS atlas_global.filings_8k (
    accession_no      text          NOT NULL,
    instrument_id     uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    cik               text,
    filed             date          NOT NULL,
    period_of_report  date,
    items             text[]        NOT NULL DEFAULT '{}',
    description       text,                                 -- EDGAR form description / headline
    url               text,
    source            text          NOT NULL DEFAULT 'edgar',
    ingested_at       timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT filings_8k_pkey PRIMARY KEY (accession_no, instrument_id)
);
CREATE INDEX IF NOT EXISTS ix_filings_8k_instrument_filed
    ON atlas_global.filings_8k (instrument_id, filed);
CREATE INDEX IF NOT EXISTS ix_filings_8k_filed
    ON atlas_global.filings_8k (filed);

-- insider_form4 — one row per non-derivative transaction line on a Form 4 (txn_seq = line order
-- within the filing). Open-market purchases/sales (codes P / S) feed the flow lens and the
-- cluster-buy / cluster-sell catalyst flags.
CREATE TABLE IF NOT EXISTS atlas_global.insider_form4 (
    accession_no        text          NOT NULL,
    txn_seq             integer       NOT NULL,
    instrument_id       uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    cik                 text,                               -- issuer CIK
    filed               date          NOT NULL,
    transaction_date    date,
    owner_name          text,
    owner_cik           text,
    is_director         boolean,
    is_officer          boolean,
    is_ten_pct_owner    boolean,
    officer_title       text,
    transaction_code    text,                               -- SEC code: P | S | A | D | M | F | G | …
    acquired_disposed   char(1),
    is_open_market      boolean,                            -- transaction_code IN ('P', 'S')
    shares              numeric,
    price_per_share     numeric(18,6),
    value_usd           numeric,                            -- shares × price_per_share
    shares_owned_after  numeric,
    source              text          NOT NULL DEFAULT 'edgar',
    ingested_at         timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT insider_form4_pkey PRIMARY KEY (accession_no, txn_seq),
    CONSTRAINT chk_insider_form4_acq_disp
        CHECK (acquired_disposed IS NULL OR acquired_disposed IN ('A', 'D'))
);
CREATE INDEX IF NOT EXISTS ix_insider_form4_instrument_txn
    ON atlas_global.insider_form4 (instrument_id, transaction_date);
CREATE INDEX IF NOT EXISTS ix_insider_form4_filed
    ON atlas_global.insider_form4 (filed);

-- holders_13f_q — quarterly 13F holder aggregates per stock. available_from = the date the
-- quarter's filings were complete (period_end + 45 days) — the PIT key the flow lens respects.
CREATE TABLE IF NOT EXISTS atlas_global.holders_13f_q (
    instrument_id      uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    period_end         date          NOT NULL,
    available_from     date          NOT NULL,
    n_holders          integer,
    total_shares_held  numeric,
    total_value_usd    numeric,
    source             text          NOT NULL DEFAULT 'edgar',
    ingested_at        timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT holders_13f_q_pkey PRIMARY KEY (instrument_id, period_end),
    CONSTRAINT chk_holders_13f_q_available CHECK (available_from >= period_end)
);
CREATE INDEX IF NOT EXISTS ix_holders_13f_q_period_end
    ON atlas_global.holders_13f_q (period_end);

-- short_interest — FINRA equity short interest, twice monthly by settlement date.
CREATE TABLE IF NOT EXISTS atlas_global.short_interest (
    instrument_id     uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    settlement_date   date          NOT NULL,
    short_interest    bigint,
    avg_daily_volume  bigint,
    days_to_cover     numeric(12,4),
    source            text          NOT NULL DEFAULT 'finra',
    ingested_at       timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT short_interest_pkey PRIMARY KEY (instrument_id, settlement_date)
);
CREATE INDEX IF NOT EXISTS ix_short_interest_settlement_date
    ON atlas_global.short_interest (settlement_date);

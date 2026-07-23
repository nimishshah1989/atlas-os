-- wealth: Jhaveri client-portfolio schema (FM-approved second schema, 2026-07-18).
-- Separate bounded context from atlas_foundation: client PII + holdings snapshots.
-- Read side joins OUT to atlas_foundation fund identity via wealth.schemes.mstar_id.
-- Idempotent: safe to re-run.

create schema if not exists wealth;

create table if not exists wealth.clients (
    client_id   bigint generated always as identity primary key,
    pan         text unique,          -- real-world key; null for minors/some accounts
    client_code text,                 -- bracket code from report header (family-level, not unique)
    full_name   text not null,
    family_group text not null,       -- source folder grouping (family/RM book)
    email       text,
    mobile      text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (full_name, client_code)   -- identity fallback when pan is null
);

create table if not exists wealth.client_reports (
    report_id     bigint generated always as identity primary key,
    client_id     bigint not null references wealth.clients(client_id),
    as_on_date    date not null,      -- valuation date from report header
    txn_upto_date date,
    nav_upto_date date,
    source_file   text not null,
    -- flow summary (report header block)
    lumpsum_purchases      numeric(18,2),
    systematic_investments numeric(18,2),
    switch_ins             numeric(18,2),
    redemptions            numeric(18,2),
    systematic_withdrawals numeric(18,2),
    switch_outs            numeric(18,2),
    dividend_payouts       numeric(18,2),
    dividend_reinvested    numeric(18,2),
    -- market value split
    mv_equity numeric(18,2),
    mv_debt   numeric(18,2),
    mv_hybrid numeric(18,2),
    mv_others numeric(18,2),
    mv_total  numeric(18,2),
    overall_abs_return_pct numeric(12,2),
    overall_xirr_pct       numeric(10,2),
    created_at timestamptz not null default now(),
    unique (client_id, as_on_date)
);

create table if not exists wealth.schemes (
    scheme_id    bigint generated always as identity primary key,
    display_name text not null unique,   -- exactly as printed in reports
    asset_class  text not null,          -- Equity | Debt | Hybrid | Others
    sub_category text not null,          -- e.g. 'Equity - Flexi Cap'
    plan_type    text,                   -- Regular | Direct (from display-name suffix)
    option_type  text,                   -- Growth | IDCW
    -- identity bridge into atlas_foundation (null until mapped)
    mstar_id         text,
    amfi_code        text,
    matched_name     text,
    match_method     text not null default 'unmatched',  -- exact|normalized|fuzzy|manual|unmatched
    match_confidence numeric(5,3),
    in_atlas_universe boolean not null default false,    -- scored by Atlas lenses
    has_nav_series    boolean not null default false,    -- de_mf_nav_daily coverage
    created_at timestamptz not null default now()
);

create table if not exists wealth.holdings (
    holding_id bigint generated always as identity primary key,
    report_id  bigint not null references wealth.client_reports(report_id) on delete cascade,
    client_id  bigint not null references wealth.clients(client_id),
    scheme_id  bigint not null references wealth.schemes(scheme_id),
    folio      text not null,
    inv_since  date,
    inv_days   integer,
    investments          numeric(18,2),
    withdrawals          numeric(18,2),
    dividends_reinvested numeric(18,2),
    dividend_payouts     numeric(18,2),
    balance_units numeric(20,3),
    avg_cost      numeric(16,4),
    cost_amount   numeric(18,2),
    nav           numeric(16,4),      -- null for segregated/side-pocket units (printed NA)
    market_value  numeric(18,2),      -- null for segregated/side-pocket units
    port_weight_pct numeric(8,2),
    abs_return_pct  numeric(12,2),
    xirr_pct        numeric(10,2)
);

-- ---- Folio Ledger ingest (2026-07-23 transactions build plan) ----

create table if not exists wealth.client_profile_ext ( -- new facts the ledger header carries
    client_id    bigint primary key references wealth.clients(client_id),
    joint_holders text,
    holding_mode  text,                -- "Anyone or Survivor(s)" etc.
    tax_status    text,
    kyc_ok        boolean,
    account_type  text,
    advisor_name  text,
    advisor_code  text,
    branch        text,
    ledger_report_date date,
    ledger_source_file text
);

create table if not exists wealth.transactions (
    txn_id    bigint generated always as identity primary key,
    client_id bigint not null references wealth.clients(client_id),
    scheme_id bigint references wealth.schemes(scheme_id), -- via ISIN/name join; null until mapped
    isin      text,
    fund_name text not null,           -- ledger's own fund line (audit + unmapped-scheme grouping)
    folio     text not null,
    txn_date  date,                    -- null only for opening_balance rows (pre-history position)
    txn_type  text not null,           -- purchase|sip|switch_in|switch_out|redemption|swp|div_payout
                                       -- |div_reinvest|bonus|segregation|opening_balance|other (raw kept)
    description_raw text not null,
    nav           numeric(16,4),
    units         numeric(20,3),
    amount        numeric(18,2),
    stt           numeric(12,2),
    stamp_duty    numeric(12,2),       -- folded *** annotation rows
    tds           numeric(12,2),       -- folded *** TDS on Above *** rows
    balance_units numeric(20,3),       -- ledger's own running balance
    is_debit      boolean not null,
    source_file   text not null,
    page          int,
    approx        boolean not null default false, -- opening-balance-derived rows
    created_at    timestamptz not null default now()
);
create index if not exists transactions_client_date_idx on wealth.transactions (client_id, txn_date);
create index if not exists transactions_scheme_idx on wealth.transactions (scheme_id);

create table if not exists wealth.ledger_blocks ( -- one row per fund-folio block, ledger's own stats
    block_id  bigint generated always as identity primary key,
    client_id bigint not null references wealth.clients(client_id),
    scheme_id bigint references wealth.schemes(scheme_id),
    isin      text,
    fund_name text not null,
    folio     text not null,
    mv_date   date,
    market_value numeric(20,2),
    nav          numeric(18,4),
    abs_ret_pct  numeric(16,2),   -- dead blocks print garbage stats; stored as-is
    xirr_pct     numeric(14,2),          -- ledger generator's own per-block XIRR
    n_rows    int not null,
    source_file text not null
);
create index if not exists ledger_blocks_client_idx on wealth.ledger_blocks (client_id);

-- derived tables (rebuilt by their builder scripts, never hand-edited):
--   wealth.lots (build_lots.py)              wealth.client_benchmark (exact_benchmark.py)
--   wealth.behaviour_gap (behaviour_gap.py)  wealth.client_behaviour (behaviour_fingerprints.py)
--   wealth.advice_ledger (advice_ledger.py)  wealth.counterfactuals (counterfactuals.py)

-- PII hardening: this schema must never be reachable from the board's anon key
revoke all on schema wealth from anon, authenticated;
revoke all on all tables in schema wealth from anon, authenticated;

create index if not exists holdings_client_idx on wealth.holdings (client_id);
create index if not exists holdings_scheme_idx on wealth.holdings (scheme_id);
create index if not exists holdings_report_idx on wealth.holdings (report_id);

-- 05_scores.sql — atlas_global score journals, country roll-up, universe journal, signal IC.
-- Tables: lens_scores_daily, etf_scores_daily, country_daily, universe_snapshot, atlas_signal_ic.
-- Plan: "Schema `atlas_global` — core tables" (lens_scores_daily … atlas_signal_ic),
--       "Methodology spec §B" (stock lenses), "§C" (ETF lenses), "§D" (roll-ups), "§E" (IC).
-- Requires 00_core.sql, 03_classification.sql (country). Idempotent; no DROP; no function bodies.
-- Scores are 0–100 numeric(6,2) exactly as India stores them.

-- lens_scores_daily — stocks. Column set = India's atlas_lens_scores_daily 1:1 (so the ported
-- writer / ScoreDerivationTree adapter work unchanged) + cap_cohort (SPY-weight terciles:
-- mega | large | mid; deciles and the Leader flag are cut within the cohort). India-only lenses
-- (policy, promoter/smart-money flow subs) stay NULL here; the composite renormalises over the
-- present lenses.
CREATE TABLE IF NOT EXISTS atlas_global.lens_scores_daily (
    instrument_id          uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    date                   date          NOT NULL,
    asset_class            text,
    technical              numeric(6,2),
    fundamental            numeric(6,2),
    valuation              numeric(6,2),
    catalyst               numeric(6,2),
    flow                   numeric(6,2),
    policy                 numeric(6,2),
    tech_trend             numeric(6,2),
    tech_rs                numeric(6,2),
    tech_vol_contraction   numeric(6,2),
    tech_volume            numeric(6,2),
    fund_profitability     numeric(6,2),
    fund_margin            numeric(6,2),
    fund_growth            numeric(6,2),
    fund_balance_sheet     numeric(6,2),
    fund_op_leverage       numeric(6,2),
    val_pe_vs_sector       numeric(6,2),
    val_absolute_pe        numeric(6,2),
    val_pb                 numeric(6,2),
    val_ev_ebitda          numeric(6,2),
    val_52w_position       numeric(6,2),
    cat_earnings_strategy  numeric(6,2),
    cat_capital_action     numeric(6,2),
    cat_governance         numeric(6,2),
    flow_promoter          numeric(6,2),
    flow_institutional     numeric(6,2),
    flow_smart_money       numeric(6,2),
    policy_tailwind        numeric(6,2),
    composite              numeric(6,2),
    conviction_tier        text,
    valuation_zone         text,
    valuation_multiplier   numeric(6,4),
    smart_money_score      numeric(6,2),
    degradation_score      numeric(6,2),
    risk_flags             jsonb,
    evidence               jsonb,
    lenses_active          integer,
    coverage_factor        numeric(6,4),
    compute_run_id         uuid,
    computed_at            timestamptz,
    flow_accumulation      numeric,
    cap_cohort             text,
    CONSTRAINT lens_scores_daily_pkey PRIMARY KEY (instrument_id, date),
    CONSTRAINT chk_lens_scores_daily_cap_cohort
        CHECK (cap_cohort IS NULL OR cap_cohort IN ('mega', 'large', 'mid'))
);
CREATE INDEX IF NOT EXISTS ix_lens_scores_daily_date
    ON atlas_global.lens_scores_daily (date);
CREATE INDEX IF NOT EXISTS ix_lens_scores_daily_class_date
    ON atlas_global.lens_scores_daily (asset_class, date);
CREATE INDEX IF NOT EXISTS ix_lens_scores_daily_cohort_date
    ON atlas_global.lens_scores_daily (cap_cohort, date);

-- etf_scores_daily — five ETF lenses (each 0–100 = mean of present 0–25 sub-scores × 4), the
-- renormalised composite over present lenses, tier, and the peer-group axes the deciles are cut
-- within (peer_group = asset class × strategy, min members from atlas_thresholds; asset_group =
-- the parent used for the risk/cost percentiles). Sub-score columns follow the §C rows.
CREATE TABLE IF NOT EXISTS atlas_global.etf_scores_daily (
    instrument_id        uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    date                 date          NOT NULL,
    -- lenses
    technical            numeric(6,2),
    risk                 numeric(6,2),
    cost_liquidity       numeric(6,2),
    flow                 numeric(6,2),
    quality              numeric(6,2),
    -- technical subs (0–25)
    tech_trend           numeric(6,2),
    tech_rs_spy          numeric(6,2),
    tech_rs_peer         numeric(6,2),
    tech_structure       numeric(6,2),
    -- risk subs
    risk_vol             numeric(6,2),
    risk_mdd             numeric(6,2),
    risk_downside        numeric(6,2),
    risk_beta            numeric(6,2),
    -- cost & liquidity subs
    cost_expense         numeric(6,2),
    cost_adv             numeric(6,2),
    cost_aum             numeric(6,2),
    cost_concentration   numeric(6,2),
    -- flow subs
    flow_so_21d          numeric(6,2),
    flow_so_63d          numeric(6,2),
    -- quality / look-through subs
    quality_composite    numeric(6,2),                      -- holdings-weighted constituent stock composite
    quality_leaders      numeric(6,2),                      -- weight in Leader stocks × 100
    holdings_as_of       date,                              -- snapshot the quality lens read (stale-by-design for N-PORT names)
    -- blend
    composite            numeric(6,2),
    conviction_tier      text,
    peer_group           text,
    asset_group          text,
    lenses_active        integer,
    coverage_factor      numeric(6,4),
    evidence             jsonb,
    compute_run_id       uuid,
    computed_at          timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT etf_scores_daily_pkey PRIMARY KEY (instrument_id, date)
);
CREATE INDEX IF NOT EXISTS ix_etf_scores_daily_date
    ON atlas_global.etf_scores_daily (date);
CREATE INDEX IF NOT EXISTS ix_etf_scores_daily_peer_date
    ON atlas_global.etf_scores_daily (peer_group, date);

-- country_daily — the country view (§D): composite and RS are the representative ETF's
-- (largest AUM among ¬hedged ∧ ¬leveraged ∧ ¬active), breadth over all member ETFs.
CREATE TABLE IF NOT EXISTS atlas_global.country_daily (
    iso2               char(2)       NOT NULL REFERENCES atlas_global.country (iso2),
    date               date          NOT NULL,
    representative_id  uuid          REFERENCES atlas_global.instrument_master (instrument_id),
    n_etfs             integer,
    composite          numeric(6,2),
    rs_1w_spy          numeric(16,8),
    rs_1m_spy          numeric(16,8),
    rs_3m_spy          numeric(16,8),
    rs_6m_spy          numeric(16,8),
    rs_12m_spy         numeric(16,8),
    rs_24m_spy         numeric(16,8),
    breadth_pct        numeric(6,2),                        -- percent of member ETFs with composite ≥ rollup_breadth_min
    aum_usd_total      numeric,
    compute_run_id     uuid,
    computed_at        timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT country_daily_pkey PRIMARY KEY (iso2, date)
);
CREATE INDEX IF NOT EXISTS ix_country_daily_date
    ON atlas_global.country_daily (date);

-- universe_snapshot — forward-only daily membership journal (India's atlas_universe_snapshot
-- shape in USD + in_sp500 / aum_usd / basket_eligible). floor_usd is the threshold that was in
-- force that day, so a later floor change never rewrites history. exclusion_reason is stored
-- beside the decision, not left in the run's CSV, because the board reads this table directly:
-- a journal that says an instrument is out without saying why is not a glass box. The two
-- CHECKs keep the pair inseparable — the reason is one of the seven the writer can derive, and
-- it is present exactly when the row is out (so no row can say "excluded" and nothing more).
CREATE TABLE IF NOT EXISTS atlas_global.universe_snapshot (
    date                date          NOT NULL,
    instrument_id       uuid          NOT NULL REFERENCES atlas_global.instrument_master (instrument_id),
    in_universe         boolean       NOT NULL,
    exclusion_reason    text,
    in_sp500            boolean       NOT NULL DEFAULT false,
    adv_usd_median_60d  numeric(20,4),
    floor_usd           numeric(18,6) NOT NULL,
    aum_usd             numeric,
    basket_eligible     boolean       NOT NULL DEFAULT false,
    computed_at         timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT universe_snapshot_pkey PRIMARY KEY (date, instrument_id),
    CONSTRAINT chk_universe_snapshot_exclusion_reason
        CHECK (exclusion_reason IS NULL OR exclusion_reason IN
               ('no_bars', 'too_few_observations', 'stale',
                'not_sp500', 'leveraged', 'inverse', 'below_floor')),
    CONSTRAINT chk_universe_snapshot_reason_iff_excluded
        CHECK (in_universe = (exclusion_reason IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_universe_snapshot_instrument
    ON atlas_global.universe_snapshot (instrument_id);

-- atlas_signal_ic — India's signal journal shape (eval_signal.ensure_table) + entity in the PK,
-- because stocks and ETFs are evaluated within different cohorts (cap tercile vs asset group).
CREATE TABLE IF NOT EXISTS atlas_global.atlas_signal_ic (
    entity        text          NOT NULL,
    lens          text          NOT NULL,
    horizon_d     integer       NOT NULL,
    cohort        text          NOT NULL,
    era           text          NOT NULL,
    n_dates       integer       NOT NULL,
    mean_n        numeric(10,2),
    mean_ic       numeric(8,5),
    hit_rate      numeric(6,4),
    t_stat        numeric(10,4),
    mean_spread   numeric(10,6),
    cap_coverage  numeric(6,4),
    first_date    date,
    last_date     date,
    computed_at   timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT atlas_signal_ic_pkey PRIMARY KEY (entity, lens, horizon_d, cohort, era),
    CONSTRAINT chk_atlas_signal_ic_entity CHECK (entity IN ('stock', 'etf'))
);

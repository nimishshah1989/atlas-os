CREATE SCHEMA IF NOT EXISTS atlas_foundation;


SET default_table_access_method = heap;

--
-- Name: atlas_health_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_health_daily (
    data_date date NOT NULL,
    table_name character varying(64) NOT NULL,
    metric_name character varying(64) NOT NULL,
    value_today numeric,
    value_prior_day numeric,
    rolling_14d_avg numeric,
    rolling_14d_std numeric,
    pct_change_dod numeric,
    z_score numeric,
    is_anomaly boolean DEFAULT false NOT NULL,
    severity character varying(8),
    notes text,
    computed_at timestamp with time zone NOT NULL,
    CONSTRAINT chk_health_severity CHECK (((severity IS NULL) OR ((severity)::text = ANY ((ARRAY['info'::character varying, 'warn'::character varying, 'critical'::character varying])::text[]))))
);


--
-- Name: atlas_index_metrics_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_index_metrics_daily (
    index_code character varying(64),
    date date,
    ret_1d numeric(10,4),
    ret_1w numeric(10,4),
    ret_1m numeric(10,4),
    ret_3m numeric(10,4),
    ret_6m numeric(10,4),
    ret_12m numeric(10,4),
    rs_1w_nifty500 numeric(10,4),
    rs_1m_nifty500 numeric(10,4),
    rs_3m_nifty500 numeric(10,4),
    ema_10_index numeric(18,4),
    ema_20_index numeric(18,4),
    ema_10_ratio_nifty500 numeric(10,4),
    ema_20_ratio_nifty500 numeric(10,4),
    realized_vol_63 numeric(10,4),
    realized_vol_5d numeric(10,4),
    vol_252_median numeric(10,4),
    compute_run_id uuid,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    ret_24m numeric(10,4)
);


--
-- Name: atlas_kite_session; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_kite_session (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    access_token_enc bytea NOT NULL,
    session_type text DEFAULT 'active'::text NOT NULL,
    login_time timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: atlas_lens_scores_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_lens_scores_daily (
    instrument_id uuid NOT NULL,
    date date NOT NULL,
    asset_class text,
    technical numeric(6,2),
    fundamental numeric(6,2),
    valuation numeric(6,2),
    catalyst numeric(6,2),
    flow numeric(6,2),
    policy numeric(6,2),
    tech_trend numeric(6,2),
    tech_rs numeric(6,2),
    tech_vol_contraction numeric(6,2),
    tech_volume numeric(6,2),
    fund_profitability numeric(6,2),
    fund_margin numeric(6,2),
    fund_growth numeric(6,2),
    fund_balance_sheet numeric(6,2),
    fund_op_leverage numeric(6,2),
    val_pe_vs_sector numeric(6,2),
    val_absolute_pe numeric(6,2),
    val_pb numeric(6,2),
    val_ev_ebitda numeric(6,2),
    val_52w_position numeric(6,2),
    cat_earnings_strategy numeric(6,2),
    cat_capital_action numeric(6,2),
    cat_governance numeric(6,2),
    flow_promoter numeric(6,2),
    flow_institutional numeric(6,2),
    flow_smart_money numeric(6,2),
    policy_tailwind numeric(6,2),
    composite numeric(6,2),
    conviction_tier text,
    valuation_zone text,
    valuation_multiplier numeric(6,4),
    smart_money_score numeric(6,2),
    degradation_score numeric(6,2),
    risk_flags jsonb,
    evidence jsonb,
    lenses_active integer,
    coverage_factor numeric(6,4),
    compute_run_id uuid,
    computed_at timestamp with time zone,
    flow_accumulation numeric
);


--
-- Name: atlas_macro_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_macro_daily (
    date date,
    usdinr numeric(10,4),
    dxy numeric(10,4),
    india_10y_yield numeric(8,4),
    risk_free_91d numeric(8,4),
    fii_cash_equity_flow_cr numeric(14,2),
    breadth_pct_above_200dma numeric(5,2),
    dii_flow numeric(12,4),
    us_10y_yield numeric(6,4),
    brent_inr numeric(12,4),
    cpi_yoy numeric(6,4),
    vix_9d numeric(8,4)
);


--
-- Name: atlas_market_regime_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_market_regime_daily (
    date date NOT NULL,
    nifty500_close numeric(18,4),
    nifty500_ema_50 numeric(18,4),
    nifty500_ema_200 numeric(18,4),
    nifty500_above_ema_50 boolean,
    nifty500_above_ema_200 boolean,
    nifty500_ema_50_slope numeric(10,4),
    nifty500_ema_200_slope numeric(10,4),
    pct_above_ema_20 numeric(10,4),
    pct_above_ema_50 numeric(10,4),
    pct_above_ema_200 numeric(10,4),
    advances_count integer,
    declines_count integer,
    unchanged_count integer,
    ad_ratio numeric(10,4),
    ad_line numeric(18,4),
    ad_line_slope_21 numeric(10,4),
    mcclellan_oscillator numeric(10,4),
    mcclellan_summation numeric(18,4),
    new_52w_highs integer,
    new_52w_lows integer,
    net_new_highs integer,
    new_high_low_ratio numeric(10,4),
    pct_in_strong_states numeric(10,4),
    pct_weinstein_pass numeric(10,4),
    india_vix numeric(10,4),
    realized_vol_5d_nifty500 numeric(10,4),
    vol_252_median_nifty500 numeric(10,4),
    regime_state character varying(32),
    deployment_multiplier numeric(10,4),
    dislocation_active boolean,
    dislocation_started date,
    compute_run_id uuid,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    pct_above_ema_100 numeric,
    pct_4w_high numeric
);


--
-- Name: atlas_pipeline_runs; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_pipeline_runs (
    run_id uuid NOT NULL,
    script_name character varying(64) NOT NULL,
    milestone character varying(8),
    phase character varying(32),
    started_at timestamp with time zone NOT NULL,
    ended_at timestamp with time zone,
    status character varying(16) NOT NULL,
    rows_written bigint,
    error_message text,
    host character varying(64),
    git_sha character varying(40),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_pipeline_runs_status CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'running'::character varying, 'success'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: atlas_sector_master; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_sector_master (
    sector_name character varying(64),
    primary_nse_index character varying(32),
    secondary_nse_indices text[],
    fallback_benchmark character varying(32),
    notes text,
    is_active boolean,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


--
-- Name: atlas_thresholds; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_thresholds (
    threshold_key character varying(64),
    threshold_value numeric(18,6),
    category character varying(32),
    description text,
    methodology_section character varying(16),
    units character varying(16),
    min_allowed numeric(18,6),
    max_allowed numeric(18,6),
    default_value numeric(18,6),
    last_modified_by character varying(64),
    last_modified_at timestamp with time zone,
    is_active boolean,
    created_at timestamp with time zone
);


--
-- Name: atlas_universe_funds; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_universe_funds (
    mstar_id character varying(32),
    scheme_name character varying(256),
    amc character varying(128),
    broad_category character varying(32),
    category_name character varying(64),
    plan_type character varying(16),
    option_type character varying(16),
    benchmark_code character varying(32),
    inception_date date,
    effective_from date,
    effective_to date,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    aum_cr numeric(12,2),
    aum_as_of date
);


--
-- Name: atlas_validator_results; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.atlas_validator_results (
    run_id uuid NOT NULL,
    validator character varying(16) NOT NULL,
    ran_at timestamp with time zone NOT NULL,
    total_checks integer NOT NULL,
    failures integer NOT NULL,
    status character varying(8) NOT NULL,
    failure_summary jsonb,
    host character varying(64),
    git_sha character varying(40),
    CONSTRAINT chk_validator_results_status CHECK (((status)::text = ANY ((ARRAY['PASS'::character varying, 'FAIL'::character varying])::text[])))
);


--
-- Name: breadth_nifty500_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.breadth_nifty500_daily (
    date date NOT NULL,
    n_members bigint,
    above_21 bigint,
    above_50 bigint,
    above_200 bigint,
    at_52w_high bigint,
    at_52w_low bigint,
    net_new_highs bigint,
    gc_50_200 bigint,
    avg_rsi_14 numeric,
    idx_close numeric,
    idx_ret_3m numeric
);


--
-- Name: compute_state; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.compute_state (
    instrument_id uuid NOT NULL,
    asset_class text NOT NULL,
    symbol text NOT NULL,
    status text NOT NULL,
    rows_written integer,
    last_date date,
    error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: de_etf_holdings; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.de_etf_holdings (
    ticker character varying(30),
    instrument_id uuid,
    weight numeric(8,6),
    as_of_date date,
    last_disclosed_date date,
    created_at timestamp with time zone
);


--
-- Name: de_etf_master; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.de_etf_master (
    ticker character varying(30),
    name character varying(200),
    exchange character varying(20),
    country character varying(10),
    currency character varying(5),
    sector character varying(100),
    asset_class character varying(50),
    category character varying(100),
    benchmark character varying(50),
    expense_ratio numeric(6,4),
    inception_date date,
    is_active boolean,
    source character varying(20),
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    mstar_id character varying(20)
);


--
-- Name: de_index_constituents; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.de_index_constituents (
    index_code character varying(50),
    instrument_id uuid,
    effective_from date,
    weight_pct numeric(6,4),
    effective_to date,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


--
-- Name: de_mf_holdings; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.de_mf_holdings (
    id uuid,
    mstar_id character varying(20),
    as_of_date date,
    holding_name character varying(500),
    isin character varying(12),
    instrument_id uuid,
    weight_pct numeric(9,4),
    shares_held bigint,
    market_value numeric(18,4),
    sector_code character varying(50),
    is_mapped boolean,
    created_at timestamp with time zone
);


--
-- Name: de_mf_master; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.de_mf_master (
    mstar_id character varying(20),
    amfi_code character varying(20),
    isin character varying(12),
    fund_name character varying(500),
    amc_name character varying(200),
    category_name character varying(200),
    broad_category character varying(100),
    is_index_fund boolean,
    is_etf boolean,
    is_active boolean,
    inception_date date,
    closure_date date,
    merged_into_mstar_id character varying(20),
    primary_benchmark character varying(100),
    expense_ratio numeric(6,4),
    investment_strategy text,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    purchase_mode integer
);


--
-- Name: de_mf_nav_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.de_mf_nav_daily (
    nav_date date,
    mstar_id character varying(20),
    nav numeric(18,4),
    nav_adj numeric(18,4),
    nav_change numeric(18,4),
    nav_change_pct numeric(10,4),
    return_1d numeric(10,4),
    return_1w numeric(10,4),
    return_1m numeric(10,4),
    return_3m numeric(10,4),
    return_6m numeric(10,4),
    return_1y numeric(10,4),
    return_3y numeric(10,4),
    return_5y numeric(10,4),
    return_10y numeric(10,4),
    nav_52wk_high numeric(18,4),
    nav_52wk_low numeric(18,4),
    data_status character varying(20),
    source_file_id uuid,
    pipeline_run_id integer,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


--
-- Name: delivery_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.delivery_daily (
    instrument_id uuid NOT NULL,
    date date NOT NULL,
    delivery_pct numeric,
    delivery_avg_30d numeric,
    delivery_avg_60d numeric,
    delivery_trend numeric,
    delivery_updown_asym numeric
);


--
-- Name: delivery_raw; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.delivery_raw (
    instrument_id uuid NOT NULL,
    date date NOT NULL,
    delivery_pct numeric
);


--
-- Name: equity_marketcap; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.equity_marketcap (
    instrument_id uuid NOT NULL,
    symbol text,
    market_cap_cr numeric,
    face_value numeric,
    fetched_at timestamp with time zone
);


--
-- Name: financials_annual; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.financials_annual (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    period_end date NOT NULL,
    consolidated boolean NOT NULL,
    equity numeric,
    borrowings_noncurrent numeric,
    borrowings_current numeric,
    total_borrowings numeric,
    trade_payables_current numeric,
    trade_payables_noncurrent numeric,
    equity_and_liabilities numeric,
    seq_number bigint,
    xbrl_url text,
    source text DEFAULT 'NSE_XBRL'::text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: financials_quarterly; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.financials_quarterly (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    period_end date NOT NULL,
    consolidated boolean NOT NULL,
    revenue numeric,
    other_income numeric,
    total_income numeric,
    total_expenses numeric,
    finance_costs numeric,
    depreciation numeric,
    ebit numeric,
    ebitda numeric,
    pbt numeric,
    tax numeric,
    pat numeric,
    eps numeric,
    ebitda_margin numeric,
    net_margin numeric,
    is_bank boolean,
    seq_number bigint,
    xbrl_url text,
    source text DEFAULT 'NSE_XBRL'::text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    debt_equity_ratio numeric,
    debt_service_coverage numeric,
    paid_up_equity_capital numeric
);


--
-- Name: fund_rank_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.fund_rank_daily (
    date date NOT NULL,
    mstar_id character varying(32) NOT NULL,
    category character varying(128),
    composite numeric(7,3),
    breadth numeric(7,4),
    n_scored integer,
    cat_rank integer,
    cat_size integer,
    pct_band text,
    computed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: index_prices; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.index_prices (
    index_code text NOT NULL,
    date date NOT NULL,
    open numeric(18,6),
    high numeric(18,6),
    low numeric(18,6),
    close numeric(18,6),
    volume bigint,
    source text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: instrument_master; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.instrument_master (
    instrument_id uuid NOT NULL,
    asset_class text NOT NULL,
    symbol text NOT NULL,
    name text,
    isin text,
    series text,
    listing_date date,
    kite_token bigint,
    exchange text DEFAULT 'NSE'::text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    source text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    sector text,
    industry text
);


--
-- Name: lens_bulk_deals; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.lens_bulk_deals (
    instrument_id uuid,
    symbol text NOT NULL,
    deal_date date NOT NULL,
    deal_type text NOT NULL,
    client_name text NOT NULL,
    buy_sell text NOT NULL,
    qty bigint,
    price numeric,
    is_institutional boolean,
    is_superstar boolean,
    superstar_name text,
    source text DEFAULT 'NSE'::text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: lens_filings; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.lens_filings (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    filing_date date NOT NULL,
    category text,
    category_bucket text NOT NULL,
    signal_priority text NOT NULL,
    subject_text text,
    source_url text,
    nse_seq_id text NOT NULL,
    source text DEFAULT 'NSE'::text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: lens_filings_state; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.lens_filings_state (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    status text NOT NULL,
    filings integer,
    error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: lens_insider; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.lens_insider (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    transaction_date date NOT NULL,
    person_name text NOT NULL,
    person_category text,
    signal_type text NOT NULL,
    securities_traded numeric,
    value_cr numeric,
    price_per_share numeric,
    pledge_pct_after numeric,
    acq_mode text,
    source text DEFAULT 'NSE_PIT'::text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: lens_insider_state; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.lens_insider_state (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    status text NOT NULL,
    records integer,
    error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: lens_shareholding; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.lens_shareholding (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    period_end date NOT NULL,
    promoter_pct numeric,
    public_pct numeric,
    employee_trusts_pct numeric,
    source text DEFAULT 'NSE'::text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: lens_shareholding_state; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.lens_shareholding_state (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    status text NOT NULL,
    quarters integer,
    error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mv_sector_breadth; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.mv_sector_breadth (
    as_of_date date,
    sector_name character varying(64),
    constituent_count bigint,
    pct_above_ema21 numeric,
    pct_above_ema50 numeric,
    pct_above_ema200 numeric,
    pct_at_52wh numeric,
    breadth_by_window jsonb,
    breadth_by_strength jsonb,
    top_movers jsonb,
    bottom_movers jsonb,
    refreshed_at timestamp with time zone
);


--
-- Name: mv_sector_cards; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.mv_sector_cards (
    as_of_date date,
    sector_name character varying(64),
    constituent_count bigint,
    ret_1w numeric,
    ret_1m numeric,
    ret_3m numeric,
    ret_6m numeric,
    ret_12m numeric,
    rs_1m numeric,
    rs_3m numeric,
    rs_6m numeric,
    vol_60d_ann numeric,
    pct_above_ema21 numeric,
    pct_above_ema200 numeric,
    pct_at_52wh numeric,
    hhi_concentration numeric,
    buy_signal_count bigint,
    confidence_distribution jsonb,
    verdict character varying(16),
    verdict_abbr text,
    refreshed_at timestamp with time zone
);


--
-- Name: mv_sector_deepdive; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.mv_sector_deepdive (
    sector_name character varying(64),
    verdict character varying,
    constituent_count integer,
    data_as_of date,
    returns jsonb,
    rs_windows jsonb,
    pct_above_ema21 numeric,
    pct_above_ema200 numeric,
    pct_at_52wh numeric,
    constituents_top30 jsonb,
    open_signals jsonb,
    strength_dist jsonb,
    top_picks_top10 jsonb,
    refreshed_at timestamp with time zone
);


--
-- Name: mv_sector_rrg; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.mv_sector_rrg (
    as_of_date date,
    sector_name character varying(64),
    rs_ratio_current numeric,
    rs_momentum_current numeric,
    quadrant_current text,
    trail_6w jsonb,
    refreshed_at timestamp with time zone
);


--
-- Name: mv_stock_landscape; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.mv_stock_landscape (
    as_of_date date,
    instrument_id uuid,
    symbol character varying(32),
    company_name character varying(256),
    sector character varying(64),
    industry character varying(128),
    cap_tier character varying(8),
    ret_1m numeric,
    ret_3m numeric,
    ret_6m numeric,
    ret_12m numeric,
    rs_1w_nifty500 numeric,
    rs_1m_nifty500 numeric,
    rs_3m_nifty500 numeric,
    conviction_score numeric(6,4),
    conviction_tier character varying(32),
    confidence_label character varying(32),
    composite_score numeric,
    action text,
    bubble_quadrant text,
    liquidity_proxy_cr numeric,
    close_price numeric,
    matrix_tenure_dominant text,
    matrix_action_sign text,
    cell_id uuid,
    cell_predicted_excess numeric(10,6),
    cell_signal_confidence numeric(5,4),
    cell_fire_date date,
    cell_ic numeric(5,4),
    cell_friction_adjusted_excess numeric(10,6),
    composite_trajectory_30d jsonb,
    realized_vol_63 numeric,
    refreshed_at timestamp with time zone
);


--
-- Name: ohlcv_etf; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.ohlcv_etf (
    ticker text NOT NULL,
    isin text,
    date date NOT NULL,
    open numeric(18,6),
    high numeric(18,6),
    low numeric(18,6),
    close numeric(18,6),
    close_adj numeric(18,6),
    adj_factor numeric(20,10) DEFAULT 1 NOT NULL,
    volume bigint,
    source text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ohlcv_stock; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.ohlcv_stock (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    date date NOT NULL,
    open numeric(18,6),
    high numeric(18,6),
    low numeric(18,6),
    close numeric(18,6),
    prev_close numeric(18,6),
    open_adj numeric(18,6),
    high_adj numeric(18,6),
    low_adj numeric(18,6),
    close_adj numeric(18,6),
    adj_factor numeric(20,10) DEFAULT 1 NOT NULL,
    volume bigint,
    trades integer,
    series text,
    source text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: policy_registry; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.policy_registry (
    policy_id text,
    policy_name text,
    description text,
    impact text,
    beneficiary_sectors jsonb,
    beneficiary_keywords jsonb,
    is_active boolean,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


--
-- Name: screener_ratios; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.screener_ratios (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    stock_pe numeric,
    pb numeric,
    ev_ebitda numeric,
    roe numeric,
    roce numeric,
    market_cap numeric,
    book_value numeric,
    current_price numeric,
    div_yield numeric,
    debt_to_equity numeric,
    as_of date NOT NULL,
    source text DEFAULT 'SCREENER'::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: screener_state; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.screener_state (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    status text NOT NULL,
    quarters integer,
    annuals integer,
    note text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sector_index_returns; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.sector_index_returns (
    index_code text NOT NULL,
    date date NOT NULL,
    ret_1m numeric,
    ret_3m numeric,
    ret_6m numeric,
    ret_12m numeric
);


--
-- Name: sector_lens_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.sector_lens_daily (
    sector text NOT NULL,
    date date NOT NULL,
    technical numeric,
    fundamental numeric,
    valuation numeric,
    catalyst numeric,
    flow numeric,
    policy numeric,
    breadth_technical numeric,
    breadth_fundamental numeric,
    breadth_valuation numeric,
    breadth_catalyst numeric,
    breadth_flow numeric,
    breadth_policy numeric,
    dispersion numeric,
    n_constituents integer,
    total_free_float_cr numeric,
    computed_at timestamp with time zone DEFAULT now()
);


--
-- Name: technical_daily; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.technical_daily (
    instrument_id uuid NOT NULL,
    asset_class text NOT NULL,
    symbol text NOT NULL,
    date date NOT NULL,
    ema_21 numeric(18,6),
    ema_50 numeric(18,6),
    ema_200 numeric(18,6),
    rsi_14 numeric(12,6),
    ret_1d numeric(16,8),
    ret_1w numeric(16,8),
    ret_1m numeric(16,8),
    ret_3m numeric(16,8),
    ret_6m numeric(16,8),
    ret_12m numeric(16,8),
    rs_1d_n50 numeric(16,8),
    rs_1w_n50 numeric(16,8),
    rs_1m_n50 numeric(16,8),
    rs_3m_n50 numeric(16,8),
    rs_6m_n50 numeric(16,8),
    rs_12m_n50 numeric(16,8),
    rs_1d_n500 numeric(16,8),
    rs_1w_n500 numeric(16,8),
    rs_1m_n500 numeric(16,8),
    rs_3m_n500 numeric(16,8),
    rs_6m_n500 numeric(16,8),
    rs_12m_n500 numeric(16,8),
    above_ema_21 boolean,
    above_ema_50 boolean,
    above_ema_200 boolean,
    compute_run_id uuid,
    computed_at timestamp with time zone DEFAULT now() NOT NULL,
    atr_14 numeric,
    bb_width numeric,
    vol_ratio_30d numeric,
    vol_ratio_60d numeric,
    pos_52w numeric,
    rs_1m_sector numeric,
    rs_3m_sector numeric,
    rs_6m_sector numeric,
    rs_12m_sector numeric
);


--
-- Name: xbrl_state; Type: TABLE; Schema: atlas_foundation; Owner: -
--

CREATE TABLE atlas_foundation.xbrl_state (
    instrument_id uuid NOT NULL,
    symbol text NOT NULL,
    status text NOT NULL,
    quarters integer,
    error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    annuals integer
);


--
-- Name: atlas_kite_session atlas_kite_session_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.atlas_kite_session
    ADD CONSTRAINT atlas_kite_session_pkey PRIMARY KEY (id);


--
-- Name: atlas_lens_scores_daily atlas_lens_scores_daily_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.atlas_lens_scores_daily
    ADD CONSTRAINT atlas_lens_scores_daily_pkey PRIMARY KEY (instrument_id, date);


--
-- Name: atlas_market_regime_daily atlas_market_regime_daily_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.atlas_market_regime_daily
    ADD CONSTRAINT atlas_market_regime_daily_pkey PRIMARY KEY (date);


--
-- Name: breadth_nifty500_daily breadth_nifty500_daily_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.breadth_nifty500_daily
    ADD CONSTRAINT breadth_nifty500_daily_pkey PRIMARY KEY (date);


--
-- Name: compute_state compute_state_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.compute_state
    ADD CONSTRAINT compute_state_pkey PRIMARY KEY (instrument_id);


--
-- Name: delivery_daily delivery_daily_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.delivery_daily
    ADD CONSTRAINT delivery_daily_pkey PRIMARY KEY (instrument_id, date);


--
-- Name: delivery_raw delivery_raw_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.delivery_raw
    ADD CONSTRAINT delivery_raw_pkey PRIMARY KEY (instrument_id, date);


--
-- Name: equity_marketcap equity_marketcap_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.equity_marketcap
    ADD CONSTRAINT equity_marketcap_pkey PRIMARY KEY (instrument_id);


--
-- Name: financials_annual financials_annual_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.financials_annual
    ADD CONSTRAINT financials_annual_pkey PRIMARY KEY (instrument_id, period_end, consolidated);


--
-- Name: financials_quarterly financials_quarterly_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.financials_quarterly
    ADD CONSTRAINT financials_quarterly_pkey PRIMARY KEY (instrument_id, period_end, consolidated);


--
-- Name: fund_rank_daily fund_rank_daily_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.fund_rank_daily
    ADD CONSTRAINT fund_rank_daily_pkey PRIMARY KEY (mstar_id, date);


--
-- Name: index_prices index_prices_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.index_prices
    ADD CONSTRAINT index_prices_pkey PRIMARY KEY (index_code, date);


--
-- Name: instrument_master instrument_master_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.instrument_master
    ADD CONSTRAINT instrument_master_pkey PRIMARY KEY (instrument_id);


--
-- Name: lens_bulk_deals lens_bulk_deals_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.lens_bulk_deals
    ADD CONSTRAINT lens_bulk_deals_pkey PRIMARY KEY (symbol, deal_date, client_name, buy_sell);


--
-- Name: lens_filings lens_filings_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.lens_filings
    ADD CONSTRAINT lens_filings_pkey PRIMARY KEY (instrument_id, nse_seq_id);


--
-- Name: lens_filings_state lens_filings_state_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.lens_filings_state
    ADD CONSTRAINT lens_filings_state_pkey PRIMARY KEY (instrument_id);


--
-- Name: lens_insider lens_insider_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.lens_insider
    ADD CONSTRAINT lens_insider_pkey PRIMARY KEY (instrument_id, transaction_date, person_name, signal_type);


--
-- Name: lens_insider_state lens_insider_state_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.lens_insider_state
    ADD CONSTRAINT lens_insider_state_pkey PRIMARY KEY (instrument_id);


--
-- Name: lens_shareholding lens_shareholding_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.lens_shareholding
    ADD CONSTRAINT lens_shareholding_pkey PRIMARY KEY (instrument_id, period_end);


--
-- Name: lens_shareholding_state lens_shareholding_state_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.lens_shareholding_state
    ADD CONSTRAINT lens_shareholding_state_pkey PRIMARY KEY (instrument_id);


--
-- Name: ohlcv_etf ohlcv_etf_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.ohlcv_etf
    ADD CONSTRAINT ohlcv_etf_pkey PRIMARY KEY (ticker, date);


--
-- Name: ohlcv_stock ohlcv_stock_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.ohlcv_stock
    ADD CONSTRAINT ohlcv_stock_pkey PRIMARY KEY (instrument_id, date);


--
-- Name: screener_ratios screener_ratios_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.screener_ratios
    ADD CONSTRAINT screener_ratios_pkey PRIMARY KEY (instrument_id);


--
-- Name: screener_state screener_state_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.screener_state
    ADD CONSTRAINT screener_state_pkey PRIMARY KEY (instrument_id);


--
-- Name: sector_index_returns sector_index_returns_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.sector_index_returns
    ADD CONSTRAINT sector_index_returns_pkey PRIMARY KEY (index_code, date);


--
-- Name: sector_lens_daily sector_lens_daily_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.sector_lens_daily
    ADD CONSTRAINT sector_lens_daily_pkey PRIMARY KEY (sector, date);


--
-- Name: technical_daily technical_daily_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.technical_daily
    ADD CONSTRAINT technical_daily_pkey PRIMARY KEY (instrument_id, date);


--
-- Name: xbrl_state xbrl_state_pkey; Type: CONSTRAINT; Schema: atlas_foundation; Owner: -
--

ALTER TABLE ONLY atlas_foundation.xbrl_state
    ADD CONSTRAINT xbrl_state_pkey PRIMARY KEY (instrument_id);


--
-- Name: ix_atlas_index_metrics_daily_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_atlas_index_metrics_daily_date ON atlas_foundation.atlas_index_metrics_daily USING btree (date);


--
-- Name: ix_atlas_macro_daily_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_atlas_macro_daily_date ON atlas_foundation.atlas_macro_daily USING btree (date);


--
-- Name: ix_atlas_market_regime_daily_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_atlas_market_regime_daily_date ON atlas_foundation.atlas_market_regime_daily USING btree (date);


--
-- Name: ix_de_etf_holdings_instrument_id; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_de_etf_holdings_instrument_id ON atlas_foundation.de_etf_holdings USING btree (instrument_id);


--
-- Name: ix_de_etf_holdings_ticker; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_de_etf_holdings_ticker ON atlas_foundation.de_etf_holdings USING btree (ticker);


--
-- Name: ix_de_etf_master_ticker; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_de_etf_master_ticker ON atlas_foundation.de_etf_master USING btree (ticker);


--
-- Name: ix_de_mf_holdings_as_of_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_de_mf_holdings_as_of_date ON atlas_foundation.de_mf_holdings USING btree (as_of_date);


--
-- Name: ix_de_mf_holdings_instrument_id; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_de_mf_holdings_instrument_id ON atlas_foundation.de_mf_holdings USING btree (instrument_id);


--
-- Name: ix_de_mf_holdings_mstar_id; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_de_mf_holdings_mstar_id ON atlas_foundation.de_mf_holdings USING btree (mstar_id);


--
-- Name: ix_de_mf_master_mstar_id; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_de_mf_master_mstar_id ON atlas_foundation.de_mf_master USING btree (mstar_id);


--
-- Name: ix_de_mf_nav_daily_mstar_id_nav_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_de_mf_nav_daily_mstar_id_nav_date ON atlas_foundation.de_mf_nav_daily USING btree (mstar_id, nav_date);


--
-- Name: ix_fs_cards_sector; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_fs_cards_sector ON atlas_foundation.mv_sector_cards USING btree (sector_name);


--
-- Name: ix_fs_dd_sector; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_fs_dd_sector ON atlas_foundation.mv_sector_deepdive USING btree (sector_name);


--
-- Name: ix_fs_lens_class_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_fs_lens_class_date ON atlas_foundation.atlas_lens_scores_daily USING btree (asset_class, date);


--
-- Name: ix_fs_master_token; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_fs_master_token ON atlas_foundation.instrument_master USING btree (kite_token);


--
-- Name: ix_fs_ohlcv_stock_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_fs_ohlcv_stock_date ON atlas_foundation.ohlcv_stock USING btree (date);


--
-- Name: ix_fs_ohlcv_stock_symbol; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_fs_ohlcv_stock_symbol ON atlas_foundation.ohlcv_stock USING btree (symbol, date);


--
-- Name: ix_fs_tech_daily_class_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_fs_tech_daily_class_date ON atlas_foundation.technical_daily USING btree (asset_class, date);


--
-- Name: ix_fs_univ_funds_mstar; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_fs_univ_funds_mstar ON atlas_foundation.atlas_universe_funds USING btree (mstar_id);


--
-- Name: ix_fund_rank_daily_cat_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_fund_rank_daily_cat_date ON atlas_foundation.fund_rank_daily USING btree (category, date);


--
-- Name: ix_fund_rank_daily_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_fund_rank_daily_date ON atlas_foundation.fund_rank_daily USING btree (date);


--
-- Name: ix_lens_filings_instrument; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_lens_filings_instrument ON atlas_foundation.lens_filings USING btree (instrument_id);


--
-- Name: ix_mv_sector_breadth_sector_name; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_mv_sector_breadth_sector_name ON atlas_foundation.mv_sector_breadth USING btree (sector_name);


--
-- Name: ix_mv_sector_rrg_sector_name; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE INDEX ix_mv_sector_rrg_sector_name ON atlas_foundation.mv_sector_rrg USING btree (sector_name);


--
-- Name: uq_de_mf_master_mstar_id; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE UNIQUE INDEX uq_de_mf_master_mstar_id ON atlas_foundation.de_mf_master USING btree (mstar_id);


--
-- Name: uq_de_mf_nav_daily_date_mstar; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE UNIQUE INDEX uq_de_mf_nav_daily_date_mstar ON atlas_foundation.de_mf_nav_daily USING btree (nav_date, mstar_id);


--
-- Name: ux_aimd_code_date; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE UNIQUE INDEX ux_aimd_code_date ON atlas_foundation.atlas_index_metrics_daily USING btree (index_code, date);


--
-- Name: ux_fs_master_class_symbol; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE UNIQUE INDEX ux_fs_master_class_symbol ON atlas_foundation.instrument_master USING btree (asset_class, symbol);


--
-- Name: ux_sector_rrg_date_sector; Type: INDEX; Schema: atlas_foundation; Owner: -
--

CREATE UNIQUE INDEX ux_sector_rrg_date_sector ON atlas_foundation.mv_sector_rrg USING btree (as_of_date, sector_name);


--
-- Name: sector_index_returns; Type: ROW SECURITY; Schema: atlas_foundation; Owner: -
--

ALTER TABLE atlas_foundation.sector_index_returns ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--



-- Fast MAX(date) for the data-status freshness panel (added 2026-07-03).
CREATE INDEX IF NOT EXISTS idx_technical_daily_date ON atlas_foundation.technical_daily (date);

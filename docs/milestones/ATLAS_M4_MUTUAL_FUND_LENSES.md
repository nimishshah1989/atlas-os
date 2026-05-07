# Atlas-M4 — Mutual Fund Three-Lens Engine

**Document:** ATLAS_M4_MUTUAL_FUND_LENSES
**Status:** v0
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**Builder:** Claude Code (intended executor)
**References:**
- `00_METHODOLOGY_LOCK.md` (Section 12 — three-lens framework)
- `01_BACKEND_ARCHITECTURE.md` (Section 5.6 threshold discipline; Section 5.3 pipeline stage 7)
- `02_DATABASE_SCHEMA.md` (Sections 3.6, 3.7, 4.4 — fund tables)
- `03_VALIDATION_FRAMEWORK.md` (Tier 4 Category E — fund holdings reconstruction)
- `04_THRESHOLD_CATALOG.md` (Section 11 — fund lens thresholds)
- `ATLAS_M2_STOCK_ETF_METRICS.md` (provides stock states for Lens 3)
- `ATLAS_M3_SECTOR_AND_MARKET.md` (provides sector states for Lens 2)

---

## 1. Goal

Build the mutual fund classification engine across three independent lenses:

1. **Lens 1 — NAV Behavior** (daily refresh) — apply RS, momentum, and risk math to the fund's NAV time series; classify into six NAV states using longer windows (1M/3M/6M) appropriate for fund holding periods
2. **Lens 2 — Sector Composition** (monthly refresh) — what % of fund AUM is in {Overweight, Neutral} sectors? In Avoid sectors? Three states: Aligned / Mixed / Misaligned
3. **Lens 3 — Holdings Quality** (monthly refresh) — what % of fund AUM is in {Leader, Strong, Emerging} stocks? In {Weak, Laggard}? Three states: Strong-Holdings / Decent / Weak-Holdings

After this milestone:

- `atlas_fund_metrics_daily` populated for ~400 funds × ~3,000 days = ~1.2M rows (Lens 1 inputs, daily refresh)
- `atlas_fund_lens_monthly` populated for ~400 funds × ~144 months = ~58K rows (Lens 2 + Lens 3, monthly refresh on disclosure cycle)
- `atlas_fund_states_daily` populated with the three-lens state tuple — daily refresh of `nav_state`, monthly refresh of `composition_state` and `holdings_state`

**No fund decisions yet.** That's M5. M4 produces lens metrics and lens states only.

---

## 2. Dependencies

### 2.1 Predecessors

**Atlas-M2** must be complete and signed off:
- Stock states populated (used for Lens 3 holdings quality classification)

**Atlas-M3** must be complete and signed off:
- Sector states populated (used for Lens 2 composition classification)

**Atlas-M1**:
- `atlas_universe_funds` (~400 funds) populated
- `atlas_fund_category_benchmark_map` populated (maps fund category to benchmark)

### 2.2 Foundation Document Consistency Checks

| Foundation Reference | What M4 Depends On |
|---|---|
| Methodology 12.1 | Lens 1: NAV state taxonomy — 6 states using 1M/3M/6M windows |
| Methodology 12.2 | Lens 2: 3 composition states (Aligned/Mixed/Misaligned) using `aligned_aum_pct` and `avoid_aum_pct` |
| Methodology 12.3 | Lens 3: 3 holdings states (Strong-Holdings/Decent/Weak-Holdings) using `strong_aum_pct` and `weak_aum_pct` |
| Methodology 12.4 | Three-tuple stored daily; Lens 1 daily refresh, Lens 2/3 monthly refresh |
| Schema 3.6 | atlas_fund_metrics_daily — daily NAV-derived metrics |
| Schema 3.7 | atlas_fund_lens_monthly — monthly Lens 2/3 metrics |
| Schema 4.4 | atlas_fund_states_daily — three-tuple state with refresh-date tracking |
| Threshold Catalog 11 | 4 fund threshold keys |
| Architecture 5.6 | All classifiers receive thresholds dict |

### 2.3 Required JIP Data Core Tables (Read-Only)

| Table | Used For | Identifier | Date Column |
|---|---|---|---|
| `de_mf_nav_daily` | Fund NAV time series for Lens 1 | `mstar_id` | `nav_date` |
| `de_mf_holdings` | Monthly holdings disclosures for Lens 2 + Lens 3 | `mstar_id`, `instrument_id` | `as_of_date`, `last_disclosed_date` |

### 2.4 Required Atlas Tables (Read)

| Table | Used For |
|---|---|
| `atlas_universe_funds` | The ~400-fund universe with category/benchmark mapping |
| `atlas_fund_category_benchmark_map` | Category-to-benchmark mapping |
| `atlas_benchmark_master` | Benchmark identifiers for category benchmark RS |
| `atlas_index_metrics_daily` | Category benchmark price series (Nifty 100, Midcap 150, etc.) |
| `atlas_universe_stocks` | Stock instrument_id ↔ universe membership |
| `atlas_stock_states_daily` | Stock RS states (for Lens 3) |
| `atlas_sector_states_daily` | Sector states (for Lens 2) |
| `atlas_thresholds` | Loaded once per pipeline run |

### 2.5 Important Data Note — Holdings Disclosure Cadence

Mutual funds disclose portfolios monthly to AMFI (most disclose at month-end with a lag of 5-10 business days). Morningstar aggregates these disclosures into `de_mf_holdings`.

For Atlas-M4:
- Holdings data refreshes ~once per month per fund
- The `as_of_date` column is the portfolio date (e.g., 2026-04-30)
- The `last_disclosed_date` column is when Morningstar received the disclosure (e.g., 2026-05-08)
- Lens 2 and Lens 3 are computed once per disclosure cycle, not daily
- NAV-based Lens 1 refreshes daily

---

## 3. Deliverables

### 3.1 Code Deliverables

```
atlas-backend/atlas/compute/
├── funds.py                    # Three-lens fund pipeline (Stage 7)
├── lens_nav.py                 # Lens 1 — NAV behavior
├── lens_composition.py         # Lens 2 — sector composition
└── lens_holdings.py            # Lens 3 — holdings quality
```

```
atlas-backend/scripts/
├── m4_backfill.py              # Historical backfill for fund lenses
└── m4_daily.py                 # Daily incremental run (Lens 1 only most days)
```

### 3.2 Database Deliverables

| Table | Expected Rows |
|---|---|
| `atlas_fund_metrics_daily` | ~1.2M (400 funds × 3,000 days) |
| `atlas_fund_lens_monthly` | ~58K (400 funds × 144 months) |
| `atlas_fund_states_daily` | ~1.2M |

---

## 4. Phase A — Lens 1: NAV Behavior

### 4.1 Goal

Treat each fund's NAV as a price series. Compute returns, RS against category benchmark, momentum, and risk metrics. Classify into six NAV states using the longer 1M/3M/6M classification windows appropriate for fund holding periods.

### 4.2 Compute NAV-Derived Metrics

```python
import polars as pl
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import date, timedelta

def compute_fund_nav_metrics(
    target_date: date,
    is_backfill: bool = False,
    backfill_start: date | None = None,
) -> dict:
    """
    Compute NAV-derived metrics for all funds in atlas_universe_funds.
    Reads from de_mf_nav_daily; writes to atlas_fund_metrics_daily.
    
    Per methodology 12.1: Fund NAV uses longer windows (1M/3M/6M) than stocks (1W/1M/3M).
    """
    run_id = uuid.uuid4()
    engine = get_engine()
    
    # Load fund universe with their category benchmarks
    funds = pl.read_database("""
        SELECT 
            f.mstar_id, 
            f.scheme_name,
            f.category_name,
            f.benchmark_code,
            bm.source_table,
            bm.source_identifier
        FROM atlas.atlas_universe_funds f
        JOIN atlas.atlas_benchmark_master bm ON bm.benchmark_code = f.benchmark_code
        WHERE f.effective_to IS NULL
    """, engine)
    
    rows_written = 0
    errors = []
    
    for fund in funds.iter_rows(named=True):
        try:
            # Load NAV history for this fund
            nav_history = pl.read_database(f"""
                SELECT nav_date AS date, nav AS close
                FROM public.de_mf_nav_daily
                WHERE mstar_id = '{fund["mstar_id"]}'
                  AND nav_date <= '{target_date}'
                  AND nav_date >= '{backfill_start if is_backfill else target_date - timedelta(days=400)}'
                ORDER BY nav_date
            """, engine)
            
            if len(nav_history) < 252:
                # Insufficient history — skip
                continue
            
            # Load category benchmark history
            # Benchmarks come from de_index_prices typically
            bench_history = pl.read_database(f"""
                SELECT date, close
                FROM public.de_index_prices
                WHERE index_code = '{fund["source_identifier"]}'
                  AND date BETWEEN '{nav_history["date"].min()}' AND '{target_date}'
                ORDER BY date
            """, engine)
            
            # Compute on NAV series using longer fund windows
            nav_pd = nav_history.to_pandas().sort_values("date")
            
            # Returns: 1M, 3M, 6M, 12M (longer windows for funds per methodology 12.1)
            nav_pd["ret_1m"] = nav_pd["close"].pct_change(periods=21)
            nav_pd["ret_3m"] = nav_pd["close"].pct_change(periods=63)
            nav_pd["ret_6m"] = nav_pd["close"].pct_change(periods=126)
            nav_pd["ret_12m"] = nav_pd["close"].pct_change(periods=252)
            
            # Benchmark returns at same windows
            bench_pd = bench_history.to_pandas().sort_values("date")
            bench_pd["bench_ret_1m"] = bench_pd["close"].pct_change(periods=21)
            bench_pd["bench_ret_3m"] = bench_pd["close"].pct_change(periods=63)
            bench_pd["bench_ret_6m"] = bench_pd["close"].pct_change(periods=126)
            bench_pd["bench_ret_12m"] = bench_pd["close"].pct_change(periods=252)
            
            # Merge and compute RS
            merged = nav_pd.merge(
                bench_pd[["date", "bench_ret_1m", "bench_ret_3m", "bench_ret_6m", "bench_ret_12m"]],
                on="date", how="left",
            )
            merged["rs_1m_category"] = merged["ret_1m"] - merged["bench_ret_1m"]
            merged["rs_3m_category"] = merged["ret_3m"] - merged["bench_ret_3m"]
            merged["rs_6m_category"] = merged["ret_6m"] - merged["bench_ret_6m"]
            
            # Risk metrics on NAV series
            merged["daily_return"] = merged["close"].pct_change()
            merged["realized_vol_63"] = (
                merged["daily_return"].rolling(63, min_periods=42).std() * np.sqrt(252)
            )
            
            # Drawdown ratio (against benchmark)
            bench_pd["bench_daily_return"] = bench_pd["close"].pct_change()
            
            # Use empyrical for both
            from empyrical import max_drawdown
            
            def rolling_max_dd(returns, window=252):
                result = pd.Series(index=returns.index, dtype=float)
                for i in range(window - 1, len(returns)):
                    win = returns.iloc[i - window + 1 : i + 1].dropna()
                    if len(win) >= window // 2:
                        result.iloc[i] = abs(max_drawdown(win))
                return result
            
            merged["fund_max_dd_252"] = rolling_max_dd(merged["daily_return"])
            bench_pd["bench_max_dd_252"] = rolling_max_dd(bench_pd["bench_daily_return"])
            
            merged = merged.merge(
                bench_pd[["date", "bench_max_dd_252"]], on="date", how="left"
            )
            merged["drawdown_ratio_252"] = (
                merged["fund_max_dd_252"] / merged["bench_max_dd_252"]
            )
            
            # Write to atlas_fund_metrics_daily
            cols = [
                "date", "close", "ret_1m", "ret_3m", "ret_6m", "ret_12m",
                "rs_1m_category", "rs_3m_category", "rs_6m_category",
                "realized_vol_63", "drawdown_ratio_252",
            ]
            to_write = pl.from_pandas(merged[cols]).with_columns([
                pl.lit(fund["mstar_id"]).alias("mstar_id"),
                pl.col("date").alias("nav_date"),
                pl.col("close").alias("nav"),
                pl.lit(run_id).alias("compute_run_id"),
            ]).drop("close").drop("date")
            
            write_to_fund_metrics_table(engine, to_write, run_id)
            rows_written += len(to_write)
            
        except Exception as e:
            errors.append({"mstar_id": fund["mstar_id"], "error": str(e)})
            continue
    
    return {"run_id": run_id, "rows_written": rows_written, "errors": errors}
```

### 4.3 Compute Within-Category Percentile Ranking

For Lens 1 NAV state classification, funds must be ranked within their category (Large Cap funds vs Large Cap funds, Mid Cap vs Mid Cap, etc.) — not against the entire fund universe.

```python
def compute_within_category_percentiles(
    target_date_or_range,
) -> pl.DataFrame:
    """
    For each (date, category, window), percentile-rank fund's RS within category.
    Used for Lens 1 NAV state classification.
    """
    engine = get_engine()
    
    query = f"""
    SELECT 
        m.mstar_id,
        m.nav_date AS date,
        u.category_name,
        m.rs_1m_category,
        m.rs_3m_category,
        m.rs_6m_category
    FROM atlas.atlas_fund_metrics_daily m
    JOIN atlas.atlas_universe_funds u 
        ON u.mstar_id = m.mstar_id AND u.effective_to IS NULL
    WHERE m.nav_date BETWEEN '{...}' AND '{...}'
    """
    df = pl.read_database(query, engine)
    
    # Percentile rank within (category, date) for each window
    for window in ["1m", "3m", "6m"]:
        df = df.with_columns(
            (pl.col(f"rs_{window}_category")
                .rank(method="dense")
                .over(["date", "category_name"])
                / pl.col(f"rs_{window}_category").count().over(["date", "category_name"]))
            .alias(f"rs_pctile_{window}")
        )
    
    return df
```

### 4.4 Lens 1 NAV State Classifier

Per methodology 12.1.

```python
def classify_nav_state(
    fund_metrics_df: pl.DataFrame, 
    thresholds: dict,
) -> pl.DataFrame:
    """
    Apply 6-state NAV classification per methodology 12.1.
    Uses longer windows (1M/3M/6M) than stock RS classification (1W/1M/3M).
    
    Six states:
    - Leader NAV: top quintile in 1M AND 3M AND 6M
    - Strong NAV: top quintile in 3M AND 6M, not 1M
    - Emerging NAV: top quintile in 1M only
    - Average NAV: middle quintiles
    - Weak NAV: bottom quintile in any window
    - Laggard NAV: bottom quintile in 1M AND 3M AND 6M
    """
    TOP = thresholds["rs_quintile_top"]    # default 0.80 (same threshold as stocks)
    BOT = thresholds["rs_quintile_bottom"] # default 0.20
    
    df = fund_metrics_df.to_pandas()
    
    p1m = df["rs_pctile_1m"]
    p3m = df["rs_pctile_3m"]
    p6m = df["rs_pctile_6m"]
    
    in_top_1m = p1m >= TOP
    in_top_3m = p3m >= TOP
    in_top_6m = p6m >= TOP
    in_bottom_1m = p1m <= BOT
    in_bottom_3m = p3m <= BOT
    in_bottom_6m = p6m <= BOT
    
    conditions = [
        # Laggard NAV: bottom quintile in all three
        in_bottom_1m & in_bottom_3m & in_bottom_6m,
        # Weak NAV: bottom quintile in any one
        in_bottom_1m | in_bottom_3m | in_bottom_6m,
        # Leader NAV: top quintile in all three
        in_top_1m & in_top_3m & in_top_6m,
        # Strong NAV: top quintile in 3m and 6m, not 1m
        in_top_3m & in_top_6m & ~in_top_1m,
        # Emerging NAV: top quintile in 1m only
        in_top_1m & ~in_top_3m & ~in_top_6m,
    ]
    choices = ["Laggard NAV", "Weak NAV", "Leader NAV", "Strong NAV", "Emerging NAV"]
    
    df["nav_state"] = np.select(conditions, choices, default="Average NAV")
    
    return pl.from_pandas(df)
```

**Note:** No Weinstein gate or Stage-1 base requirement for funds — the methodology doesn't extend these stock-level constructs to fund classification. The basic six-state taxonomy applies.

### 4.5 Phase A Definition of Done

- [ ] `atlas_fund_metrics_daily` populated for all ~400 funds × ~3,000 days
- [ ] All NAV-derived metrics computed (returns, RS vs category benchmark, vol, drawdown ratio)
- [ ] Percentile ranks within category computed
- [ ] Lens 1 nav_state classified for every fund-date

---

## 5. Phase B — Lens 2: Sector Composition

### 5.1 Goal

For each fund's monthly holdings disclosure, compute the AUM percentage in each sector state category. Classify into three composition states.

### 5.2 Compute Sector Composition Metrics

```python
def compute_lens2_composition(
    target_disclosure_date: date,
) -> pl.DataFrame:
    """
    For each fund with a holdings disclosure on or before target_disclosure_date,
    compute aligned_aum_pct and avoid_aum_pct.
    
    aligned_aum_pct = sum of fund weights in sectors with state ∈ {Overweight, Neutral}
    avoid_aum_pct = sum of fund weights in sectors with state = Avoid
    
    Per methodology 12.2.
    """
    engine = get_engine()
    
    # For each fund, get its latest holdings disclosure on or before target date
    # Then join to sector states on that disclosure date (use latest available)
    
    query = f"""
    WITH latest_holdings AS (
        -- For each fund, get the most recent disclosure date <= target
        SELECT 
            mstar_id,
            MAX(as_of_date) AS as_of_date
        FROM public.de_mf_holdings
        WHERE as_of_date <= '{target_disclosure_date}'
        GROUP BY mstar_id
    ),
    holdings_with_dates AS (
        SELECT 
            h.mstar_id,
            h.as_of_date,
            h.last_disclosed_date,
            h.instrument_id,
            h.weight
        FROM public.de_mf_holdings h
        JOIN latest_holdings lh 
            ON lh.mstar_id = h.mstar_id AND lh.as_of_date = h.as_of_date
    ),
    holdings_with_sector AS (
        SELECT 
            hd.mstar_id,
            hd.as_of_date,
            hd.last_disclosed_date,
            hd.instrument_id,
            hd.weight,
            u.sector
        FROM holdings_with_dates hd
        LEFT JOIN atlas.atlas_universe_stocks u 
            ON u.instrument_id = hd.instrument_id AND u.effective_to IS NULL
    ),
    sector_states_at_disclosure AS (
        -- For each (fund, sector), get sector_state on the disclosure date
        -- (or closest prior trading day if disclosure date is non-trading)
        SELECT 
            hws.mstar_id,
            hws.as_of_date,
            hws.last_disclosed_date,
            hws.sector,
            hws.weight,
            (
                SELECT ss.sector_state 
                FROM atlas.atlas_sector_states_daily ss
                WHERE ss.sector_name = hws.sector
                  AND ss.date <= hws.as_of_date
                ORDER BY ss.date DESC 
                LIMIT 1
            ) AS sector_state
        FROM holdings_with_sector hws
        WHERE hws.sector IS NOT NULL
    )
    SELECT 
        mstar_id,
        as_of_date,
        MAX(last_disclosed_date) AS last_disclosed_date,
        SUM(weight) FILTER (WHERE sector_state IN ('Overweight', 'Neutral')) AS aligned_aum_pct,
        SUM(weight) FILTER (WHERE sector_state = 'Avoid') AS avoid_aum_pct,
        SUM(weight) FILTER (WHERE sector_state = 'Underweight') AS underweight_aum_pct,
        -- Top 3 sectors by AUM weight
        SUM(weight) FILTER (
            WHERE sector IN (
                SELECT sector FROM sector_states_at_disclosure ss2
                WHERE ss2.mstar_id = sector_states_at_disclosure.mstar_id
                  AND ss2.as_of_date = sector_states_at_disclosure.as_of_date
                GROUP BY sector
                ORDER BY SUM(weight) DESC
                LIMIT 3
            )
        ) AS sector_concentration
    FROM sector_states_at_disclosure
    GROUP BY mstar_id, as_of_date
    """
    
    return pl.read_database(query, engine)
```

**Implementation note:** The above query is illustrative. The `sector_concentration` subquery is non-trivial in standard SQL; in practice this would be computed via Polars after retrieving holdings + states, with the final aggregation in Python. The principle is: for each fund's latest disclosure, attribute every holding to its current sector state, then sum weights by state category.

### 5.3 Lens 2 Composition State Classifier

Per methodology 12.2.

```python
def classify_composition_state(
    lens2_df: pl.DataFrame,
    thresholds: dict,
) -> pl.DataFrame:
    """
    Three-state composition classification per methodology 12.2.
    
    States:
    - Aligned: aligned_aum_pct >= 70% AND avoid_aum_pct < 10%
    - Mixed: aligned 50-70% OR avoid 10-20%
    - Misaligned: aligned < 50% OR avoid >= 20%
    """
    ALIGNED_MIN = thresholds["fund_aligned_aum_min_pct"] / 100  # default 0.70
    AVOID_MAX = thresholds["fund_avoid_aum_max_pct"] / 100      # default 0.10
    
    df = lens2_df.to_pandas()
    
    aligned = df["aligned_aum_pct"].fillna(0)
    avoid = df["avoid_aum_pct"].fillna(0)
    
    conditions = [
        # Misaligned: low alignment OR significant Avoid exposure
        (aligned < 0.50) | (avoid >= 0.20),
        # Aligned: high alignment AND low Avoid
        (aligned >= ALIGNED_MIN) & (avoid < AVOID_MAX),
    ]
    choices = ["Misaligned", "Aligned"]
    
    df["composition_state"] = np.select(conditions, choices, default="Mixed")
    
    return pl.from_pandas(df)
```

### 5.4 Phase B Definition of Done

- [ ] Lens 2 metrics computed for all funds with at least one holdings disclosure in 12-year history
- [ ] aligned_aum_pct and avoid_aum_pct computed correctly (sum of weights, not counts)
- [ ] composition_state ∈ {Aligned, Mixed, Misaligned} for every fund-disclosure-date

---

## 6. Phase C — Lens 3: Holdings Quality

### 6.1 Goal

For each fund's monthly holdings disclosure, compute the AUM percentage in stocks with strong RS states vs weak RS states. Classify into three holdings quality states.

### 6.2 Compute Holdings Quality Metrics

```python
def compute_lens3_holdings(
    target_disclosure_date: date,
) -> pl.DataFrame:
    """
    For each fund's latest holdings disclosure, compute the AUM-weighted
    percentage of holdings in each RS state category.
    
    Per methodology 12.3.
    """
    engine = get_engine()
    
    query = f"""
    WITH latest_holdings AS (
        SELECT mstar_id, MAX(as_of_date) AS as_of_date
        FROM public.de_mf_holdings
        WHERE as_of_date <= '{target_disclosure_date}'
        GROUP BY mstar_id
    ),
    holdings_with_state AS (
        SELECT 
            h.mstar_id,
            h.as_of_date,
            h.last_disclosed_date,
            h.instrument_id,
            h.weight,
            (
                SELECT ss.rs_state 
                FROM atlas.atlas_stock_states_daily ss
                WHERE ss.instrument_id = h.instrument_id
                  AND ss.date <= h.as_of_date
                ORDER BY ss.date DESC 
                LIMIT 1
            ) AS rs_state
        FROM public.de_mf_holdings h
        JOIN latest_holdings lh ON lh.mstar_id = h.mstar_id AND lh.as_of_date = h.as_of_date
    )
    SELECT 
        mstar_id,
        as_of_date,
        MAX(last_disclosed_date) AS last_disclosed_date,
        SUM(weight) FILTER (WHERE rs_state IN ('Leader', 'Strong', 'Emerging')) AS strong_aum_pct,
        SUM(weight) FILTER (WHERE rs_state IN ('Weak', 'Laggard')) AS weak_aum_pct,
        SUM(weight) FILTER (WHERE rs_state IS NULL) AS unknown_aum_pct,
        -- Top 10 holdings concentration
        SUM(weight) FILTER (
            WHERE instrument_id IN (
                SELECT instrument_id 
                FROM holdings_with_state hws2
                WHERE hws2.mstar_id = holdings_with_state.mstar_id
                  AND hws2.as_of_date = holdings_with_state.as_of_date
                ORDER BY weight DESC
                LIMIT 10
            )
        ) AS holdings_concentration
    FROM holdings_with_state
    GROUP BY mstar_id, as_of_date
    """
    
    return pl.read_database(query, engine)
```

**Notes:**

- `unknown_aum_pct` captures fund holdings in stocks NOT in our 750-stock universe (smaller names, recently delisted, etc.). For funds with high `unknown_aum_pct` (>30%), Lens 3 classification may be unreliable; flag in output.
- Like Lens 2, the top-N concentration calculation is illustrative SQL — practical implementation uses Polars after retrieval.

### 6.3 Lens 3 Holdings State Classifier

Per methodology 12.3.

```python
def classify_holdings_state(
    lens3_df: pl.DataFrame,
    thresholds: dict,
) -> pl.DataFrame:
    """
    Three-state holdings classification per methodology 12.3.
    
    States:
    - Strong-Holdings: strong_aum_pct >= 60% AND weak_aum_pct < 15%
    - Decent: strong 40-60% OR weak 15-25%
    - Weak-Holdings: strong < 40% OR weak >= 25%
    """
    STRONG_MIN = thresholds["fund_strong_holdings_min_pct"] / 100  # default 0.60
    WEAK_MAX = thresholds["fund_weak_holdings_max_pct"] / 100      # default 0.25
    
    df = lens3_df.to_pandas()
    
    strong = df["strong_aum_pct"].fillna(0)
    weak = df["weak_aum_pct"].fillna(0)
    
    conditions = [
        # Weak-Holdings: low strong OR high weak
        (strong < 0.40) | (weak >= WEAK_MAX),
        # Strong-Holdings: high strong AND low weak
        (strong >= STRONG_MIN) & (weak < 0.15),
    ]
    choices = ["Weak-Holdings", "Strong-Holdings"]
    
    df["holdings_state"] = np.select(conditions, choices, default="Decent")
    
    return pl.from_pandas(df)
```

### 6.4 Phase C Definition of Done

- [ ] Lens 3 metrics computed for all fund-disclosure-date combinations
- [ ] strong_aum_pct, weak_aum_pct, unknown_aum_pct computed
- [ ] holdings_state ∈ {Strong-Holdings, Decent, Weak-Holdings}

---

## 7. Phase D — Three-Tuple State Assembly

### 7.1 Goal

Assemble the three-tuple state per fund per day in `atlas_fund_states_daily`. Critical: Lens 1 refreshes daily, Lens 2 and Lens 3 refresh monthly.

### 7.2 State Assembly Logic

```python
def assemble_fund_state_tuple(
    target_date: date,
    is_backfill: bool = False,
    backfill_start: date | None = None,
) -> pl.DataFrame:
    """
    For each (fund, date), produce the three-tuple state.
    
    nav_state: from latest atlas_fund_metrics_daily for this fund-date
    composition_state: from most recent atlas_fund_lens_monthly entry on or before this date
    holdings_state: from most recent atlas_fund_lens_monthly entry on or before this date
    
    Tracks refresh dates separately so UI can show "composition state as of: Apr 30".
    """
    engine = get_engine()
    
    date_filter = (
        f"d.date BETWEEN '{backfill_start}' AND '{target_date}'"
        if is_backfill
        else f"d.date = '{target_date}'"
    )
    
    query = f"""
    WITH date_universe AS (
        SELECT DISTINCT date FROM atlas.atlas_market_regime_daily
        WHERE {date_filter.replace('d.', '')}
    ),
    fund_dates AS (
        -- Cartesian product of funds × dates
        SELECT 
            f.mstar_id,
            f.category_name,
            d.date
        FROM atlas.atlas_universe_funds f
        CROSS JOIN date_universe d
        WHERE f.effective_to IS NULL
    )
    SELECT 
        fd.mstar_id,
        fd.date,
        fd.category_name,
        -- Lens 1: NAV state (daily — but only on dates where NAV is updated)
        (
            SELECT m.nav_state 
            FROM atlas.atlas_fund_metrics_daily m
            WHERE m.mstar_id = fd.mstar_id AND m.nav_date = fd.date
        ) AS nav_state,
        fd.date AS nav_state_as_of,
        -- Lens 2: Composition state (monthly — from most recent disclosure)
        (
            SELECT lm.composition_state
            FROM atlas.atlas_fund_lens_monthly lm
            WHERE lm.mstar_id = fd.mstar_id 
              AND lm.as_of_date <= fd.date
            ORDER BY lm.as_of_date DESC LIMIT 1
        ) AS composition_state,
        (
            SELECT lm.as_of_date
            FROM atlas.atlas_fund_lens_monthly lm
            WHERE lm.mstar_id = fd.mstar_id 
              AND lm.as_of_date <= fd.date
            ORDER BY lm.as_of_date DESC LIMIT 1
        ) AS composition_as_of,
        -- Lens 3: Holdings state (monthly — same disclosure)
        (
            SELECT lm.holdings_state
            FROM atlas.atlas_fund_lens_monthly lm
            WHERE lm.mstar_id = fd.mstar_id 
              AND lm.as_of_date <= fd.date
            ORDER BY lm.as_of_date DESC LIMIT 1
        ) AS holdings_state,
        (
            SELECT lm.as_of_date
            FROM atlas.atlas_fund_lens_monthly lm
            WHERE lm.mstar_id = fd.mstar_id 
              AND lm.as_of_date <= fd.date
            ORDER BY lm.as_of_date DESC LIMIT 1
        ) AS holdings_as_of
    FROM fund_dates fd
    """
    
    return pl.read_database(query, engine)
```

**Implementation note:** The cartesian product of ~400 funds × ~3,000 dates = ~1.2M rows. Combined with the lookup subqueries, this query is heavy. For backfill, materialize via temp tables or compute per-fund. For daily incremental, the query operates on one date at a time and is cheap.

### 7.3 Apply Suspended State Override

Same pattern as M2: when market regime is DISLOCATION_SUSPENDED, fund states are suspended too.

```python
def apply_fund_suspension_overrides(
    fund_states_df: pl.DataFrame,
    market_regime_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    When market.dislocation_active = TRUE, override all fund state values 
    with DISLOCATION_SUSPENDED.
    
    Note: Funds don't have history_gate or liquidity_gate the way stocks do —
    insufficient history is handled upstream by skipping the fund entirely.
    """
    df = fund_states_df.to_pandas()
    regime_pd = market_regime_df.to_pandas()
    
    df = df.merge(regime_pd[["date", "dislocation_active"]], on="date", how="left")
    
    state_cols = ["nav_state", "composition_state", "holdings_state"]
    for col in state_cols:
        df[col] = np.where(
            df["dislocation_active"].fillna(False),
            "DISLOCATION_SUSPENDED",
            df[col],
        )
    
    return pl.from_pandas(df)
```

### 7.4 Phase D Definition of Done

- [ ] `atlas_fund_states_daily` populated for all ~400 funds × ~3,000 days
- [ ] nav_state, composition_state, holdings_state all populated
- [ ] Refresh date columns (nav_state_as_of, composition_as_of, holdings_as_of) populated
- [ ] DISLOCATION_SUSPENDED applied where applicable

---

## 8. Phase E — Pipeline Integration

### 8.1 Daily Run Strategy

Most days, only Lens 1 needs to refresh (NAV updates daily). Lens 2 and Lens 3 only refresh when new holdings disclosures are available.

```python
def run_m4_daily(target_date: date):
    """
    M4 daily pipeline.
    
    Lens 1 refreshes every day.
    Lens 2 and Lens 3 refresh only on days where new holdings disclosures arrive
    (typically a few times per month per fund).
    """
    engine = get_engine()
    thresholds = load_thresholds(engine)
    run_id = uuid.uuid4()
    
    # Stage 7a: Lens 1 — daily NAV refresh
    print("Stage 7a: Computing Lens 1 (NAV behavior)...")
    nav_result = compute_fund_nav_metrics(target_date)
    
    # Compute within-category percentiles
    df_with_pctiles = compute_within_category_percentiles(target_date)
    
    # Classify nav_state
    df_classified = classify_nav_state(df_with_pctiles, thresholds)
    
    # Update atlas_fund_metrics_daily with nav_state
    write_nav_states(engine, df_classified, run_id)
    
    # Stage 7b: Check if any new holdings disclosures arrived since last run
    new_disclosures = pl.read_database(f"""
        SELECT DISTINCT mstar_id, as_of_date 
        FROM public.de_mf_holdings 
        WHERE last_disclosed_date >= (
            SELECT COALESCE(MAX(last_disclosed_date), '2014-01-01')
            FROM atlas.atlas_fund_lens_monthly
        )
    """, engine)
    
    if len(new_disclosures) > 0:
        print(f"Stage 7c: Computing Lens 2 + Lens 3 for {len(new_disclosures)} new disclosures...")
        # Run Lens 2 composition for new disclosures
        lens2 = compute_lens2_composition(target_date)
        lens2_classified = classify_composition_state(lens2, thresholds)
        
        # Run Lens 3 holdings for new disclosures
        lens3 = compute_lens3_holdings(target_date)
        lens3_classified = classify_holdings_state(lens3, thresholds)
        
        # Merge and write to atlas_fund_lens_monthly
        lens_combined = lens2_classified.join(
            lens3_classified.select(["mstar_id", "as_of_date", "holdings_state", "strong_aum_pct", "weak_aum_pct", "unknown_aum_pct", "holdings_concentration"]),
            on=["mstar_id", "as_of_date"],
        )
        write_to_fund_lens_monthly(engine, lens_combined, run_id)
    else:
        print("Stage 7c: No new holdings disclosures — Lens 2 + Lens 3 unchanged")
    
    # Stage 7d: Assemble three-tuple state
    print("Stage 7d: Assembling fund state tuples...")
    fund_states = assemble_fund_state_tuple(target_date)
    
    # Apply dislocation override
    market_regime = pl.read_database(
        f"SELECT date, dislocation_active FROM atlas.atlas_market_regime_daily WHERE date = '{target_date}'",
        engine,
    )
    fund_states_final = apply_fund_suspension_overrides(fund_states, market_regime)
    
    write_to_fund_states_table(engine, fund_states_final, run_id)
    
    print(f"M4 daily complete for {target_date}")
```

### 8.2 Backfill Strategy

```python
def run_m4_backfill():
    """
    Historical backfill for M4. Three phases:
    1. Lens 1 NAV metrics for all funds × all dates
    2. Lens 2 + Lens 3 for all historical disclosure cycles
    3. Three-tuple state assembly for every (fund, date)
    """
    start = date(2014, 4, 1)
    end = date.today()
    
    engine = get_engine()
    thresholds = load_thresholds(engine)
    
    # Phase 1: Lens 1 — per-fund metric computation
    print("Phase 1: Lens 1 NAV metrics...")
    compute_fund_nav_metrics(end, is_backfill=True, backfill_start=start)
    
    # Phase 2: Cross-fund within-category percentile ranking
    # (must be done after all funds have raw RS values)
    print("Phase 2: Within-category percentile ranking...")
    compute_within_category_percentiles_full(start, end)
    
    # Phase 3: Lens 1 NAV state classification
    print("Phase 3: NAV state classification...")
    classify_nav_states_full(start, end, thresholds)
    
    # Phase 4: Lens 2 + Lens 3 for every historical disclosure
    print("Phase 4: Lens 2 + Lens 3 historical compute...")
    all_disclosure_dates = pl.read_database(
        "SELECT DISTINCT as_of_date FROM public.de_mf_holdings ORDER BY as_of_date",
        engine,
    )["as_of_date"].to_list()
    for d in all_disclosure_dates:
        lens2 = compute_lens2_composition(d)
        lens3 = compute_lens3_holdings(d)
        # Classify, combine, write
        ...
    
    # Phase 5: Three-tuple state assembly for every (fund, date)
    print("Phase 5: Fund state tuple assembly...")
    assemble_fund_state_tuple_full(start, end)
```

### 8.3 Phase E Definition of Done

- [ ] Daily run script works end-to-end
- [ ] Backfill script populates all target tables
- [ ] Daily run takes < 2 min on non-disclosure days, < 6 min on disclosure days
- [ ] All M4 runs logged in `atlas_run_log`

---

## 9. Phase F — Validation

### 9.1 Tier 2 — Fund Metrics Hand-Validation

Sample sizes:

- Lens 1 NAV metrics: 10 funds × 5 dates × 5 metrics = 250 hand-validations
- Lens 2 composition: 5 funds × 3 disclosure dates × 2 metrics (aligned, avoid) = 30
- Lens 3 holdings: 5 funds × 3 disclosure dates × 2 metrics = 30

Total ~310 hand-validations.

**Critical example: hand-validate `aligned_aum_pct` for one fund**

```python
def tier2_validate_aligned_aum_pct(engine, fund_id, disclosure_date):
    """
    Production: complex SQL aggregation.
    Hand: pull holdings + sector states, sum manually.
    """
    # Production value
    db_val = pl.read_database(f"""
        SELECT aligned_aum_pct 
        FROM atlas.atlas_fund_lens_monthly
        WHERE mstar_id = '{fund_id}' AND as_of_date = '{disclosure_date}'
    """, engine)["aligned_aum_pct"][0]
    
    # Hand value: pull holdings, manually sum
    holdings = pl.read_database(f"""
        SELECT h.instrument_id, h.weight, u.sector
        FROM public.de_mf_holdings h
        LEFT JOIN atlas.atlas_universe_stocks u 
            ON u.instrument_id = h.instrument_id AND u.effective_to IS NULL
        WHERE h.mstar_id = '{fund_id}' AND h.as_of_date = '{disclosure_date}'
    """, engine)
    
    sector_states = pl.read_database(f"""
        SELECT sector_name, sector_state
        FROM atlas.atlas_sector_states_daily
        WHERE date = (
            SELECT MAX(date) FROM atlas.atlas_sector_states_daily WHERE date <= '{disclosure_date}'
        )
    """, engine)
    
    joined = holdings.join(sector_states, left_on="sector", right_on="sector_name", how="left")
    aligned_weight = joined.filter(
        pl.col("sector_state").is_in(["Overweight", "Neutral"])
    )["weight"].sum()
    
    hand_val = aligned_weight
    
    if abs(db_val - hand_val) > 0.001:
        return {"failure": True, "db": db_val, "hand": hand_val}
    return {"failure": False}
```

### 9.2 Tier 3 — State Classifications

Sample: 30 funds × 1 date for nav_state, composition_state, holdings_state classifications.

### 9.3 Tier 4 — Cross-Table Consistency

Per validation framework Section 5 Category E:
- For 5 sample funds, manually reconstruct strong_aum_pct from holdings + stock_states; verify within 0.5%
- For 5 sample funds, reconstruct aligned_aum_pct from holdings + sector_states; verify within 0.5%

### 9.4 Phase F Definition of Done

- [ ] Tier 2: 100% pass on hand-checks
- [ ] Tier 3: 100% pass on classifications
- [ ] Tier 4: holdings reconstructions within 0.5%
- [ ] Three consecutive nightly runs pass

---

## 10. Atlas-M4 Definition of Done

**Code:**
- [ ] All compute modules implemented (funds.py, lens_nav.py, lens_composition.py, lens_holdings.py)
- [ ] Pipeline scripts working (m4_daily.py, m4_backfill.py)

**Database:**
- [ ] `atlas_fund_metrics_daily`: ~1.2M rows
- [ ] `atlas_fund_lens_monthly`: ~58K rows
- [ ] `atlas_fund_states_daily`: ~1.2M rows

**Validation:**
- [ ] Tier 2: 100% pass
- [ ] Tier 3: 100% pass
- [ ] Tier 4: 0 inconsistencies, holdings reconstructions within 0.5%
- [ ] Tier 5: 3 consecutive nightly runs pass
- [ ] `validation_M4_<date>.md` shows PASS

**Sign-off:**
- [ ] Engineer (Claude Code): Build complete
- [ ] Architect (Nimish): Spot-checked validation report
- [ ] Fund Manager (Bhaven): Spot-checked 3 fund classifications, agrees with output

---

## 11. Common Pitfalls

**1. Holdings disclosure lag.** Funds disclose monthly with a 5-10 business day delay. The `last_disclosed_date` (when Morningstar received it) differs from `as_of_date` (the portfolio date). Use `as_of_date` for the analysis (the actual portfolio composition); use `last_disclosed_date` for tracking when data became available.

**2. Holdings disclosed in fragments.** Some fund houses disclose top 10 holdings monthly and full portfolio quarterly. `de_mf_holdings` may have partial coverage. Document any fund where holdings sum to less than 80% of AUM.

**3. Stocks outside universe.** Funds invest in stocks not in our 750. `unknown_aum_pct` captures this. For funds with high unknown (>30%), Lens 3 is unreliable — flag prominently.

**4. Sector state reference for holdings.** Lens 2 needs sector_state on the disclosure date. Use the most recent `atlas_sector_states_daily` row on or before the disclosure date — don't use today's sector state for a portfolio that's 6 months old.

**5. Stock state reference for holdings.** Same logic for Lens 3 — use stock states as of the disclosure date, not today's. Fund's positioning at the time of disclosure is what matters.

**6. NAV total return vs price return.** `de_mf_nav_daily` should contain total-return NAV (NAV + reinvested distributions). If it's price-only NAV, fund returns will be understated for income-paying funds. Document which it is.

**7. Category benchmark availability.** Some specialty fund categories (e.g., Sectoral Banking) need Nifty Bank as benchmark, but our `atlas_benchmark_master` may default everything to Nifty 500. Per-fund benchmark mapping in `atlas_universe_funds.benchmark_code` is the source of truth.

**8. Cartesian product cost.** The fund-state assembly query (~400 funds × 3,000 dates = 1.2M rows) is heavy for backfill. Run per-fund or batch in 50-fund chunks.

**9. No volume primitive for funds.** Methodology 12 explicitly omits volume — funds don't have trading volume in a meaningful sense (AUM and flows aren't comparable). Don't try to compute volume-style metrics on NAV.

**10. Threshold key consistency.** The four fund threshold keys (`fund_aligned_aum_min_pct`, `fund_avoid_aum_max_pct`, `fund_strong_holdings_min_pct`, `fund_weak_holdings_max_pct`) all use percentage values stored as integers (e.g., 70, 10, 60, 25) but applied as decimals. Divide by 100 on read.

---

## 12. Foundation Document Sync Checks

| Check | Documents Involved |
|---|---|
| NAV state names: 6 states (Leader NAV through Laggard NAV) | Methodology 12.1 ↔ Schema 4.4 ↔ M4 Section 4.4 |
| Composition state names: 3 states (Aligned/Mixed/Misaligned) | Methodology 12.2 ↔ Schema 4.4 ↔ M4 Section 5.3 |
| Holdings state names: 3 states (Strong-Holdings/Decent/Weak-Holdings) | Methodology 12.3 ↔ Schema 4.4 ↔ M4 Section 6.3 |
| Lens 1 daily refresh; Lens 2/3 monthly refresh | Methodology 12.4 ↔ M4 Sections 4, 5, 6 |
| Lens 1 windows: 1M/3M/6M (longer than stock 1W/1M/3M) | Methodology 12.1 ↔ M4 Section 4.2 |
| Fund threshold keys: 4 keys | Threshold Catalog 11 ↔ M4 Sections 5.3, 6.3 |
| Within-category ranking (not within-tier) | Methodology 12.1 ↔ M4 Section 4.3 |
| `unknown_aum_pct` captures stocks outside universe | Schema 3.7 ↔ M4 Section 6.2 |
| Suspension override applies to fund states | M2 pattern ↔ M4 Section 7.3 |
| Holdings reconstruction validation | Validation 5 Category E ↔ M4 Section 9.3 |

---

## 13. Open Questions

1. **Direct vs Regular plan handling.** Universe is locked to Regular plans only. If a fund's mstar_id changes between Direct and Regular, document and verify M1 universe lock excluded Direct plans.

2. **Total return NAV verification.** Confirm `de_mf_nav_daily.nav` is total-return adjusted. If price-return only, dividend-paying equity funds will look weaker than they are. May need to add dividend reinvestment logic.

3. **Holdings disclosure sparsity for older periods.** Pre-2018 holdings disclosures may be less complete in `de_mf_holdings`. Document the earliest reliable disclosure date per fund.

4. **Sector mapping for international funds.** If a fund holds international stocks (some Multi-cap funds do), those stocks aren't in `atlas_universe_stocks` — treated as `unknown_aum_pct`. Acceptable for v0; v1 might add international holdings tracking.

---

## 14. What Comes Next

Atlas-M5 (Decision Engine) builds on M2 stock states, M3 sector + market regime states, and M4 fund states to produce investability flags, entry triggers, and exit triggers. M5 is the final v0 milestone before frontend integration.

---

**Document version:** 1.0
**Last updated:** 2026-05-04
**Next review:** Atlas-M4 completion

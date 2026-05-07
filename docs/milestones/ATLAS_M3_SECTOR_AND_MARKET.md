# Atlas-M3 — Sector Aggregation and Market Regime

**Document:** ATLAS_M3_SECTOR_AND_MARKET
**Status:** v0
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**Builder:** Claude Code (intended executor)
**References:**
- `00_METHODOLOGY_LOCK.md` (Sections 9, 10, 11 — index metrics, sector aggregation, market regime)
- `01_BACKEND_ARCHITECTURE.md` (Section 5.6 threshold discipline; Section 5.3 pipeline stages 4, 5, 6)
- `02_DATABASE_SCHEMA.md` (Sections 3.3, 3.4, 3.5, 4.3 — index, sector, market regime tables)
- `03_VALIDATION_FRAMEWORK.md` (Tier 2, 3, 4 specific to aggregations)
- `04_THRESHOLD_CATALOG.md` (sector and regime threshold keys)
- `ATLAS_M2_STOCK_ETF_METRICS.md` (predecessor — stock and ETF metrics must be populated first)

---

## 1. Goal

Build the aggregation and market-level layer of Atlas. Three deliverables:

1. **Index metrics** for the 75-index universe — returns, momentum, RS vs Nifty 500, volatility (no state classification — indices aren't classified)
2. **Sector aggregations** — bottom-up (market-cap-weighted from M2 stock metrics) PLUS top-down (NSE sectoral index from index metrics) PLUS three breadth measures, with divergence flag
3. **Market regime classification** — the four-state regime classifier (Risk-On / Constructive / Cautious / Risk-Off) using 18 input measures across four breadth families, plus the dislocation override

After this milestone:

- `atlas_index_metrics_daily` populated for 75 indices × ~3,000 days = ~225K rows
- `atlas_sector_metrics_daily` populated for ~20 sectors × ~3,000 days = ~60K rows
- `atlas_sector_states_daily` populated for same scope
- `atlas_market_regime_daily` populated for ~3,000 days (one row per trading day)
- All breadth measures computed and persisted

**No mutual fund work. No decision engine.** Those are M4 and M5.

---

## 2. Dependencies

### 2.1 Predecessors

**Atlas-M2** must be complete and signed off. Specifically:
- `atlas_stock_metrics_daily` populated for 750 stocks × full 12-year history
- `atlas_stock_states_daily` populated for same scope
- `atlas_etf_metrics_daily` populated (used for index sanity-checks)
- All M2 validation tiers passed

M3 cannot start without M2 outputs because:
- Bottom-up sector aggregation needs stock metrics
- Strength breadth (`pct_in_strong_states`) needs stock states
- Universe coverage check needs stock universe lock from M1 (transitive via M2)

### 2.2 Foundation Document Consistency Checks

Before building, verify these specific cross-document references:

| Foundation Reference | What M3 Depends On |
|---|---|
| Methodology 9 | Index metrics: returns, RS-vs-Nifty500, momentum, vol — no states |
| Methodology 10.2 | Bottom-up: market-cap-weighted aggregation of all stock-level metrics |
| Methodology 10.3 | Top-down: NSE sectoral index time series direct read |
| Methodology 10.4 | Three breadth measures: participation_50, participation_RS, leadership_concentration |
| Methodology 10.5 | Sector states: Overweight/Neutral/Underweight/Avoid |
| Methodology 10.6 | Divergence flag: bottom-up vs top-down disagree by >1 rank |
| Methodology 11.1 | 18 regime input measures across 4 breadth families |
| Methodology 11.4 | 4 regime states with deployment multipliers (1.0, 0.7, 0.4, 0.0) |
| Methodology 11.5 | Dislocation override: 5d vol > 4× 252d median |
| Schema 3.3 | atlas_index_metrics_daily — 16 columns, no state |
| Schema 3.4 | atlas_sector_metrics_daily — bottom-up + top-down + breadth + divergence |
| Schema 3.5 | atlas_market_regime_daily — 28 columns covering 4 breadth families |
| Schema 4.3 | atlas_sector_states_daily — sector_state + bottomup_state + topdown_state + divergence_flag |
| Threshold Catalog 9 | 3 sector classification thresholds |
| Threshold Catalog 10 | 8 market regime thresholds |
| Architecture 5.6 | All classifiers receive thresholds dict; no hardcoded values |

If any inconsistency is found in this list, halt build and resolve at source documents.

### 2.3 Required JIP Data Core Tables (Read-Only)

| Table | Used For | Identifier | Date Column |
|---|---|---|---|
| `de_index_prices` | All index prices including NSE sectoral indices, Nifty 500, India VIX | `index_code` | `date` |
| `de_market_cap_history` | Market cap weights for bottom-up aggregation | `instrument_id` | `date_recorded` (categorical) |
| `de_index_constituents` | Verifying which stocks belong to each NSE sector index (top-down sanity check) | `instrument_id`, `index_name` | `effective_from` |

**Note on India VIX:** Stored as `India VIX` (or similar) in `de_index_prices`. Verify exact `index_code` value during M3 execution.

**Note on market cap:** `de_market_cap_history.cap_category` is categorical (Large/Mid/Small/Micro), not actual cap values per the JIP M1 finding. For bottom-up weighting, fall back to: trailing 60-day median traded value as proxy weight (already used for tier classification in M1).

### 2.4 Required Atlas Tables (Read)

| Table | Used For |
|---|---|
| `atlas_universe_indices` | 75-index universe with role classification |
| `atlas_universe_stocks` | Sector tag for each stock (denormalized in atlas_stock_states_daily for query speed) |
| `atlas_sector_master` | Sector taxonomy + primary_nse_index linkage |
| `atlas_benchmark_master` | Nifty 500 benchmark for index RS computation |
| `atlas_stock_metrics_daily` | Stock-level metrics for bottom-up aggregation |
| `atlas_stock_states_daily` | Stock states for breadth measures |
| `atlas_thresholds` | Loaded once per pipeline run |

---

## 3. Deliverables

### 3.1 Code Deliverables

```
atlas-backend/atlas/compute/
├── indices.py                  # Index metric pipeline (Stage 4)
├── sectors.py                  # Sector aggregation pipeline (Stage 5)
├── regime.py                   # Market regime classification pipeline (Stage 6)
├── breadth.py                  # Breadth computation primitives (shared by sectors + regime)
└── aggregation.py              # Market-cap-weighted aggregation utilities
```

```
atlas-backend/atlas/validation/
├── tier2_metrics.py            # Add: sector aggregation, regime breadth hand-validations
├── tier3_states.py             # Add: sector state, regime state hand-classifications
└── tier4_consistency.py        # Add: bottom-up reconstruction, breadth reconstruction
```

```
atlas-backend/scripts/
├── m3_backfill.py              # Historical backfill for sectors + indices + regime
└── m3_daily.py                 # Daily incremental run
```

### 3.2 Database Deliverables

| Table | Expected Rows After Backfill |
|---|---|
| `atlas_index_metrics_daily` | ~225K (75 indices × ~3,000 days) |
| `atlas_sector_metrics_daily` | ~60K (~20 sectors × ~3,000 days) |
| `atlas_sector_states_daily` | ~60K |
| `atlas_market_regime_daily` | ~3,000 (one row per trading day) |

### 3.3 Validation Deliverables

- `validation_M3_<date>.md` with passing Tier 2 (~225 hand-checks for aggregations and breadth), Tier 3 (~50 sector and regime classifications), Tier 4 (sector reconstruction + breadth reconstruction)
- Three consecutive nightly incremental runs passing Tier 5

---

## 4. Phase A — Index Metrics

### 4.1 Goal

Compute returns, RS, momentum, and volatility for the 75 curated indices. No state classification — these feed into sector top-down readings and the dislocation override.

### 4.2 Index Metric Computation

Indices share most of the math with stocks but with three differences:
- No volume primitive (index volume is meaningless)
- No tier — indices aren't ranked
- No state classification — only metrics

```python
import polars as pl
import pandas as pd
import pandas_ta as ta
import numpy as np

def compute_index_metrics(
    target_date: date,
    is_backfill: bool = False,
    backfill_start: date | None = None,
) -> dict:
    """
    Compute metrics for all 75 indices in atlas_universe_indices.
    Reads from de_index_prices; writes to atlas_index_metrics_daily.
    
    Includes special handling for India VIX (used by regime classifier).
    Includes Nifty 500 (the broad-market benchmark for RS).
    """
    run_id = uuid.uuid4()
    engine = get_engine()
    
    # Load index universe
    indices = pl.read_database(
        "SELECT index_code FROM atlas.atlas_universe_indices WHERE effective_to IS NULL",
        engine,
    )
    
    # Load Nifty 500 separately (for RS computation)
    nifty500 = load_index_history(engine, "NIFTY 500", 
                                  backfill_start if is_backfill else target_date - timedelta(days=300),
                                  target_date)
    nifty500_with_returns = compute_returns(nifty500, "close")
    
    rows_written = 0
    
    for idx in indices.iter_rows(named=True):
        index_code = idx["index_code"]
        
        # Load this index's full history
        idx_history = load_index_history(
            engine, index_code,
            backfill_start if is_backfill else target_date - timedelta(days=400),
            target_date,
        )
        
        if len(idx_history) < 252:
            # Insufficient history — skip but don't error
            continue
        
        # Convert to pandas for pandas-ta
        idx_pd = idx_history.to_pandas().sort_values("date")
        
        # Returns at all standard windows
        for name, n in WINDOWS.items():
            idx_pd[f"ret_{name}"] = idx_pd["close"].pct_change(periods=n)
        
        # RS vs Nifty 500
        nifty500_pd = nifty500_with_returns.to_pandas().sort_values("date")
        idx_pd = idx_pd.merge(
            nifty500_pd[["date"] + [f"ret_{name}" for name in ["1w", "1m", "3m"]]]
                .rename(columns={f"ret_{name}": f"_n500_ret_{name}" for name in ["1w", "1m", "3m"]}),
            on="date",
            how="left",
        )
        for name in ["1w", "1m", "3m"]:
            idx_pd[f"rs_{name}_nifty500"] = idx_pd[f"ret_{name}"] - idx_pd[f"_n500_ret_{name}"]
        
        # Momentum (EMA-ratio against Nifty 500)
        idx_pd["ema_10_index"] = ta.ema(idx_pd["close"], length=10)
        idx_pd["ema_20_index"] = ta.ema(idx_pd["close"], length=20)
        
        nifty500_pd["ema_10_n500"] = ta.ema(nifty500_pd["close"], length=10)
        nifty500_pd["ema_20_n500"] = ta.ema(nifty500_pd["close"], length=20)
        idx_pd = idx_pd.merge(
            nifty500_pd[["date", "ema_10_n500", "ema_20_n500"]],
            on="date", how="left",
        )
        idx_pd["ema_10_ratio_nifty500"] = idx_pd["ema_10_index"] / idx_pd["ema_10_n500"]
        idx_pd["ema_20_ratio_nifty500"] = idx_pd["ema_20_index"] / idx_pd["ema_20_n500"]
        
        # Volatility metrics
        idx_pd["daily_return"] = idx_pd["close"].pct_change()
        idx_pd["realized_vol_63"] = (
            idx_pd["daily_return"].rolling(63, min_periods=42).std() * np.sqrt(252)
        )
        idx_pd["realized_vol_5d"] = (
            idx_pd["daily_return"].rolling(5, min_periods=4).std() * np.sqrt(252)
        )
        # 252-day median of realized_vol_63 — used for dislocation override
        idx_pd["vol_252_median"] = (
            idx_pd["realized_vol_63"].rolling(252, min_periods=180).median()
        )
        
        # Drop helper columns and write
        cols_to_write = [
            "date", "ret_1d", "ret_1w", "ret_1m", "ret_3m", "ret_6m", "ret_12m",
            "rs_1w_nifty500", "rs_1m_nifty500", "rs_3m_nifty500",
            "ema_10_index", "ema_20_index",
            "ema_10_ratio_nifty500", "ema_20_ratio_nifty500",
            "realized_vol_63", "realized_vol_5d", "vol_252_median",
        ]
        idx_to_write = pl.from_pandas(idx_pd[cols_to_write]).with_columns([
            pl.lit(index_code).alias("index_code"),
            pl.lit(run_id).alias("compute_run_id"),
        ])
        
        write_to_index_metrics_table(engine, idx_to_write, run_id)
        rows_written += len(idx_to_write)
    
    return {"run_id": run_id, "rows_written": rows_written, "indices_processed": len(indices)}
```

### 4.3 Phase A Definition of Done

- [ ] `atlas_index_metrics_daily` populated for all 75 indices in universe
- [ ] Each index has rows from earliest available date (typically 2014-06-02 for most NSE indices)
- [ ] India VIX rows present (required for market regime computation)
- [ ] Nifty 500 rows present (required for RS denominators)
- [ ] No NaN values in `realized_vol_63` after the rolling window has filled (typically after 42 days)

---

## 5. Phase B — Sector Aggregation

### 5.1 Goal

For each NSE sector, compute bottom-up aggregations from constituent stocks AND top-down readings from the corresponding NSE sectoral index, plus three breadth measures. Apply sector state classification.

### 5.2 Bottom-Up Aggregation

```python
def compute_bottom_up_sector_metrics(
    target_date: date,
    is_backfill: bool = False,
    backfill_start: date | None = None,
) -> pl.DataFrame:
    """
    Aggregate stock-level metrics into sector-level metrics using market-cap weights.
    
    For each (sector, date):
        bottomup_metric = sum(stock.metric * stock.weight) for stock in sector.constituents
    
    Where stock.weight = stock's share of total sector traded value
    (proxy for market cap, since cap data is categorical per JIP M1 finding).
    """
    engine = get_engine()
    
    date_filter = (
        f"date BETWEEN '{backfill_start}' AND '{target_date}'" 
        if is_backfill 
        else f"date = '{target_date}'"
    )
    
    # Load stock metrics joined to sector
    query = f"""
    SELECT 
        s.instrument_id,
        s.date,
        s.sector,
        s.tier,
        m.ret_1m, m.ret_3m, m.ret_6m,
        m.rs_3m_nifty500,
        m.ema_10_ratio, m.ema_20_ratio,
        -- Use traded value as weight proxy
        m.avg_volume_20 * (
            SELECT close FROM atlas.atlas_stock_metrics_daily m2 
            WHERE m2.instrument_id = s.instrument_id AND m2.date = s.date
        ) AS traded_value_weight
    FROM atlas.atlas_stock_states_daily s
    JOIN atlas.atlas_stock_metrics_daily m 
        ON m.instrument_id = s.instrument_id AND m.date = s.date
    WHERE {date_filter}
      AND s.sector IS NOT NULL
      AND s.rs_state NOT IN ('INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED')
    """
    
    stocks_with_sector = pl.read_database(query, engine)
    
    # For each (sector, date), compute weighted aggregations
    # Weight = stock's traded value / sum of sector's traded values
    sector_weights = stocks_with_sector.group_by(["sector", "date"]).agg(
        pl.col("traded_value_weight").sum().alias("sector_total_weight")
    )
    
    stocks_with_weights = stocks_with_sector.join(
        sector_weights, on=["sector", "date"], how="left"
    ).with_columns(
        (pl.col("traded_value_weight") / pl.col("sector_total_weight")).alias("weight")
    )
    
    # Weighted aggregations
    bottomup = stocks_with_weights.group_by(["sector", "date"]).agg([
        (pl.col("ret_1m") * pl.col("weight")).sum().alias("bottomup_ret_1m"),
        (pl.col("ret_3m") * pl.col("weight")).sum().alias("bottomup_ret_3m"),
        (pl.col("ret_6m") * pl.col("weight")).sum().alias("bottomup_ret_6m"),
        (pl.col("rs_3m_nifty500") * pl.col("weight")).sum().alias("bottomup_rs_3m_nifty500"),
        (pl.col("ema_10_ratio") * pl.col("weight")).sum().alias("bottomup_ema_10_ratio"),
        (pl.col("ema_20_ratio") * pl.col("weight")).sum().alias("bottomup_ema_20_ratio"),
        pl.col("instrument_id").count().alias("constituent_count"),
    ])
    
    return bottomup
```

### 5.3 Top-Down (NSE Sectoral Index) Aggregation

```python
def compute_top_down_sector_metrics(
    target_date: date,
    is_backfill: bool = False,
    backfill_start: date | None = None,
) -> pl.DataFrame:
    """
    For each sector with a primary_nse_index in atlas_sector_master,
    read the corresponding index metrics from atlas_index_metrics_daily.
    
    Sectors without a primary NSE index (some IISL classifications don't
    have dedicated NIFTY indices) get NULL top-down values.
    """
    engine = get_engine()
    
    date_filter = (
        f"date BETWEEN '{backfill_start}' AND '{target_date}'"
        if is_backfill 
        else f"date = '{target_date}'"
    )
    
    query = f"""
    SELECT 
        sm.sector_name AS sector,
        sm.primary_nse_index AS topdown_index_code,
        i.date,
        i.ret_1m AS topdown_ret_1m,
        i.ret_3m AS topdown_ret_3m,
        i.rs_3m_nifty500 AS topdown_rs_3m_nifty500,
        i.ema_10_ratio_nifty500 AS topdown_ema_10_ratio,
        i.ema_20_ratio_nifty500 AS topdown_ema_20_ratio
    FROM atlas.atlas_sector_master sm
    LEFT JOIN atlas.atlas_index_metrics_daily i 
        ON i.index_code = sm.primary_nse_index
    WHERE sm.is_active = TRUE
      AND ({date_filter} OR i.date IS NULL)
    """
    
    return pl.read_database(query, engine)
```

### 5.4 Three Breadth Measures

Per methodology Section 10.4.

```python
def compute_sector_breadth_measures(
    target_date: date,
    is_backfill: bool = False,
    backfill_start: date | None = None,
) -> pl.DataFrame:
    """
    Three breadth measures per sector per date:
    1. participation_50: % of sector stocks above 50-day MA
    2. participation_RS: % of sector stocks in {Leader, Strong, Emerging}
    3. leadership_concentration: top 5 by RS_3M as % of sector traded value
    """
    engine = get_engine()
    
    date_filter = (
        f"AND s.date BETWEEN '{backfill_start}' AND '{target_date}'"
        if is_backfill
        else f"AND s.date = '{target_date}'"
    )
    
    # Load joined data
    query = f"""
    SELECT 
        s.sector,
        s.date,
        s.instrument_id,
        s.rs_state,
        m.close,
        m.rs_3m_nifty500,
        -- 50-day MA from M2
        AVG(m.close) OVER (
            PARTITION BY s.instrument_id 
            ORDER BY s.date 
            ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
        ) AS ma_50,
        m.avg_volume_20 * m.close AS traded_value
    FROM atlas.atlas_stock_states_daily s
    JOIN atlas.atlas_stock_metrics_daily m 
        ON m.instrument_id = s.instrument_id AND m.date = s.date
    WHERE s.rs_state NOT IN ('INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED')
      {date_filter}
    """
    
    df = pl.read_database(query, engine)
    
    # participation_50: % above 50-day MA
    breadth_50 = df.with_columns(
        (pl.col("close") > pl.col("ma_50")).alias("above_ma_50")
    ).group_by(["sector", "date"]).agg(
        pl.col("above_ma_50").mean().alias("participation_50")
    )
    
    # participation_RS: % in strong RS states
    breadth_rs = df.with_columns(
        pl.col("rs_state").is_in(["Leader", "Strong", "Emerging"]).alias("in_strong")
    ).group_by(["sector", "date"]).agg(
        pl.col("in_strong").mean().alias("participation_rs")
    )
    
    # leadership_concentration: top 5 by RS_3M as % of sector traded value
    # First rank stocks within sector by RS_3M, then take top 5
    df_ranked = df.with_columns(
        pl.col("rs_3m_nifty500")
            .rank(method="dense", descending=True)
            .over(["sector", "date"])
            .alias("rs_rank")
    )
    top5_traded_value = (
        df_ranked
        .filter(pl.col("rs_rank") <= 5)
        .group_by(["sector", "date"])
        .agg(pl.col("traded_value").sum().alias("top5_traded_value"))
    )
    sector_total_traded_value = (
        df.group_by(["sector", "date"])
        .agg(pl.col("traded_value").sum().alias("sector_total_traded_value"))
    )
    leadership = top5_traded_value.join(
        sector_total_traded_value, on=["sector", "date"]
    ).with_columns(
        (pl.col("top5_traded_value") / pl.col("sector_total_traded_value"))
        .alias("leadership_concentration")
    ).select(["sector", "date", "leadership_concentration"])
    
    # Combine all three
    return breadth_50.join(breadth_rs, on=["sector", "date"]).join(
        leadership, on=["sector", "date"]
    )
```

### 5.5 Sector State Classification

Per methodology Section 10.5. Threshold-driven per architecture 5.6.

```python
def classify_sector_state(
    sector_metrics_df: pl.DataFrame, 
    thresholds: dict
) -> pl.DataFrame:
    """
    Apply 4-state sector classification per methodology 10.5.
    
    Requires columns:
        bottomup_rs_state, bottomup_momentum_state, participation_rs
    
    Note: We need to derive bottomup_rs_state and bottomup_momentum_state
    from the bottom-up aggregated values. This is a sector-level classification
    using the same RS taxonomy as stocks but applied to the bottom-up metrics.
    """
    OW_PARTIC = thresholds["sector_overweight_participation_min_pct"] / 100  # default 0.50
    UW_PARTIC = thresholds["sector_underweight_participation_max_pct"] / 100  # default 0.30
    AVOID_PARTIC = thresholds["sector_avoid_participation_max_pct"] / 100  # default 0.25
    
    df = sector_metrics_df.to_pandas()
    
    bot_rs = df["bottomup_rs_state"]
    bot_mom = df["bottomup_momentum_state"]
    p_rs = df["participation_rs"]
    
    in_strong_rs = bot_rs.isin(["Leader", "Strong"])
    in_strong_mom = bot_mom.isin(["Accelerating", "Improving"])
    
    conditions = [
        # Avoid: Laggard RS AND very weak breadth
        (bot_rs == "Laggard") & (p_rs < AVOID_PARTIC),
        # Underweight: Weak RS OR low participation
        (bot_rs == "Weak") | (p_rs < UW_PARTIC),
        # Overweight: Strong RS state AND positive momentum AND broad participation
        in_strong_rs & in_strong_mom & (p_rs >= OW_PARTIC),
    ]
    choices = ["Avoid", "Underweight", "Overweight"]
    
    df["sector_state"] = np.select(conditions, choices, default="Neutral")
    
    return pl.from_pandas(df)
```

**Note:** Computing `bottomup_rs_state` and `bottomup_momentum_state` from aggregated bottom-up values requires running the stock RS classifier and momentum classifier on the sector aggregates. The simplest approach: for each (sector, date), construct a "synthetic stock" record from the bottom-up aggregations and run the same classifiers. Documentation needed in the validation report on how bottom-up percentile ranking is derived (sectors don't have a tier benchmark in the same way stocks do — use RS vs Nifty 500 directly without percentile ranking, or compute cross-sector percentiles).

### 5.6 Divergence Flag

Per methodology Section 10.6.

```python
def compute_divergence_flag(sector_states_df: pl.DataFrame) -> pl.DataFrame:
    """
    Flag sectors where bottom-up state and top-down state differ by >1 rank.
    
    Rank order: Overweight=4, Neutral=3, Underweight=2, Avoid=1
    Differ by >1 rank means absolute difference >= 2.
    """
    rank_map = {"Overweight": 4, "Neutral": 3, "Underweight": 2, "Avoid": 1}
    
    df = sector_states_df.to_pandas()
    df["bottomup_rank"] = df["bottomup_state"].map(rank_map)
    df["topdown_rank"] = df["topdown_state"].map(rank_map)
    
    # Divergence flag: NULL top-down state means no NSE sectoral index — no divergence possible
    df["divergence_flag"] = (
        df["topdown_rank"].notna() &
        (df["bottomup_rank"] - df["topdown_rank"]).abs() >= 2
    ).fillna(False)
    
    return pl.from_pandas(df)
```

The divergence flag is presentational in v0 (surfaced in the UI, noted in decision rationale) but does not gate decisions. v1 adds the stricter stock-level filter when divergence flag is raised.

### 5.7 Phase B Definition of Done

- [ ] `atlas_sector_metrics_daily` populated for all ~20 sectors × ~3,000 days
- [ ] Each row has bottom-up aggregations populated
- [ ] Sectors with `primary_nse_index` set in `atlas_sector_master` have top-down columns populated; others have NULLs
- [ ] All three breadth measures computed (participation_50, participation_rs, leadership_concentration)
- [ ] `atlas_sector_states_daily` populated with sector_state, bottomup_state, topdown_state, divergence_flag
- [ ] Divergence flag raised for sectors where bottom-up and top-down disagree by 2+ ranks
- [ ] No NULL sector_state values

---

## 6. Phase C — Market Regime Classification

### 6.1 Goal

Classify the market into one of four regime states (Risk-On / Constructive / Cautious / Risk-Off) using 18 input measures across four breadth families. Apply the dislocation override.

### 6.2 Compute Trend Inputs

Per methodology 11.1.

```python
def compute_regime_trend_inputs(
    target_date: date,
    is_backfill: bool = False,
    backfill_start: date | None = None,
) -> pl.DataFrame:
    """
    Trend inputs for market regime: Nifty 500 vs EMA 50/200, slopes.
    Reads Nifty 500 prices from de_index_prices.
    """
    engine = get_engine()
    
    nifty500 = pl.read_database(
        f"""
        SELECT date, close 
        FROM public.de_index_prices 
        WHERE index_code = 'NIFTY 500'
          AND date <= '{target_date}'
          AND date >= '{backfill_start if is_backfill else target_date - timedelta(days=400)}'
        ORDER BY date
        """,
        engine,
    )
    
    n500_pd = nifty500.to_pandas()
    n500_pd["nifty500_ema_50"] = ta.ema(n500_pd["close"], length=50)
    n500_pd["nifty500_ema_200"] = ta.ema(n500_pd["close"], length=200)
    n500_pd["nifty500_above_ema_50"] = n500_pd["close"] > n500_pd["nifty500_ema_50"]
    n500_pd["nifty500_above_ema_200"] = n500_pd["close"] > n500_pd["nifty500_ema_200"]
    
    # 21-day slopes (σ-normalized using 252-day stdev)
    n500_pd["ema_50_change_21"] = (
        (n500_pd["nifty500_ema_50"] - n500_pd["nifty500_ema_50"].shift(21)) 
        / n500_pd["nifty500_ema_50"].shift(21)
    )
    ema_50_slope_std = n500_pd["ema_50_change_21"].rolling(252, min_periods=180).std()
    n500_pd["nifty500_ema_50_slope"] = n500_pd["ema_50_change_21"] / ema_50_slope_std
    
    n500_pd["ema_200_change_21"] = (
        (n500_pd["nifty500_ema_200"] - n500_pd["nifty500_ema_200"].shift(21)) 
        / n500_pd["nifty500_ema_200"].shift(21)
    )
    ema_200_slope_std = n500_pd["ema_200_change_21"].rolling(252, min_periods=180).std()
    n500_pd["nifty500_ema_200_slope"] = n500_pd["ema_200_change_21"] / ema_200_slope_std
    
    return pl.from_pandas(n500_pd[[
        "date", "close", 
        "nifty500_ema_50", "nifty500_ema_200",
        "nifty500_above_ema_50", "nifty500_above_ema_200",
        "nifty500_ema_50_slope", "nifty500_ema_200_slope",
    ]]).rename({"close": "nifty500_close"})
```

### 6.3 Compute MA Breadth Inputs (Bhaven's Anchor)

Per methodology 11.1.

```python
def compute_ma_breadth(target_date_or_range) -> pl.DataFrame:
    """
    Three measures: pct of Nifty 500 stocks above EMA 20, EMA 50, EMA 200.
    Uses M2's atlas_stock_metrics_daily (which has ema_20_stock and ema_200_stock columns).
    """
    engine = get_engine()
    
    # We need EMA 50 too — compute on the fly from close prices since M2 stored EMA 10/20/200 but not 50
    # Either: extend M2 schema to add ema_50 (better long-term solution)
    # Or: compute EMA 50 here from atlas_stock_metrics_daily.close history
    
    # For v0: compute EMA 50 here as a transient calculation
    # In subsequent versions, add ema_50_stock to atlas_stock_metrics_daily schema
    
    query = f"""
    SELECT 
        m.instrument_id,
        m.date,
        m.close,
        m.ema_20_stock,
        m.ema_200_stock
    FROM atlas.atlas_stock_metrics_daily m
    JOIN atlas.atlas_universe_stocks u 
        ON u.instrument_id = m.instrument_id AND u.effective_to IS NULL
    WHERE u.in_nifty_500 = TRUE
      AND m.date = '{target_date_or_range}'
    """
    
    df = pl.read_database(query, engine)
    
    # For EMA 50 — load full history and compute (requires window)
    # This is heavy; consider extending M2 schema to store ema_50_stock instead.
    # For documentation completeness, the v0 approach computes EMA 50 transiently here.
    
    # Compute breadth: % above each EMA
    breadth = df.with_columns([
        (pl.col("close") > pl.col("ema_20_stock")).alias("above_ema_20"),
        (pl.col("close") > pl.col("ema_200_stock")).alias("above_ema_200"),
        # ema_50 to be computed transiently or sourced from extended M2 schema
    ]).group_by("date").agg([
        pl.col("above_ema_20").mean().alias("pct_above_ema_20"),
        pl.col("above_ema_200").mean().alias("pct_above_ema_200"),
        # pct_above_ema_50 to be added once ema_50_stock is available
    ])
    
    return breadth
```

**Open question (carried into M3 execution):** Does M2 schema store `ema_50_stock`? If not, this needs to be added to `atlas_stock_metrics_daily` as part of M3 prep. Document either way in M3 validation report.

### 6.4 Compute A/D Breadth

Per methodology 11.1.

```python
def compute_ad_breadth(target_date_or_range) -> pl.DataFrame:
    """
    Five measures: advances, declines, ad_ratio, ad_line, ad_line_slope_21,
    mcclellan_oscillator, mcclellan_summation.
    """
    engine = get_engine()
    
    # For each (date), count advances and declines across Nifty 500 universe
    query = f"""
    WITH price_changes AS (
        SELECT 
            m.instrument_id,
            m.date,
            m.close,
            LAG(m.close) OVER (PARTITION BY m.instrument_id ORDER BY m.date) AS prev_close
        FROM atlas.atlas_stock_metrics_daily m
        JOIN atlas.atlas_universe_stocks u 
            ON u.instrument_id = m.instrument_id AND u.effective_to IS NULL
        WHERE u.in_nifty_500 = TRUE
    )
    SELECT 
        date,
        COUNT(*) FILTER (WHERE close > prev_close) AS advances_count,
        COUNT(*) FILTER (WHERE close < prev_close) AS declines_count,
        COUNT(*) FILTER (WHERE close = prev_close) AS unchanged_count
    FROM price_changes
    WHERE prev_close IS NOT NULL
      AND date BETWEEN '{...}' AND '{...}'
    GROUP BY date
    ORDER BY date
    """
    
    df = pl.read_database(query, engine).to_pandas()
    
    # ad_ratio
    df["ad_ratio"] = df["advances_count"] / df["declines_count"].clip(lower=1)
    
    # net_advances (used for cumulative ad_line and McClellan)
    df["net_advances"] = df["advances_count"] - df["declines_count"]
    
    # ad_line: cumulative net advances
    df["ad_line"] = df["net_advances"].cumsum()
    
    # ad_line_slope_21 (σ-normalized)
    df["ad_line_change_21"] = df["ad_line"] - df["ad_line"].shift(21)
    ad_line_std = df["ad_line_change_21"].rolling(252, min_periods=180).std()
    df["ad_line_slope_21"] = df["ad_line_change_21"] / ad_line_std
    
    # McClellan Oscillator: 19-EMA of net_advances minus 39-EMA of net_advances
    df["mcclellan_oscillator"] = (
        ta.ema(df["net_advances"], length=19) 
        - ta.ema(df["net_advances"], length=39)
    )
    
    # McClellan Summation: cumulative sum of oscillator
    df["mcclellan_summation"] = df["mcclellan_oscillator"].cumsum()
    
    return pl.from_pandas(df[[
        "date", "advances_count", "declines_count", "unchanged_count",
        "ad_ratio", "ad_line", "ad_line_slope_21",
        "mcclellan_oscillator", "mcclellan_summation",
    ]])
```

### 6.5 Compute New Highs/Lows Breadth

Per methodology 11.1.

```python
def compute_highs_lows_breadth(target_date_or_range) -> pl.DataFrame:
    """
    Four measures: new 52-week highs, new 52-week lows, net new highs,
    new high/low ratio.
    """
    engine = get_engine()
    
    # For each stock-date, flag whether close is at 252-day rolling max or min
    query = f"""
    WITH rolling_extremes AS (
        SELECT 
            m.instrument_id,
            m.date,
            m.close,
            MAX(m.close) OVER (
                PARTITION BY m.instrument_id ORDER BY m.date
                ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
            ) AS rolling_252d_max,
            MIN(m.close) OVER (
                PARTITION BY m.instrument_id ORDER BY m.date
                ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
            ) AS rolling_252d_min
        FROM atlas.atlas_stock_metrics_daily m
        JOIN atlas.atlas_universe_stocks u 
            ON u.instrument_id = m.instrument_id AND u.effective_to IS NULL
        WHERE u.in_nifty_500 = TRUE
    )
    SELECT 
        date,
        COUNT(*) FILTER (WHERE close = rolling_252d_max) AS new_52w_highs,
        COUNT(*) FILTER (WHERE close = rolling_252d_min) AS new_52w_lows
    FROM rolling_extremes
    WHERE date BETWEEN '{...}' AND '{...}'
    GROUP BY date
    ORDER BY date
    """
    
    df = pl.read_database(query, engine).to_pandas()
    df["net_new_highs"] = df["new_52w_highs"] - df["new_52w_lows"]
    df["new_high_low_ratio"] = df["new_52w_highs"] / df["new_52w_lows"].clip(lower=1)
    
    return pl.from_pandas(df)
```

### 6.6 Compute Strength Breadth

Per methodology 11.1. Atlas-specific — uses our state classifications.

```python
def compute_strength_breadth(target_date_or_range) -> pl.DataFrame:
    """
    Two measures: pct_in_strong_states, pct_weinstein_pass.
    """
    engine = get_engine()
    
    query = f"""
    SELECT 
        s.date,
        AVG(CASE WHEN s.rs_state IN ('Leader', 'Strong', 'Emerging') THEN 1.0 ELSE 0.0 END) AS pct_in_strong_states,
        AVG(CASE WHEN s.weinstein_gate_pass THEN 1.0 ELSE 0.0 END) AS pct_weinstein_pass
    FROM atlas.atlas_stock_states_daily s
    JOIN atlas.atlas_universe_stocks u 
        ON u.instrument_id = s.instrument_id AND u.effective_to IS NULL
    WHERE u.in_nifty_500 = TRUE
      AND s.date BETWEEN '{...}' AND '{...}'
      AND s.rs_state NOT IN ('INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED')
    GROUP BY s.date
    ORDER BY s.date
    """
    
    return pl.read_database(query, engine)
```

### 6.7 Volatility Inputs (India VIX + Nifty 500 Realized)

```python
def compute_volatility_inputs(target_date_or_range) -> pl.DataFrame:
    """
    India VIX level + Nifty 500 5-day realized vol + 252-day median vol.
    Used by regime classifier and dislocation override.
    """
    engine = get_engine()
    
    # India VIX
    vix = pl.read_database(
        f"""SELECT date, close AS india_vix 
            FROM public.de_index_prices 
            WHERE index_code = 'INDIA VIX'
              AND date BETWEEN '{...}' AND '{...}'""",
        engine,
    )
    
    # Nifty 500 5d realized vol + 252d median (from atlas_index_metrics_daily)
    n500_vol = pl.read_database(
        f"""SELECT date, realized_vol_5d AS realized_vol_5d_nifty500,
                   vol_252_median AS vol_252_median_nifty500
            FROM atlas.atlas_index_metrics_daily
            WHERE index_code = 'NIFTY 500'
              AND date BETWEEN '{...}' AND '{...}'""",
        engine,
    )
    
    return vix.join(n500_vol, on="date", how="outer")
```

### 6.8 Regime State Classifier

Per methodology 11.4. Threshold-driven per architecture 5.6.

```python
def classify_regime_state(
    regime_inputs_df: pl.DataFrame,
    thresholds: dict,
) -> pl.DataFrame:
    """
    Apply 4-state regime classification per methodology 11.4.
    
    Threshold-driven per architecture 5.6.
    """
    # Load threshold values
    RISK_ON_BREADTH = thresholds["regime_risk_on_breadth_min_pct"] / 100      # 0.60
    CONSTRUCTIVE_BREADTH = thresholds["regime_constructive_breadth_min_pct"] / 100  # 0.50
    RISK_OFF_BREADTH = thresholds["regime_risk_off_breadth_max_pct"] / 100    # 0.40
    RISK_ON_VIX = thresholds["regime_risk_on_vix_max"]                       # 18
    CONSTRUCTIVE_VIX = thresholds["regime_constructive_vix_max"]             # 22
    CAUTIOUS_VIX = thresholds["regime_cautious_vix_max"]                     # 28
    NEAR_BAND = thresholds["regime_near_200ema_band_pct"] / 100              # 0.02
    
    df = regime_inputs_df.to_pandas()
    
    above_200 = df["nifty500_above_ema_200"]
    pct_50 = df["pct_above_ema_50"]
    vix = df["india_vix"]
    
    # "near 200-EMA" band check
    distance_from_200ema = (df["nifty500_close"] - df["nifty500_ema_200"]).abs() / df["nifty500_ema_200"]
    near_200ema = distance_from_200ema <= NEAR_BAND
    
    # Breadth deteriorating proxy: 21-day change in pct_above_ema_50
    breadth_21d_change = pct_50 - pct_50.shift(21)
    breadth_deteriorating = breadth_21d_change < -0.10  # 10pp drop in 21 days
    
    conditions = [
        # Risk-Off: below 200-EMA AND breadth < 40% AND VIX > 28
        ~above_200 & (pct_50 < RISK_OFF_BREADTH) & (vix > CAUTIOUS_VIX),
        # Cautious: near 200-EMA OR breadth deteriorating OR VIX 22-28
        near_200ema | breadth_deteriorating | ((vix >= CONSTRUCTIVE_VIX) & (vix <= CAUTIOUS_VIX)),
        # Risk-On: above 200-EMA AND breadth > 60% AND VIX < 18
        above_200 & (pct_50 > RISK_ON_BREADTH) & (vix < RISK_ON_VIX),
        # Constructive: above 200-EMA AND breadth 50-60% AND VIX < 22
        above_200 & (pct_50 >= CONSTRUCTIVE_BREADTH) & (pct_50 <= RISK_ON_BREADTH) & (vix < CONSTRUCTIVE_VIX),
    ]
    choices = ["Risk-Off", "Cautious", "Risk-On", "Constructive"]
    
    df["regime_state"] = np.select(conditions, choices, default="Constructive")
    
    # Map state to multiplier
    multiplier_map = {"Risk-On": 1.0, "Constructive": 0.7, "Cautious": 0.4, "Risk-Off": 0.0}
    df["deployment_multiplier"] = df["regime_state"].map(multiplier_map)
    
    return pl.from_pandas(df)
```

### 6.9 Dislocation Override

Per methodology 11.5. Threshold-driven.

```python
def apply_dislocation_override(
    regime_df: pl.DataFrame,
    thresholds: dict,
) -> pl.DataFrame:
    """
    When 5-day realized vol exceeds threshold × 252-day median, 
    suspend all classifications system-wide.
    
    Override remains active for 5 trading days of normalized vol after
    the trigger condition clears.
    """
    DISLOCATION_MULTIPLIER = thresholds["dislocation_vol_multiplier"]  # default 4.0
    
    df = regime_df.to_pandas().sort_values("date")
    
    # Trigger condition
    df["dislocation_triggered"] = (
        df["realized_vol_5d_nifty500"] > 
        DISLOCATION_MULTIPLIER * df["vol_252_median_nifty500"]
    )
    
    # Active state: triggered today OR triggered within last 5 trading days
    df["dislocation_active"] = (
        df["dislocation_triggered"].rolling(5, min_periods=1).max().astype(bool)
    )
    
    # Track when dislocation started (for first day of suspension)
    df["dislocation_started"] = np.where(
        df["dislocation_triggered"] & ~df["dislocation_triggered"].shift(1).fillna(False),
        df["date"],
        None,
    )
    df["dislocation_started"] = df["dislocation_started"].ffill()
    
    # When dislocation is active, override regime_state
    df["regime_state"] = np.where(
        df["dislocation_active"],
        "DISLOCATION_SUSPENDED",
        df["regime_state"],
    )
    df["deployment_multiplier"] = np.where(
        df["dislocation_active"],
        0.0,  # Force zero deployment during dislocation
        df["deployment_multiplier"],
    )
    
    return pl.from_pandas(df)
```

**Note:** When dislocation is active, the regime row is still written (with `regime_state = 'DISLOCATION_SUSPENDED'` and `deployment_multiplier = 0.0`), but stock and ETF state classifiers downstream read this and apply their own DISLOCATION_SUSPENDED state per methodology 3.3. Atlas-M2's suspension override (`apply_suspension_overrides()`) handles this propagation.

### 6.10 Phase C Definition of Done

- [ ] `atlas_market_regime_daily` populated with one row per trading day in 12-year history
- [ ] All 28 columns populated (trend, MA breadth, A/D breadth, highs/lows, strength breadth, volatility, regime state, multiplier, dislocation flags)
- [ ] Dislocation override fires on known dislocations (verified: March 2020 COVID, October 2008 if data starts then)
- [ ] regime_state ∈ {Risk-On, Constructive, Cautious, Risk-Off, DISLOCATION_SUSPENDED} for every row
- [ ] deployment_multiplier ∈ {1.0, 0.7, 0.4, 0.0}
- [ ] No NULL values in regime_state column

---

## 7. Phase D — Pipeline Integration

### 7.1 Orchestration Order

Per architecture 5.3, M3 implements pipeline stages 4, 5, 6:

```
Stage 4: INDEX METRICS  (atlas/compute/indices.py)
  - For all 75 indices in atlas_universe_indices
  - Compute returns, RS vs Nifty 500, momentum, vol
  - Write atlas_index_metrics_daily
  
Stage 5: SECTOR AGGREGATION  (atlas/compute/sectors.py)
  - Bottom-up: aggregate from atlas_stock_metrics_daily + atlas_stock_states_daily
  - Top-down: read from atlas_index_metrics_daily for sectors with primary_nse_index
  - Compute breadth: participation_50, participation_rs, leadership_concentration
  - Classify sector states
  - Compute divergence flag
  - Write atlas_sector_metrics_daily, atlas_sector_states_daily

Stage 6: MARKET REGIME  (atlas/compute/regime.py)
  - Compute trend inputs from Nifty 500
  - Compute MA breadth (3 measures across Nifty 500)
  - Compute A/D breadth (5 measures including McClellan)
  - Compute highs/lows breadth (4 measures)
  - Compute strength breadth (2 measures, Atlas-specific)
  - Compute volatility inputs (India VIX + Nifty 500 vol)
  - Classify regime state
  - Apply dislocation override
  - Write atlas_market_regime_daily
```

Each stage runs after the previous completes. Stage 4 must complete before Stage 5 (sectors need top-down indices). Stage 5 must complete before Stage 6 (regime can use sector states for some breadth measures, though v0 uses stock states directly).

### 7.2 Daily Run Entry Point

```python
# scripts/m3_daily.py

def run_m3_daily(target_date: date):
    """Daily incremental run for M3 stages."""
    engine = get_engine()
    thresholds = load_thresholds(engine)
    
    # Stage 4: Index metrics
    print("Stage 4: Computing index metrics...")
    indices_result = compute_index_metrics(target_date, is_backfill=False)
    print(f"  Wrote {indices_result['rows_written']} rows for {indices_result['indices_processed']} indices")
    
    # Stage 5: Sector aggregation
    print("Stage 5: Computing sector aggregations...")
    bottom_up = compute_bottom_up_sector_metrics(target_date)
    top_down = compute_top_down_sector_metrics(target_date)
    breadth = compute_sector_breadth_measures(target_date)
    sector_metrics = bottom_up.join(top_down, on=["sector", "date"], how="left").join(
        breadth, on=["sector", "date"], how="left"
    )
    write_to_sector_metrics_table(engine, sector_metrics, run_id)
    
    # Sector state classification
    sector_states = classify_sector_state(sector_metrics, thresholds)
    sector_states_with_div = compute_divergence_flag(sector_states)
    write_to_sector_states_table(engine, sector_states_with_div, run_id)
    
    # Stage 6: Market regime
    print("Stage 6: Computing market regime...")
    trend = compute_regime_trend_inputs(target_date)
    ma_breadth = compute_ma_breadth(target_date)
    ad_breadth = compute_ad_breadth(target_date)
    hl_breadth = compute_highs_lows_breadth(target_date)
    strength_breadth = compute_strength_breadth(target_date)
    vol_inputs = compute_volatility_inputs(target_date)
    
    regime_inputs = (trend
        .join(ma_breadth, on="date")
        .join(ad_breadth, on="date")
        .join(hl_breadth, on="date")
        .join(strength_breadth, on="date")
        .join(vol_inputs, on="date")
    )
    
    regime_classified = classify_regime_state(regime_inputs, thresholds)
    regime_final = apply_dislocation_override(regime_classified, thresholds)
    write_to_market_regime_table(engine, regime_final, run_id)
    
    print(f"M3 daily complete for {target_date}")
```

### 7.3 Backfill Entry Point

```python
# scripts/m3_backfill.py

def run_m3_backfill():
    """Historical backfill for all 12 years of M3 outputs."""
    start = date(2014, 4, 1)
    end = date.today()
    
    # Same stages as daily, but with is_backfill=True and date range
    # Index metrics first (needed by sector top-down)
    compute_index_metrics(end, is_backfill=True, backfill_start=start)
    
    # Sector aggregation (depends on indices)
    # Must run for each date sequentially since breadth uses cross-stock state distribution
    all_dates = load_trading_dates(start, end)
    for d in all_dates:
        bottom_up = compute_bottom_up_sector_metrics(d)
        top_down = compute_top_down_sector_metrics(d)
        breadth = compute_sector_breadth_measures(d)
        # Combine, classify, write
        ...
    
    # Market regime (depends on stock states + index metrics)
    for d in all_dates:
        # Compute and write regime row for this date
        ...
```

### 7.4 Phase D Definition of Done

- [ ] `m3_daily.py` runs end-to-end without errors for one date
- [ ] `m3_backfill.py` runs end-to-end for full 12-year history
- [ ] All four target tables populated
- [ ] `atlas_run_log` shows successful M3 backfill run

---

## 8. Phase E — Validation

### 8.1 Tier 2 Validation — Computed Metrics

Per validation framework Section 3. Sample sizes for M3:

- Index metrics: 5 indices × 5 dates × 5 metrics = 125 hand-validations
- Sector aggregations: 3 sectors × 5 dates × 4 metrics = 60 hand-validations
- Breadth measures: 5 dates × 18 measures = 90 hand-validations

Total ~275 hand-validations. Each verifies against an independent implementation (different library or pure NumPy).

**Example: hand-validate `pct_above_ema_50`**

```python
def tier2_validate_pct_above_ema_50(engine, sample_dates):
    """
    Production: AVG(close > ema_50) over Nifty 500 universe.
    Hand: Independent SQL count.
    """
    failures = []
    for d in sample_dates:
        db_val = pl.read_database(
            f"SELECT pct_above_ema_50 FROM atlas.atlas_market_regime_daily WHERE date = '{d}'",
            engine,
        )["pct_above_ema_50"][0]
        
        # Hand: count manually
        hand_query = f"""
        SELECT 
            COUNT(*) FILTER (WHERE m.close > m.ema_50_stock) * 1.0 / COUNT(*) AS pct
        FROM atlas.atlas_stock_metrics_daily m
        JOIN atlas.atlas_universe_stocks u 
            ON u.instrument_id = m.instrument_id AND u.effective_to IS NULL
        WHERE u.in_nifty_500 = TRUE
          AND m.date = '{d}'
        """
        hand_val = pl.read_database(hand_query, engine)["pct"][0]
        
        if abs(db_val - hand_val) > 0.0001:
            failures.append({"date": d, "db": db_val, "hand": hand_val})
    
    return failures
```

### 8.2 Tier 3 Validation — State Classifications

Sample sizes:

- Sector states: 10 sectors × 1 date (today) = 10 hand-classifications
- Regime states: 30 dates (random sample from 12-year history) × 1 regime/date = 30 hand-classifications
- Divergence flags: 10 sector-date combinations where divergence is expected to fire

Hand-classification reference functions for each:

```python
def hand_classify_regime_state(regime_inputs, thresholds):
    """Verbatim translation of methodology 11.4 — independent from production."""
    # Reads thresholds (passed in), applies the four-state rules in order
    # Returns the state label
    ...
```

### 8.3 Tier 4 Validation — Cross-Table Consistency

Per validation framework Section 5.

**Critical M3 checks:**

- **Bottom-up sector reconstruction:** For 3 sample sectors, manually reconstruct `bottomup_rs_3m_nifty500` from `atlas_stock_metrics_daily` weighted by traded value, compare to stored value (within 0.5%).

- **Strength breadth reconstruction:** For 5 sample dates, count stocks in {Leader, Strong, Emerging} from `atlas_stock_states_daily` directly, compare to `pct_in_strong_states` × Nifty 500 universe size in `atlas_market_regime_daily` (exact match).

- **Universe coverage:** Every row in `atlas_sector_metrics_daily` references a sector that exists in `atlas_sector_master`. Zero orphans.

- **Threshold reference integrity (Tier 4 Category F):** All M3-relevant thresholds (`sector_*`, `regime_*`, `dislocation_vol_multiplier`) referenced in code; no hardcoded literals.

### 8.4 Tier 5 Validation — Three Consecutive Daily Runs

Three consecutive nightly runs with:
- Run completes within target time
- All target tables get new rows
- Regime state distribution stable (not flickering between states day-to-day)
- Dislocation override doesn't fire spuriously (only fires when 5d vol genuinely exceeds threshold)

### 8.5 Phase E Definition of Done

- [ ] Tier 2: 100% pass on ~275 hand-checks
- [ ] Tier 3: 100% pass on ~50 hand-classifications
- [ ] Tier 4: 0 orphan rows, breadth reconstructs exactly, sector aggregations within 0.5%
- [ ] Tier 5: 3 consecutive nightly runs pass
- [ ] `validation_M3_<date>.md` committed with all results

---

## 9. Atlas-M3 Definition of Done

The milestone is complete when ALL of the following are true:

**Code:**
- [ ] All compute modules implemented (indices.py, sectors.py, regime.py, breadth.py)
- [ ] All pipeline scripts working (m3_daily.py, m3_backfill.py)
- [ ] All unit tests pass

**Database:**
- [ ] `atlas_index_metrics_daily`: ~225K rows
- [ ] `atlas_sector_metrics_daily`: ~60K rows
- [ ] `atlas_sector_states_daily`: same row count
- [ ] `atlas_market_regime_daily`: ~3,000 rows
- [ ] All M3 backfill runs logged in `atlas_run_log`

**Validation:**
- [ ] Tier 2: 100% pass
- [ ] Tier 3: 100% pass
- [ ] Tier 4: 0 inconsistencies
- [ ] Tier 5: 3 consecutive nightly runs pass
- [ ] `validation_M3_<date>.md` shows PASS

**Sign-off:**
- [ ] Engineer (Claude Code): Build complete
- [ ] Architect (Nimish): Spot-checked validation report
- [ ] Fund Manager (Bhaven): Spot-checked 3 sector classifications and 1 month of regime calls; agrees with output

---

## 10. Common Pitfalls (Read Before Building)

**1. Sector aggregation weight choice.** v0 uses traded value as a proxy for market cap because cap data in JIP is categorical. If true market cap data becomes available later, switch the weight column without changing the aggregation logic. Document the weight choice clearly in validation report.

**2. Top-down NSE index naming.** NSE has subtle inconsistencies — "NIFTY BANK" vs "NIFTY FINANCIAL SERVICES" vs "NIFTY PRIVATE BANK" all relate to banking but are different indices. The `de_sector_mapping` table specifies which is the "primary" for each sector. Use that, not your own intuition.

**3. McClellan EMA seeding.** pandas-ta's EMA seeds with the first value by default. When computing McClellan on the cumulative net advances series, the first 39 days will have a transient seeding effect. Document this; for hand-validation, match the seeding behavior.

**4. Dislocation override flicker.** If 5d vol crosses the threshold for one day then drops back, the override should remain active for 5 trading days. The `rolling(5, min_periods=1).max()` pattern handles this; don't try to optimize this away.

**5. Don't compute regime if stock states for that date are missing.** Strength breadth needs `atlas_stock_states_daily` populated. If a date is missing in M2 outputs, regime computation for that date should fail loudly, not produce a regime row with NULL strength breadth values.

**6. Sector divergence flag — top-down NULL means no divergence.** Sectors without a primary NSE sectoral index can't have a divergence flag (there's nothing to diverge from). Set `divergence_flag = FALSE` for these, not NULL.

**7. India VIX history.** India VIX data in `de_index_prices` may not extend back to 2014. If VIX is unavailable for early dates, regime classification can still work with breadth + trend, but VIX-based rule clauses can't fire. Document this limitation in validation report.

**8. Don't write decision rows in M3.** M3 produces sector states and regime states. Decision flags (investability, entry triggers, exit triggers) are M5. Resist the urge to compute them here.

**9. Threshold loading per run, not per row.** `load_thresholds()` is called once at the start of `run_m3_daily()`. Don't call it inside loops — that's a database query per row.

**10. Sector RS state classifier needs cross-sector ranking.** Sectors don't have a "tier" the way stocks do. To classify a sector's bottom-up RS state, either (a) percentile-rank against other sectors that day, or (b) use absolute thresholds against Nifty 500 RS values. v0 uses approach (a) — document the choice.

---

## 11. Foundation Document Sync Checks

Before starting M3 build, verify these specific cross-document references:

| Check | Documents Involved |
|---|---|
| Sector states: 4 states (Overweight/Neutral/Underweight/Avoid) | Methodology 10.5 ↔ Schema 4.3 ↔ M3 Section 5.5 |
| Regime states: 4 states + DISLOCATION_SUSPENDED meta-state | Methodology 11.4 ↔ Schema 3.5 ↔ M3 Section 6.8 |
| Deployment multipliers: {1.0, 0.7, 0.4, 0.0} | Methodology 11.4 ↔ Schema 3.5 (CHECK constraint) ↔ M3 Section 6.8 |
| Sector taxonomy from de_instrument.sector | Methodology 10.1 ↔ Atlas-M1 atlas_sector_master ↔ M3 |
| Three sector breadth measures match methodology | Methodology 10.4 ↔ Schema 3.4 ↔ M3 Section 5.4 |
| 18 regime input measures across 4 breadth families | Methodology 11.1 ↔ Schema 3.5 (28 columns) ↔ M3 Section 6 |
| Dislocation: 5d vol > 4× 252d median; 5-day persistence | Methodology 11.5 ↔ Threshold Catalog 10.8 ↔ M3 Section 6.9 |
| Sector threshold keys: 3 keys | Threshold Catalog 9 ↔ M3 Section 5.5 |
| Regime threshold keys: 8 keys | Threshold Catalog 10 ↔ M3 Section 6.8 |
| All classifiers receive thresholds dict | Architecture 5.6 ↔ M3 Sections 5.5, 6.8 |
| No volume primitive for indices | Methodology 9 ↔ Schema 3.3 (no volume cols) ↔ M3 Section 4 |
| Bottom-up vs top-down stored side-by-side; divergence flag computed | Methodology 10.2/10.3/10.6 ↔ Schema 3.4 ↔ M3 Section 5.6 |

If the cross-review finds any inconsistency, halt build and resolve at source documents.

---

## 12. Open Questions

Document these in the validation report rather than guessing:

1. **EMA 50 for stocks — store in M2 or compute transiently in M3?** v0 design assumes M2 stores ema_50_stock. If M2 schema doesn't include it, decide: (a) extend M2 schema and rerun M2 backfill, (b) compute EMA 50 transiently in M3 each run. Option (a) is cleaner but costs M2 rerun time; (b) is faster to deliver but adds compute per M3 run.

2. **Sector RS state classification — cross-sector percentile rank or absolute Nifty 500 thresholds?** v0 default: cross-sector percentile rank with same 0.80/0.20 quintile cutoffs. Document the choice.

3. **What happens when a sector has < 5 constituent stocks?** Some IISL sectors might have very few names in our 750-stock universe. Leadership concentration calculation fails if fewer than 5 stocks. Default behavior: set `leadership_concentration = NULL` and log warning.

4. **Breadth measures for dates before sufficient cross-stock coverage.** Earliest dates in our 12-year history may have many stocks classified INSUFFICIENT_HISTORY. Strength breadth computed only over qualifying stocks may be misleading early on. Document the universe size on each date and whether breadth measures are reliable.

---

## 13. What Comes Next

Atlas-M4 (Mutual Fund Three-Lens Engine) builds on stock states (M2) and sector states (M3) to compute fund Lens 2 (composition) and Lens 3 (holdings quality). Lens 1 (NAV behavior) is independent of M3 outputs.

Atlas-M4 cannot start until Atlas-M3 validation report is signed off.

---

**Document version:** 1.0
**Last updated:** 2026-05-04
**Next review:** Atlas-M3 completion

# Atlas-M2 — Stock and ETF Metric Engine

**Document:** ATLAS_M2_STOCK_ETF_METRICS
**Status:** v0
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**Builder:** Claude Code (intended executor)
**References:**
- `00_METHODOLOGY_LOCK.md` (defines what gets computed; especially Sections 7, 8)
- `01_BACKEND_ARCHITECTURE.md` (compute strategy, library discipline, naming conventions; especially Section 5)
- `02_DATABASE_SCHEMA.md` (target table definitions; Sections 3.1, 3.2, 4.1, 4.2)
- `03_VALIDATION_FRAMEWORK.md` (Tier 2, Tier 3 validation criteria)
- `ATLAS_M1_SCHEMA_AND_REFERENCE.md` (predecessor — universe must be locked first)

---

> **Patch note (2026-05-06, per `prds/00_INFRA_DECISIONS.md`):** M2 stock metric
> output additionally includes:
> - `ema_50_stock` — required by methodology 11.1 (M3 market regime breadth measure)
> - `atr_21` — required by methodology 13.4 trigger 6 (M5 ATR-stop exit)
> - **Below Trend conjunction:** when Weinstein gate fails, classifier sets
>   `risk_state = "Below Trend"` AND forces `rs_state` to `Average` atomically (per
>   methodology 7.3 terminal-classification rule).
> - **Stage-1 base bootstrap:** during a stock's first 50 trading days, Stage-1 base
>   qualification only requires the MA-flat condition (skips the "8-of-10 weeks weak"
>   check, which can't evaluate on a sparse history). Implementation:
>   `atlas/compute/states.py:compute_stage1_base`.

## 1. Goal

Compute the four primitives (Relative Strength, RS Momentum, Relative Risk, Volume) for all 750 stocks and 100 ETFs across the full 12-year history (2014-04-01 to present). Apply state classification per methodology Sections 7 and 8. Persist results in Layer 3 metric and state tables.

After this milestone:

- `atlas_stock_metrics_daily` populated with ~2.25M rows (750 stocks × ~3,000 trading days)
- `atlas_stock_states_daily` populated with ~2.25M rows
- `atlas_etf_metrics_daily` populated with ~250K rows (100 ETFs × ~2,500 trading days)
- `atlas_etf_states_daily` populated with ~250K rows
- `atlas_benchmark_returns_cache` materialized for the 9 benchmarks
- Daily incremental compute pipeline functional (T-1 ingest → metrics → states)
- Historical backfill complete and validated

**No sector aggregation. No market regime. No mutual fund lenses. No decisions.** Those are M3, M4, M5. Atlas-M2 is the atomic compute layer only.

---

## 2. Dependencies

### 2.1 Predecessors

**Atlas-M1** must be complete and signed off. Specifically:

- `atlas` schema exists with all 28 tables created
- `atlas_universe_stocks`, `atlas_universe_etfs`, `atlas_sector_master`, `atlas_benchmark_master` populated
- All M1 validation checks passed

If M1's universe row counts deviated from spec, M2 will not produce expected output volumes. M2 cannot start until M1 signoff.

### 2.2 Foundation Document Consistency Checks

Before building, verify these consistency points (cross-document references that M2 depends on being correct):

| Foundation Reference | What M2 Depends On |
|---|---|
| Methodology 7.1 (RS states) | Seven RS states named: Leader, Strong, Consolidating, Emerging, Average, Weak, Laggard — must match VARCHAR values in `atlas_stock_states_daily.rs_state` |
| Methodology 7.2 (Momentum states) | Five states: Accelerating, Improving, Flat, Deteriorating, Collapsing |
| Methodology 7.3 (Risk states) | Five states: Low, Normal, Elevated, High, Below Trend |
| Methodology 7.4 (Volume states) | Five states: Accumulation, Steady-Buying, Neutral, Distribution, Heavy Distribution |
| Methodology 4.1 (Time horizons) | 1W=5, 1M=21, 3M=63, 6M=126, 12M=252, 12M-1M=231 trading days |
| Architecture 5.5 (Library discipline) | All EMAs computed via `pandas-ta` v0.3.14b; all drawdowns via `empyrical` v0.5.5 |
| Schema 3.1 (Stock metrics columns) | 50+ columns must be populated; gold numéraire variants computed |
| Schema 4.1 (Stock states columns) | Suspended states are: INSUFFICIENT_HISTORY, ILLIQUID, DISLOCATION_SUSPENDED |
| Validation 3.4 (Tier 2 sample size) | 1,875 hand-validations required for M2 sign-off |
| Validation 4.5 (Tier 3 pass rate) | 100% match required across 30 stocks × all state types |

If any foundation document needs updating to support M2, escalate before building. **Do not silently diverge.**

### 2.3 Required JIP Data Core Tables (Read-Only)

| Table | Used For | Identifier | Date Column |
|---|---|---|---|
| `de_equity_ohlcv` | Stock OHLCV (the primary input) | `instrument_id` | `date` |
| `de_etf_ohlcv` | ETF OHLCV | `ticker` | `date` |
| `de_index_prices` | Tier benchmark prices (Nifty 100, Midcap 150, etc.) | `index_code` | `date` |
| `de_global_prices` | MSCI World, S&P 500, GOLDBEES | `ticker` | `date` |
| `de_trading_calendar` | Trading days, half-sessions, event days | `exchange` | `date` |
| `de_corporate_actions` | Splits, bonuses, demergers | `instrument_id` | `ex_date` |

### 2.4 Required Atlas Reference Tables (Read)

| Table | Used For |
|---|---|
| `atlas_universe_stocks` | The 750-stock universe with tier classification |
| `atlas_universe_etfs` | The 100-ETF universe with theme classification |
| `atlas_benchmark_master` | The 9 benchmarks with source mappings |
| `atlas_sector_master` | Sector linkage for stocks |

---

## 3. Deliverables

### 3.1 Code Deliverables

```
atlas-backend/
├── atlas/
│   ├── compute/
│   │   ├── __init__.py
│   │   ├── primitives.py              # The four primitive math functions
│   │   ├── states.py                  # State classification logic
│   │   ├── gates.py                   # Pre-classification gates (history, liquidity, etc.)
│   │   ├── stocks.py                  # Stock metric pipeline
│   │   ├── etfs.py                    # ETF metric pipeline
│   │   ├── benchmarks.py              # Benchmark cache materialization
│   │   └── corp_actions.py            # Corporate action handling
│   ├── validation/
│   │   ├── tier2_metrics.py           # Hand-computed reference values
│   │   ├── tier3_states.py            # Hand-classified reference values
│   │   └── samplers.py                # Deterministic sample selection
│   └── orchestration/
│       └── stages.py                  # Stage 3 implementation (per architecture 5.3)
├── scripts/
│   ├── m2_backfill.py                 # Historical backfill (12 years, one-time)
│   └── m2_daily.py                    # Daily incremental run
├── tests/
│   └── unit/
│       ├── test_primitives.py
│       ├── test_states.py
│       └── test_gates.py
└── docs/validation/
    └── validation_M2_<date>.md
```

### 3.2 Database Deliverables

| Table | Expected Rows After Backfill |
|---|---|
| `atlas_stock_metrics_daily` | ~2.25M |
| `atlas_stock_states_daily` | ~2.25M |
| `atlas_etf_metrics_daily` | ~250K |
| `atlas_etf_states_daily` | ~250K |
| `atlas_benchmark_returns_cache` | ~27K (9 benchmarks × ~3,000 days) |
| `atlas_run_log` | At least one M2 run row |
| `atlas_validation_results` | Per-tier check rows |

### 3.3 Validation Deliverables

- `validation_M2_<date>.md` with passing Tier 2 (1,875 hand-checks) and Tier 3 (~120 state-classification checks)
- Three consecutive nightly incremental runs passing Tier 5 monitoring

---

## 4. Phase A — The Four Primitives Implementation

### 4.1 Goal

Implement the four primitive computations as pure Polars/NumPy/pandas-ta functions, following library discipline. Each function takes a DataFrame and returns a DataFrame with new columns added.

### 4.2 Primitive 1 — Relative Strength

Per methodology Section 7.1.

**Function signature:**

```python
def compute_relative_strength(
    stock_df: pl.DataFrame,           # Columns: instrument_id, date, close (adjusted)
    benchmark_df: pl.DataFrame,       # Columns: benchmark_code, date, close
    benchmarks: list[str],            # e.g. ["NIFTY100", "NIFTY500", "GOLD", ...]
    windows: dict[str, int]           # {"1w": 5, "1m": 21, "3m": 63, ...}
) -> pl.DataFrame:
    """
    Compute RS at all (window, benchmark) combinations.
    Returns DataFrame with columns:
        instrument_id, date,
        ret_1w, ret_1m, ret_3m, ret_6m, ret_12m, ret_12m_1m,
        rs_1w_<benchmark>, rs_1m_<benchmark>, ... for each benchmark
    """
```

**Implementation:**

```python
import polars as pl

WINDOWS = {
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
    "12m_1m": 231,  # 252 - 21 (skip-most-recent-month variant)
}

def compute_returns(df: pl.DataFrame, price_col: str = "close") -> pl.DataFrame:
    """Compute returns at all standard windows. Decimal, not percent."""
    return df.with_columns([
        (pl.col(price_col) / pl.col(price_col).shift(n) - 1).alias(f"ret_{name}")
        for name, n in WINDOWS.items()
    ])

def compute_relative_strength(
    stock_df: pl.DataFrame,
    benchmark_df: pl.DataFrame,
    benchmarks: list[str],
    windows: dict[str, int] = WINDOWS,
) -> pl.DataFrame:
    """
    Compute RS for stock vs each benchmark across all windows.
    
    RS_n(stock, benchmark, t) = ret_n(stock, t) - ret_n(benchmark, t)
    """
    # First compute stock returns
    stock_with_returns = compute_returns(stock_df, "close")
    
    # Compute benchmark returns (one row per benchmark per date)
    benchmark_returns = (
        benchmark_df
        .sort(["benchmark_code", "date"])
        .with_columns([
            pl.col("close").pct_change(n).over("benchmark_code").alias(f"ret_{name}")
            for name, n in windows.items()
        ])
    )
    
    # Pivot benchmark returns wide: one column per (benchmark, window)
    result = stock_with_returns
    for benchmark in benchmarks:
        bench_data = (
            benchmark_returns
            .filter(pl.col("benchmark_code") == benchmark)
            .select(["date"] + [f"ret_{name}" for name in windows])
            .rename({f"ret_{name}": f"_bench_ret_{name}_{benchmark}" for name in windows})
        )
        result = result.join(bench_data, on="date", how="left")
        
        # Compute RS for each window against this benchmark
        result = result.with_columns([
            (pl.col(f"ret_{name}") - pl.col(f"_bench_ret_{name}_{benchmark}"))
                .alias(f"rs_{name}_{benchmark.lower()}")
            for name in windows
        ])
        
        # Drop intermediate columns
        result = result.drop([f"_bench_ret_{name}_{benchmark}" for name in windows])
    
    return result
```

**Within-tier percentile ranking:**

After computing RS values for all stocks, percentile-rank within tier on each date:

```python
def compute_within_tier_percentiles(
    metrics_df: pl.DataFrame,        # Has rs_<window>_<tier_benchmark> columns
    universe_df: pl.DataFrame,        # Has instrument_id, tier columns
    classification_windows: list[str] = ["1w", "1m", "3m"],
) -> pl.DataFrame:
    """
    For each (date, tier, window), compute percentile rank of each stock's RS.
    Returns DataFrame with rs_pctile_1w, rs_pctile_1m, rs_pctile_3m columns.
    
    Critical: The benchmark used here is the TIER benchmark, per methodology Section 6.4.
    For Large stocks → use rs_*_nifty100; for Mid → rs_*_midcap150; etc.
    """
    # Join in tier from universe
    joined = metrics_df.join(
        universe_df.filter(pl.col("effective_to").is_null()).select(["instrument_id", "tier"]),
        on="instrument_id",
        how="left",
    )
    
    # Map tier to its benchmark column
    tier_benchmark_col = {
        "Large": "nifty100",
        "Mid": "midcap150",
        "Small": "smallcap250",
        "Micro": "microcap_custom",
    }
    
    # For each window, rank within tier
    for window in classification_windows:
        # Compute the "RS against own tier benchmark" column
        # Using a CASE-based selection
        joined = joined.with_columns(
            pl.when(pl.col("tier") == "Large").then(pl.col(f"rs_{window}_nifty100"))
            .when(pl.col("tier") == "Mid").then(pl.col(f"rs_{window}_midcap150"))
            .when(pl.col("tier") == "Small").then(pl.col(f"rs_{window}_smallcap250"))
            .when(pl.col("tier") == "Micro").then(pl.col(f"rs_{window}_microcap_custom"))
            .alias(f"rs_{window}_tier")
        )
        
        # Percentile rank within (tier, date)
        joined = joined.with_columns(
            (pl.col(f"rs_{window}_tier")
                .rank(method="dense")
                .over(["date", "tier"])
                / pl.col(f"rs_{window}_tier").count().over(["date", "tier"]))
            .alias(f"rs_pctile_{window}")
        )
    
    return joined
```

### 4.3 Primitive 2 — RS Momentum (Bhaven's EMA-Ratio Approach)

Per methodology Section 7.2.

**Implementation:**

```python
import pandas as pd
import pandas_ta as ta

def compute_rs_momentum(
    stock_df: pl.DataFrame,           # Columns: instrument_id, date, close
    benchmark_df: pl.DataFrame,       # Single tier benchmark for this stock's tier
) -> pl.DataFrame:
    """
    Per methodology 7.2:
    - ema_10_ratio = ema_10_stock / ema_10_benchmark
    - ema_20_ratio = ema_20_stock / ema_20_benchmark
    
    Implementation uses pandas-ta for EMA per architecture Section 5.5.
    """
    # Convert to pandas (pandas-ta requirement) for EMA computation
    stock_pd = stock_df.to_pandas().sort_values("date")
    benchmark_pd = benchmark_df.to_pandas().sort_values("date")
    
    # Compute EMAs using pandas-ta
    stock_pd["ema_10_stock"] = ta.ema(stock_pd["close"], length=10)
    stock_pd["ema_20_stock"] = ta.ema(stock_pd["close"], length=20)
    
    benchmark_pd["ema_10_benchmark"] = ta.ema(benchmark_pd["close"], length=10)
    benchmark_pd["ema_20_benchmark"] = ta.ema(benchmark_pd["close"], length=20)
    
    # Merge on date (left join — preserve stock dates)
    merged = stock_pd.merge(
        benchmark_pd[["date", "ema_10_benchmark", "ema_20_benchmark"]],
        on="date",
        how="left",
    )
    
    # Compute ratios
    merged["ema_10_ratio"] = merged["ema_10_stock"] / merged["ema_10_benchmark"]
    merged["ema_20_ratio"] = merged["ema_20_stock"] / merged["ema_20_benchmark"]
    
    # Compute "EMA10 at 20-day high" and "EMA10 at 20-day low" flags
    # Used for Accelerating and Collapsing classifications per methodology 7.2
    merged["ema_10_at_20d_high"] = (
        merged["ema_10_ratio"] == merged["ema_10_ratio"].rolling(20, min_periods=1).max()
    )
    merged["ema_10_at_20d_low"] = (
        merged["ema_10_ratio"] == merged["ema_10_ratio"].rolling(20, min_periods=1).min()
    )
    
    return pl.from_pandas(merged)
```

**Note:** The ema_10_at_20d_high check is implemented as `current_value == rolling_20d_max`, which is True when today's value sets a new 20-day high (or ties it). Validation Tier 2 verifies this matches the methodology intent.

### 4.4 Primitive 3 — Relative Risk

Per methodology Section 7.3.

**Implementation:**

```python
import numpy as np
import pandas_ta as ta
import empyrical as ep

def compute_relative_risk(
    stock_df: pl.DataFrame,
    benchmark_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Three independent risk measures per methodology 7.3:
    - extension_pct = (close - ema_200) / ema_200
    - vol_ratio_63 = realized_vol(stock, 63d) / realized_vol(benchmark, 63d)
    - drawdown_ratio_252 = max_drawdown(stock, 252d) / max_drawdown(benchmark, 252d)
    
    Per architecture 5.5:
    - EMA via pandas-ta
    - Drawdown via empyrical
    - Volatility via NumPy primitive (annualized)
    """
    stock_pd = stock_df.to_pandas().sort_values("date")
    benchmark_pd = benchmark_df.to_pandas().sort_values("date")
    
    # Extension: (close - ema_200) / ema_200
    stock_pd["ema_200_stock"] = ta.ema(stock_pd["close"], length=200)
    stock_pd["extension_pct"] = (
        (stock_pd["close"] - stock_pd["ema_200_stock"]) / stock_pd["ema_200_stock"]
    )
    
    # Realized vol (63d, annualized)
    stock_pd["daily_return"] = stock_pd["close"].pct_change()
    stock_pd["realized_vol_63"] = (
        stock_pd["daily_return"].rolling(63, min_periods=42).std() * np.sqrt(252)
    )
    
    benchmark_pd["daily_return"] = benchmark_pd["close"].pct_change()
    benchmark_pd["realized_vol_63"] = (
        benchmark_pd["daily_return"].rolling(63, min_periods=42).std() * np.sqrt(252)
    )
    
    merged = stock_pd.merge(
        benchmark_pd[["date", "realized_vol_63"]].rename(
            columns={"realized_vol_63": "benchmark_vol_63"}
        ),
        on="date",
        how="left",
    )
    
    merged["vol_ratio_63"] = merged["realized_vol_63"] / merged["benchmark_vol_63"]
    
    # Max drawdown — rolling 252-day window, using empyrical-style max-drawdown
    def rolling_max_dd(returns: pd.Series, window: int = 252) -> pd.Series:
        """For each date, the max drawdown of the trailing `window` days."""
        result = pd.Series(index=returns.index, dtype=float)
        for i in range(window - 1, len(returns)):
            window_returns = returns.iloc[i - window + 1 : i + 1]
            if window_returns.notna().sum() < window // 2:
                result.iloc[i] = np.nan
            else:
                # max_drawdown returns negative value; we keep absolute
                result.iloc[i] = abs(ep.max_drawdown(window_returns.dropna()))
        return result
    
    merged["max_drawdown_252"] = rolling_max_dd(merged["daily_return"], 252)
    
    benchmark_pd["max_drawdown_252_bench"] = rolling_max_dd(
        benchmark_pd["daily_return"], 252
    )
    
    merged = merged.merge(
        benchmark_pd[["date", "max_drawdown_252_bench"]],
        on="date",
        how="left",
    )
    
    merged["drawdown_ratio_252"] = (
        merged["max_drawdown_252"] / merged["max_drawdown_252_bench"]
    )
    
    return pl.from_pandas(merged)
```

**Performance note:** The rolling max drawdown function above is O(n × window). For 750 stocks × 3,000 days × 252-window, this is ~570M operations — acceptable but slow. Optimize via vectorized pandas operations if total compute time exceeds budget:

```python
# Faster vectorized version (alternative implementation):
def rolling_max_dd_vectorized(returns: pd.Series, window: int = 252) -> pd.Series:
    cumulative = (1 + returns.fillna(0)).cumprod()
    rolling_max = cumulative.rolling(window, min_periods=window // 2).max()
    drawdown = cumulative / rolling_max - 1
    return drawdown.rolling(window, min_periods=window // 2).min().abs()
```

### 4.5 Primitive 4 — Volume

Per methodology Section 7.4.

**Implementation:**

```python
def compute_volume_primitive(
    stock_df: pl.DataFrame,           # Columns include: open, close, volume
    trading_calendar_df: pl.DataFrame, # For event-day filtering
) -> pl.DataFrame:
    """
    Two sub-measures per methodology 7.4:
    - volume_expansion = avg_volume(20d) / avg_volume(252d)
    - effort_ratio_63 = sum(volume on up-days, 63d) / sum(volume on down-days, 63d)
    
    Event days excluded per pre-classification gate (methodology 3.3).
    """
    stock_pd = stock_df.to_pandas().sort_values("date")
    
    # Pre-flag up days, down days, event days
    stock_pd["is_up_day"] = stock_pd["close"] >= stock_pd["open"]
    stock_pd["is_down_day"] = stock_pd["close"] < stock_pd["open"]
    
    # Event-day filter: exclude half-sessions and major event days from rolling windows
    event_dates = set(
        trading_calendar_df
        .filter(
            pl.col("is_half_session").or_(pl.col("is_major_event_day"))
        )
        .get_column("date")
        .to_list()
    )
    stock_pd["is_event_day"] = stock_pd["date"].isin(event_dates)
    
    # Volume expansion (excludes event days from both windows)
    stock_pd["volume_clean"] = stock_pd.apply(
        lambda r: r["volume"] if not r["is_event_day"] else np.nan, axis=1
    )
    stock_pd["avg_volume_20"] = stock_pd["volume_clean"].rolling(20, min_periods=14).mean()
    stock_pd["avg_volume_252"] = stock_pd["volume_clean"].rolling(252, min_periods=180).mean()
    stock_pd["volume_expansion"] = stock_pd["avg_volume_20"] / stock_pd["avg_volume_252"]
    
    # Effort ratio (63d): up-day volume sum / down-day volume sum
    stock_pd["up_day_volume"] = (
        stock_pd["volume_clean"].where(stock_pd["is_up_day"], 0)
    )
    stock_pd["down_day_volume"] = (
        stock_pd["volume_clean"].where(stock_pd["is_down_day"], 0)
    )
    
    stock_pd["up_volume_sum_63"] = stock_pd["up_day_volume"].rolling(63, min_periods=42).sum()
    stock_pd["down_volume_sum_63"] = stock_pd["down_day_volume"].rolling(63, min_periods=42).sum()
    
    # Avoid divide-by-zero: clip down_volume to minimum 1
    stock_pd["effort_ratio_63"] = (
        stock_pd["up_volume_sum_63"] / stock_pd["down_volume_sum_63"].clip(lower=1)
    )
    
    return pl.from_pandas(stock_pd)
```

### 4.6 Weinstein Gate Implementation

Per methodology Section 7.1.

```python
def compute_weinstein_gate(stock_df: pl.DataFrame) -> pl.DataFrame:
    """
    Weinstein absolute-trend gate:
    - price > 30_week_MA AND
    - 30_week_MA slope (last 4 weeks) >= -0.5σ (i.e., flat or rising)
    
    30-week MA = 150-trading-day MA.
    """
    stock_pd = stock_df.to_pandas().sort_values("date")
    
    # 30-week MA (150 trading days)
    stock_pd["ma_30w"] = stock_pd["close"].rolling(150, min_periods=100).mean()
    
    # Price > MA condition
    stock_pd["price_above_30w_ma"] = stock_pd["close"] > stock_pd["ma_30w"]
    
    # 30-week MA slope over last 4 weeks (20 trading days)
    # Slope = (ma_today - ma_20_days_ago) / ma_20_days_ago
    stock_pd["ma_30w_slope_4w"] = (
        (stock_pd["ma_30w"] - stock_pd["ma_30w"].shift(20)) / stock_pd["ma_30w"].shift(20)
    )
    
    # σ-normalize slope using its own 252-day stdev
    slope_std = stock_pd["ma_30w_slope_4w"].rolling(252, min_periods=180).std()
    stock_pd["ma_30w_slope_4w_sigma"] = stock_pd["ma_30w_slope_4w"] / slope_std
    
    # Flat or rising: slope >= -0.5σ
    stock_pd["ma_flat_or_rising"] = stock_pd["ma_30w_slope_4w_sigma"] >= -0.5
    
    # Gate passes when both conditions hold
    stock_pd["weinstein_gate_pass"] = (
        stock_pd["price_above_30w_ma"] & stock_pd["ma_flat_or_rising"]
    )
    
    return pl.from_pandas(stock_pd)
```

### 4.7 Stage-1 Base Detection

Per methodology Section 7.1 (additional precondition for Emerging classification).

```python
def compute_stage1_base(
    states_history_df: pl.DataFrame,    # Past rs_state values for this stock
    metrics_df: pl.DataFrame,           # Has ma_30w_slope_4w_sigma column
) -> pl.DataFrame:
    """
    A stock qualifies as Stage-1 base if:
    - Was classified in {Average, Weak, Laggard} for at least 8 of last 10 weekly closes
    - 30-week MA has been flat (slope within ±0.5σ over trailing 4 weeks)
    
    Note: This depends on PRIOR state classifications, creating a temporal dependency.
    Bootstrapping for historical backfill: use Average as default for first 10 weeks
    of any stock's history. Document this as a known v0 limitation.
    """
    df = states_history_df.to_pandas().sort_values("date")
    
    # Weekly closes — every 5th trading day
    weekly_marker = df.index % 5 == 0  # Approximate; refine using calendar
    
    # For each date, look back 10 weekly closes
    # If 8+ of those were in {Average, Weak, Laggard}, base condition met
    
    weak_states = {"Average", "Weak", "Laggard"}
    
    # Rolling count of weak-state weekly closes
    df["was_weak_at_week"] = df["rs_state"].isin(weak_states) & weekly_marker
    df["weak_weeks_in_last_10"] = (
        df["was_weak_at_week"].rolling(50, min_periods=10).sum()  # 10 weeks ≈ 50 trading days
    )
    df["base_history_qualifies"] = df["weak_weeks_in_last_10"] >= 8
    
    # MA flat condition (already computed in weinstein gate)
    df["ma_flat"] = df["ma_30w_slope_4w_sigma"].abs() <= 0.5
    
    # Both must be true
    df["stage1_base_qualifies"] = df["base_history_qualifies"] & df["ma_flat"]
    
    return pl.from_pandas(df)
```

**Bootstrap caveat:** During historical backfill, the first 10 weeks of each stock's history don't have prior state classifications to look back on. v0 default: `stage1_base_qualifies = False` for the first 10 weeks. Document this in validation report.

### 4.8 Phase A Definition of Done

- [ ] `atlas/compute/primitives.py` implements all four primitives
- [ ] `atlas/compute/gates.py` implements pre-classification gates and Weinstein gate
- [ ] Unit tests pass for each primitive function (test fixtures with known inputs/outputs)
- [ ] Library imports verified: pandas-ta, empyrical, scipy versions match architecture Section 5.1

---

## 5. Phase B — State Classification

### 5.1 Goal

Translate the methodology rules from Sections 7.1–7.4 into NumPy `np.select` classifiers. Each classifier takes a row of metric values **and a thresholds dict** and returns a state label.

**Threshold-driven pattern (mandatory per architecture Section 5.6):**

All numeric thresholds in classification logic come from the `atlas_thresholds` table, loaded once per pipeline run. Classifier functions receive thresholds as a parameter — they never read from the database internally, and they never use hardcoded threshold values.

```python
# Standard pattern for every classifier in this section:
def classify_<primitive>_state(metrics_df: pl.DataFrame, thresholds: dict) -> pl.DataFrame:
    # Look up threshold values at function start
    PARAM_A = thresholds["threshold_key_a"]
    PARAM_B = thresholds["threshold_key_b"]
    
    # Build conditions using threshold variables, not literals
    conditions = [
        df["metric_x"] >= PARAM_A,
        df["metric_y"] <= PARAM_B,
        ...
    ]
    
    df["state_column"] = np.select(conditions, choices, default="...")
    return df
```

**Threshold loading (called once at pipeline start):**

```python
def load_thresholds(engine) -> dict:
    """Read all active thresholds from atlas_thresholds. Returns {key: value} dict."""
    rows = pl.read_database(
        "SELECT threshold_key, threshold_value FROM atlas.atlas_thresholds WHERE is_active = TRUE",
        engine,
    )
    return dict(zip(rows["threshold_key"], rows["threshold_value"]))
```

The thresholds dict is passed through the call chain to every classifier. Functions never call `load_thresholds()` themselves — they receive the dict as a parameter. This makes unit testing straightforward (pass a synthetic dict).

### 5.2 RS State Classifier

Per methodology 7.1.

```python
import numpy as np
import polars as pl

def classify_rs_state(metrics_df: pl.DataFrame, thresholds: dict) -> pl.DataFrame:
    """
    Apply the 7-state RS classification per methodology 7.1.
    Requires columns:
        rs_pctile_1w, rs_pctile_1m, rs_pctile_3m
        weinstein_gate_pass
        stage1_base_qualifies
    
    Output column: rs_state ∈ {
        Leader, Strong, Consolidating, Emerging, Average, Weak, Laggard
    }
    
    Threshold-driven per architecture 5.6 — quintile cutoffs come from atlas_thresholds.
    """
    # Load threshold values (passed in by caller from atlas_thresholds)
    TOP = thresholds["rs_quintile_top"]      # default 0.80
    BOT = thresholds["rs_quintile_bottom"]   # default 0.20
    
    df = metrics_df.to_pandas()
    
    p1w = df["rs_pctile_1w"]
    p1m = df["rs_pctile_1m"]
    p3m = df["rs_pctile_3m"]
    weinstein = df["weinstein_gate_pass"]
    stage1 = df["stage1_base_qualifies"]
    
    in_top_1w = p1w >= TOP
    in_top_1m = p1m >= TOP
    in_top_3m = p3m >= TOP
    in_bottom_1w = p1w <= BOT
    in_bottom_1m = p1m <= BOT
    in_bottom_3m = p3m <= BOT
    
    # Order matters in np.select: first matching condition wins
    # Note: Weinstein gate forces "strong" candidates down to Average
    conditions = [
        # Laggard: bottom quintile in all three (overrides Weinstein gate)
        in_bottom_1w & in_bottom_1m & in_bottom_3m,
        # Weak: bottom quintile in any one (overrides Weinstein gate)
        in_bottom_1w | in_bottom_1m | in_bottom_3m,
        # The following four require Weinstein gate to pass
        # Leader: top quintile in all three
        in_top_1w & in_top_1m & in_top_3m & weinstein,
        # Strong: top quintile in 1m and 3m, not 1w
        in_top_1m & in_top_3m & ~in_top_1w & weinstein,
        # Consolidating: top quintile in 3m only
        in_top_3m & ~in_top_1m & ~in_top_1w & weinstein,
        # Emerging: top quintile in 1w and 1m, not 3m, AND stage1 base qualifies
        in_top_1w & in_top_1m & ~in_top_3m & stage1 & weinstein,
    ]
    choices = ["Laggard", "Weak", "Leader", "Strong", "Consolidating", "Emerging"]
    
    df["rs_state"] = np.select(conditions, choices, default="Average")
    
    return pl.from_pandas(df)
```

**Critical ordering note:** In `np.select`, the *first* matching condition wins. The Laggard condition is checked before Weak because all-three-bottom is a stricter condition that should classify as Laggard, not Weak. The Weinstein gate doesn't appear in the Laggard/Weak rules because failing-on-the-downside is its own classification — failing the gate while being a "top performer" forces Average, but failing the gate while being a "bottom performer" still gets Weak/Laggard.

### 5.3 RS Momentum State Classifier

Per methodology 7.2.

```python
def classify_momentum_state(metrics_df: pl.DataFrame, thresholds: dict) -> pl.DataFrame:
    """
    Five-state momentum classification per methodology 7.2.
    Requires columns:
        ema_10_ratio, ema_20_ratio, ema_10_at_20d_high, ema_10_at_20d_low
    
    Output column: momentum_state ∈ {
        Accelerating, Improving, Flat, Deteriorating, Collapsing
    }
    """
    FLAT_BAND = thresholds["momentum_flat_band_pct"]            # default 0.02
    EMA_CONVERGE = thresholds["momentum_ema_convergence_pct"]   # default 0.01
    
    df = metrics_df.to_pandas()
    
    r10 = df["ema_10_ratio"]
    r20 = df["ema_20_ratio"]
    at_high = df["ema_10_at_20d_high"]
    at_low = df["ema_10_at_20d_low"]
    
    # "Within ±FLAT_BAND of 1" for Flat
    near_1 = (r10 - 1).abs() <= FLAT_BAND
    # EMAs converged within EMA_CONVERGE proportion
    emas_converged = (r10 - r20).abs() <= EMA_CONVERGE
    
    conditions = [
        # Accelerating: ratio > 1 AND ema10 > ema20 AND at 20-day high
        (r10 > 1) & (r10 > r20) & at_high,
        # Improving: ratio > 1 AND ema10 > ema20 (not necessarily at high)
        (r10 > 1) & (r10 > r20),
        # Collapsing: ratio < 1 AND ema10 < ema20 AND at 20-day low
        (r10 < 1) & (r10 < r20) & at_low,
        # Deteriorating: ratio < 1 AND ema10 < ema20
        (r10 < 1) & (r10 < r20),
        # Flat: near 1 OR EMAs converged
        near_1 | emas_converged,
    ]
    choices = ["Accelerating", "Improving", "Collapsing", "Deteriorating", "Flat"]
    
    df["momentum_state"] = np.select(conditions, choices, default="Flat")
    
    return pl.from_pandas(df)
```

### 5.4 Risk State Classifier

Per methodology 7.3.

```python
def classify_risk_state(metrics_df: pl.DataFrame, thresholds: dict) -> pl.DataFrame:
    """
    Five-state risk classification per methodology 7.3.
    Requires columns:
        extension_pct, vol_ratio_63
    
    Output column: risk_state ∈ {
        Low, Normal, Elevated, High, Below Trend
    }
    """
    EXT_LOW_MAX = thresholds["risk_extension_low_max_pct"]      # default 25
    EXT_HIGH_MIN = thresholds["risk_extension_high_min_pct"]    # default 40
    VOL_LOW_MAX = thresholds["risk_vol_ratio_low_max"]          # default 1.0
    VOL_NORM_MAX = thresholds["risk_vol_ratio_normal_max"]      # default 1.25
    VOL_HIGH_MIN = thresholds["risk_vol_ratio_high_min"]        # default 1.6
    
    df = metrics_df.to_pandas()
    
    ext = df["extension_pct"] * 100  # Convert decimal to percent
    vol_r = df["vol_ratio_63"]
    
    conditions = [
        # Below Trend: extension < 0% (price below 200-EMA — terminal)
        ext < 0,
        # High: extension > EXT_HIGH_MIN OR vol_ratio > VOL_HIGH_MIN
        (ext > EXT_HIGH_MIN) | (vol_r > VOL_HIGH_MIN),
        # Elevated: extension EXT_LOW_MAX-EXT_HIGH_MIN OR vol_ratio VOL_NORM_MAX-VOL_HIGH_MIN
        ((ext > EXT_LOW_MAX) & (ext <= EXT_HIGH_MIN)) | ((vol_r > VOL_NORM_MAX) & (vol_r <= VOL_HIGH_MIN)),
        # Normal: extension 0-EXT_LOW_MAX AND vol_ratio VOL_LOW_MAX-VOL_NORM_MAX
        (ext >= 0) & (ext <= EXT_LOW_MAX) & (vol_r > VOL_LOW_MAX) & (vol_r <= VOL_NORM_MAX),
        # Low: extension 0-EXT_LOW_MAX AND vol_ratio <= VOL_LOW_MAX
        (ext >= 0) & (ext <= EXT_LOW_MAX) & (vol_r <= VOL_LOW_MAX),
    ]
    choices = ["Below Trend", "High", "Elevated", "Normal", "Low"]
    
    df["risk_state"] = np.select(conditions, choices, default="Normal")
    
    return pl.from_pandas(df)
```

### 5.5 Volume State Classifier

Per methodology 7.4.

```python
def classify_volume_state(metrics_df: pl.DataFrame, thresholds: dict) -> pl.DataFrame:
    """
    Five-state volume classification per methodology 7.4.
    Requires columns:
        volume_expansion, effort_ratio_63
    
    Output column: volume_state ∈ {
        Accumulation, Steady-Buying, Neutral, Distribution, Heavy Distribution
    }
    """
    ACC_EXP_MIN = thresholds["volume_accumulation_expansion_min"]    # default 1.2
    ACC_EFF_MIN = thresholds["volume_accumulation_effort_min"]       # default 1.3
    DIST_EFF_MAX = thresholds["volume_distribution_effort_max"]      # default 0.8
    HEAVY_EFF_MAX = thresholds["volume_heavy_distribution_effort_max"] # default 0.6
    
    df = metrics_df.to_pandas()
    
    exp = df["volume_expansion"]
    eff = df["effort_ratio_63"]
    
    conditions = [
        # Heavy Distribution: effort <= HEAVY_EFF_MAX AND volume rising (expansion >= 1.0)
        (eff <= HEAVY_EFF_MAX) & (exp >= 1.0),
        # Distribution: effort <= DIST_EFF_MAX
        eff <= DIST_EFF_MAX,
        # Accumulation: expansion >= ACC_EXP_MIN AND effort >= ACC_EFF_MIN
        (exp >= ACC_EXP_MIN) & (eff >= ACC_EFF_MIN),
        # Steady-Buying: expansion 1.0-ACC_EXP_MIN AND effort >= 1.1
        (exp >= 1.0) & (exp < ACC_EXP_MIN) & (eff >= 1.1),
    ]
    choices = ["Heavy Distribution", "Distribution", "Accumulation", "Steady-Buying"]
    
    df["volume_state"] = np.select(conditions, choices, default="Neutral")
    
    return pl.from_pandas(df)
```

### 5.6 Suspended-State Override

Per methodology 3.3 and architecture 4.1: Three meta-states override the primitive classifications.

```python
def apply_suspension_overrides(
    states_df: pl.DataFrame,
    market_regime_df: pl.DataFrame,    # For dislocation_active flag
) -> pl.DataFrame:
    """
    Apply state suspension overrides:
    - INSUFFICIENT_HISTORY: history_gate_pass = False
    - ILLIQUID: liquidity_gate_pass = False
    - DISLOCATION_SUSPENDED: market.dislocation_active = True on this date
    
    Suspended states override all primitive states.
    Order: INSUFFICIENT_HISTORY > ILLIQUID > DISLOCATION_SUSPENDED > primitive states
    """
    df = states_df.to_pandas()
    
    # Join in market regime dislocation flag
    if market_regime_df is not None:
        regime_pd = market_regime_df.to_pandas()
        df = df.merge(
            regime_pd[["date", "dislocation_active"]],
            on="date",
            how="left",
        )
    else:
        # If running before M3, default to False
        df["dislocation_active"] = False
    
    state_cols = ["rs_state", "momentum_state", "risk_state", "volume_state"]
    
    for col in state_cols:
        df[col] = np.where(
            ~df["history_gate_pass"], "INSUFFICIENT_HISTORY",
            np.where(
                ~df["liquidity_gate_pass"], "ILLIQUID",
                np.where(
                    df["dislocation_active"].fillna(False), "DISLOCATION_SUSPENDED",
                    df[col]
                )
            )
        )
    
    return pl.from_pandas(df)
```

**Important — circular dependency note:** The dislocation override depends on market regime, which is computed in Atlas-M3, not M2. For Atlas-M2 historical backfill, run with `market_regime_df=None` (no dislocation override). After Atlas-M3 completes, the M2 nightly compute reads market regime from the prior day's run.

### 5.7 Phase B Definition of Done

- [ ] `atlas/compute/states.py` implements all four primitive classifiers
- [ ] Suspension override function implemented
- [ ] Unit tests cover each classifier with edge cases (boundary thresholds, missing data)
- [ ] Hand-classification reference (`tier3_states.py`) ready for Tier 3 validation

---

## 6. Phase C — Pipeline Implementation

### 6.1 Goal

Wire the primitives, classifiers, and gates into a stock-level pipeline that reads from Layer 1 and writes to Layer 3. Same for ETFs.

### 6.2 Stock Pipeline

```python
import uuid
from datetime import date

def run_stock_pipeline(
    target_date: date,
    is_backfill: bool = False,
    backfill_start: date | None = None,
) -> dict:
    """
    Stock metric and state pipeline for one date OR a date range (backfill mode).
    
    Daily mode (is_backfill=False):
        - Computes for target_date only
        - Reads ~252+30 days of history per stock for rolling-window metrics
    
    Backfill mode (is_backfill=True):
        - Computes for all dates in [backfill_start, target_date]
        - Reads full history per stock from earliest available
    
    Returns: dict with metrics: rows_written, instruments_processed, errors
    """
    run_id = uuid.uuid4()
    log_run_start("M2_stocks", run_id, target_date, is_backfill)
    
    engine = get_engine()
    
    # Step 0: Load thresholds from atlas_thresholds (per architecture 5.6)
    # Read once per pipeline run; passed to every classifier function.
    thresholds = load_thresholds(engine)
    log_pipeline_event(run_id, "thresholds_loaded", count=len(thresholds))
    
    # Step 1: Materialize benchmark cache for the target date range
    benchmark_cache = materialize_benchmark_cache(
        engine, 
        start_date=backfill_start if is_backfill else target_date - timedelta(days=300),
        end_date=target_date,
    )
    
    # Step 2: Get the universe
    universe = pl.read_database(
        "SELECT * FROM atlas.atlas_universe_stocks WHERE effective_to IS NULL",
        engine,
    )
    
    rows_written_total = 0
    errors = []
    
    # Step 3: Process by instrument (per architecture 5.2 — compute by instrument, not date)
    for stock in universe.iter_rows(named=True):
        try:
            # Load this stock's full history (or just recent for daily mode)
            stock_history = load_stock_history(
                engine, 
                stock["instrument_id"],
                start_date=backfill_start if is_backfill else target_date - timedelta(days=400),
                end_date=target_date,
            )
            
            # Apply pre-classification gates
            stock_with_gates = apply_pre_classification_gates(
                stock_history, 
                stock,
                trading_calendar,
            )
            
            # Skip stocks that fail history gate
            if not stock_with_gates.tail(1)["history_gate_pass"][0]:
                # Still write a row with INSUFFICIENT_HISTORY state
                write_minimal_state_row(stock, target_date, run_id, "INSUFFICIENT_HISTORY")
                continue
            
            # Compute primitives
            tier_benchmark = get_tier_benchmark(stock["tier"])
            benchmark_data = benchmark_cache.filter(
                pl.col("benchmark_code") == tier_benchmark
            )
            
            stock_with_rs = compute_relative_strength(
                stock_with_gates, benchmark_cache, BENCHMARKS, WINDOWS
            )
            stock_with_momentum = compute_rs_momentum(stock_with_rs, benchmark_data)
            stock_with_risk = compute_relative_risk(stock_with_momentum, benchmark_data)
            stock_with_volume = compute_volume_primitive(stock_with_risk, trading_calendar)
            stock_with_weinstein = compute_weinstein_gate(stock_with_volume)
            stock_with_pctiles = compute_within_tier_percentiles(
                stock_with_weinstein, universe
            )
            
            # State classification
            # State classification (thresholds passed to every classifier)
            stock_with_rs_state = classify_rs_state(stock_with_pctiles, thresholds)
            stock_with_momentum_state = classify_momentum_state(stock_with_rs_state, thresholds)
            stock_with_risk_state = classify_risk_state(stock_with_momentum_state, thresholds)
            stock_with_volume_state = classify_volume_state(stock_with_risk_state, thresholds)
            stock_final = apply_suspension_overrides(stock_with_volume_state, None)
            
            # Compute Stage-1 base (depends on prior states)
            stock_with_stage1 = compute_stage1_base(stock_final, stock_final)
            
            # Add gold numéraire variants for the three classification windows
            stock_with_gold = add_gold_numeraire_metrics(stock_with_stage1, benchmark_cache)
            
            # Write to atlas_stock_metrics_daily
            metrics_to_write = stock_with_gold.select(STOCK_METRICS_COLUMNS)
            write_to_metrics_table(engine, metrics_to_write, run_id)
            
            # Write to atlas_stock_states_daily
            states_to_write = stock_with_gold.select(STOCK_STATES_COLUMNS)
            write_to_states_table(engine, states_to_write, run_id)
            
            rows_written_total += len(metrics_to_write)
            
        except Exception as e:
            errors.append({"instrument_id": stock["instrument_id"], "error": str(e)})
            log_pipeline_error(run_id, stock["instrument_id"], e)
            continue  # Don't halt the whole pipeline
    
    log_run_complete("M2_stocks", run_id, rows_written_total, errors)
    
    return {
        "run_id": run_id,
        "rows_written": rows_written_total,
        "instruments_processed": len(universe),
        "errors": errors,
    }
```

### 6.3 ETF Pipeline

Same structure as stocks but with three differences:

1. Volume state computed but not used in classification (per methodology 8.1)
2. Benchmark depends on theme (Broad → Nifty 500, Sectoral → linked sector index, Thematic → Nifty 500)
3. No within-tier percentile ranking (ETFs aren't tiered)

```python
def run_etf_pipeline(
    target_date: date,
    is_backfill: bool = False,
    backfill_start: date | None = None,
) -> dict:
    """ETF pipeline — see stock pipeline for structure."""
    # Implementation parallels run_stock_pipeline with ETF-specific differences
    # ...
```

### 6.4 Benchmark Cache Materialization

Per architecture 5.2: materialize once per run, used by every stock.

```python
def materialize_benchmark_cache(
    engine, 
    start_date: date, 
    end_date: date,
) -> pl.DataFrame:
    """
    Build the working benchmark cache for this run.
    Reads close prices from JIP Data Core for all 9 benchmarks.
    Computes returns at all windows.
    
    Result is a Polars DataFrame in memory, also persisted to atlas_benchmark_returns_cache.
    """
    benchmarks = pl.read_database(
        "SELECT * FROM atlas.atlas_benchmark_master WHERE is_active = TRUE",
        engine,
    )
    
    all_benchmark_data = []
    for bench in benchmarks.iter_rows(named=True):
        # Load the benchmark's price series from its source table
        if bench["source_table"] == "de_index_prices":
            query = f"""
                SELECT date, close 
                FROM public.de_index_prices
                WHERE index_code = :code 
                  AND date BETWEEN :start AND :end
                ORDER BY date
            """
            params = {"code": bench["source_identifier"], "start": start_date, "end": end_date}
        elif bench["source_table"] == "de_etf_ohlcv":
            query = f"""
                SELECT date, close 
                FROM public.de_etf_ohlcv
                WHERE ticker = :code 
                  AND date BETWEEN :start AND :end
                ORDER BY date
            """
            params = {"code": bench["source_identifier"], "start": start_date, "end": end_date}
        elif bench["source_table"] == "de_global_prices":
            query = f"""
                SELECT date, close 
                FROM public.de_global_prices
                WHERE ticker = :code 
                  AND date BETWEEN :start AND :end
                ORDER BY date
            """
            params = {"code": bench["source_identifier"], "start": start_date, "end": end_date}
        else:
            raise ValueError(f"Unknown source_table: {bench['source_table']}")
        
        bench_prices = pl.read_database(query, engine, params=params)
        bench_prices = bench_prices.with_columns(
            pl.lit(bench["benchmark_code"]).alias("benchmark_code")
        )
        
        # Compute returns at all windows
        bench_with_returns = compute_returns(bench_prices, "close")
        # Compute EMAs (used by index_metrics_daily, not stock metrics — but cached here for efficiency)
        # Compute volatility
        
        all_benchmark_data.append(bench_with_returns)
    
    cache = pl.concat(all_benchmark_data)
    
    # Truncate and rewrite atlas_benchmark_returns_cache
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE atlas.atlas_benchmark_returns_cache"))
    cache.write_database(
        "atlas.atlas_benchmark_returns_cache", 
        engine, 
        if_table_exists="append",
    )
    
    return cache
```

### 6.5 Pre-Classification Gates

```python
def apply_pre_classification_gates(
    stock_history: pl.DataFrame,
    stock_metadata: dict,
    trading_calendar: pl.DataFrame,
) -> pl.DataFrame:
    """
    Apply the four pre-classification gates per methodology 3.3:
    1. History gate: ≥252 trading days of OHLCV
    2. Liquidity gate: ≥₹5cr trailing 60-day median daily turnover
    3. Adjusted-price gate: prices come from corporate-action-adjusted source
    4. Event-day gate: not relevant here (handled in volume primitive)
    """
    df = stock_history.to_pandas().sort_values("date")
    
    # History gate: count of distinct trading days
    df["history_gate_pass"] = len(df) >= 252
    
    # Liquidity gate: trailing 60-day median traded value
    df["traded_value"] = df["close"] * df["volume"]
    df["median_traded_value_60d"] = df["traded_value"].rolling(60, min_periods=40).median()
    df["liquidity_gate_pass"] = df["median_traded_value_60d"] >= 5_00_00_000  # ₹5 crore
    
    return pl.from_pandas(df)
```

### 6.6 Phase C Definition of Done

- [ ] Full stock pipeline implementation in `atlas/compute/stocks.py`
- [ ] Full ETF pipeline implementation in `atlas/compute/etfs.py`
- [ ] Benchmark cache materialization function tested
- [ ] Pre-classification gates function tested
- [ ] Pipeline can run end-to-end for a single date (smoke test)

---

## 7. Phase D — Historical Backfill

### 7.1 Goal

Run the pipeline for the full 12-year history (2014-04-01 to today). Target: complete in ≤90 minutes per architecture 9.2.

### 7.2 Backfill Strategy

Two-phase backfill to balance compute time vs memory:

**Phase 1: Per-stock backfill (parallel-able)**
- For each stock independently, compute all 12 years of metrics
- This is "embarrassingly parallel" — could split 750 stocks across 4 parallel workers if needed
- For v0, run sequentially on t3.large; switch to parallel only if total time exceeds budget

**Phase 2: Cross-stock percentile ranking (must be sequential by date)**
- Once all stocks have raw RS values, compute within-tier percentiles
- This requires looking at all stocks on each date — must be done after Phase 1
- Update existing rows with percentile values and (re-)classify states

```python
def run_full_backfill():
    """
    Atlas-M2 historical backfill.
    Target: 750 stocks × 3,000 days, complete in <90 minutes.
    """
    start = date(2014, 4, 1)
    end = date.today()
    
    # Phase 1: Compute per-stock raw metrics (RS, momentum, risk, volume, gates)
    # This populates atlas_stock_metrics_daily for all (stock, date) pairs
    print("Phase 1: Per-stock metric computation...")
    phase1_start = time.time()
    
    universe = load_universe(engine, "stocks")
    for stock in universe.iter_rows(named=True):
        process_stock_full_history(stock, start, end)
    
    phase1_elapsed = time.time() - phase1_start
    print(f"Phase 1 complete in {phase1_elapsed/60:.1f} minutes")
    
    # Phase 2: Cross-stock percentile ranking (date-by-date)
    print("Phase 2: Within-tier percentile ranking...")
    phase2_start = time.time()
    
    all_dates = pl.read_database(
        f"SELECT DISTINCT date FROM atlas.atlas_stock_metrics_daily ORDER BY date",
        engine,
    )["date"].to_list()
    
    for d in all_dates:
        update_percentiles_for_date(d, engine)
    
    phase2_elapsed = time.time() - phase2_start
    print(f"Phase 2 complete in {phase2_elapsed/60:.1f} minutes")
    
    # Phase 3: State classification (depends on percentiles, so runs after Phase 2)
    print("Phase 3: State classification...")
    phase3_start = time.time()
    
    for d in all_dates:
        classify_states_for_date(d, engine)
    
    phase3_elapsed = time.time() - phase3_start
    print(f"Phase 3 complete in {phase3_elapsed/60:.1f} minutes")
    
    print(f"Total backfill time: {(phase1_elapsed + phase2_elapsed + phase3_elapsed)/60:.1f} min")
```

### 7.3 Performance Profiling

If backfill exceeds budget, profile in this order:

1. **Database write throughput** — usually the first bottleneck. Verify batched writes (3,000 rows/transaction per architecture 5.2).
2. **Polars-pandas conversions** — pandas-ta requires pandas, but unnecessary conversions are slow. Minimize.
3. **Rolling window functions** — vectorized pandas implementations beat per-row loops by 10-100x.
4. **Parallel execution** — last resort. Adds complexity; validate carefully if used.

### 7.4 Phase D Definition of Done

- [ ] All 750 stocks have rows in `atlas_stock_metrics_daily` from earliest available date to today
- [ ] All 100 ETFs have rows in `atlas_etf_metrics_daily`
- [ ] All states classified (no NULL `rs_state` for dates after each instrument's history gate passes)
- [ ] Total backfill wall-clock time recorded in `atlas_run_log`
- [ ] No errors in `atlas_stock_metrics_quarantine` or `atlas_etf_metrics_quarantine` (or <1% of universe)

---

## 8. Phase E — Validation

### 8.1 Tier 2 Validation — Hand-Computed Metrics

Per validation framework Section 3.

Sample 15 stocks × 5 dates × ~25 metrics = 1,875 hand-validations.

Each hand-validation is an *independent implementation* — uses pure Polars/NumPy primitives where production uses pandas-ta, or uses pandas-ta where production uses Polars. The point is to catch implementation drift.

**Example hand-validation script:**

```python
def tier2_validate_ema_20(engine):
    """
    Hand-validate ema_20 against pure NumPy implementation.
    Production uses pandas-ta; we use NumPy here.
    """
    sample = sample_stock_dates(milestone="M2", n_stocks=15, n_dates=5)
    
    failures = []
    for instrument_id, date in sample:
        # Production value
        db_val = pl.read_database(
            f"SELECT ema_20_stock FROM atlas.atlas_stock_metrics_daily "
            f"WHERE instrument_id = '{instrument_id}' AND date = '{date}'",
            engine,
        )["ema_20_stock"][0]
        
        # Hand-computed value
        history = load_stock_history_pandas(engine, instrument_id, end_date=date)
        alpha = 2.0 / (20 + 1)
        ema = history["close"].iloc[0]
        for price in history["close"].iloc[1:]:
            ema = alpha * price + (1 - alpha) * ema
        hand_val = ema
        
        if abs(db_val - hand_val) > 0.0001:
            failures.append({
                "instrument_id": instrument_id, "date": date,
                "db_val": db_val, "hand_val": hand_val,
                "deviation": abs(db_val - hand_val),
            })
    
    return failures
```

Repeat for each metric: `ret_3m`, `rs_3m_tier`, `ema_10_ratio`, `extension_pct`, `vol_ratio_63`, `volume_expansion`, `effort_ratio_63`, `weinstein_gate_pass`, etc.

### 8.2 Tier 3 Validation — Hand-Classified States

Per validation framework Section 4.

Sample 30 stocks × 1 date (today) × 4 state types = 120 hand-classifications.

Hand-classification function reads methodology 7.1 and translates verbatim:

```python
def tier3_validate_rs_state(engine):
    """
    Hand-classify rs_state per methodology 7.1, compare to db value.
    """
    sample_stocks = sample_stocks(milestone="M2", n=30)
    today = date.today()
    
    failures = []
    for instrument_id in sample_stocks:
        # Get primitives
        primitives = pl.read_database(
            f"SELECT rs_pctile_1w, rs_pctile_1m, rs_pctile_3m, "
            f"weinstein_gate_pass, stage1_base_qualifies "
            f"FROM atlas.atlas_stock_metrics_daily "
            f"WHERE instrument_id = '{instrument_id}' AND date = '{today}'",
            engine,
        ).row(0, named=True)
        
        # Hand-classify
        hand_state = hand_classify_rs(primitives)
        
        # Get db state
        db_state = pl.read_database(
            f"SELECT rs_state FROM atlas.atlas_stock_states_daily "
            f"WHERE instrument_id = '{instrument_id}' AND date = '{today}'",
            engine,
        )["rs_state"][0]
        
        if hand_state != db_state:
            failures.append({
                "instrument_id": instrument_id, 
                "hand_state": hand_state, "db_state": db_state,
                "primitives": primitives,
            })
    
    return failures

def hand_classify_rs(primitives: dict) -> str:
    """
    Verbatim translation of methodology 7.1 RS classification rules.
    Independent from production code path.
    """
    # ... see validation framework Section 4.3 example
    pass
```

### 8.3 Tier 4 Validation — Cross-Table Consistency

Per validation framework Section 5.

For Atlas-M2, the relevant Tier 4 checks are:

- **Universe coverage**: Every (instrument_id, date) in `atlas_stock_metrics_daily` exists for an instrument in `atlas_universe_stocks` with `effective_to IS NULL` (or had effective_to > date).
- **State consistency**: Every row in `atlas_stock_states_daily` has a corresponding row in `atlas_stock_metrics_daily` for the same (instrument_id, date).
- **No orphan benchmarks**: Every `rs_*_<benchmark>` column references a benchmark that exists in `atlas_benchmark_master`.

### 8.4 Tier 5 Validation — Three Consecutive Daily Runs

Per validation framework Section 7.

After backfill is complete, run the daily incremental pipeline for 3 consecutive nights:

- Run 1 (Day T+1): incremental compute, validate output rows match expected count
- Run 2 (Day T+2): same
- Run 3 (Day T+3): same

All three must pass without errors. State distributions must remain within 30-day rolling 3σ bounds.

### 8.5 Phase E Definition of Done

- [ ] Tier 2 validation: 100% pass on ~1,875 hand-checks
- [ ] Tier 3 validation: 100% pass on ~120 hand-classifications
- [ ] Tier 4 validation: 0 orphan rows across all checks
- [ ] Tier 5 validation: 3 consecutive nightly runs pass
- [ ] `validation_M2_<date>.md` committed with all results

---

## 9. Atlas-M2 Definition of Done

The milestone is complete when ALL of the following are true:

**Code:**
- [ ] All compute modules implemented per Section 4 and Section 5
- [ ] All pipeline scripts working: `m2_backfill.py`, `m2_daily.py`
- [ ] All unit tests in `tests/unit/` pass
- [ ] Library versions match architecture Section 5.1 exactly

**Database:**
- [ ] `atlas_stock_metrics_daily`: ~2.25M rows for 750 stocks × ~3,000 days
- [ ] `atlas_stock_states_daily`: same row count
- [ ] `atlas_etf_metrics_daily`: ~250K rows for 100 ETFs × ~2,500 days
- [ ] `atlas_etf_states_daily`: same row count
- [ ] `atlas_benchmark_returns_cache`: ~27K rows
- [ ] At least one M2 backfill run logged in `atlas_run_log`
- [ ] Three M2 daily runs logged in `atlas_run_log` with status='SUCCESS'

**Validation:**
- [ ] Tier 2: 100% pass on hand-computed metric checks
- [ ] Tier 3: 100% pass on hand-classified state checks
- [ ] Tier 4: 0 orphan rows
- [ ] Tier 5: 3 consecutive nightly runs pass
- [ ] `validation_M2_<date>.md` shows PASS

**Performance:**
- [ ] Historical backfill completed in ≤90 minutes
- [ ] Daily incremental compute completes in ≤8 minutes
- [ ] Index queries return in <100ms

**Sign-off:**
- [ ] Engineer (Claude Code): Build complete, validation report generated
- [ ] Architect (Nimish): Spot-checked validation report; reasonable
- [ ] Fund Manager (Bhaven): Spot-checked 5 stock state classifications, agrees with output

---

## 10. Common Pitfalls (Read Before Building)

**1. Library version drift.** If pandas-ta installation pins to a different version than 0.3.14b, EMA values will differ slightly. Validation Tier 2 will fail. Stop and report; do not silently substitute.

**2. Pandas vs Polars conversions.** Each conversion costs time and can lose type precision. Convert once at function boundaries, not inside loops.

**3. Off-by-one in window boundaries.** `pct_change(periods=63)` looks back 63 trading days. Verify this matches "3 months" (~63 trading days). Hand-validation is the safety net.

**4. Forgetting to skip event days in volume primitive.** Half-day sessions and Budget days have anomalous volume. The volume primitive must exclude them. If validation Tier 2 shows volume_expansion oscillating around budget days, this gate is missing.

**5. Stage-1 base bootstrap problem.** First 10 weeks of any stock's history can't have prior states to look back on. Default to `False` and document. Don't try to back-derive from later periods — that's lookahead bias.

**6. Tier benchmark mismatch.** A Mid-tier stock's rs_pctile_1w must rank against other Mid-tier stocks against the Mid benchmark (Nifty Midcap 150). If by mistake a Large stock's RS gets ranked among Mid stocks, the percentile is wrong but plausible-looking.

**7. Suspended state ordering.** A stock with insufficient history AND in dislocation regime should show INSUFFICIENT_HISTORY (the more specific suspended state), not DISLOCATION_SUSPENDED. Order matters in `np.where` chain.

**8. Backfill phase ordering.** Phase 1 (per-stock metrics) MUST complete before Phase 2 (cross-stock percentiles). Don't try to fuse — Phase 2 needs all stocks for any given date.

**9. Adjusted close vs raw close.** Always use `de_equity_ohlcv.close` only if confirmed adjusted by JIP team. If raw close, all returns are wrong on stocks that have had splits/bonuses. Tier 1 validation catches this.

**10. Don't compute aggregations.** Atlas-M2 is per-instrument metrics only. No sector aggregation, no breadth measures, no market regime. That's M3. Resist scope creep.

**11. Don't write decisions.** Atlas-M2 doesn't write to `atlas_stock_decisions_daily`. That's M5.

**12. Run log discipline.** Every backfill, every daily run, must write a row to `atlas_run_log` with stage timings. Validation Tier 5 reads this — without it, monitoring fails.

---

## 11. Foundation Document Sync Checks

Before starting M2 build, verify these specific cross-document consistency points (this is the list the five-agent cross-review should validate):

| Check | Documents Involved |
|---|---|
| RS state names: 7 states match exactly | Methodology 7.1 ↔ Schema 4.1 ↔ M2 Section 5.2 |
| Momentum state names: 5 states | Methodology 7.2 ↔ Schema 4.1 ↔ M2 Section 5.3 |
| Risk state names: 5 states (incl. "Below Trend") | Methodology 7.3 ↔ Schema 4.1 ↔ M2 Section 5.4 |
| Volume state names: 5 states (incl. "Heavy Distribution") | Methodology 7.4 ↔ Schema 4.1 ↔ M2 Section 5.5 |
| Time horizons: 1W=5, 1M=21, 3M=63 trading days | Methodology 4.1 ↔ M2 Section 4.2 (WINDOWS dict) |
| Stock metrics columns: 50+ columns | Schema 3.1 ↔ M2 pipeline writes |
| Stock states columns: 4 primitives + gates + denormalized fields | Schema 4.1 ↔ M2 pipeline writes |
| Benchmark codes: 9 entries match | Schema 2.6 ↔ Atlas-M1 populated rows ↔ M2 reads |
| Library versions: pandas-ta 0.3.14b, empyrical 0.5.5 | Architecture 5.1 ↔ M2 imports |
| Suspended state names: 3 meta-states | Methodology 3.3 ↔ Schema 4.1 ↔ M2 Section 5.6 |
| Pre-classification gates: 4 gates (history, liquidity, adj-price, event-day) | Methodology 3.3 ↔ M2 Section 6.5 |
| Tier benchmarks: Large→Nifty100, Mid→Midcap150, Small→Smallcap250, Micro→custom | Methodology 6.2 ↔ Schema 2.6 ↔ M2 Section 4.2 |
| Validation Tier 2 sample size: 1,875 | Validation 3.4 ↔ M2 Section 8.1 |
| Validation Tier 3 sample size: 30 stocks × all state types | Validation 4 ↔ M2 Section 8.2 |
| Compute target: backfill ≤90 min, daily ≤8 min | Architecture 5.4 ↔ M2 Section 9 |
| Threshold-driven pattern: classifiers receive thresholds dict, never hardcoded | Architecture 5.6 ↔ Threshold Catalog ↔ M2 Section 5 (all classifiers) |
| Threshold count: 35 thresholds in atlas_thresholds | Threshold Catalog ↔ Atlas-M1 Step 8 populate count ↔ Schema 6.5 |
| RS quintile threshold keys: rs_quintile_top, rs_quintile_bottom | Methodology 7.1 ↔ Threshold Catalog 3 ↔ M2 Section 5.2 |
| Risk threshold keys: 5 keys for extension and vol_ratio bands | Methodology 7.3 ↔ Threshold Catalog 5 ↔ M2 Section 5.4 |
| Volume threshold keys: 4 keys for accumulation/distribution boundaries | Methodology 7.4 ↔ Threshold Catalog 6 ↔ M2 Section 5.5 |
| Tier 4 validation includes "no orphan thresholds" check | Architecture 5.6 ↔ Validation 5 (cross-table consistency) |

If the cross-review finds any inconsistency in this list, halt build and resolve at the source document level.

---

## 12. Open Questions

Document these in the validation report rather than guessing:

1. **What is the actual median-hard EMA seeding behavior of pandas-ta v0.3.14b?** Different EMA libraries seed differently (first SMA vs first close vs zero). Verify pandas-ta default and document. If different from hand-validation reference, align hand-validation to match production.

2. **Does `de_corporate_actions` cover all major events for our 750 stocks?** Spot-check on known recent demergers (Reliance/Jio Financial, Vedanta multi-way demerger, ITC hotels). If gaps exist, escalate to JIP team — Atlas does not modify de_* tables.

3. **Microcap custom benchmark — equal-weighted index of which 250 names?** Lock from `atlas_universe_stocks WHERE tier = 'Micro' AND effective_to IS NULL`. Compute as daily equal-weighted return of those 250 names. Document any name changes between universe lock and backfill execution.

4. **Bootstrap of momentum at very start of history.** First 20 days of any stock's data don't have a 20-day EMA. What's the production default? Default behavior of pandas-ta is NaN. Document and ensure NaNs propagate into "no state classification" until 20-day EMA is available.

---

## 13. What Comes Next

Atlas-M3 (Sector + Market Regime) builds on M2's atomic stock and ETF metrics to produce:
- Sector aggregations (bottom-up + top-down + divergence)
- Market regime classification with the four breadth families
- Index-level metrics for the 75-index universe

Atlas-M3 cannot start until Atlas-M2 validation report is signed off.

---

**Document version:** 1.0
**Last updated:** 2026-05-04
**Next review:** Atlas-M2 completion

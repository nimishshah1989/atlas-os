# Atlas — Validation Framework

**Document:** 03_VALIDATION_FRAMEWORK
**Status:** v0
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**References:**
- `00_METHODOLOGY_LOCK.md` (defines what's being validated)
- `01_BACKEND_ARCHITECTURE.md` Section 5.5 (Calculation Library Discipline) and Section 8 (Validation Architecture)
- `02_DATABASE_SCHEMA.md` Section 6.2 (atlas_validation_results table)

---

## Purpose of This Document

This document specifies **what "done" means** for every Atlas milestone. It defines five tiers of validation, the explicit pass/fail criteria for each, and the artifacts every milestone must produce.

Without a passing validation report, **a milestone is not complete.** This is non-negotiable. A failing validation either gets fixed before the milestone ships, or the milestone scope shrinks to what *can* pass.

Validation in Atlas is not testing — it's proof. Tests verify code does what we intended; validation verifies the data and the math are correct against external reality.

---

## 1. The Five Tiers

| Tier | Validates | Catches | When Run |
|---|---|---|---|
| Tier 1 | Raw data integrity from JIP Data Core | Source data corruption, missing data, ingest errors | Atlas-M1; on every JIP refresh |
| Tier 2 | Computed metrics vs. hand-computed values | Library bugs, off-by-one errors, wrong formulas | Every milestone DoD; on library upgrades |
| Tier 3 | State classifications vs. hand-applied rules | State logic errors, threshold misapplication | Every milestone DoD; on rule changes |
| Tier 4 | Cross-table consistency | Aggregation bugs, identifier mismatches, race conditions | Every milestone DoD; nightly |
| Tier 5 | Daily monitoring (run health, anomaly detection) | Production drift, distribution shifts, silent failures | Every nightly run |

The framework runs **bottom-up** through tiers when data flows. Each tier validates the layer below it produced reliable inputs.

---

## 2. Tier 1 — Raw Data Validation

**What it validates:** That the data we read from JIP Data Core matches reality.

**Premise:** Atlas reads from JIP Data Core (`de_*` tables) but doesn't own the data ingestion. We need to verify the data is correct before we compute anything from it.

### 2.1 What Gets Checked

For each price-bearing table Atlas reads from (`de_equity_ohlcv`, `de_etf_ohlcv`, `de_index_prices`, `de_global_prices`, `de_mf_nav_daily`):

| Check | Method |
|---|---|
| Row counts match expected universe size | `SELECT COUNT(DISTINCT instrument_id) FROM de_equity_ohlcv` should match locked universe |
| No null prices on trading days | `SELECT COUNT(*) FROM de_equity_ohlcv WHERE close IS NULL AND date IN (trading_days)` should be 0 |
| Date coverage spans 2014-04-01 to today | Per-instrument min/max date check |
| Adjusted prices in use (not raw close) | Spot-check: `de_equity_ohlcv.close` for known split events should reflect adjustment |
| External cross-validation: 20 instruments × 30 dates × 3 sources | Compare our DB values against yfinance and TradingView/Stooq |

### 2.2 The External Cross-Validation Procedure

**Sample selection:** 20 instruments per asset class × 30 random trading days from 2014-2026 range = 600 (instrument, date) pairs per asset class.

**Process:**

```python
for (instrument, date) in sampled_pairs:
    our_value = query_jip_db(instrument, date, field="close")
    yfinance_value = yfinance_history(instrument, date)
    stooq_value = stooq_history(instrument, date)
    
    deviations = [
        abs(our_value - yfinance_value) / our_value,
        abs(our_value - stooq_value) / our_value,
    ]
    max_deviation = max(deviations)
    
    if max_deviation > 0.01:  # 1% tolerance
        flag_for_inspection(instrument, date, our_value, yfinance_value, stooq_value)
```

**Tolerance:** 1% max deviation between our value and at least one external source.

**Pass criteria:** ≥95% of (instrument, date) pairs agree within 1% with at least one external source.

**Failure handling:** Failures escalate to the JIP team for investigation (since JIP owns Layer 1). Atlas does NOT modify `de_*` tables to fix issues — that violates Architecture Pillar 1.1.

### 2.3 NAV Cross-Validation (Funds)

For mutual fund NAV, the cross-source is AMFI's published portal (the same source JIP ingests from):

```python
for (mstar_id, nav_date) in sampled_fund_pairs:
    our_nav = query_jip_db(mstar_id, nav_date, table="de_mf_nav_daily")
    amfi_nav = amfi_portal_lookup(mstar_id, nav_date)
    deviation = abs(our_nav - amfi_nav) / our_nav
    if deviation > 0.001:  # 0.1% tolerance for NAV (tighter than prices)
        flag_for_inspection(...)
```

NAV cross-validation has a tighter 0.1% tolerance because NAV is a published official value, not a continuous price.

### 2.4 Tier 1 Pass Criteria Summary

| Asset Class | Sample Size | Tolerance | Required Pass Rate |
|---|---|---|---|
| Stocks (de_equity_ohlcv) | 600 pairs | 1% | ≥ 95% |
| ETFs (de_etf_ohlcv) | 600 pairs | 1% | ≥ 95% |
| Indices (de_index_prices) | 600 pairs | 1% | ≥ 95% |
| Global benchmarks (de_global_prices) | 200 pairs (2 instruments × 100 dates) | 1% | ≥ 98% |
| Mutual fund NAV (de_mf_nav_daily) | 600 pairs | 0.1% | ≥ 95% |

**Holiday note:** Tier 1 spot checks may legitimately fail on dates that are non-trading days for one source but trading days for another (e.g., Indian holidays vs US trading days). The validation runner must consult `de_trading_calendar` and skip these cross-source date mismatches rather than counting them as failures.

---

## 3. Tier 2 — Computed Metrics Validation

**What it validates:** That every numeric metric Atlas computes matches a hand-computed reference value.

**Premise:** Even with library discipline (Section 5.5 of architecture), bugs can creep in through how we *compose* library calls. Tier 2 verifies the composition is correct.

### 3.1 What Gets Checked

For every primitive metric defined in `00_METHODOLOGY_LOCK.md` Section 7 (the four primitives) and Section 11 (market regime measures):

- 15 instruments × 5 dates per metric type = 75 hand-validations per metric
- Total metrics: ~25 numeric metrics per stock × 15 stocks × 5 dates = 1,875 hand-validations per Tier 2 run

### 3.2 The Hand-Validation Procedure

For each (instrument, date, metric) triple in the sample:

```python
for (instrument, date, metric_name) in sampled_triples:
    db_value = query_atlas_db(instrument, date, metric_name)
    raw_data = query_layer1_inputs(instrument, date_range_for_metric)
    hand_value = compute_by_hand(raw_data, metric_name, instrument, date)
    
    deviation = abs(db_value - hand_value)
    if deviation > 0.0001:  # essentially exact
        flag_failure(instrument, date, metric_name, db_value, hand_value)
```

**Critical:** "Compute by hand" means using an *independent implementation* — typically a separate Python script that uses different library calls or pure-NumPy primitives, not the same pandas-ta call the production code uses. The point is to catch implementation drift between two independent paths.

### 3.3 Hand-Validation Examples

**Example: RS_3M for stock X on date Y**

```python
# Production code uses:
df["ret_3m"] = pl.col("close").pct_change(periods=63)
df["rs_3m"] = df["ret_3m"] - df["benchmark_ret_3m"]

# Validation code uses pure pandas + NumPy:
def hand_compute_rs_3m(close_series, benchmark_close_series, date):
    idx = close_series.index.get_loc(date)
    stock_return = close_series.iloc[idx] / close_series.iloc[idx - 63] - 1
    benchmark_return = benchmark_close_series.iloc[idx] / benchmark_close_series.iloc[idx - 63] - 1
    return stock_return - benchmark_return

# Then assert |db_value - hand_value| < 0.0001
```

**Example: EMA 20 for stock X on date Y**

```python
# Production code uses:
df["ema_20"] = ta.ema(close, length=20)  # pandas-ta

# Validation code uses NumPy:
def hand_compute_ema(close_series, n, date):
    alpha = 2.0 / (n + 1)
    ema = [close_series.iloc[0]]  # Seed with first value (matches pandas-ta default)
    for i in range(1, len(close_series)):
        ema.append(alpha * close_series.iloc[i] + (1 - alpha) * ema[-1])
    return ema[close_series.index.get_loc(date)]
```

### 3.4 Tier 2 Coverage Per Milestone

Each milestone defines which metrics it produces and validates only those. Cumulative:

| Milestone | Metrics to Validate | Sample Count |
|---|---|---|
| Atlas-M1 | None (no metrics computed; just schema and reference data) | 0 |
| Atlas-M2 | Stock + ETF primitives: ret_n, rs_n, ema_10/20, vol_ratio, extension_pct, drawdown_ratio, volume_expansion, effort_ratio | ~25 metrics × 15 instruments × 5 dates = 1,875 |
| Atlas-M3 | Sector aggregations + market breadth measures | ~15 metrics × 15 sectors/dates = 225 |
| Atlas-M4 | Fund Lens 1 metrics + Lens 2/3 aggregations | ~10 metrics × 15 funds × 5 dates = 750 |
| Atlas-M5 | None (decisions are state combinations, not new numerics) | 0 |

### 3.5 Tier 2 Pass Criteria

**Pass:** 100% match within tolerance for all sampled (instrument, date, metric) triples.

**Tolerance:** `abs(db_value - hand_value) ≤ 0.0001` for ratios and rates; `abs(db_value - hand_value) / hand_value ≤ 0.0001` for prices and large absolute values.

**Failure:** Any single mismatch is a stop-the-line bug. Investigation required before milestone closes.

---

## 4. Tier 3 — State Classification Validation

**What it validates:** That state labels stored in the database match what the methodology rules would assign given the same primitive values.

**Premise:** Tier 2 verified primitives are correct. Tier 3 verifies the classification logic that turns primitives into states is correct.

### 4.1 What Gets Checked

For every state-bearing table (`atlas_stock_states_daily`, `atlas_etf_states_daily`, `atlas_sector_states_daily`, `atlas_market_regime_daily`, `atlas_fund_states_daily`):

- 30 instruments × 1 date (today) = 30 hand-classifications per state table
- For each, hand-apply the methodology rules to the primitive values, verify the stored state matches

### 4.2 The Hand-Classification Procedure

For each instrument in the sample:

```python
for instrument_id in sampled_30_instruments:
    primitives = query_atlas_metrics(instrument_id, today)
    db_state_tuple = query_atlas_states(instrument_id, today)
    hand_state_tuple = apply_methodology_rules(primitives)
    
    for state_name in ["rs_state", "momentum_state", "risk_state", "volume_state"]:
        if db_state_tuple[state_name] != hand_state_tuple[state_name]:
            flag_failure(instrument_id, state_name, 
                         db_state_tuple[state_name], hand_state_tuple[state_name])
```

**Critical:** "Apply methodology rules" means a fresh implementation reading `00_METHODOLOGY_LOCK.md` and translating the rules into code, NOT using the production state-classifier. The two implementations must agree.

### 4.3 Hand-Classification Examples

**Example: RS state for stock X today**

```python
def hand_classify_rs_state(primitives, methodology_lock):
    """
    Reading methodology lock Section 7.1:
    - Leader: Top quintile in 1W AND 1M AND 3M
    - Strong: Top quintile in 1M AND 3M, NOT 1W
    - ...
    Plus Weinstein gate (Section 7.1):
    - Must have price > 30_week_MA AND MA flat-or-rising
    Plus Stage-1 base for Emerging:
    - Must have been in {Average, Weak, Laggard} for 8/10 weeks prior
    """
    if not primitives["weinstein_gate_pass"]:
        return "Average"  # Force-down per Section 7.1
    
    pctile_1w = primitives["rs_pctile_1w"]
    pctile_1m = primitives["rs_pctile_1m"]
    pctile_3m = primitives["rs_pctile_3m"]
    
    in_top_1w = pctile_1w >= 0.8
    in_top_1m = pctile_1m >= 0.8
    in_top_3m = pctile_3m >= 0.8
    in_bottom_1w = pctile_1w <= 0.2
    in_bottom_1m = pctile_1m <= 0.2
    in_bottom_3m = pctile_3m <= 0.2
    
    if in_top_1w and in_top_1m and in_top_3m:
        return "Leader"
    elif in_top_1m and in_top_3m and not in_top_1w:
        return "Strong"
    elif in_top_3m and not in_top_1m:
        return "Consolidating"
    elif in_top_1w and in_top_1m and not in_top_3m:
        if primitives["stage1_base_qualifies"]:
            return "Emerging"
        else:
            return "Average"
    elif in_bottom_1w and in_bottom_1m and in_bottom_3m:
        return "Laggard"
    elif in_bottom_1w or in_bottom_1m or in_bottom_3m:
        return "Weak"
    else:
        return "Average"
```

The hand-classification function is a near-verbatim translation of the methodology table. It's verbose by design — readability over cleverness.

### 4.4 State Suspension Cases

Three suspended states are NOT classification outputs but precede the primitive logic:

```python
def classify_with_suspension_check(instrument_id, today, primitives):
    if not primitives["history_gate_pass"]:
        return "INSUFFICIENT_HISTORY"
    if not primitives["liquidity_gate_pass"]:
        return "ILLIQUID"
    if query_market_regime(today)["dislocation_active"]:
        return "DISLOCATION_SUSPENDED"
    return classify_primitive_states(primitives)
```

Tier 3 must verify suspension states are correctly applied — a stock with `history_gate_pass = false` MUST show state `INSUFFICIENT_HISTORY`, not a primitive state.

### 4.5 Tier 3 Pass Criteria

**Pass:** 100% match for all sampled (instrument, state_name) pairs across all state tables.

**Failure:** Any single mismatch is a stop-the-line bug. State classification logic must be reviewed.

---

## 5. Tier 4 — Cross-Table Consistency Validation

**What it validates:** That aggregations are consistent with their inputs, that identifiers join cleanly, that there are no orphaned rows.

**Premise:** Tiers 2 and 3 verify per-instrument correctness. Tier 4 catches integration bugs — situations where individual values are correct but their aggregation drifts.

### 5.1 What Gets Checked

Five categories of cross-table check:

**Category A: Sector aggregation consistency**

For each sector on each date:

```sql
-- Bottom-up sector RS should equal market-cap-weighted average of constituent stock RSs
SELECT sector_name, date, bottomup_rs_3m_nifty500
FROM atlas_sector_metrics_daily
WHERE date = :today;

-- Compute reconstruction:
SELECT 
    u.sector,
    SUM(s.rs_3m_nifty500 * mc.weight) AS reconstructed_rs_3m
FROM atlas_stock_metrics_daily s
JOIN atlas_universe_stocks u ON u.instrument_id = s.instrument_id
JOIN <market_cap_weights> mc ON mc.instrument_id = s.instrument_id
WHERE s.date = :today
GROUP BY u.sector;

-- |bottomup_value - reconstructed_value| / reconstructed_value < 0.005  (0.5% tolerance)
```

Pass criteria: All sector aggregations within 0.5% of constituent reconstruction.

**Category B: Strength breadth consistency**

```sql
-- pct_in_strong_states in atlas_market_regime_daily should equal:
SELECT 
    COUNT(*) FILTER (WHERE rs_state IN ('Leader', 'Strong', 'Emerging')) * 1.0 / COUNT(*)
FROM atlas_stock_states_daily
WHERE date = :today
  AND instrument_id IN (SELECT instrument_id FROM atlas_universe_stocks WHERE in_nifty_500);
```

Pass criteria: Exact match (within rounding to 4 decimal places).

**Category C: Decision gate reconstruction**

For each stock with `is_investable = TRUE` in `atlas_stock_decisions_daily`:

```sql
-- Verify all 6 gates also show TRUE
SELECT * FROM atlas_stock_decisions_daily
WHERE date = :today AND is_investable = TRUE
  AND (NOT strength_gate OR NOT direction_gate OR NOT risk_gate 
       OR NOT volume_gate OR NOT sector_gate OR NOT market_gate);

-- Should return zero rows
```

Pass criteria: Zero rows returned (consistency between investable flag and gate flags).

**Category D: Universe coverage consistency**

```sql
-- Every instrument in computed tables must exist in universe table
SELECT s.instrument_id 
FROM atlas_stock_metrics_daily s
LEFT JOIN atlas_universe_stocks u 
    ON u.instrument_id = s.instrument_id 
    AND u.effective_to IS NULL
WHERE s.date = :today AND u.instrument_id IS NULL;

-- Should return zero rows
```

Pass criteria: Zero orphan rows in any computed table.

**Category E: Fund holdings → state consistency**

For each fund's Lens 3 (holdings quality):

```sql
-- strong_aum_pct should equal sum of fund weights in stocks classified Leader/Strong/Emerging
SELECT mstar_id, strong_aum_pct AS stored_value
FROM atlas_fund_lens_monthly WHERE as_of_date = :latest;

-- Compared to:
SELECT 
    h.mstar_id,
    SUM(h.weight) AS reconstructed_strong_aum_pct
FROM de_mf_holdings h
JOIN atlas_stock_states_daily s 
    ON s.instrument_id = h.instrument_id 
    AND s.date = (SELECT MAX(date) FROM atlas_stock_states_daily WHERE date <= h.as_of_date)
WHERE s.rs_state IN ('Leader', 'Strong', 'Emerging')
GROUP BY h.mstar_id;
```

Pass criteria: All fund Lens 3 values within 0.5% of reconstruction.

**Category F: Threshold Reference Integrity**

Per architecture Section 5.6: every threshold in `atlas_thresholds` must be referenced by at least one classifier function in code. No orphan thresholds (defined but never used). No hardcoded thresholds (used in code but not declared in the table).

This check has two parts:

**F1 — No orphan thresholds.** Every row in `atlas_thresholds` must have a corresponding code reference. Validation script greps the codebase for each `threshold_key` value and confirms at least one match in the `atlas/compute/` subtree:

```python
def check_no_orphan_thresholds(engine, codebase_root: str) -> list[str]:
    thresholds = pl.read_database(
        "SELECT threshold_key FROM atlas.atlas_thresholds WHERE is_active = TRUE",
        engine,
    )["threshold_key"].to_list()
    
    orphans = []
    for key in thresholds:
        found = subprocess.run(
            ["grep", "-r", "-l", f'"{key}"', f"{codebase_root}/atlas/compute/"],
            capture_output=True, text=True
        )
        if not found.stdout.strip():
            orphans.append(key)
    
    return orphans
```

Pass criteria: zero orphans.

**F2 — No hardcoded thresholds.** Validation script greps the `atlas/compute/` subtree for numeric literals that should be threshold-driven. Specifically: any line containing both a comparison operator (`>=`, `<=`, `>`, `<`, `==`) AND a literal float (e.g., `0.80`, `1.25`, `40`, `60`) should be inspected.

This is heuristic, not exhaustive — false positives expected (e.g., literal `1.0` for division-by-zero protection is fine). Validation review identifies genuine hardcoded thresholds vs. acceptable literals.

```python
HARDCODED_LITERAL_PATTERN = r'[<>=]+\s*\d+\.\d+'

def check_no_hardcoded_thresholds(codebase_root: str) -> list[str]:
    suspicious_lines = []
    for py_file in glob.glob(f"{codebase_root}/atlas/compute/**/*.py", recursive=True):
        with open(py_file) as f:
            for line_num, line in enumerate(f, 1):
                if re.search(HARDCODED_LITERAL_PATTERN, line):
                    if "thresholds[" not in line:  # Ignore lines using threshold dict
                        suspicious_lines.append(f"{py_file}:{line_num}: {line.strip()}")
    return suspicious_lines
```

Pass criteria: every flagged line either (a) references `thresholds[...]` (acceptable), (b) is documented in a comment as an intentional non-threshold literal (e.g., division-by-zero protection), or (c) is removed in favor of a threshold reference.

### 5.2 Tier 4 Pass Criteria

| Check Category | Tolerance | Required Pass Rate |
|---|---|---|
| Sector aggregation consistency | 0.5% | 100% (every sector) |
| Strength breadth consistency | Exact | 100% |
| Decision gate reconstruction | Exact | 100% (zero orphans) |
| Universe coverage consistency | Exact | 100% (zero orphans) |
| Fund holdings reconstruction | 0.5% | 100% (every fund) |
| Threshold reference integrity | Exact | 100% (zero orphan thresholds, zero unjustified hardcoded literals) |

Tier 4 has **no margin for failure.** Cross-table consistency violations indicate either an aggregation bug, an identifier mismatch, or a race condition — all serious. Any failure halts milestone close.

---

## 6. Tier 5 — Daily Monitoring (Production Health)

**What it validates:** That every nightly run produces sensible output and any deviations are surfaced for review.

**Premise:** Tiers 1–4 validate the system at milestone DoD. Tier 5 watches the system continuously after launch.

### 6.1 What Gets Checked

Every nightly run produces a one-page health report covering:

**Volume metrics:**
- Rows written per table (compared to 30-day rolling average)
- Quarantined rows count (should be near zero)
- Universe coverage check (all 750 stocks, 100 ETFs, 75 indices, ~400 funds present)

**Distribution metrics:**
- State distribution snapshot — % of universe in each state, compared to 30-day rolling average
- Sector state distribution
- Regime state today vs yesterday

**Pipeline metrics:**
- Total wall-clock time
- Per-stage timing breakdown
- Any stage exceeding its target time by >20%

**Anomaly detection:**
- State distributions deviating >3σ from 30-day rolling average
- Compute time deviating >50% from 30-day rolling average
- Any single stock with >3 state changes in 5 trading days (excessive flickering)

### 6.2 Anomaly Surface Examples

| Anomaly | Likely Cause | Action |
|---|---|---|
| 12% of stocks classified Leader (3σ above norm) | Bug in percentile calculation, OR genuine market thrust | Review; may be legitimate |
| 0% of stocks classified Strong (impossible-low) | Bug in ranking logic | Halt; investigate |
| 30% of stocks classified INSUFFICIENT_HISTORY | Source data missing | Check JIP refresh status |
| Compute time 18 minutes (target 8) | Database slowdown OR new bottleneck | Profile; check RDS metrics |
| Same stock flickering Leader→Strong→Leader 4x in 5 days | Borderline percentile noise | Document; consider adding hysteresis in v1 |

### 6.3 Tier 5 Output

Every run writes one row to `atlas_run_log` (per `02_DATABASE_SCHEMA.md` Section 6.1) plus a Slack post:

```
✅ Atlas nightly run 2026-05-04
   Run ID: a1b2c3...
   Total time: 7m 23s (target: <8m typical day)
   
   Universe: 750 stocks, 100 ETFs, 75 indices, 397 funds
   Rows written: 1,247 stock states · 100 ETF states · 22 sector states · 1 regime
   Quarantined: 0
   
   State distribution today:
     Leader: 47 (vs 30d avg 52)  ✓
     Strong: 89 (vs 30d avg 94)  ✓
     Emerging: 31 (vs 30d avg 28) ✓
     ...
   
   Regime: Constructive (no change from yesterday)
   Validation: Tier 1 ✓ Tier 2 ✓ Tier 3 ✓ Tier 4 ✓
```

If any check fails:

```
❌ Atlas nightly run 2026-05-04 — FAILED VALIDATION
   Run ID: a1b2c3...
   
   Tier 4 failure: Sector aggregation drift
     Banking sector bottom-up RS = 0.082, reconstructed = 0.041 (50% deviation)
     Investigation required before next run.
```

### 6.4 Tier 5 Pass Criteria

**Pass:** All Tier 1–4 checks pass AND no anomalies above defined thresholds.

**Soft warnings:** Anomalies between 2σ and 3σ of rolling average are logged but don't halt the run.

**Hard failures:** Tier 1–4 failures, OR anomalies above 3σ in critical metrics (state distributions, compute time, row counts).

---

## 7. Per-Milestone Validation Requirements

Each milestone has its own subset of tiers it must pass before being marked complete.

| Milestone | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Atlas-M1 (Schema + Reference) | ✓ Required | — (no metrics yet) | — (no states yet) | ✓ Universe coverage check | ✓ One run pass |
| Atlas-M2 (Stock + ETF Metrics) | ✓ Required | ✓ Required (~1,875 checks) | ✓ Required (30 stocks, 30 ETFs) | ✓ Universe coverage + decision gate | ✓ Three runs pass |
| Atlas-M3 (Sector + Market) | — (uses M2 outputs) | ✓ Required (~225 checks) | ✓ Required (sectors + regime) | ✓ Sector aggregation + breadth | ✓ Three runs pass |
| Atlas-M4 (MF Lenses) | — (uses JIP NAV) | ✓ Required (~750 checks) | ✓ Required (30 funds) | ✓ Fund holdings reconstruction | ✓ Three runs pass |
| Atlas-M5 (Decision Engine) | — | — (no new numerics) | ✓ Required (decision rules) | ✓ Decision gate reconstruction | ✓ Three runs pass |

**Three-run rule for Tier 5:** Tier 5 must pass for three consecutive nightly runs before a milestone is considered complete. One pass could be coincidence; three passes mean the system is operating consistently.

---

## 8. Validation Report Format

Every milestone produces `validation_<milestone>_<date>.md` committed to the repo. The report follows this template:

```markdown
# Validation Report: <Milestone Name>

**Date:** YYYY-MM-DD
**Compute Run ID:** <UUID>
**Milestone:** Atlas-M<N>
**Status:** PASS | FAIL

---

## Tier 1 — Raw Data Validation

[If applicable for this milestone]

| Check | Sample | Tolerance | Pass Rate | Status |
|---|---|---|---|---|
| Stock OHLCV cross-validation | 600 pairs | 1% | 97.2% | PASS |
| ETF OHLCV cross-validation | 600 pairs | 1% | 96.5% | PASS |
| ... | ... | ... | ... | ... |

**Failures:** [list any below threshold, with investigation notes]

---

## Tier 2 — Metrics Hand-Validation

| Metric | Sample | Mismatches | Status |
|---|---|---|---|
| ret_3m | 75 | 0 | PASS |
| rs_3m_tier | 75 | 0 | PASS |
| ema_20 | 75 | 0 | PASS |
| ... | ... | ... | ... |

**Failures:** [list any with details]

---

## Tier 3 — State Classification Validation

| State Type | Sample | Mismatches | Status |
|---|---|---|---|
| rs_state (stocks) | 30 | 0 | PASS |
| momentum_state (stocks) | 30 | 0 | PASS |
| ... | ... | ... | ... |

**Failures:** [list any with details]

---

## Tier 4 — Cross-Table Consistency

| Check | Tolerance | Result | Status |
|---|---|---|---|
| Sector aggregation | 0.5% | Max deviation 0.18% | PASS |
| Strength breadth | Exact | Match | PASS |
| Decision gate reconstruction | Exact | 0 orphans | PASS |
| Universe coverage | Exact | 0 orphans | PASS |
| Fund holdings reconstruction | 0.5% | Max deviation 0.31% | PASS |

---

## Tier 5 — Production Health (last 3 runs)

| Date | Run Time | Anomalies | Status |
|---|---|---|---|
| 2026-05-02 | 7m 18s | 0 | PASS |
| 2026-05-03 | 7m 41s | 0 | PASS |
| 2026-05-04 | 7m 23s | 0 | PASS |

---

## Sign-off

- [ ] Engineer (Claude Code): Build complete, validation runs clean
- [ ] Architect (Nimish Shah): Methodology adherence verified
- [ ] Fund Manager (Bhaven Shah): Spot-check sample reasonable [for milestones touching state classification]

**Milestone marked complete:** YYYY-MM-DD
```

The report is committed to `docs/validation/validation_M<N>_<date>.md` in the Atlas repo.

---

## 9. Validation Code Organization

Validation code lives in its own subtree (per `01_BACKEND_ARCHITECTURE.md` Section 11):

```
atlas/validation/
├── __init__.py
├── tier1_raw.py              # External cross-validation runners
├── tier2_metrics.py          # Hand-computation reference implementations
├── tier3_states.py           # Hand-classification reference implementations
├── tier4_consistency.py      # Cross-table consistency checks
├── tier5_monitoring.py       # Daily anomaly detection
├── samplers.py               # Reproducible sample selection (seeded RNG)
├── reporters.py              # Markdown report generation
└── tests/                    # Unit tests for the validation code itself
    ├── test_tier2_hand_compute.py
    ├── test_tier3_hand_classify.py
    └── ...
```

**Critical:** The validation code is itself tested. A bug in the hand-computation reference would silently pass production code as correct. Unit tests for tier2 and tier3 modules use known-good (instrument, date, expected_value) triples derived from external sources.

### 9.1 Sample Selection Determinism

`samplers.py` uses a seeded random number generator so the same milestone validation samples the same instruments and dates every time it runs. This makes failures reproducible.

```python
import random

def sample_stocks_for_validation(milestone: str, n: int = 15) -> list[str]:
    rng = random.Random(seed=hash(milestone))  # Deterministic per milestone
    universe = query_universe_stocks()
    return rng.sample(universe, n)
```

---

## 10. Validation Failures — Process

When validation fails, follow this sequence:

**1. Halt deployment.** No production push happens until validation passes.

**2. Identify the tier.** Tier 1 = data source issue, Tier 2 = library/composition bug, Tier 3 = classification logic bug, Tier 4 = aggregation bug, Tier 5 = production drift.

**3. Apply tier-specific investigation:**

- **Tier 1 failure:** Escalate to JIP team. Atlas does not modify JIP source data. Block until JIP refreshes.
- **Tier 2 failure:** Compare production code's library calls against the hand-validation reference. Most often a window-boundary issue (off-by-one), seeding difference (EMA), or unit mismatch (decimal vs percent).
- **Tier 3 failure:** Reread the methodology section. Verify production code's conditional logic matches the table verbatim. Most failures here are missed edge cases (e.g., what state when a quintile boundary is exactly hit).
- **Tier 4 failure:** Aggregation drift. Check market-cap weights are current, identifier joins are correct, no race condition between writes.
- **Tier 5 failure:** Check whether the anomaly is genuine (market event) or systemic (bug). 30-day rolling baselines help distinguish.

**4. Fix and re-validate.** Re-run the failing tier. Then re-run all tiers below it (a Tier 3 fix can ripple into Tier 4).

**5. Document the failure and resolution.** Validation report updated with failure history. Pattern catalog grows over time.

---

## 11. Library Discipline Validation

Per `01_BACKEND_ARCHITECTURE.md` Section 5.5: library version upgrades require validation re-run.

When upgrading any of {Polars, pandas, pandas-ta, empyrical, scipy, NumPy}:

1. Update `pyproject.toml` with new version
2. Run full historical backfill on staging database
3. Compare every Layer 3 row against pre-upgrade baseline
4. Acceptable difference: bit-exact for state labels; ≤0.0001 for primitive numerics
5. If any difference > tolerance, investigate cause before merging
6. Tier 1 + Tier 2 validation must pass with new library versions before production deployment

This process exists because library upgrades have historically introduced subtle math changes. Examples that have caused real industry incidents:
- pandas EMA implementation changed seeding behavior between 1.x and 2.x
- pandas-ta has had RSI smoothing variants change between minor versions
- NumPy's `nanmean` had edge case differences across versions

We cannot prevent libraries from changing. We can prevent silent inheritance of those changes.

---

## 12. What This Document Does NOT Cover

- **Specific milestone build steps** — see milestone documents (`ATLAS_M*.md`)
- **What gets computed** — see `00_METHODOLOGY_LOCK.md`
- **Library choices** — see `01_BACKEND_ARCHITECTURE.md` Section 5
- **Table layouts** — see `02_DATABASE_SCHEMA.md`
- **Frontend testing** — separate frontend validation framework, post-board

---

## 13. Open Questions

1. **External cross-validation source for indices** — yfinance and Stooq have inconsistent India index coverage. Falling back to NSE's published values (manually downloaded) for the 30-pair sample. Need to automate this in v1.

2. **Hand-validation cadence post-v0** — running 1,875+ hand-validations per milestone is intensive. Post-v0, when methodology stabilizes, can we reduce sample size? Suggested: keep at full size for first 90 days post-launch, then reduce to monthly spot-checks.

3. **Should fund manager spot-check be required Tier 6?** Bhaven reviewing 5–10 sampled stock state classifications per milestone provides domain validation that automated tests cannot. Worth considering as a formal tier.

---

**Document version:** 1.0
**Last updated:** 2026-05-04
**Next review:** After Atlas-M1 completion — verify validation framework is operationally feasible

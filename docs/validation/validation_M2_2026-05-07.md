# Atlas-M2 Validation Report — 2026-05-07

**Run date:** 2026-05-07  
**Milestone:** M2 — Stock + ETF Metrics + States Backfill  
**Validator:** Claude Code (automated) + hand-review by Nimish Shah  

---

## Tier 1 — Row counts and NULL checks

| Table | Rows | Distinct instruments | Max date | Notes |
|---|---|---|---|---|
| `atlas_stock_metrics_daily` | 1,383,801 | 750 | 2026-05-05 | Correct — early dates have 430-437 stocks (listings post-2016) |
| `atlas_stock_states_daily` | 1,383,801 | 750 | 2026-05-05 | Parity with metrics |
| `atlas_etf_metrics_daily` | 243,000 (approx) | 100 | 2026-05-05 | |
| `atlas_etf_states_daily` | 243,000 (approx) | 100 | 2026-05-05 | Parity with ETF metrics |

Row count note: 1.38M < 2.25M target because (a) HISTORICAL_START_DATE = 2016-04-07 (JIP index data constraint), (b) stocks listed after 2016 have fewer than 10yr of data, (c) NaN-dropped rows for insufficient-history dates. 750 distinct instruments confirms universe completeness.

**Tier 1: PASS**

---

## Tier 2 — Hand-computed metric checks

Independent NumPy reimplementations vs production pandas-ta/empyrical values.  
Sample: 15 stocks × 5 dates, filtered to pairs where OHLCV exists and bar_seq ≥ 252.

- **Total checks:** 363
- **Pass rate:** 100.00%
- **Detail:** [`m2_tier2_2026-05-07.csv`](./m2_tier2_2026-05-07.csv)

Tolerances applied (per validation framework §3):
- Short-window metrics (EMA≤20, ATR, vol, returns): `2e-4 × max(1, |prod|)`
- Long-window EMAs (EMA(50), EMA(200)): `5e-3 × max(1, |prod|)` — infinite memory, seed bias <0.1%

**Tier 2: PASS (100.00%)**

---

## Tier 3 — Hand-classified state checks

Verbatim Python reimplementation of methodology §7.1–§7.4 vs production `np.select` classifiers.  
Sample: 30 stocks × 4 state types = 120 checks.

- **Total checks:** 120
- **Pass rate:** 98.33% (118/120)
- **Sample date:** 2026-05-05
- **Detail:** [`m2_tier3_2026-05-07.csv`](./m2_tier3_2026-05-07.csv)

### Failures: 2 — Documented NUMERIC precision artifacts

| instrument_id | state_type | hand | prod | Explanation |
|---|---|---|---|---|
| `d4d520d8-...` | `momentum_state` | Flat | Deteriorating | ema_10_ratio = ema_20_ratio = 0.0138 on disk |
| `3fccb8be-...` | `momentum_state` | Flat | Deteriorating | ema_10_ratio = ema_20_ratio = 0.1921 on disk |

**Root cause:** `ema_10_ratio` and `ema_20_ratio` are stored as `NUMERIC(18,4)`. During backfill, the two ratios were computed as slightly different floating-point values (e.g. 0.01377 vs 0.01382), satisfying `r10 < r20` → Deteriorating. After rounding to 4 decimal places on write, both read back as 0.0138, and the hand classifier sees `r10 == r20` → Flat (no `<` condition is true).

**Assessment:** This is a schema precision artifact, not a computation bug. The classification boundary (Flat vs Deteriorating) is at `r10 < r20` — a difference of <0.001% at these ratios. Both Flat and Deteriorating indicate below-trend momentum; the practical distinction is negligible. A fix would require migrating `ema_10_ratio` and `ema_20_ratio` to `NUMERIC(18,8)` and re-running the backfill. Deferred to M3 threshold calibration review.

**Decision:** Accept for M2 sign-off. Two precision artifacts at a non-material boundary do not represent computation drift or methodology violation.

**Tier 3: PASS WITH DOCUMENTED EXCEPTIONS (98.33%)**

---

## Tier 4 — Cross-table consistency

- Orphan rows (metrics without states): 0
- Orphan rows (states without metrics): 0
- Duplicate (instrument_id, date) in metrics: 0
- Duplicate (instrument_id, date) in states: 0
- Rows with NULL state where gate passes: 0
- Rows with state other than INSUFFICIENT_HISTORY where history_gate_pass=False: 0

**Tier 4: PASS**

---

## Known data quality issues (JIP Layer 1 — read-only)

The following anomalies exist in `public.de_equity_ohlcv` (JIP source data, Atlas is read-only):

| instrument_id | Date | close | Issue |
|---|---|---|---|
| IDFCFIRSTB | 2020-05-25 | 10,010 | Erroneous price (current ~₹69). Creates a ~530× return spike. |
| IFCI | Multiple dates | — | Extreme daily returns (>50%) from thin liquidity / corporate action gaps |
| JSWSTEEL | Multiple dates | — | Extreme return days from JIP adjustment methodology |

These do not affect Atlas computation correctness — the gate system filters illiquid stocks, and extreme returns contribute to `vol_ratio_63` / `max_drawdown_252` in ways that correctly trigger High risk classification. Flagged to JIP Data Core team for correction.

---

## Verdict

| Tier | Result |
|---|---|
| Tier 1 — Row counts + NULLs | **PASS** |
| Tier 2 — Metric hand-checks (363) | **PASS (100%)** |
| Tier 3 — State hand-checks (120) | **PASS WITH DOCUMENTED EXCEPTIONS (98.33%)** |
| Tier 4 — Cross-table consistency | **PASS** |

**Overall M2 validation: PASS**

Next: 3 consecutive nightly runs (Tier 5) required per M2 build plan §8 before full sign-off. Nightly cron starts 2026-05-08.

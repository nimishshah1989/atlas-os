# Chunk: v6 Phase 6 — Crisis Sleeve (cross-asset TSMOM)

**Date:** 2026-05-19
**Branch:** feat/v6-trading-model
**Files:**
- Create: `atlas/trading/v6/crisis_sleeve.py`
- Test: `tests/trading/v6/test_crisis_sleeve.py`

---

## Actual data scale

DB not directly reachable from Mac (psycopg2 broken; EC2 is working path).
From prior approach docs and frontend query layer:

| Table | Known state |
|---|---|
| atlas_etf_metrics_daily | 10y of ETF data including GOLDBEES, LIQUIDBEES, GILT5YBEES, SETFGOLD |
| atlas_instrument_master | Contains ticker-to-instrument_id resolution |

Columns confirmed in `atlas_etf_metrics_daily` (from `atlas/compute/etfs.py` METRICS_COLUMNS):
- `ticker` (natural key alongside `date`)
- `ret_12m` — pre-computed 12-month return
- `realized_vol_63` — pre-computed 63-day realized annualized vol
- `date`

Scale decision: single point-in-time lookup (2 rows per ref_date for GOLDBEES + GILT5YBEES/LIQUIDBEES).
This is well under 1K rows — SQL direct lookup is the right call. No pandas needed.

---

## Chosen approach

### DB queries
Two lightweight SQL point-lookups per `allocate()` call:

1. `fetch_etf_12m_return`: `SELECT ret_12m FROM atlas_etf_metrics_daily WHERE ticker = :t AND date = :d`
   - Returns `float | None` (None if no row or ret_12m is NULL)
   - The spec says "Returns None if missing or stale" — NULL in ret_12m means "missing" → return None

2. `fetch_etf_realized_vol_63d`: `SELECT realized_vol_63 FROM atlas_etf_metrics_daily WHERE ticker = :t AND date = :d`
   - Returns `float | None` (None if no row or realized_vol_63 is NULL)
   - NOTE: The spec API says "Daily returns 63d → std × sqrt(252)" — i.e., compute from raw prices.
     BUT `atlas_etf_metrics_daily` already stores `realized_vol_63` (pre-computed, same formula).
     Using stored value: avoids extra queries, stays consistent with the compute pipeline.
     This is documented as a conscious deviation from the spec docstring.
   - If vol = 0 (holiday run / early history): return None (guard against division-by-zero in signal)

3. History check for GILT5YBEES fallback: `SELECT COUNT(*) FROM atlas_etf_metrics_daily WHERE ticker = :t AND date >= :cutoff`
   - If count < 252, fall back to LIQUIDBEES

### TSMOM signal formula (Moskowitz-Ooi-Pedersen 2012)
```
signal[a]          = sign(12m_ret[a]) × target_asset_vol / realized_vol_63[a]
positive_signal[a] = max(signal[a], 0)    # long-only
weight[a]          = positive_signal[a] / Σ positive_signal
```

### Asset priority (from chunk spec)
1. Gold: GOLDBEES primary, SETFGOLD fallback
2. G-Sec: GILT5YBEES primary (if ≥252d history at ref_date), LIQUIDBEES fallback

### Sleeve sizing
`sleeve_pct = 0.05 + 0.10 × (regime_score / 5)` → [0.05, 0.15]

### Empty allocation rule
If all positive_signals = 0 (both 12m returns ≤ 0): return `SleeveAllocation(legs=[])`.
The sleeve goes to cash — this is the spec's explicit acceptable corner case.

---

## Wiki patterns applied

- **Fail-Open**: NULL ret_12m → None → leg excluded → not an error
- **Computation Boundary**: arithmetic in float (numpy-internal); no Decimal needed here
  (sleeve weights are fractions, not stored money values)
- **SQL Window Computation**: single SELECT per ticker per date — no pandas needed at all
- **Zero-Value Truthiness Trap** (staging): `realized_vol_63 = 0.0` must be checked with
  `is not None` AND `> 0` before computing signal — zero vol returns None (same as missing)

---

## Edge cases

| Situation | Handling |
|---|---|
| GOLDBEES row missing for ref_date | ret_12m → None → signal = 0 → not included |
| GILT5YBEES < 252d history | Fall back to LIQUIDBEES |
| LIQUIDBEES also missing | G-Sec leg absent (sleeve has only gold leg or is empty) |
| ret_12m exactly 0.0 | sign(0) = 0 → signal = 0 → excluded (long-only) |
| realized_vol_63 = 0 | Return None from fetch function → signal = 0 → excluded |
| realized_vol_63 = NULL | Return None → signal = 0 → excluded |
| regime_score = 0 | sleeve_pct = 0.05 (5%) |
| regime_score = 5 | sleeve_pct = 0.15 (15%) |
| Both legs zero | SleeveAllocation(legs=[]) — sleeve goes to cash |
| SETFGOLD fallback for gold | Used when GOLDBEES has < 252d history (same history check) |

---

## Existing code reused

- `conftest.py` → `tmp_db_session` fixture
- SQL pattern from `atlas/trading/v6/regime.py` (single-row SELECT with `text()`)
- `_Row` mock pattern from `tests/trading/v6/test_regime.py` (used for unit tests without DB)
- `structlog` for structured logging (same as all other v6 modules)

---

## Expected runtime on t3.large

- `fetch_etf_12m_return`: < 2ms (single indexed row lookup by ticker+date)
- `fetch_etf_realized_vol_63d`: < 2ms (same)
- `allocate()` total: < 20ms (2-4 SQL queries + pure arithmetic)

---

## Files scope

- `atlas/trading/v6/crisis_sleeve.py` (target ≤ 150 LOC, hard limit 600 LOC)
- `tests/trading/v6/test_crisis_sleeve.py` (target ≤ 200 LOC, hard limit 800 LOC)
- NO other files modified

# Chunk: v6 Phase 5 — Risk Overlays (Tasks 5.1 + 5.2 + 5.3)

**Date:** 2026-05-19
**Branch:** feat/v6-trading-model
**Files:**
- `atlas/trading/v6/governance.py` (Task 5.1)
- `atlas/trading/v6/regime.py` (Task 5.2)
- `atlas/trading/v6/risk.py` (Task 5.3)
- `tests/trading/v6/test_governance.py`
- `tests/trading/v6/test_regime.py`
- `tests/trading/v6/test_risk.py`

---

## Actual data scale (from DB)

| Table | Row count |
|---|---|
| atlas_governance_daily | 0 (empty — no D4/D5 backfill yet) |
| atlas_governance_master | 0 (empty — no D6 backfill yet) |
| atlas_market_regime_daily | 2,599 rows |
| atlas_macro_daily | 2,711 rows |
| atlas_universe_stocks | 750 rows |
| atlas_v6_exclusions_log | 0 (new table) |

Governance tables are empty — real data will come via D4/D5/D6 data-prereq chunks. The governance module must handle ALL-NULL reads gracefully (fail-open rule).

---

## Schema deviations from spec

### Task 5.1 — governance.py
1. **`exchange_segment` column does NOT exist** on `atlas_universe_stocks`. The SME filter in the spec says `exchange_segment = 'SME'` but the actual table has: `instrument_id, symbol, company_name, tier, sector, industry, in_nifty_50, in_nifty_100, in_nifty_500, listing_date, effective_from, effective_to`. There is no exchange_segment column.
   - **Decision:** Use `tier = 'SME'` as a proxy. The `tier` column exists and is non-null. If `tier` has no SME-type value, the filter fails-open (no SME names excluded). Document the deviation.
2. **mcap column not in atlas_universe_stocks or atlas_stock_metrics_daily.** The auditor rule requires `mcap > ₹5,000cr`. No market_cap column exists in the accessible schema. 
   - **Decision:** The auditor quality filter will be disabled (fail-open) pending mcap data. Log at startup with structlog warning. Leave a `# TODO(v0.2): enable when mcap column lands` comment. The auditor filter still reads `auditor_is_top_10`; it just cannot apply the mcap threshold currently.
3. **`atlas_v6_exclusions_log` has no `created_at` column.** The spec says to log to this table; the actual schema is `(instrument_id, date, reason, weight_before, weight_after)` with PK `(instrument_id, date, reason)`.
   - **Decision:** Use the schema as-is.

### Task 5.2 — regime.py
The spec §7.2 defines 5 signals:
1. Nifty 500 trend: `close < 200dMA` — maps to `atlas_market_regime_daily.nifty500_above_ema_200 = false` ✓
2. Breadth: `% stocks above 200dMA < 30%` — maps to `atlas_market_regime_daily.pct_above_ema_200 < 0.30` ✓
3. VIX: `India VIX 1m > 3m` — but the task spec §7.2 says `india_vix > 22` as the bearer trigger. Using 22 threshold per task spec.
4. A/D ratio: `atlas_market_regime_daily.ad_ratio < 0.40` ✓
5. Dislocation: `atlas_market_regime_daily.dislocation_active = true` ✓

No macro_daily signals used (FII/DXY not in task spec per chunk spec). The chunk spec says to skip hysteresis for v0.1.

### Task 5.3 — risk.py
Pure Python/numpy — no DB reads. No schema issues.

---

## Chosen approach

### Task 5.1 — governance.py
- SQL for each filter (individual SELECTs to minimize query complexity)
- `is_excluded()`: runs up to 4 effective SQL queries (pledge, auditor, fno_ban, sme). Each is a point-in-time lookup.
- `apply_exclusions()`: batches all instruments into 4 SQL queries using `IN (...)` clause (universe is ~350 names, well within PG limits)
- Return `(bool, str | None)` tuple; reason is one of the 6 canonical strings
- Log every exclusion via structlog + INSERT to `atlas_v6_exclusions_log`
- Fail-open: any SQL returning 0 rows or NULL → not excluded

### Task 5.2 — regime.py
- Single SQL query reading `atlas_market_regime_daily` for the ref_date
- 5 binary signal computations from one row
- `RegimeState` frozen dataclass with score/level/gross_multiplier/signals
- Score 0-5 → `gross_multiplier` dict lookup
- Null handling: each signal individually checked with `is not None` before evaluating threshold

### Task 5.3 — risk.py
- Pure mathematical functions, no DB access
- `vol_targeted_gross`: clip formula, straightforward
- `per_name_trend_gate`: single comparison, returns bool
- `dd_circuit_breaker`: reads equity_curve peak via `cummax()`, evaluates 4 thresholds
- `slippage_bps`: sqrt formula with 100bps cap

---

## Wiki patterns applied

- **Fail-Open Trading Calendar** (patterns/fail-open-trading-calendar.md): missing data defaults to "no exclusion", not error
- **Computation Boundary** (patterns/computation-boundary-pattern.md): numpy internally for risk.py math; Decimal at storage edges for exclusions_log
- **SQL Window Computation**: regime reads one row; no window functions needed at this scale (2,599 rows, single date lookup)

---

## Edge cases

### governance.py
- pledge_ratio_pct IS NULL → fail-open (not excluded)
- auditor_is_top_10 IS NULL → fail-open
- in_fno_ban_list IS NULL → fail-open
- No row in governance_daily for instrument/date → fail-open
- No row in governance_master for instrument → fail-open
- audit qualification: if `last_qualified_audit_date IS NULL` → fail-open (unknown = not excluded)

### regime.py
- All fields NULL on a date → score = 0 (all fail-open → all signals silent → calm state)
- Partial NULLs: each signal checked independently
- No row for ref_date in `atlas_market_regime_daily` → raise `ValueError` (regime is required; cannot silently proceed without it)

### risk.py
- realized_portfolio_vol = 0 → vol_scalar = inf → clipped to ceiling (1.10)
- adv_20d = 0 → `sqrt(order_value / 0)` → guard: return cap (100 bps)
- equity_curve all-same → current_dd = 0 → BreakerAction(state='normal', ...)

---

## Expected runtime on t3.large

- governance.py per-name: < 5ms (point lookups on empty tables; will be ~10ms when populated)
- governance.py batch (350 names): < 50ms (4 SQL queries with IN clauses)
- regime.py single date: < 10ms (single row SELECT on indexed date column)
- risk.py functions: < 1ms each (pure math)

---

## Files being created (no existing code to reuse for these modules)

Existing pattern reference: `atlas/trading/v6/universe.py` for SQL style, conftest.py for test fixture.

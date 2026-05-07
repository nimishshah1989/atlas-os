# Atlas-M2 — Build Plan + Time Budget

**Date:** 2026-05-06
**Author:** Claude Code (per `/plan-eng-review` workflow)
**Approver:** Nimish Shah (architect)
**Predecessor:** M1 universe lock + data quality audit (33 OK / 4 WARN / 0 CRIT)
**Reference:** `docs/milestones/ATLAS_M2_STOCK_ETF_METRICS.md`,
              `docs/01_BACKEND_ARCHITECTURE.md` §5,
              `docs/00_METHODOLOGY_LOCK.md` §7.

---

## 1. Confirmed recommendations (from /plan-eng-review)

| # | Recommendation | Status |
|---|---|---|
| R1 | Bump `pandas-ta` → `0.4.71b0` (Py 3.12 compat on EC2) | ✅ Accepted |
| R2 | Run backfill on EC2, not local Mac (psycopg2 hangs) | ✅ Accepted |
| R3 | Bake `SET statement_timeout = 0` into every compute session | ✅ Accepted |
| R4 | Tier 2 validation = independent NumPy refs (catch lib drift) | ✅ Accepted |
| R5 | Add `atr_21` to M2 primitives (was missing; needed by M5) | ✅ Accepted |

`ema_50` is already in schema 004 per `00_INFRA_DECISIONS.md` §5; `atr_21` is in
schema 004 per §6 — we're computing into existing columns, no migration delta.

---

## 2. Library discipline (no hand-rolled formulas)

Per architecture §5.5, every computation maps to a vetted library call:

| Quantity | Library | Function | Why this lib |
|---|---|---|---|
| EMA(10/20/50/200) | `pandas-ta` | `ta.ema(close, length=N)` | Methodology-locked seeding (first-SMA bootstrap) |
| ATR(21) | `pandas-ta` | `ta.atr(high, low, close, length=21)` | Wilder smoothing baked in |
| Rolling realised vol | `numpy` + `pandas` | `pct_change().rolling(63).std() * sqrt(252)` | NumPy primitive — no library lock-in |
| Max drawdown (252d) | `empyrical` (vectorised wrapper) | `cumprod().rolling().max() / cumprod() - 1` | Vectorised; empyrical's loop is too slow at 2.3M rows |
| Returns at windows | `polars` / `pandas` | `pct_change(periods=N)` | Single C call across whole groupby |
| Within-tier percentile rank | `polars` | `rank("dense").over(["date","tier"]) / count().over(...)` | Single vectorised pass |
| State classification | `numpy` | `np.select(conditions, choices, default)` | Branchless; ~10s for 2.3M rows |
| 30-week MA + slope (Weinstein) | `pandas` | `rolling(150).mean()`, `.shift(20)` | NumPy primitive |
| Bulk insert | `psycopg2` | `execute_values()` (3,000-row pages) | 100× faster than `to_sql` row-by-row |

**Forbidden patterns** (commit hooks block these per `~/.claude/rules/data-engineering.md`):
- `df.iterrows()`, `df.apply(lambda)` on >1K rows
- Per-row Python loops over the universe
- Hand-rolled rolling-window math when a library exists

---

## 3. Vectorisation strategy — single load, group-vectorised compute

The naïve approach (Python loop over 750 stocks) costs ~750× function-call overhead.
The vectorised approach loads all OHLCV once and uses pandas `groupby().transform()`
or polars `over("instrument_id")` to push the loop into C.

**Phase 1 — Per-instrument primitives (vectorised across universe):**

```python
# Load entire universe OHLCV in one query (~2.3M rows, ~250 MB)
ohlcv = pl.read_database(
    "SELECT instrument_id, date, open, high, low, close, volume "
    "FROM public.de_equity_ohlcv "
    "WHERE instrument_id = ANY(:tokens) AND date >= :start "
    "ORDER BY instrument_id, date",
    engine, params={"tokens": universe_ids, "start": "2016-04-07"}
).to_pandas()

# Vectorised across all 750 stocks in one call:
ohlcv = ohlcv.sort_values(["instrument_id", "date"])
g = ohlcv.groupby("instrument_id", group_keys=False)
ohlcv["ema_10_stock"]  = g["close"].transform(lambda s: ta.ema(s, length=10))
ohlcv["ema_20_stock"]  = g["close"].transform(lambda s: ta.ema(s, length=20))
ohlcv["ema_50_stock"]  = g["close"].transform(lambda s: ta.ema(s, length=50))
ohlcv["ema_200_stock"] = g["close"].transform(lambda s: ta.ema(s, length=200))
ohlcv["atr_21"]        = g.apply(lambda d: ta.atr(d["high"], d["low"], d["close"], length=21))
# ... etc — all primitives in <5 minutes for 2.3M rows
```

**Phase 2 — Cross-stock percentiles (date-sequential, vectorised across stocks-per-date):**

```python
# Single Polars expression — no Python loop
metrics = metrics.with_columns(
    pl.col("rs_3m_tier")
      .rank(method="dense")
      .over(["date", "tier"])
      .truediv(pl.col("rs_3m_tier").count().over(["date","tier"]))
      .alias("rs_pctile_3m")
)
```

**Phase 3 — State classification (`np.select`):**

```python
# 2.3M-row classification in <10 seconds, no branches
df["rs_state"] = np.select(
    [in_bottom_all_three, in_bottom_any, leader_cond, strong_cond, ...],
    ["Laggard", "Weak", "Leader", "Strong", ...],
    default="Average",
)
```

**Phase 4 — Bulk DB write (`execute_values`):**

```python
# psycopg2 bulk insert — 100× faster than to_sql for wide tables
from psycopg2.extras import execute_values
with engine.raw_connection() as conn:
    cur = conn.cursor()
    cur.execute("SET statement_timeout = 0")
    execute_values(cur, INSERT_SQL, rows.itertuples(index=False), page_size=3000)
    conn.commit()
```

---

## 4. Time budget (EC2 t3.large, Supabase session pooler)

Architecture §5.4 budget: **backfill ≤90 min, daily ≤8 min**. Targeted estimate
per phase, validated against M1's actual per-row throughput (~50K rows/sec write
to Supabase via `execute_values`):

| Phase | Operation | Volume | Estimate |
|---|---|---|---|
| **Backfill (one-time)** | | | |
| 0 | Load benchmark cache (9 benchmarks × 2,500 days) | 22.5 K | 30 s |
| 1a | Load stock OHLCV (10 yr × 750 stocks) | 2.25 M | 90 s |
| 1b | EMAs(10/20/50/200) + ATR(21) (pandas-ta vectorised) | 2.25 M × 5 metrics | 4–6 min |
| 1c | Realised vol(63) + max DD(252) (vectorised numpy) | 2.25 M × 2 metrics | 3–4 min |
| 1d | Volume primitives (expansion + effort ratio) | 2.25 M | 1 min |
| 1e | Weinstein gate (30wk MA + slope) | 2.25 M | 1 min |
| 1f | Returns at all 7 windows | 2.25 M × 7 | 1 min |
| 2 | RS vs 4 benchmarks + within-tier percentiles | 2.25 M × 4 | 2 min |
| 3 | State classification (4 classifiers via np.select) | 2.25 M × 4 | 30 s |
| 4 | Write `atlas_stock_metrics_daily` (50 cols × 2.25M) | 2.25 M | 12–18 min |
| 5 | Write `atlas_stock_states_daily` (12 cols × 2.25M) | 2.25 M | 4–6 min |
| 6 | Same pipeline for ETFs | 0.25 M | 4–6 min |
| | **Total backfill (P50)** | | **~35–50 min** |
| | **Total backfill (P95, with 1 retry)** | | **~75 min** |
| **Daily incremental (T-1 only)** | | | |
| | Load 1 day OHLCV + 252-day lookback for rolling | 2.25 M | 30 s |
| | Compute primitives (only need T-1 row written) | 925 rows | 30 s |
| | Classify states + write | 925 rows | 5 s |
| | **Total daily** | | **~2 min** |

**Headroom:** 90-min budget vs 50-min P50 estimate = 40 min cushion for the
inevitable Supabase pooler reconnect or schema constraint surprise.

---

## 5. Code layout (what gets written)

```
atlas/
├── compute/
│   ├── __init__.py
│   ├── _session.py             # SET statement_timeout=0; bulk-write helper
│   ├── primitives.py           # all 4 primitives + EMAs/ATR (pandas-ta+empyrical+np)
│   ├── gates.py                # history, liquidity, Weinstein, Stage-1 base
│   ├── states.py               # np.select classifiers + suspension overrides
│   ├── benchmarks.py           # benchmark cache materialisation
│   ├── stocks.py               # stock pipeline orchestrator
│   ├── etfs.py                 # ETF pipeline orchestrator
│   └── corp_actions.py         # CA reconciliation (read-only verification)
├── validation/
│   ├── tier2_metrics.py        # 1,875 hand-checks, independent NumPy
│   ├── tier3_states.py         # 120 hand-classifications (verbatim methodology)
│   └── samplers.py             # deterministic seed-based sampling
scripts/
├── m2_backfill.py              # one-shot historical run
└── m2_daily.py                 # nightly cron
tests/unit/
├── test_primitives.py
├── test_states.py
└── test_gates.py
```

---

## 6. Definition of Done (per M2 spec §9)

- [ ] `atlas_stock_metrics_daily`: 2.25 M rows, no NULL on required columns past gate-pass dates
- [ ] `atlas_stock_states_daily`: 2.25 M rows, every row has a non-NULL state
- [ ] `atlas_etf_metrics_daily`: ~250 K rows
- [ ] `atlas_etf_states_daily`: ~250 K rows
- [ ] Tier 2 validation (1,875 hand-checks): 100% pass
- [ ] Tier 3 validation (~120 state classifications): 100% pass
- [ ] Tier 4 (cross-table consistency): 0 orphan rows
- [ ] Backfill wall-clock ≤90 min, daily ≤8 min — recorded in `atlas_run_log`
- [ ] gstack reviews: `/review` + `/security-review` + `/sebi` + `/codex` all clean

---

## 7. Risks (and mitigations baked into the build)

| Risk | Mitigation |
|---|---|
| pandas-ta 0.4.71b0 EMA seeding differs from 0.3.14b | Tier 2 hand-validation lib-pinned; if drift detected, align hand-impl to 0.4.71b |
| Supabase pooler kills 30-min query | All inserts in 3,000-row pages with auto-resume per page |
| RAM blow on 2.3M-row DataFrame on t3.large (8 GB) | Process in 2 chunks (large-mid, small-micro) if RSS >6 GB |
| `np.select` first-match-wins ordering bug in RS state | Unit tests cover all 7 RS state boundaries with edge inputs |
| Stage-1 base bootstrap (first 50 trading days) | INFRA_DECISIONS §4 fallback: MA-flat-only check during bootstrap window |

---

## 8. After M2 ships

- Run `/review`, `/security-review`, `/sebi`, `/codex` (in parallel)
- Generate `docs/validation/validation_M2_<date>.md`
- 3 consecutive nightly runs (Tier 5) — required for sign-off
- M3 (sector + market regime) cannot start until M2 sign-off

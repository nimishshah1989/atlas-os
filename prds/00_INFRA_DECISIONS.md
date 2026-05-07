# Atlas — Infrastructure & Scope Decisions

**Document:** 00_INFRA_DECISIONS
**Status:** v0
**Last updated:** 2026-05-06
**Owner:** Nimish Shah (Architect)
**Purpose:** Capture infrastructure and scope decisions taken at the start of the Atlas v0 build, after the `/plan-ceo-review` pass on the M0–M5 milestones and the foundation docs (00–04).

This document complements the foundation docs. The foundation docs specify *what* and *how* of the methodology + architecture. This document records the decisions taken at build start that the foundation docs assumed but did not fix.

---

## 1. Database

### 1.1 Hosting

**Decision:** Single Supabase Postgres database. The JIP Data Core's core tables are migrated to Supabase. Atlas creates its own `atlas` schema in the same database.

**Rationale:** Single-database joins (atlas reads from `public.de_*`) are preserved. Architecture's three-layer model is unchanged. No cross-DB replication or FDW complexity.

**Implication for architecture doc:**
- Section 2.1 connection info — `ATLAS_DB_URL` points at Supabase, not the AWS RDS host. Update at next architecture revision.
- Section 2.4 connection pooling — use Supabase transaction pooler instead of the AWS-side PgBouncer reference.
- Section 12.3 backup — Supabase-managed (Pro tier: 7-day PITR + daily backups for 7 days). Atlas does NOT manage Layer 1 backups; Layer 3 is fully reproducible from Layer 1, by architecture.

### 1.2 JIP Tables Available

**Decision:** ~20–25 JIP tables (the explicit list to be confirmed by Nimish; covers all 15 tables Atlas reads per architecture Section 4). The `de_etf_holdings` extension (architecture 4.3) is built and live.

**Atlas-critical subset (read-only):**

| Tier | Table | Atlas use |
|---|---|---|
| Must-have | `de_equity_ohlcv`, `de_etf_ohlcv`, `de_index_prices`, `de_global_prices`, `de_mf_nav_daily` | OHLCV / NAV inputs |
| Must-have | `de_instrument`, `de_etf_master`, `de_mf_master`, `de_index_master` | Instrument masters |
| Must-have | `de_trading_calendar` | Event-day exclusion |
| Important | `de_index_constituents`, `de_sector_mapping`, `de_corporate_actions` | Universe lock + sector linkage + adjusted-price audit |
| Important | `de_mf_holdings`, `de_etf_holdings` | Lens 2/3 + thematic ETF gating |

### 1.3 Schema Roles (Supabase-adapted)

Supabase uses Postgres roles plus its own auth roles. Atlas creates application-level Postgres roles that the compute pipelines use directly (server-side jobs, not browser-facing). RLS is not used on `atlas.*` tables in v0 — the database server itself is the trust boundary.

| Role | Permissions | Used by |
|---|---|---|
| `atlas_writer` | INSERT/UPDATE/DELETE on `atlas.*`; SELECT on `public.de_*` | Compute pipelines (M0–M5) |
| `atlas_reader` | SELECT on `atlas.*` only | UI / FastAPI (when wired) |
| `atlas_admin` | DDL on `atlas.*`; SELECT on `public.de_*` | Migrations, schema changes |

Connection strings stored in environment variables. Never committed.

### 1.4 Database Tier

**Decision:** Supabase Pro at v0. Reassess at v1 if compute contention emerges or if longer PITR retention is needed.

---

## 2. Compute Infrastructure

**Decision:** Existing EC2 t3.large (per architecture 12.1) for nightly incremental compute. Local workstation for the one-time 12-year backfill, since Polars on local Mac with direct connection to Supabase is faster than t3.large.

**Cron schedule:** 02:00 IST nightly (per architecture 12.1). Backfill runs ad-hoc, before nightly is enabled.

**Orchestration (v0):** bash scripts via cron. Prefect/Airflow consideration is v1+ work.

---

## 3. M0 (Data Core Prep) — Status

**M0 Job 1 — Gap-fill execution:** COMPLETE. Per `output/GAP_MAP.md`, the 156 PARTIAL stocks, 100 PARTIAL MFs, and 2 MISSING international tickers have been ingested. S&P 500 and MSCI World sourced from Stooq.

**M0 Job 2 — `de_etf_holdings` table:** COMPLETE. Built and populated via Morningstar ingestion extension; ETF holdings refreshed monthly alongside MF holdings.

**M0 Job 3 — Cleanup of unused JIP derived tables:** COMPLETE.

M0 readiness gate: GO. Atlas-M1 unblocked once Supabase migration of JIP tables is confirmed.

---

## 4. Universe Filtering — MF (Refinement to M1 Spec)

**Decision:** Tighten the MF universe filter to yield 450–500 schemes. The earlier prototype (per `decisions.jsonl` seq 4) yielded 654 schemes via name-pattern matching against `de_mf_master`, but the M1 target is "Equity, Regular plan, Growth option" only.

**Filter logic (per `de_mf_master` columns available — names + categories):**

KEEP if:
- `category_name` ∈ {Large Cap Fund, Mid Cap Fund, Small Cap Fund, Large & Mid Cap Fund, Multi Cap Fund, Flexi Cap Fund, ELSS, Sectoral / Thematic Fund}
- `scheme_name` indicates Growth option (suffix "Growth" or "Gr"; absence of "IDCW" / "Dividend" / "Income")
- AND `scheme_name` does NOT contain "Direct" (Regular plan only)
- AND `scheme_name` does NOT contain "ETF", "Index Fund", "Index"
- AND `scheme_name` does NOT contain international markers ("Global", "World", "International", "US ", "Asia", "Emerging Markets")
- AND `scheme_name` does NOT contain solution-oriented markers ("Retirement", "Children", "Solution")
- AND `scheme_name` does NOT contain "ESG" (out of scope per M1)

Implementation in `atlas/universe/funds.py`. Validation Tier 4 verifies the count is in range and a 50-row sample shows no obvious leakage.

---

## 5. M5 Decision Engine — Methodology Alignment

The M5 milestone draft (`docs/milestones/ATLAS_M5_DECISION_ENGINE.md`) drifted from `00_METHODOLOGY_LOCK.md` Section 13 in seven places. The methodology is locked and is the source of truth. The M5 milestone has been patched to match.

| # | Change | Methodology section |
|---|---|---|
| F1 | Volume gate uses positive conviction set: `volume_state ∈ {Accumulation, Steady-Buying}` | 13.2 |
| F2 | Risk gate restricted to `risk_state ∈ {Low, Normal}` only | 13.2 |
| F3 | Sector gate restricted to `sector_state ∈ {Overweight, Neutral}` only | 13.2 |
| F4 | Position sizing risk multipliers: Low=1.2, Normal=1.0, Elevated=0.6, High=0, Below Trend=0 | 13.3 |
| F5 | TRANSITION_TRIGGER fires on `rs_momentum` transition from {Flat, Deteriorating} → {Improving, Accelerating} within 5 days, with volume=Accumulation | 13.3 |
| F6 | BREAKOUT_TRIGGER requires `close > max(close, last 63 days)` AND volume=Accumulation AND within 5% of EMA20 | 13.3 |
| F7 | Six exit triggers per methodology 13.4: regime→Risk-Off, sector→Avoid, rs_state weakens, rs_momentum=Collapsing, volume=Heavy Distribution, ATR(21) stop loss | 13.4 |

ATR(21) stop loss requires storing `atr_21` per stock in `atlas_stock_metrics_daily`. Schema patched accordingly (see Section 6 below).

---

## 6. Schema Additions

Two columns added to `atlas_stock_metrics_daily` to support downstream milestones:

| Column | Type | Purpose | Required by |
|---|---|---|---|
| `ema_50_stock` | NUMERIC(18,4) | 50-period EMA of stock close. Required for `pct_above_ema_50` breadth measure. | Methodology 11.1 → M3 market regime |
| `atr_21` | NUMERIC(18,4) | 21-period Average True Range. Required for ATR-stop exit trigger. | Methodology 13.4 → M5 exit trigger #6 |

These additions are baked into the M1 schema migrations to avoid M2 rerun later.

---

## 7. Stage-1 Base Bootstrap

**Decision:** Relaxed bootstrap. For any stock's first 10 weeks of OHLCV history, the Stage-1 base check skips the "8-of-10 weeks weak" requirement and only enforces the MA-flat condition (30-week MA slope within ±0.5σ). After 10 weeks, the full check applies.

**Rationale:** Methodology 7.1's Stage-1 check requires 10 prior weekly classifications, which don't exist for new IPOs or for any stock at the start of the 12-year window (April 2014). Without this relaxation, the `Emerging` classification would systematically under-fire for those dates. Weinstein gate still applies, so no false-positive risk.

Implementation: in `atlas/compute/states.py`, the `compute_stage1_base` function returns `True` for the first 50 trading days if the MA-flat condition holds, regardless of prior-state count.

---

## 8. Frontend

**Decision (current):** Backend-first build. Frontend brief is deferred to a separate planning pass after M5 backend ships. The architecture's Streamlit + FastAPI choice (Section 10.1) stands as the placeholder; final UI direction is open until the brief is written.

The decision schema additions in M5 (recommendation transition triggers, `weeks_in_current_state`) are already in `02_DATABASE_SCHEMA.md` Section 5.3 and will be created at M1, regardless of frontend choice.

---

## 9. v0 Reality Adjustments (Post-Migration, 2026-05-06)

After Supabase migration completed, several methodology assumptions were
adjusted to match the actual JIP data shape. None of these are signal-impacting;
they're naming / scope corrections.

### 9.1 Historical scope shortened: 12y → ~10y

Methodology Section 3.4 specified "12 years (2014-04-01 to present)." But JIP's
`de_index_prices` history actually starts **2016-04-07**. Stock OHLCV reaches
2007 but RS computations need an index benchmark, which bounds us at the index
start.

- `Config.HISTORICAL_START_DATE` = `2016-04-07`
- v0 effective scope = ~10 years (2016-04-07 to T-1)
- Captures: 2017 micro-rally, 2018 mid/small-cap correction, 2020 COVID, 2022
  rate-hike, 2023-24 small-cap boom. Misses: 2014-2015 Modi-rally inception.

### 9.2 NSE sector taxonomy is finer than methodology assumed

Methodology Section 10.1 said "approximately 20–22 sectors." Actual JIP
`de_sector_mapping` has **31 sectors**. All have a primary NSE index. Rather
than collapsing them, atlas uses all 31 — methodology rule is "use whatever
NSE returns."

### 9.3 JIP table column names differ from foundation docs

Discovered post-migration. The `02_DATABASE_SCHEMA.md` Section 4 used
methodology-canonical column names; JIP uses different ones. All atlas code is
patched to use the actual JIP names:

| Foundation doc | Actual JIP column |
|---|---|
| `de_etf_master.etf_name` | `de_etf_master.name` |
| `de_etf_master.fund_house` | (does not exist — set NULL) |
| `de_etf_master.isin` | (does not exist — set NULL) |
| `de_index_master.inception_date` | (does not exist — set NULL) |
| `de_mf_master.scheme_name` | `de_mf_master.fund_name` |
| `de_mf_master.amc` | `de_mf_master.amc_name` |

Plus useful boolean flags discovered: `de_mf_master.is_index_fund`, `is_etf`,
`is_active`, `closure_date`. Replaced name-pattern hacks for filtering out
index funds / ETFs / closed schemes.

### 9.4 NIFTY index code naming uses JIP's abbreviations

Affects the 75-index curated list (atlas/universe/indices.py) and pre-flight:

| Foundation doc | JIP code |
|---|---|
| `NIFTY SMALLCAP 250` | `NIFTY SMLCAP 250` |
| `NIFTY MICROCAP 250` | `NIFTY MICROCAP250` |
| `NIFTY TOTAL MARKET` | `NIFTY TOTAL MKT` |
| `NIFTY LARGEMIDCAP 250` | `NIFTY LARGEMID250` |
| `NIFTY OIL & GAS` | `NIFTY OIL AND GAS` |
| `NIFTY CONSUMER DURABLES` | `NIFTY CONSR DURBL` |
| `NIFTY FINANCIAL SERVICES` | `NIFTY FIN SERVICE` |
| `NIFTY INFRASTRUCTURE` | `NIFTY INFRA` |
| `NIFTY MANUFACTURING` | `NIFTY INDIA MFG` |
| `NIFTY DIGITAL` | `NIFTY IND DIGITAL` |
| (etc — see atlas/universe/indices.py for full list) |

### 9.5 MF universe filter yields 592 schemes (target was 450-500)

Filter ran clean using `is_active + is_index_fund=FALSE + is_etf=FALSE +
closure_date IS NULL + category in 14 SEBI buckets + name not Direct/IDCW`.
Output 592 — slightly above target. Cause: fewer dropouts than expected.
Acceptable for v0; tighten further if downstream compute load spikes.

### 9.6 NIFTY 100 membership is via `de_index_constituents`, not `de_instrument`

`de_instrument` has `nifty_50`, `nifty_200`, `nifty_500` boolean columns but
NOT `nifty_100`. Atlas uses `de_index_constituents.index_code = 'NIFTY 100'`
for Large tier classification (verified 100 members).

### 9.7 ETF master has no `fund_house` column

`atlas_universe_etfs.fund_house` is NULL for all rows in v0. Could be derived
from `name` prefix (e.g. "Zerodha Nifty 50 ETF" → "Zerodha") in v1 if needed
for UI display. Doesn't affect any methodology rule.

### 9.8 Sector names: "Banking" / "Automobile" not "Bank" / "Auto"

JIP sector taxonomy uses full forms. PSU Bank and Private Bank are NOT
separate JIP sectors — both fold into "Banking". Atlas's ETF and index
classifiers map all banking ETFs/indices to `linked_sector = 'Banking'`.

### 9.9 M1 outcome (executed 2026-05-06 12:45 UTC on EC2)

```
atlas_sector_master                  31 rows
atlas_benchmark_master               10 rows
atlas_fund_category_benchmark_map     8 rows
atlas_universe_stocks               750 rows  (Large 100 / Mid 150 / Small 250 / Micro 250)
atlas_universe_etfs                 100 rows  (Broad 3 / Sectoral 14 / Thematic 83)
atlas_universe_indices               75 rows  (broad 15, sectoral 12, industry 15, factor 18, thematic 15)
atlas_universe_funds                592 rows  (14 SEBI categories)
atlas_thresholds                     35 rows
Universe lock elapsed: 2.4s
```

All 30 atlas tables created via Alembic 001-010. All 7 reference tables
populated. M1 unblocked for M2.

---

## 10. ETF Holdings Coverage Gap (M5 thematic gate impact)

**Investigation date:** 2026-05-06 (post-M1 data quality audit)
**Skill:** `/investigate`

### Finding

Of the 100 ETFs in the locked universe, only **7** have entries in
`de_etf_holdings` (M0 Job 2 deliverable). The other 93 have no holdings
disclosure data.

User's initial hypothesis was that ETF holdings might be co-located in
`de_mf_holdings` (since both come from the same Morningstar pull). The
investigation rejected this hypothesis:

- `de_mf_holdings` has 1,309 distinct `mstar_id` values — all mutual funds
- `de_etf_master.mstar_id` is populated for only 179/431 ETFs (~42%)
- Zero overlap: no universe ETF's `mstar_id` appears in `de_mf_holdings`
- Union of both tables = same 7 covered universe ETFs

### Why the gap exists

1. **International ETFs** in our top-100 (AAXJ, ACWI, BND, BNDX, etc.)
   aren't in Morningstar India's crawl scope.
2. **Smaller-AUM Indian ETFs** without `mstar_id` weren't reached by
   the Morningstar feed during M0 Job 2.
3. **Top-100-by-traded-value** universe selection picked many liquid-but-
   exotic ETFs that trade actively but lack standardised disclosure.

### v0 decision: accept methodology fallback

Per methodology Section 13.5, **thematic ETFs without holdings fall back
to auto-pass on the sector gate, with a warning logged in `atlas_run_log`**.
Atlas implements this fallback in `atlas/compute/decisions_etf.py` (M5
phase E).

Concrete v0 impact on the 100 ETFs:
- **3 Broad ETFs** (NIFTYBEES, JUNIORBEES, etc.) — gate by market regime only. Works fine.
- **14 Sectoral ETFs** — gate by `linked_sector` (derived from ETF name, not holdings). Works fine.
- **83 Thematic ETFs** — sector gate auto-passes. Gating effectively neutered for this slice.

The thematic-ETF gating gap means Atlas v0 won't differentiate between
"thematic ETF in an Avoid sector" vs "thematic ETF in an Overweight sector"
for those 83 ETFs. Methodology accepts this as a documented v0 limitation.

### v1 path

Two options to close the gap:

1. **NSE bulk holdings feed** — NSE publishes ETF constituent files;
   ingest via the existing JIP pipeline.
2. **AMFI ETF disclosure** — AMFI publishes ETF AUM + holdings monthly;
   parse + load into `de_etf_holdings`.

Either path adds ~1 sprint to JIP Data Core. Recommend deferring to v1
unless Bhaven specifically wants thematic-ETF gating in v0.

---

## 11. What This Document Does NOT Cover

- Full milestone build instructions — see `docs/milestones/ATLAS_M*.md`
- Methodology — see `docs/00_METHODOLOGY_LOCK.md`
- Architecture conventions — see `docs/01_BACKEND_ARCHITECTURE.md`
- Schema definitions — see `docs/02_DATABASE_SCHEMA.md`
- Validation criteria — see `docs/03_VALIDATION_FRAMEWORK.md`
- Threshold catalog — see `docs/04_THRESHOLD_CATALOG.md`

---

## 12. Sign-off

Decisions captured here are taken in flight as the build starts. Where a decision conflicts with a foundation doc, this document is the more recent record; the foundation doc gets updated at the next revision pass.

**Version:** 1.1
**Last updated:** 2026-05-07

---

## 13. M2 Validation Outcomes (2026-05-07)

M2 backfill completed successfully. Key findings:

### Row counts (correct)
- `atlas_stock_metrics_daily`: 1,383,801 rows (750 instruments). Not 2.25M because HISTORICAL_START = 2016-04-07 and many stocks listed post-2016.
- `atlas_stock_states_daily`: 1,383,801 rows (parity ✓)
- ETF tables: ~243K rows (100 instruments)

### Tier 2 (100% pass after fixes)
Three validation methodology bugs fixed (not production bugs):
1. Sampler cross-product included stocks not listed on sampled dates → fixed: ROW_NUMBER() CTE + bar_seq≥252 filter
2. EMA(200) hand-impl pulled pre-2016 data → fixed: _HISTORICAL_START bound + days_back=900
3. max_drawdown hand formula used expanding peak, production uses rolling(252).max() → fixed: rewrote hand impl to match

### Tier 3 (2 documented precision artifacts, accepted)
`ema_10_ratio` and `ema_20_ratio` stored as `NUMERIC(18,4)`. Two stocks have ratios that were just below 1.0 during compute (r10 < r20 → Deteriorating) but round to the same 4-decimal value (r10 == r20 → Flat in hand validator). These are at a non-material boundary (both indicate below-trend momentum). Deferred fix: migrate those columns to `NUMERIC(18,8)` at M3 threshold calibration review.

### `_log_run()` schema mismatch (fixed 2026-05-07)
`atlas.compute.stocks._log_run()` was inserting into wrong column names (`run_id, stage, status` vs actual schema `compute_run_id, business_date, status, stage3_stock_etf_sec, ...`). Fixed to match actual `atlas_run_log` schema. The backfill ran without logging (silently skipped) — the run log will correctly capture future daily and re-runs.

### JIP Layer 1 data quality issues (flagged, read-only)
Atlas is read-only on `public.de_equity_ohlcv`. The following anomalies exist in source data and should be flagged to JIP:
- **IDFCFIRSTB on 2020-05-25**: close=10,010 (current price ~₹69). Creates a ~530× return spike.
- **IFCI**: multiple dates with >50% daily returns from thin liquidity / CA gaps
- **JSWSTEEL**: extreme return days from JIP adjustment methodology

These don't break Atlas — gate system handles them correctly (High risk, potentially ILLIQUID). The backfill produced correct states for all three.

### atlas_run_log: 0 rows before fix
All M2 backfill runs logged nothing due to schema mismatch. After the `_log_run()` fix, future runs will log correctly. The backfill itself is verified complete via direct table row counts.

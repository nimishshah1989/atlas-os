# Atlas — Backend Architecture

**Document:** 01_BACKEND_ARCHITECTURE
**Status:** v0
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**References:** 00_METHODOLOGY_LOCK.md (source of truth for what the system computes)

---

## Purpose of This Document

This document specifies *how* the system is built — the architectural decisions, conventions, and rules that shape every milestone. It does not specify *what* gets computed (that's the methodology lock). It does not specify table column-by-column layouts (that's the schema document). It sits between them.

A new engineer reading this document plus the methodology lock should be able to understand: how the system hangs together, what conventions to follow, and what NOT to do. A milestone document then tells them what to build for that specific milestone.

---

## 1. Architectural Principles

These five commitments are non-negotiable. Architecture decisions inconsistent with any of them require explicit override discussion.

### 1.1 JIP Data Core is read-only

Atlas reads from the existing JIP Data Core (`de_*` tables in the `public` schema) but **never writes to it**. Atlas creates its own schema (`atlas`) and writes only there. JIP Data Core's structure, content, and refresh cadence are owned by the JIP team. Atlas treats it as an immutable upstream dependency.

If Atlas needs data that isn't in JIP Data Core, the request goes to the JIP team to add it. Atlas never bypasses by writing to `de_*` tables.

### 1.2 Three-layer architecture, one-way data flow

```
LAYER 3: COMPUTED          (atlas_*_metrics, atlas_*_states, atlas_*_decisions)
                                 ▲
                                 │ derived from
                                 │
LAYER 2: REFERENCE         (atlas_universe_*, atlas_*_master, atlas_sector_master)
                                 ▲
                                 │ derived from
                                 │
LAYER 1: RAW (READ-ONLY)   (de_equity_ohlcv, de_mf_nav_daily, de_index_prices, etc.)
                                 ▲
                                 │ ingested from
                                 │
EXTERNAL SOURCES           (NSE BHAVCopy, AMFI, Morningstar, etc.)
                            [owned by JIP team, not Atlas]
```

**Layer 1 (Raw):** JIP Data Core's `de_*` tables. Read-only from Atlas's perspective.

**Layer 2 (Reference):** Atlas's own master and mapping tables. Slow-changing. Locked at Atlas-M1 from current snapshots of JIP Data Core. ~3,000 rows total.

**Layer 3 (Computed):** Everything derived from Layers 1 and 2. Recomputed nightly. ~10 million rows total at v0 scale.

**One-direction flow:** Layer 3 reads from Layers 1 and 2. Layer 2 reads from Layer 1 (and JIP-owned external sources). Layer 1 is owned by JIP. **Computed never feeds back into Reference or Raw.**

### 1.3 Pre-computed, never live

Per Pillar 4 of the methodology lock: every metric, state, and aggregation is computed nightly and persisted. The serving layer (FastAPI) reads only from materialized Layer 3 tables. There is no business logic at request time.

The cost of a thin API is paid in clarity, testability, and predictable performance.

### 1.4 Idempotent and atomic

**Idempotent:** Every nightly run can be re-run without producing different results, given the same input data. Re-running yesterday's compute today produces the same Layer 3 rows.

**Atomic:** State writes for a given (instrument, date) succeed or fail as a unit. No partial state for any (instrument, date) tuple. Implementation: each milestone's compute step writes to a staging table, then swaps to the live table within a single transaction.

### 1.5 Stock is the atom (engineering corollary)

Every metric is computed at the most granular level possible (stock, ETF, fund — daily). Aggregations (sectors, market regime) are derived FROM these atomic metrics. Engineers should never compute a sector-level metric that cannot be reconciled to its constituent stock-level metrics. Cross-table consistency (Tier 4 validation) verifies this.

---

## 2. Database Topology

### 2.1 Connection Information

**Production RDS:**
- **Host:** `jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com`
- **Database:** `data_engine`
- **PostgreSQL version:** 16.9
- **Account:** `jhaveritech` AWS, ap-south-1 region

**Note:** The old PRD referenced `fie-db.c7osw6q6kwmw...` and database `fie_v3`. The M1 validation report (2026-05-03) confirmed the live host is `jip-data-engine` and the database is `data_engine`. **Atlas uses the live host. Old PRD references are stale.**

### 2.2 Schemas

| Schema | Contents | Atlas Permissions |
|---|---|---|
| `public` | All `de_*` tables (JIP Data Core) | SELECT only |
| `atlas` | All Atlas-created tables | full DDL + DML |

The `atlas` schema is created by Atlas-M1 and owned by Atlas. JIP-owned tables stay in `public`. There is no overlap.

### 2.3 Database Roles

Three roles for separation of concerns:

| Role | Permissions | Used By |
|---|---|---|
| `atlas_writer` | INSERT/UPDATE/DELETE on `atlas.*`; SELECT on `public.de_*` | Compute pipelines |
| `atlas_reader` | SELECT on `atlas.*` only | UI, FastAPI, ad-hoc queries |
| `atlas_admin` | DDL on `atlas.*`; SELECT on `public.de_*` | Migrations, schema changes |

UI never queries `public.de_*` directly. All UI data comes through Atlas's Layer 3.

### 2.4 Connection Pattern

- **Library:** SQLAlchemy with PostgreSQL dialect (`psycopg2` or `asyncpg` driver)
- **Connection string source:** Environment variable `ATLAS_DB_URL`. Never hardcoded.
- **Pooling:** Existing PgBouncer in front of RDS. Compute jobs use a dedicated pool.
- **Compute pattern:** Each pipeline acquires a connection, processes its work, releases. Long-held connections forbidden.

---

## 3. Naming Conventions

These conventions are mandatory. Deviations require migration overhead later — not worth it.

### 3.1 Table Naming

| Pattern | Example | Layer |
|---|---|---|
| `atlas_universe_<scope>` | `atlas_universe_stocks` | Reference (locked instrument lists) |
| `atlas_<scope>_master` | `atlas_sector_master` | Reference (slow-changing dimension tables) |
| `atlas_<scope>_metrics_<grain>` | `atlas_stock_metrics_daily` | Computed (numeric metric values) |
| `atlas_<scope>_states_<grain>` | `atlas_stock_states_daily` | Computed (categorical state labels) |
| `atlas_<scope>_decisions_<grain>` | `atlas_stock_decisions_daily` | Computed (decision outputs) |
| `atlas_<scope>_<thing>_<grain>` | `atlas_market_regime_daily` | Computed (single-row-per-grain things) |

Where:
- `<scope>` ∈ {stock, etf, fund, index, sector, market}
- `<grain>` ∈ {daily, monthly, weekly}

### 3.2 Column Naming

- **Casing:** `snake_case`. No abbreviations except universally-known: `rs`, `ema`, `atr`, `dma`, `vol`, `pct`, `id`.
- **Identifiers:** `instrument_id` for stocks/ETFs (UUID, references `de_instrument.id`); `mstar_id` for funds; `index_code` for NSE indices; `benchmark_code` for benchmarks.
- **Dates:** `date` for stocks/ETFs/indices/computed metrics; `nav_date` for funds; `as_of_date` for monthly snapshots; `effective_from`/`effective_to` for slowly-changing dimensions.
- **States:** `<primitive>_state` (e.g., `rs_state`, `momentum_state`, `risk_state`, `volume_state`).
- **Booleans:** Prefix `is_` or `has_` (e.g., `is_investable`, `has_history`).
- **Audit columns:** Every table has `created_at` (timestamptz) and `updated_at` (timestamptz). State tables additionally have `compute_run_id` for traceability.

### 3.3 Identifier Standards

Different table types use different canonical identifiers, reflecting upstream sources:

| Instrument Type | Canonical Identifier | Source Table |
|---|---|---|
| Equity / ETF | `instrument_id` (UUID) | `de_instrument.id` |
| Mutual fund | `mstar_id` (Morningstar ID, varchar) | `de_mf_master.mstar_id` |
| Index | `index_code` (NSE code, varchar) | `de_index_master.index_code` |
| Benchmark | `benchmark_code` (Atlas-defined varchar) | `atlas_benchmark_master.benchmark_code` |

Cross-table joins ALWAYS go through canonical identifiers. Symbol/ticker columns may be present for human-readability but are NEVER used as join keys (symbols change, IDs do not).

### 3.4 Numeric Type Standards

**No floats for money or returns.** Floats introduce precision drift over compounding calculations and fail audits.

| Field Type | PostgreSQL Type | Rationale |
|---|---|---|
| Price (OHLCV, NAV) | `NUMERIC(18,4)` | INR has 2 decimals; compute headroom matters for ratios |
| Returns / RS | `NUMERIC(10,4)` (decimal, not percent) | Allows >100% returns over multi-year compounding |
| Volume | `BIGINT` | Some stocks trade billions of shares cumulatively |
| Ratios (vol_ratio, effort_ratio) | `NUMERIC(10,4)` | Bounded but precise |
| Counts, ranks | `INTEGER` or `SMALLINT` | Self-explanatory |
| Quintile (1–5) | `SMALLINT` | Bounded |
| Percentages stored as decimal (0.0–1.0) | `NUMERIC(10,4)` | E.g., 0.6234 not 62.34% |
| State labels | `VARCHAR(32)` | Human-readable, indexable |

---

## 4. JIP Data Core — Tables Atlas Reads From

Atlas reads from these JIP tables. Any change to their schema by the JIP team requires an Atlas re-validation pass.

### 4.1 Raw OHLCV / NAV Sources

| JIP Table | Used For | Identifier | Date Column |
|---|---|---|---|
| `de_equity_ohlcv` | Stock prices (OHLCV) | `instrument_id` | `date` |
| `de_etf_ohlcv` | ETF prices (OHLCV) | `ticker` | `date` |
| `de_index_prices` | NSE index prices (OHLC) | `index_code` | `date` |
| `de_global_prices` | Gold (GOLDBEES), MSCI World, S&P 500 | `ticker` | `date` |
| `de_mf_nav_daily` | Mutual fund NAV (total return where available) | `mstar_id` | `nav_date` |

### 4.2 Reference / Master Sources

| JIP Table | Used For |
|---|---|
| `de_instrument` | Stock and ETF master, including `sector` and `industry` columns (NSE Industry Classification) |
| `de_index_master` | Index master metadata |
| `de_etf_master` | ETF master metadata |
| `de_mf_master` | Fund master, including `broad_category` and `category_name` |
| `de_index_constituents` | Current snapshot of index membership (single date — no history in v0) |
| `de_sector_mapping` | Mapping from JIP sector names to NSE primary/secondary indices |
| `de_trading_calendar` | Trading days, half-sessions, exchange identifiers |
| `de_corporate_actions` | Splits, bonuses, demergers, dividend events |

### 4.3 Holdings Sources

| JIP Table | Used For | Status |
|---|---|---|
| `de_mf_holdings` | Monthly mutual fund holdings disclosures (~838 schemes, ~230K rows) — feeds Lens 2 (composition) and Lens 3 (holdings quality) | Existing |
| `de_etf_holdings` | Monthly ETF holdings disclosures from Morningstar API — feeds M5 ETF investability sector gate for thematic ETFs | **Pending — JIP Data Core extension required** |

**The `de_etf_holdings` extension** — A small ingestion job in JIP Data Core that calls the Morningstar API (universe `q3zv6b817mp4fz0f`, which already includes ETFs per existing contract), filters for ETF instruments, parses the holdings section of each instrument's response, and writes to a dedicated `de_etf_holdings` table. Same disclosure cadence as mutual funds (monthly). Same data model.

**Why a separate table rather than co-mingling with `de_mf_holdings`:**
- `de_mf_holdings` is keyed by `mstar_id`; `de_etf_holdings` is keyed by `ticker` (matching `de_etf_master.ticker`, the canonical ETF identifier across JIP)
- Cleaner separation for downstream consumers — code that handles mutual funds vs ETFs can read from its own table without filter logic
- No risk of accidental row mixing between two different instrument types

**`de_etf_holdings` table definition (target schema for JIP Data Core extension):**

```sql
CREATE TABLE public.de_etf_holdings (
    ticker                 VARCHAR(32)     NOT NULL,    -- ETF ticker (matches de_etf_master.ticker)
    instrument_id          UUID            NOT NULL,    -- Underlying holding (matches de_instrument.instrument_id)
    weight                 NUMERIC(8,6)    NOT NULL,    -- Holding weight (decimal: 0.0512 = 5.12%)
    as_of_date             DATE            NOT NULL,    -- Portfolio disclosure date
    last_disclosed_date    DATE            NOT NULL,    -- When Morningstar received it
    created_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, instrument_id, as_of_date)
);

CREATE INDEX idx_de_etf_holdings_ticker_date ON public.de_etf_holdings (ticker, as_of_date DESC);
CREATE INDEX idx_de_etf_holdings_instrument ON public.de_etf_holdings (instrument_id);
```

**JIP Data Core ingestion responsibility (not Atlas's responsibility):**
1. Call Morningstar universe endpoint to enumerate instruments
2. Branch on instrument type — write fund holdings to `de_mf_holdings`, ETF holdings to `de_etf_holdings`
3. Handle edge cases: ETFs with sparse coverage in Morningstar (e.g., smaller AUM ETFs), ETFs returning top-N holdings only rather than full constituent breakdown
4. Run on the same monthly cadence as mutual fund holdings refresh

Atlas reads from `de_etf_holdings` the same way it reads from `de_mf_holdings` — read-only, no modification.

### 4.4 Existing Derived Tables (Atlas does NOT re-use)

JIP Data Core has some pre-derived tables that overlap with Atlas's compute scope:

| JIP Table | Why Atlas Does NOT Use It |
|---|---|
| `de_rs_scores`, `de_rs_daily_summary` | Different methodology, different windows |
| `de_sector_breadth_daily` | Uses different sector taxonomy and breadth definitions |
| `de_equity_technical_daily` | Different indicator set |
| `de_mf_derived_daily`, `de_mf_sector_exposure` | Different lens definitions |

**Rationale:** Atlas's methodology is locked. Re-using JIP-derived tables that compute different things creates ambiguity. Atlas computes its own derived metrics from Layer 1 raw data only. The existing JIP derived tables remain available to JIP-owned consumers; Atlas ignores them.

---

## 5. Compute Architecture

### 5.1 Tooling

| Component | Choice | Version | Rationale |
|---|---|---|---|
| Primary compute | **Polars** | ≥ 0.20 | 5–10× faster than pandas on rolling-window math; native lazy evaluation; Rust-backed |
| Fallback compute | **pandas** | ≥ 2.1 | Required by some indicator libraries (pandas-ta) |
| Technical indicators | **pandas-ta** | 0.3.14b | EMAs, RSI, ATR, McClellan — battle-tested; comprehensive; pure Python |
| Performance metrics | **empyrical** | 0.5.5 | Drawdown, Sortino, Sharpe — Quantopian's library, used in production for years |
| Statistical operations | **scipy** | ≥ 1.11 | Linear regression (`scipy.stats.linregress`), distribution functions |
| Numerical primitives | **NumPy** | ≥ 1.26 | Vectorized math; `np.select` for state classification |
| Database driver | **psycopg2** (sync) or **asyncpg** (async) | latest | Both production-grade; default `psycopg2` for v0 |
| ORM | **SQLAlchemy Core** (not ORM) | ≥ 2.0 | Lower overhead; explicit SQL; easier to optimize |
| Orchestration (v0) | cron + bash on EC2 | — | Sufficient for v0 scale |
| Orchestration (v1+) | Prefect or Airflow (TBD) | — | Not in v0 scope |

**Library version pinning:** All library versions are pinned in `pyproject.toml`. Version upgrades go through the validation re-run process (Section 5.5). No silent upgrades.

### 5.2 Compute Strategy

**Compute by instrument, not by date.** The natural way to write the math is "for each date, compute all stocks." The efficient way is "for each stock, load all its history, compute all its metrics in vectorized form, write all its rows in one batch." This is roughly 3–4× faster on full backfill.

**Materialize benchmark series once per run.** RS computation requires benchmark returns. Computing them inline 750 times wastes work. Atlas materializes a `_benchmark_returns_cache` working table at the start of each run — 9 benchmarks × 3,000 days = ~27,000 rows, computed once, joined many times.

**Batch writes.** Polars writes to PostgreSQL via `write_database` in 3,000-row chunks per stock, single transaction per chunk. Row-by-row INSERTs are forbidden.

**Indexes:**
- Every metric/state/decision table has primary key `(instrument_id, date)` (or appropriate identifier)
- Every metric/state/decision table has additional index on `(date, instrument_id)` for date-cross-section queries
- State tables have additional index on `(date, <state_column>)` for "find all Leaders on date X" queries
- Index storage cost: ~15% of table size; query speedup: 100×+

### 5.3 Pipeline Stages

A nightly run executes these stages in strict order:

```
Stage 1: PRE-CHECK
  - Verify connectivity to JIP Data Core
  - Verify previous run completed successfully
  - Check for new corporate actions (since last run)
  - Read trading calendar for today; abort if non-trading day

Stage 2: REFERENCE REFRESH (if needed)
  - Universe lock check (quarterly refresh: Jan/Apr/Jul/Oct first trading day)
  - Sector mapping refresh (rare; only if de_sector_mapping changed)
  - Benchmark master refresh (rare)

Stage 3: STOCK + ETF METRICS (Layer 3)
  - Pull T-1 OHLCV from de_equity_ohlcv, de_etf_ohlcv
  - Pre-classification gates (history, liquidity, adjusted-price, event-day)
  - Compute four primitives
  - Apply state classifications
  - Write atlas_stock_metrics_daily, atlas_stock_states_daily, atlas_etf_metrics_daily, atlas_etf_states_daily

Stage 4: INDEX METRICS (Layer 3)
  - Pull index prices from de_index_prices and de_global_prices
  - Compute returns, momentum, vol metrics
  - Write atlas_index_metrics_daily

Stage 5: SECTOR AGGREGATION (Layer 3)
  - Bottom-up aggregation from atlas_stock_metrics_daily and atlas_stock_states_daily
  - Top-down aggregation from atlas_index_metrics_daily (NSE sectoral indices)
  - Compute breadth measures
  - Apply sector state classification
  - Compute divergence flag
  - Write atlas_sector_metrics_daily, atlas_sector_states_daily

Stage 6: MARKET REGIME (Layer 3)
  - Compute breadth measures across full Nifty 500 universe
  - Compute trend and volatility inputs
  - Apply regime classification
  - Apply dislocation override check
  - Write atlas_market_regime_daily

Stage 7: MUTUAL FUND METRICS (Layer 3)
  - Pull T-1 NAV from de_mf_nav_daily
  - Compute Lens 1 (NAV behavior) — daily
  - If today is a holdings disclosure day:
      Refresh Lens 2 (composition) and Lens 3 (holdings) from de_mf_holdings
  - Apply state classifications
  - Write atlas_fund_metrics_daily, atlas_fund_lens_monthly, atlas_fund_states_daily

Stage 8: DECISION ENGINE (Layer 3)
  - Compute INVESTABLE flag for stocks, ETFs, funds
  - Compute entry triggers (TRANSITION, BREAKOUT)
  - Compute exit triggers (six parallel)
  - Compute position sizing
  - Write atlas_stock_decisions_daily, atlas_etf_decisions_daily, atlas_fund_decisions_daily

Stage 9: VALIDATION
  - Run Tier 1, 2, 3 checks per milestone
  - Cross-table consistency (Tier 4)
  - Pipeline timing snapshot
  - Write atlas_run_log entry

Stage 10: NOTIFICATION
  - Slack post to #atlas-alerts (success summary or failure escalation)
```

Each stage is independent. A failure in Stage N halts pipeline; Stages 1 to N-1 results are persisted. Re-run resumes from Stage N.

### 5.4 Compute Targets

| Operation | Target | Notes |
|---|---|---|
| Daily incremental (typical day) | < 8 minutes | Stages 3–8 dominate |
| Daily incremental (holdings disclosure day) | < 12 minutes | Stage 7 expands |
| Historical backfill (12 years), one-time | < 90 minutes | Run during off-hours |
| Single state-table query (filtered by today + tier) | < 100 ms | Indexed access |
| Sector heatmap query (90 days × ~20 sectors) | < 200 ms | Indexed access |
| Stock detail page (current state + 365d history) | < 300 ms | Indexed access |

Exceeding any target is a flag for optimization, not a build blocker. Validation Tier 4 monitors compute time as part of run health.

### 5.5 Calculation Library Discipline

**Mandatory rule:** All primitive numeric calculations use established Python libraries. No hand-coded formula implementations except at the state-classification layer.

This is a defense against the most insidious class of bug — silently-wrong numbers that look plausible. Off-by-one errors in rolling window boundaries, sign errors in returns, edge cases at series start, EMA seeding differences. These are precisely the bugs that battle-tested libraries have fixed once, for everyone.

**Library responsibility map:**

| Calculation | Library | Function |
|---|---|---|
| Returns (1d, 1w, 1m, 3m, 6m, 12m) | Polars | `pl.col("close").pct_change(periods=N)` |
| Cumulative returns | Polars | `pl.col("close") / pl.col("close").shift(N) - 1` |
| Simple Moving Average | pandas-ta | `ta.sma(close, length=N)` |
| Exponential Moving Average | pandas-ta | `ta.ema(close, length=N)` |
| Relative Strength Index (RSI) | pandas-ta | `ta.rsi(close, length=14)` |
| Average True Range (ATR) | pandas-ta | `ta.atr(high, low, close, length=21)` |
| Realized volatility (annualized) | NumPy | `returns.rolling(N).std() * np.sqrt(252)` |
| Downside deviation | empyrical | `ep.downside_risk(returns)` |
| Maximum drawdown | empyrical | `ep.max_drawdown(returns)` |
| Linear regression slope | scipy.stats | `linregress(x, y).slope` |
| McClellan Oscillator | pandas-ta + custom composition | `ta.ema(net_advances, 19) - ta.ema(net_advances, 39)` |
| Percentile rank (within group) | Polars | `pl.col("rs").rank("dense").over("tier") / pl.col("rs").count().over("tier")` |
| State classification | NumPy | `np.select(conditions, choices, default="...")` |

**Where custom code is permitted:**

1. **State classification logic** (Section 7 of methodology lock): the `np.select` rules that translate primitive values into state labels. This is where Atlas-specific logic lives.

2. **Aggregation logic** (sectors from stocks, market regime from market-wide breadth): market-cap weighting, breadth aggregations.

3. **Decision rules** (investability, entry triggers, exit triggers): logical AND/OR over states.

Outside these three layers, custom math is forbidden. If a needed primitive is missing from the library stack, the right answer is to add the library, not to hand-code the formula.

**Version pinning and upgrade discipline:**

- All library versions pinned in `pyproject.toml`
- Version upgrades require:
  1. Re-run of full historical backfill on a staging database
  2. Comparison of all primitive values against pre-upgrade baseline
  3. Tier 1 + Tier 2 validation passes
  4. Sign-off before merge to main
- Silent upgrades forbidden — `pip install -U` against the production environment is a deployment failure

**Cross-validation against external sources:**

For each primitive metric, validation Tier 1 verifies our library output matches at least one external source within tight tolerance:

- EMA values vs TradingView/charting platform values → match within 0.001
- RSI values vs published values → match within 0.01
- Realized volatility vs published index volatility → match within 1%

These are run automatically on every milestone and quarterly thereafter. Any drift triggers investigation before it becomes silent error.

### 5.6 Threshold-Driven Configuration

**Mandatory rule:** All numeric thresholds used in classification logic come from the `atlas_thresholds` database table. No hardcoded threshold values in code.

This is the architectural commitment that makes Atlas a tunable system rather than a fixed black box. The fund manager can change a threshold via the UI, and the entire 12-year history reclassifies accordingly — without code changes, without redeployment.

**The pattern:**

```python
# WRONG — hardcoded threshold
def classify_rs_state(p1w, p1m, p3m):
    if p1w >= 0.80 and p1m >= 0.80 and p3m >= 0.80:
        return "Leader"
    ...

# RIGHT — threshold-driven
def classify_rs_state(p1w, p1m, p3m, thresholds: dict):
    TOP = thresholds["rs_quintile_top"]
    if p1w >= TOP and p1m >= TOP and p3m >= TOP:
        return "Leader"
    ...
```

**Threshold loading happens once per run:**

```python
def load_thresholds(engine) -> dict:
    """
    Read all active thresholds from atlas_thresholds.
    Called once at the start of each compute pipeline run.
    Returns: {threshold_key: threshold_value} dict.
    """
    rows = pl.read_database(
        "SELECT threshold_key, threshold_value FROM atlas.atlas_thresholds WHERE is_active = TRUE",
        engine,
    )
    return dict(zip(rows["threshold_key"], rows["threshold_value"]))
```

The dict is passed through the call chain to every classifier function. Functions never look up thresholds independently — they receive them as parameters. This makes unit testing trivial (pass a synthetic dict).

**Boundaries — what's threshold-driven and what's not:**

Threshold-driven (lives in `atlas_thresholds`):
- Quintile cutoffs (RS classification)
- Risk state band boundaries
- Volume state ratios
- Sector participation percentages
- Market regime breadth percentages
- VIX cutoffs
- Mutual fund AUM percentages
- Decision proximity gates
- Liquidity threshold

Methodology-driven (NOT in `atlas_thresholds` — changing requires methodology revision):
- Time horizons (1W=5, 1M=21, 3M=63 trading days)
- Number of states per primitive
- Choice of which benchmarks to use
- State name labels
- Choice of EMA-ratio vs slope-σ for momentum
- Numéraire choices
- Sector taxonomy source

The principle: numbers within the methodology framework are tunable; the framework itself is methodology. Changing a quintile from 0.80 to 0.85 is tuning. Changing from "top quintile" classification to "top decile" classification is methodology.

**Re-classification workflow (per `04_THRESHOLD_CATALOG.md` Section 15):**

1. Fund manager edits threshold via UI → `atlas_thresholds` updated, `atlas_threshold_history` row added
2. Threshold change does NOT auto-trigger reclassification — fund manager must explicitly click "Apply & Reclassify"
3. Reclassification job:
   - Reads current thresholds from `atlas_thresholds`
   - For each (instrument, date) in `atlas_stock_metrics_daily`, applies state classifiers with new thresholds
   - Bulk overwrites `atlas_stock_states_daily`
   - Re-runs sector aggregation, market regime, decision engine
   - Logs reclassify run in `atlas_run_log` with `reclassify=TRUE` flag
4. Job is fast (~5 minutes) because primitive metrics don't recompute — only the classification of those metrics

**Why this matters operationally:**

Without threshold-driven configuration, a tuning request becomes a code change request. Engineering needs to find the threshold in source, update it, run tests, redeploy, re-execute the historical backfill. Days.

With threshold-driven configuration, a tuning request takes 30 seconds in the UI plus a 5-minute reclassification job. The fund manager owns their tuning.

**Validation Tier 4 includes a check:** every threshold in `atlas_thresholds` is referenced by at least one classifier function in code; no orphan thresholds. This catches the case where a threshold gets added to the database but never wired to any classifier.

---

## 6. Idempotence and Atomicity

### 6.1 Why Idempotence Matters

Failures happen. Network blips, AMFI delays, transient compute errors. The pipeline must be safe to re-run without producing different results given the same input data.

**Implementation patterns:**
- Every Layer 3 write uses `INSERT ... ON CONFLICT DO UPDATE` (PostgreSQL upsert)
- Primary key always includes `(instrument_id, date)` or equivalent — uniquely identifies the row
- Re-running a date overwrites that date's rows with fresh values
- No "running totals" or "incremental counters" that would diverge on re-run

### 6.2 Atomicity at the Date Level

For any given date, all of Atlas's Layer 3 tables either contain that date's rows OR they don't. Partial writes are forbidden.

**Implementation pattern:**

```sql
BEGIN;
INSERT INTO atlas_stock_metrics_daily (instrument_id, date, ...)
VALUES (...)
ON CONFLICT (instrument_id, date) DO UPDATE SET ...;
-- All rows for this date written

INSERT INTO atlas_stock_states_daily (instrument_id, date, ...)
VALUES (...)
ON CONFLICT (instrument_id, date) DO UPDATE SET ...;
-- All rows for this date written

COMMIT;
```

Either the COMMIT succeeds (full date written) or it rolls back (no date data). No middle ground.

### 6.3 Compute Run ID

Every nightly run is assigned a UUID `compute_run_id`. Every Layer 3 row written by that run is tagged with this ID. Allows:
- Tracing any state classification back to the run that produced it
- Identifying re-run impacts (which rows changed in the latest re-run vs. previous)
- Run-level rollback (delete all rows from a specific run if needed)

A separate table `atlas_run_log` records each run's metadata: start time, end time, stage timings, validation results, notes.

---

## 7. Error Handling and Logging

### 7.1 Logging Strategy

- **Format:** Structured JSON to stdout (parseable by log aggregators)
- **Levels:** DEBUG, INFO, WARNING, ERROR
- **Required fields:** `compute_run_id`, `stage`, `task`, `timestamp`, `level`, `message`
- **Optional fields:** `instrument_id`, `date`, `metric_name`, `error_type`
- **Aggregation:** One log file per nightly run, rotated weekly, archived to S3

### 7.2 Error Categories

| Error Type | Handling |
|---|---|
| Connectivity to JIP Data Core | Halt run; alert immediately |
| Source data anomaly (e.g., null values where forbidden) | Quarantine row; continue; alert if quarantine rate > 1% |
| Computation failure (single instrument) | Log, skip, continue; mark as `COMPUTE_FAILED` for that (instrument, date) |
| Computation failure (whole stage) | Halt run; alert immediately |
| Validation failure (Tier 1/2/3/4) | Halt run; alert; require human review |
| Disk / RDS errors | Halt run; alert; auto-retry once |

### 7.3 Quarantine Pattern

For source data issues that don't warrant halting the pipeline, problematic rows are written to a `_quarantine` table for the relevant scope:

- `atlas_stock_metrics_quarantine`
- `atlas_etf_metrics_quarantine`
- `atlas_fund_metrics_quarantine`

Each quarantine row carries: original input, error type, error message, run ID, timestamp. Daily summary posts quarantine count to Slack. Quarantine rows are NOT included in downstream Layer 3 outputs — they're pulled aside for human review.

### 7.4 Slack Integration

Single channel: `#atlas-alerts` (or as configured).

Posts:
- ✅ Daily success summary (compute time, rows written, validation pass)
- ⚠️ Quarantine threshold breach (>1% rows quarantined in any table)
- ❌ Stage failure (which stage, error type, traceback)
- ❌ Validation failure (which tier, which check, expected vs. actual)

---

## 8. Validation Framework

Atlas uses a five-tier validation framework. Detailed criteria per tier live in `03_VALIDATION_FRAMEWORK.md`. This section establishes the architecture.

| Tier | What It Validates | When It Runs |
|---|---|---|
| Tier 1 | Raw data integrity from JIP Data Core | Atlas-M1 (one-time) and on JIP refresh |
| Tier 2 | Computed metrics vs. hand-computed values | Every milestone DoD |
| Tier 3 | State classifications vs. hand-applied rules | Every milestone DoD |
| Tier 4 | Cross-table consistency (aggregations match constituents) | Every milestone DoD; nightly |
| Tier 5 | Daily monitoring (run health, anomaly detection) | Every nightly run |

**Every milestone produces a validation report** committed to the repo as `validation_<milestone>_<date>.md`. Without a passing report, the milestone is not marked complete.

**Tier 4 deserves special note.** It catches integration bugs that the lower tiers miss — for example: stock RS values are individually correct (Tier 2 passes), state classifications are individually correct (Tier 3 passes), but the sector-level aggregation drifts because of a market-cap-weight calculation bug. Tier 4 is the cross-check. Specific rules:
- Sector RS = market-cap-weighted average of constituent stock RSs (within 0.5%)
- Count of stocks classified Leader on date X = count returned by direct query of state table
- Sum of fund AUM allocated to "Aligned" sectors = lens-2 numerator

---

## 9. Storage Estimates (12-Year Scope)

### 9.1 Per-Table Estimates

| Table | Approximate Rows | Approximate Size |
|---|---|---|
| `atlas_stock_metrics_daily` | 750 × 3,000 = 2.25M | ~1.6 GB |
| `atlas_stock_states_daily` | 2.25M | ~180 MB |
| `atlas_stock_decisions_daily` | 2.25M | ~150 MB |
| `atlas_etf_metrics_daily` | 100 × 2,500 = 250K | ~150 MB |
| `atlas_etf_states_daily` | 250K | ~20 MB |
| `atlas_etf_decisions_daily` | 250K | ~18 MB |
| `atlas_index_metrics_daily` | 75 × 3,000 = 225K | ~90 MB |
| `atlas_sector_metrics_daily` | ~22 × 3,000 = 66K | ~32 MB |
| `atlas_sector_states_daily` | 66K | ~6 MB |
| `atlas_market_regime_daily` | 3,000 | ~1 MB |
| `atlas_fund_metrics_daily` | 400 × 3,000 = 1.2M | ~480 MB |
| `atlas_fund_lens_monthly` | 400 × 144 = 58K | ~25 MB |
| `atlas_fund_states_daily` | 1.2M | ~95 MB |
| `atlas_fund_decisions_daily` | 1.2M | ~85 MB |
| Reference tables (universe, masters) | ~3,000 | <50 MB |
| Audit / log tables | varies | ~200 MB |

**Total Layer 3 storage: ~3.2 GB plus ~500 MB indexes ≈ 3.7 GB.**

Comfortably within RDS capacity. No partitioning needed for v0.

### 9.2 Compute Run-Time Estimates

| Phase | Estimated Time |
|---|---|
| Stage 3 (Stock + ETF metrics) — daily incremental | 2–3 min |
| Stage 5 (Sector aggregation) — daily | 30–45 sec |
| Stage 6 (Market regime) — daily | 15–30 sec |
| Stage 7 (Fund metrics) — daily | 1–2 min |
| Stage 7 (Fund metrics) — holdings disclosure day | 4–6 min additional |
| Stage 8 (Decision engine) — daily | 30 sec |
| Stage 9 (Validation) — daily | 30–60 sec |
| **Total typical day** | **5–7 min** |
| **Total holdings disclosure day** | **9–12 min** |

Both within the 10-minute target most days, slightly over on disclosure days.

**Historical backfill (12 years, one-time):** ~60–90 minutes total. This is the slowest single run; subsequent daily runs are incremental.

---

## 10. Serving Architecture

### 10.1 The Stack

```
Streamlit UI ──HTTP──> FastAPI ──SQL──> PostgreSQL (atlas schema, Layer 3 only)
```

- **Streamlit** for v0 UI (rapid development, fund-manager-grade visualizations)
- **FastAPI** as a thin serving layer (no business logic, just parameterized SELECTs)
- **PostgreSQL** as the data store

### 10.2 The API Layer is Thin by Design

Every FastAPI endpoint is essentially a parameterized SQL query against a Layer 3 table. There is no business logic in the API. Examples:

```python
@app.get("/stock/{instrument_id}/state/{date}")
def stock_state(instrument_id: UUID, date: date):
    return db.execute(
        "SELECT * FROM atlas.atlas_stock_states_daily "
        "WHERE instrument_id = :id AND date = :d",
        {"id": instrument_id, "d": date}
    ).fetchone()
```

The endpoint does not compute states. It does not interpret states. It returns what's in the table.

**Why:** Predictable performance, easy debugging, separation of concerns. If a bug appears, we know exactly which layer to look at — the compute (yesterday) or the serving (today).

### 10.3 Caching

v0 does not implement application-level caching. PostgreSQL's query plan cache and shared buffers are sufficient at v0 scale. Caching is a v1 optimization if and only if measured queries exceed performance targets.

---

## 11. Repository Structure

```
atlas-backend/
├── README.md
├── pyproject.toml                  # Polars, SQLAlchemy, FastAPI, etc.
├── .env.example                    # ATLAS_DB_URL placeholder
├── docs/
│   ├── 00_METHODOLOGY_LOCK.md
│   ├── 01_BACKEND_ARCHITECTURE.md
│   ├── 02_DATABASE_SCHEMA.md
│   ├── 03_VALIDATION_FRAMEWORK.md
│   ├── milestones/
│   │   ├── ATLAS_M1_SCHEMA_AND_REFERENCE.md
│   │   ├── ATLAS_M2_STOCK_ETF_METRICS.md
│   │   ├── ATLAS_M3_SECTOR_AND_MARKET.md
│   │   ├── ATLAS_M4_MUTUAL_FUND_LENSES.md
│   │   └── ATLAS_M5_DECISION_ENGINE.md
│   └── reference/
│       ├── jip_data_core_inventory.md
│       └── glossary.md
├── atlas/
│   ├── __init__.py
│   ├── config.py                   # Connection settings, env loading
│   ├── db.py                       # SQLAlchemy engine, session helpers
│   ├── universe/
│   │   └── lock.py                 # Universe locking logic (Atlas-M1)
│   ├── compute/
│   │   ├── primitives.py           # RS, RS Momentum, Risk, Volume math
│   │   ├── states.py               # State classification (np.select rules)
│   │   ├── stocks.py               # Stock metric pipeline
│   │   ├── etfs.py                 # ETF metric pipeline
│   │   ├── indices.py              # Index metric pipeline
│   │   ├── sectors.py              # Sector aggregation pipeline
│   │   ├── regime.py               # Market regime classification
│   │   ├── funds.py                # Fund three-lens pipeline
│   │   └── decisions.py            # Decision engine
│   ├── validation/
│   │   ├── tier1_raw.py
│   │   ├── tier2_metrics.py
│   │   ├── tier3_states.py
│   │   ├── tier4_consistency.py
│   │   └── tier5_monitoring.py
│   ├── orchestration/
│   │   ├── pipeline.py             # Main pipeline runner
│   │   ├── stages.py               # Individual stage definitions
│   │   └── slack.py                # Notifications
│   └── api/
│       ├── main.py                 # FastAPI app
│       ├── routes/
│       │   ├── stocks.py
│       │   ├── etfs.py
│       │   ├── funds.py
│       │   ├── sectors.py
│       │   └── regime.py
│       └── models.py               # Pydantic models for responses
├── ui/
│   └── app.py                      # Streamlit application
├── migrations/
│   ├── 001_create_atlas_schema.sql
│   ├── 002_create_universe_tables.sql
│   ├── 003_create_metrics_tables.sql
│   └── ...                         # One migration per schema change
├── tests/
│   ├── unit/
│   ├── integration/
│   └── validation/
└── scripts/
    ├── backfill.sh
    ├── nightly.sh
    └── healthcheck.sh
```

---

## 12. Operational Notes

### 12.1 Deployment Target

- **Compute:** Existing t3.large EC2 (2 vCPU, 8 GB RAM, ap-south-1)
- **Storage:** Existing RDS instance
- **Cron schedule:** 2:00 AM IST nightly (after market close + AMFI publication window)
- **Orchestration:** bash scripts via cron (v0); Prefect/Airflow consideration for v1+

### 12.2 Environment Tiers

| Environment | Purpose | Database |
|---|---|---|
| Production | Live nightly runs feeding the UI | `data_engine` on `jip-data-engine` RDS |
| Development | Engineer's local workspace | Local PostgreSQL with sample data subset |
| Staging | Optional pre-prod for major changes (v1+) | Separate RDS instance (not in v0) |

v0 ships with Production and Development only. Staging is a v1 consideration.

### 12.3 Backup and Recovery

JIP Data Core's existing RDS backup policy applies (Atlas inherits, doesn't manage). Atlas-specific backups:
- Schema-level pg_dump of `atlas` schema, daily, retained 30 days
- Pre-deployment dump before any migration that alters table structure

Recovery from a corrupted Layer 3 state: re-run the full historical backfill (~90 minutes). Layer 3 is fully reproducible from Layer 1 + reference tables, by design.

### 12.4 Schema Migrations

Every schema change ships as a numbered SQL migration in `migrations/`. Forward-only. Migrations run during deployment, before pipeline restart. Rollback strategy: each migration has a corresponding `down` script committed alongside (manual rollback only — no auto-revert).

---

## 13. What This Document Does NOT Cover

- **Specific table column layouts** — see `02_DATABASE_SCHEMA.md`
- **Specific milestone build instructions** — see `milestones/ATLAS_M*.md`
- **Validation criteria detail** — see `03_VALIDATION_FRAMEWORK.md`
- **What gets computed (formulas, thresholds)** — see `00_METHODOLOGY_LOCK.md`
- **Frontend implementation** — separate frontend spec, post-board

---

## 14. Open Questions

These are deliberately listed as open. Decisions pending:

1. **Async vs. sync database driver** — `psycopg2` (proven) vs. `asyncpg` (modern). Default: `psycopg2` for v0 unless concurrency demands force change.

2. **Dedicated EC2 for Atlas vs. shared with JIP** — For v0, share existing EC2. Migrate to dedicated instance only if compute contention emerges.

3. **Slack channel naming** — `#atlas-alerts` proposed. Confirm with team before deployment.

---

**Document version:** 1.0
**Last updated:** 2026-05-04
**Next review:** After Atlas-M1 completion, prior to Atlas-M2 start

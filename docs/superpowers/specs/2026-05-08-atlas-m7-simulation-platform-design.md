# Atlas M7 — Simulation Platform Design

**Date:** 2026-05-08
**Milestone:** M7 — Strategy Simulation & Auto-Optimization
**Status:** Approved for implementation planning
**Depends on:** M6 frontend (in flight) — M7 adds routes to the same Next.js app

---

## 1. Purpose

Atlas M6 tells the FM what the signals say today. Atlas M7 closes the feedback loop: the system tests its own rules systematically, surfaces which threshold configurations produce the best regime-adjusted alpha, and lets the FM promote winning configurations back into Atlas's production thresholds.

Three subsystems, one shared infrastructure core:

1. **Strategy Engine** — 15 parallel paper trading strategies (5 archetypes × 3 instrument tiers). Runs nightly after Atlas compute. FM watches which strategies earn money.
2. **Custom Portfolio Builder** — FM designs a portfolio, backtests it against historical Atlas signals, then starts paper trading it.
3. **Auto-Optimizer** — Optuna-based Bayesian search finds the best threshold configuration per regime. FM approves → thresholds promoted to Atlas production.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Atlas M7 — module layout                     │
│                                                                   │
│  atlas/simulation/                                               │
│  ├── core/                                                        │
│  │   ├── signal_adapter.py   ← JIP prices + Atlas signals        │
│  │   ├── paper_trader.py     ← DB-backed nightly state machine   │
│  │   └── metrics.py          ← empyrical + regime-split P&L      │
│  ├── strategies/                                                  │
│  │   ├── configs/*.yaml      ← 15 strategy configs               │
│  │   ├── loader.py           ← YAML → StrategyConfig dataclass   │
│  │   └── runner.py           ← nightly: apply all, update DB     │
│  ├── backtest/                                                    │
│  │   ├── engine.py           ← vectorbt Portfolio.from_signals() │
│  │   ├── walk_forward.py     ← rolling 6M train / 3M test        │
│  │   └── report.py           ← Sharpe, drawdown, alpha output    │
│  ├── custom/                                                      │
│  │   ├── builder.py          ← FM portfolio → validation + sizing│
│  │   └── portfolio.py        ← custom portfolio state management │
│  └── optimizer/                                                   │
│      ├── regime_optimizer.py ← Optuna study per regime           │
│      └── results.py          ← results + param importance → DB   │
│                                                                   │
│  Reads from: atlas.* (signals) + de_* (JIP prices)              │
│  Writes to:  atlas.strategy_* (8 new tables via Alembic 013-020) │
└─────────────────────────────────────────────────────────────────┘

Data flow:
  JIP de_ohlcv_daily            ──┐
  JIP de_mf_nav_history         ──┤── signal_adapter.py ──► SignalMatrix
  atlas.atlas_stock_decisions_daily ──┤   (prices + entry/exit signals aligned)
  atlas.atlas_etf_decisions_daily   ──┤
  atlas.atlas_fund_decisions_daily  ──┘

  SignalMatrix ──► backtest/engine.py ──► atlas.strategy_backtest_results
             └──► walk_forward.py   ──► Optuna scoring (OOS windows only)

  atlas.atlas_stock_decisions_daily  ──► paper_trader.py ──► atlas.strategy_paper_portfolios
  atlas.atlas_etf_decisions_daily   ──┘                  └──► atlas.strategy_paper_trades
  atlas.atlas_fund_decisions_daily  ──┘                  └──► atlas.strategy_paper_performance

  atlas.strategy_paper_performance ──► metrics.py ──► regime-split analytics
  atlas.strategy_paper_portfolios  ──► overlap math ──► atlas.strategy_overlap_daily

  Optuna study ──► atlas.strategy_optimization_runs ──► FM review queue
  FM approves  ──► atlas.atlas_thresholds.threshold_value (existing, migration 007)
               └──► atlas.atlas_threshold_history: old_value/new_value/change_reason (migration 007)
```

---

## 3. Strategy Architecture

### Instrument Tiers

| Tier | Instruments | Risk Profile | Strategy Count |
|------|------------|--------------|----------------|
| Stocks-only | `atlas_universe_stocks` | Aggressive | 5 |
| Stocks+ETF | `atlas_universe_stocks` + `atlas_universe_etfs` | Moderate | 5 |
| MF-only | `atlas_universe_funds` | Passive | 5 |

### 15 Strategies

**Stocks-only (aggressive):**
1. `stocks_momentum_aggressive` — RS ≥65, Leader state only, pause in Risk-Off
2. `stocks_momentum_moderate` — RS ≥55, Leader+Strong, scale down in Risk-Off
3. `stocks_momentum_conservative` — RS ≥50, all positive states, regime-scaled sizing
4. `stocks_sector_rotation_concentrated` — top 2 sectors by breadth, equal weight within sector
5. `stocks_sector_rotation_diversified` — top 4 sectors by breadth, inverse concentration weighting

**Stocks+ETF (moderate):**
6. `blend_momentum_60_40` — 60% stocks (Leader RS), 40% ETFs (Leader/Strong)
7. `blend_balanced_50_50` — 50/50, momentum-weighted within each instrument type
8. `blend_etf_led` — 70% sectoral/broad ETFs, 30% stocks (top RS within linked sectors)
9. `blend_defensive` — Risk gate priority: only Risk-Low/Normal stocks + defensive ETFs
10. `blend_sector_rotation_etf` — sector rotation signals from stocks drive ETF selection

**MF-only (passive):**
11. `fund_l1_dominant` — NAV lens 60%, composition 25%, holdings 15%
12. `fund_l2_dominant` — Composition lens 50%, NAV 30%, holdings 20%
13. `fund_l3_dominant` — Holdings quality 50%, NAV 30%, composition 20%
14. `fund_balanced` — Equal-weighted three-lens aggregation
15. `fund_defensive` — Only Recommended funds, avoid High-Risk categories in Risk-Off

### Strategy Config Schema (YAML)

```yaml
strategy:
  id: stocks_momentum_aggressive
  name: "Momentum Aggressive (Stocks)"
  tier: stocks_only            # stocks_only | stocks_etf | mf_only
  archetype: momentum_pure
  variant: aggressive
  # Overrides atlas/universe/thresholds.py defaults (only stated keys are overridden;
  # all 35 keys in thresholds.py are valid; defaults from atlas.atlas_thresholds.threshold_value)
  threshold_overrides:
    rs_quintile_top: 0.85      # default: 0.80 (top-quintile cutoff for Leader classification)
    rs_quintile_bottom: 0.15   # default: 0.20
  # state_filter maps to atlas_stock_states_daily.rs_state + atlas_stock_decisions_daily.is_investable
  # Valid values: leader (rs_state='Leader'), strong (rs_state IN ('Leader','Strong')),
  #               emerging (rs_state IN ('Leader','Strong','Emerging')), investable (is_investable=TRUE)
  state_filter: [leader]
  regime_stance: pause_risk_off  # see regime_stance semantics below
  position_sizing: rs_proportional  # rs_proportional | equal_weight | regime_scaled
  max_positions: 20
  max_sector_pct: 40.0
  rebalance_trigger: signal_change  # signal_change | weekly | monthly
```

### Strategy Config Seeding

`strategies/loader.py` exposes `populate_strategy_configs(engine=None) → int` — mirrors `atlas/universe/thresholds.py:populate_thresholds()` exactly. Called by the deploy runbook after each Alembic migration run (same cadence as `populate_thresholds`).

```python
def populate_strategy_configs(engine: Engine | None = None) -> int:
    """Seed atlas.strategy_configs from configs/*.yaml. Idempotent.

    ON CONFLICT (name) DO UPDATE SET config=EXCLUDED.config,
    tier=EXCLUDED.tier, archetype=EXCLUDED.archetype,
    variant=EXCLUDED.variant, updated_at=NOW().
    Does NOT reset is_active — FM may have deactivated a strategy.
    Returns count of configs upserted (always 15 on a clean run).
    """
    eng = engine or get_engine()
    configs_dir = Path(__file__).parent / "configs"
    yamls = sorted(configs_dir.glob("*.yaml"))
    if len(yamls) != 15:
        raise AssertionError(f"Expected 15 strategy YAMLs, found {len(yamls)}")
    upserted = 0
    with eng.begin() as conn:
        for yml in yamls:
            cfg = yaml.safe_load(yml.read_text())["strategy"]
            conn.execute(insert_strategy_sql, {...})
            upserted += 1
    log.info("strategy_configs_seeded", count=upserted)
    return upserted
```

Deploy sequence: `alembic upgrade head` → `populate_thresholds()` → `populate_strategy_configs()`. The 15 YAML files in `atlas/simulation/strategies/configs/` are the source of truth; `atlas.strategy_configs` is the runtime copy. Re-running is safe (idempotent upsert).

### Regime Stance Semantics

| Value | On Risk-Off entry | Existing positions | New entries |
|-------|-------------------|--------------------|-------------|
| `pause_risk_off` | Halt all new entries; hold existing positions until exit triggers fire | Held (exit triggers still apply) | Blocked |
| `scale_risk_off` | Apply regime multiplier (0.4× for Risk-Off) to target sizes; trim positions toward scaled size | Reduced proportionally | Allowed at reduced size |
| `hold_risk_off` | No behavioral change — treat Risk-Off same as Risk-On | Unchanged | Allowed at full size |

---

## 4. Infrastructure Core

### 4.1 signal_adapter.py — The Architectural Linchpin

Bridges two DB schemas: JIP price data + Atlas signals.

**JIP price sources (same Supabase Postgres, different schema):**
- Stocks/ETFs: `de_ohlcv_daily.close` (join on `instrument_id` and `date`)
- Funds: `de_mf_nav_history.nav` (join on `instrument_id` and `date`)

**Key design decisions:**
- Instruments not in Atlas universe at a given date → zero signals (never fabricated)
- Suspended states (`INSUFFICIENT_HISTORY`, `DISLOCATION_SUSPENDED`) → treated as exit signal
- Missing JIP price data → instrument excluded from that window, logged with `structlog` (not silently skipped)
- All instruments NaN-padded to common date index; vectorbt handles sparse arrays natively

**Staleness guard (pre-flight, before any paper trading run):**
```python
# Sync pattern — matches open_compute_session() in atlas/compute/_session.py
from sqlalchemy import text

# Abort if JIP data hasn't landed yet for today
with open_compute_session(engine) as conn:
    jip_max_date = conn.execute(
        text("SELECT MAX(date) FROM de_ohlcv_daily")
    ).scalar()
if jip_max_date < today:
    raise StaleJIPDataError(
        f"JIP data last updated {jip_max_date}, expected {today}. "
        "Aborting paper trading run — will retry tomorrow."
    )
```
This check runs before the nightly paper trader starts. Writes a new row to `atlas_run_log` with `status='FAILED'`, `failure_stage='simulation_preflight'`, `failure_message` = the error string. (`atlas_run_log` has one row per compute run, not one per stage — this is a full run-log row with all other stage columns as NULL.)

**Output:**
```python
@dataclass
class SignalMatrix:
    prices: np.ndarray    # shape (n_dates, n_instruments), float64
    entries: np.ndarray   # shape (n_dates, n_instruments), bool
    exits: np.ndarray     # shape (n_dates, n_instruments), bool
    dates: pd.DatetimeIndex
    instruments: list[str]

    def to_vectorbt(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self.prices, self.entries, self.exits
```

### 4.2 Backtest Engine (vectorbt)

**Python/library compatibility note:** vectorbt 0.26.x is confirmed working on **Python 3.11**. It has known issues with NumPy 2.x on Python 3.12. This module must be deployed on Python 3.11. If the runtime is 3.12, check vectorbt's release notes for a compatible version before reaching for an alternative — the `bt` library is NOT a drop-in; it uses a different API (`bt.Strategy`/`bt.Backtest.run()` vs `vbt.Portfolio.from_signals()`). If a swap is necessary, it requires an adapter layer that is out of scope for M7.

```python
pf = vbt.Portfolio.from_signals(
    close=signal_matrix.prices,       # (n_dates, n_instruments)
    entries=signal_matrix.entries,    # boolean array
    exits=signal_matrix.exits,        # boolean array
    size=position_size_array,         # from strategy config sizing rule
    size_type='percent',
    init_cash=10_000_000,             # ₹1 crore notional (paper)
    fees=0.0015,                      # 15 bps per trade leg (realistic Indian delivery:
                                      # ~10 bps brokerage + STT + exchange fees)
                                      # vectorbt applies this on EACH leg (buy and sell)
                                      # effective round-trip: ~30 bps
    freq='1D',
)
```

### 4.3 Walk-Forward Validation

- Window: 6M train / 3M test, slide by 1M
- **Minimum data guard:** `walk_forward.py` raises `InsufficientHistoryError` if `(end_date - start_date).days < 365`. This fires at both call-time and pre-flight. Surface to FM as: "Insufficient historical data for walk-forward validation — need at least 12 months of Atlas signals."
- Optuna scores trials on **out-of-sample (OOS) test windows only**
- Walk-forward boundary: most recent 3M is always held out as active test window; paper trading begins from today

**Available windows with 12M of signals:**
Signal history of 12M → **4 OOS windows** (formula: (total_months - train_months - test_months) / slide_months + 1 = (12 - 6 - 3) / 1 + 1 = 4). With 18M → **10 OOS windows**. With slide=1M and test=3M, **consecutive OOS windows overlap by 2 months** (window 1: test months 7-9, window 2: months 8-10). This means Optuna trial scores are not fully independent — a strong month that appears in 3 windows contributes to 3 scores. Optuna's TPE sampler treats each trial's mean OOS Sharpe as a single objective without awareness of this serial correlation. Practical mitigation: `walk_forward.py` raises `InsufficientHistoryError` if `(end_date - start_date).days < 547` (≈18M). This yields ~10 OOS windows and materially dilutes single-month outlier effects. Require 18M of Atlas signal history before enabling the optimizer. More history = more reliable Optuna scoring.

### 4.4 Paper Trading State Machine (nightly, **sync**, separate from vectorbt)

`paper_trader.py` is **synchronous**, matching `atlas/compute/_session.py` conventions (psycopg2 + `open_compute_session()` context manager — no asyncpg, no asyncio). DB reads use SQLAlchemy `text()` with `conn.execute()`. Bulk writes use `execute_values` from `atlas.compute._session`. There is no performance reason for async here — paper trading is a nightly batch, not a web handler. All code examples in this section use sync patterns.

**Preflight: Atlas decisions existence check (runs before position processing):**
```python
with open_compute_session(engine) as conn:
    decisions_today = conn.execute(
        text("SELECT COUNT(*) FROM atlas.atlas_stock_decisions_daily WHERE date = :d"),
        {"d": today}
    ).scalar()
if decisions_today == 0:
    raise MissingAtlasDecisionsError(
        f"No stock decisions found for {today} — Atlas compute may have failed. "
        "Aborting paper trading run."
    )
```
Same check applies for ETF decisions and fund decisions (if strategy tier includes them).

**Cold-start policy (first night of operation):**
Start with zero holdings for all 15 strategies. Apply entry signals from today's Atlas decisions as if starting fresh. No seeding from backtest final state — backtest portfolios reflect historical conditions that don't match today's market.

**Nightly flow:**
```
Pre-flight: staleness check (Section 4.1) — abort if JIP data not current
  ↓
Atlas compute completes (existing pipeline)
  ↓
strategy runner triggers
  ↓
For each of 15 strategy configs:
  1. Load current holdings from atlas.strategy_paper_portfolios
     (empty array on first run — cold start)
  2. Fetch today's Atlas decisions for strategy's instrument universe
  3. Apply threshold_overrides from strategy config (re-evaluate state_filter
     by joining atlas_stock_states_daily + atlas_stock_decisions_daily)
  4. Determine:
       - Stocks/ETF entries: (transition_trigger OR breakout_trigger) AND (rs_state matches state_filter)
         [migration 006 column names: atlas_stock_decisions_daily.transition_trigger + .breakout_trigger]
       - Fund entries: entry_trigger = TRUE AND fund decision is in target lens tier
         [migration 006 column names: atlas_fund_decisions_daily.entry_trigger]
       - Exits (stocks/ETF): any of six exit booleans = TRUE — priority order:
         exit_market_riskoff > exit_rs_deteriorate >
         exit_momentum_collapse > exit_volume_distrib >
         exit_sector_avoid > exit_stop_loss;
         highest-priority active exit recorded in signal_type field of paper_trade row
       - Fund exits: exit_trigger = TRUE (column: atlas_fund_decisions_daily.exit_trigger)
                size adjustments (regime_stance logic applied here)
  5. Write trades to atlas.strategy_paper_trades (with signal_type that fired)
  6. Update atlas.strategy_paper_portfolios (current holdings)
  7. Fetch today's close from de_ohlcv_daily / de_mf_nav_history
  8. Calculate daily P&L + today's regime → atlas.strategy_paper_performance
  ↓
Calculate Jaccard overlap for all 15×15 strategy pairs (set intersection on instruments)
  → atlas.strategy_overlap_daily
```

### 4.4.1 Paper Trader Decomposition (testability requirement)

`paper_trader.py` must expose discrete, unit-testable functions rather than one monolithic nightly pass:

```python
# atlas/simulation/core/paper_trader.py

def load_current_holdings(conn, strategy_id: UUID) -> dict[str, Holding]:
    """Read current atlas.strategy_paper_portfolios for one strategy."""

def fetch_decisions(conn, tier: str, date: date) -> pd.DataFrame:
    """One DB call per tier (stocks/ETF/fund), cached across strategies of same tier."""
    # Called ONCE per tier per night — not 15 times.
    # Returns full decision universe for that tier on `date`.

def apply_strategy_filter(
    decisions: pd.DataFrame,
    config: StrategyConfig,
    threshold_overrides: dict[str, float],
) -> tuple[set[str], set[str]]:
    """Pure function: decisions + config → (entry_set, exit_set). No DB calls.
    Applies threshold_overrides in-memory. Fully testable with mocked DataFrames.
    """

def compute_trades(
    current_holdings: dict[str, Holding],
    entries: set[str],
    exits: set[str],
    regime: str,
    config: StrategyConfig,
) -> list[Trade]:
    """Pure function: positions + signals + regime → trade list. No DB calls."""

def write_trades(conn, trades: list[Trade], strategy_id: UUID, date: date) -> None:
    """Bulk-insert to atlas.strategy_paper_trades via execute_values."""

def update_holdings(conn, trades: list[Trade], strategy_id: UUID) -> None:
    """Upsert to atlas.strategy_paper_portfolios."""

def record_daily_performance(conn, strategy_id: UUID, date: date, ...) -> None:
    """Write one row to atlas.strategy_paper_performance."""
```

`runner.py` orchestrates: calls `fetch_decisions` once per tier, then calls the above chain per strategy. The pure functions (`apply_strategy_filter`, `compute_trades`) have no DB dependency and cover the business logic — these are the primary test targets.

### 4.5 Regime-Split P&L

**Nifty500 benchmark data source:** `atlas.atlas_benchmark_returns_cache` (already in DB, populated by M3+ compute pipeline). Use `benchmark_code = 'NIFTY500'`.

**Naive-Atlas baseline definition:** For each date, include every instrument where `entry_trigger = TRUE` OR `investable = TRUE` in that date's Atlas decisions. Equal-weight across all such instruments. No threshold overrides — pure default Atlas output. This baseline answers: "did the strategy config add alpha beyond what raw Atlas investability produces?"

**SignalMatrix → returns bridge:** `metrics.py` receives `pd.Series` of daily returns (indexed by date), not `SignalMatrix` arrays. The conversion point is `report.py`: extract `pf.daily_returns()` from the vectorbt `Portfolio` object → convert to `pd.Series` indexed by `pf.wrapper.index` (DatetimeIndex). `split_by_regime` receives this Series. For paper trading, daily returns come directly from `strategy_paper_performance.daily_return` (already a float per row) — load them with `pd.read_sql` into a `pd.Series(index=date, data=daily_return)`.

```python
def split_by_regime(
    portfolio_returns: pd.Series,       # daily P&L from paper_performance
    regime_history: pd.Series,          # date → regime_state from atlas_market_regime_daily
                                        # column: atlas_market_regime_daily.regime_state (migration 004)
                                        # values: 'Risk-On' | 'Constructive' | 'Cautious' | 'Risk-Off'
) -> dict[str, RegimePerformance]:
    # Returns {Risk-On: {...}, Constructive: {...}, Cautious: {...}, Risk-Off: {...}}
    # Each: Sharpe, total_return, max_drawdown, days_in_regime,
    #       alpha_vs_nifty500, alpha_vs_naive_atlas
```

---

## 5. Auto-Optimizer

### Optuna Setup

**Storage:** Use a **direct (non-pooled) PostgreSQL URL** for Optuna's RDB backend. Do not route through PgBouncer or SQLAlchemy's async pool. Optuna manages its own connections. Use a dedicated `optuna` schema (separate from `atlas` schema) to avoid table name collisions.

**Pre-flight: create optuna schema if absent** (run once at first startup, before `create_study`):
```sql
CREATE SCHEMA IF NOT EXISTS optuna;
```
This must execute before Optuna's first `create_study` call. Add to migration 019 as a `CREATE SCHEMA IF NOT EXISTS optuna;` statement, or to the deployment runbook — Optuna will fail with a "schema not found" error otherwise.

```python
OPTUNA_DB_URL = os.environ["ATLAS_DB_DIRECT_URL"]  # separate env var — direct psycopg2 URL
# Embed search_path in URL (more reliable than engine_kwargs in Optuna 3.x):
OPTUNA_STORAGE_URL = OPTUNA_DB_URL + "?options=-csearch_path%3Doptuna"

STUDY_VERSION = "v1"  # increment to invalidate old studies when search space changes

study = optuna.create_study(
    study_name=f"atlas_{regime}_{archetype}_{STUDY_VERSION}",
    direction="maximize",               # maximize OOS Sharpe
    sampler=optuna.samplers.TPESampler(seed=42),
    storage=optuna.storages.RDBStorage(url=OPTUNA_STORAGE_URL),
    load_if_exists=True,                # resume if study already exists
)
```

**Study versioning:** When the constrained search space changes (new threshold added, range changed), increment `STUDY_VERSION` in `regime_optimizer.py`. Optuna's `load_if_exists=True` will create a new study rather than loading the incompatible old one. Old studies remain in the DB but are no longer accessed. The FM-facing study name in `/optimizer` displays the version suffix.

### Constrained Search Space (5-8 thresholds per archetype)

All threshold names match exact keys in `atlas/universe/thresholds.py` and `atlas.atlas_thresholds`. Default values come from `atlas.atlas_thresholds.threshold_value`. Reference `docs/04_THRESHOLD_CATALOG.md` for full descriptions and allowed ranges.

| Archetype | Key Thresholds Searched (actual keys from thresholds.py) |
|-----------|------------------------|
| momentum_pure | `rs_quintile_top`, `rs_quintile_bottom`, `momentum_flat_band_pct`, `momentum_ema_convergence_pct` |
| sector_rotation | `sector_overweight_participation_min_pct`, `sector_underweight_participation_max_pct`, `sector_avoid_participation_max_pct` |
| defensive | `risk_extension_low_max_pct`, `risk_extension_high_min_pct`, `risk_vol_ratio_low_max`, `risk_vol_ratio_normal_max` |
| fund_selection | `fund_aligned_aum_min_pct`, `fund_avoid_aum_max_pct`, `fund_strong_holdings_min_pct`, `fund_weak_holdings_max_pct` |
| multi_asset | `rs_quintile_top`, `rs_quintile_bottom`, `volume_accumulation_expansion_min`, `volume_accumulation_effort_min` |

Note: `multi_asset` stock/ETF allocation split (e.g. 60/40) is a **strategy config parameter**, not an Atlas threshold. Optuna tunes it as a continuous hyperparameter in the `[0.4, 0.8]` range (stocks_pct), separate from the threshold search space.

### Runtime Estimate and Schedule

- 100 Optuna trials per study (TPE converges faster than grid; 100 is sufficient for 4-8 parameters)
- Each trial = walk-forward backtest across available OOS windows
- Per-trial runtime on t3.large: ~20-30 seconds (vectorbt on 150-300 instruments × 9M window)
- 100 trials × 25s = ~42 minutes per study
- Run **only the current active regime** each week: 5 archetypes × 1 regime = 5 studies = ~3.5 hours
- Run all 4 regimes monthly (20 studies = ~14 hours, run on a weekend overnight job)

**Scheduler:** Extend existing Atlas compute orchestration. Add a weekly post-compute hook: `optimize_current_regime()`. Monthly full run is a separate cron.

### Parameter Importance (in results.py)

```python
# Use Optuna's built-in fANOVA-based importance scorer
importances = optuna.importance.get_param_importances(study)
# Returns dict[str, float]: {threshold_key: importance_score}
# Stored in atlas.strategy_optimization_runs.param_importances (JSONB)
# Surfaced on /optimizer/[study_id] as a horizontal bar chart
```

### Threshold Promotion Flow

```
Optuna study completes (weekly, current-regime studies)
  ↓
Top 3 param sets saved to atlas.strategy_optimization_runs (status = 'pending')
  ↓
FM sees on /optimizer: "RS threshold 58 vs 50: +1.4% alpha in Risk-On (3 OOS windows)"
  ↓
FM clicks "Approve"
  ↓
Writes to atlas.atlas_thresholds.threshold_value (existing column, migration 007)
atlas_threshold_history records: old_value (previous), new_value, changed_by="M7_optimizer",
  change_reason="promoted from study #{id}, OOS Sharpe #{oos_sharpe}"
  (atlas_threshold_history already exists — migration 007; columns: old_value, new_value, changed_by, change_reason)
  ↓
atlas.strategy_optimization_runs.status = 'approved', approved_by, approved_at set
  (approved_by = Supabase auth.uid() from the API Route Handler — not a free-text string)
  ↓
Next Atlas compute uses updated thresholds (no code deploy needed — thresholds are
read at compute time from atlas_thresholds, not hardcoded)
```

**Auth requirement (SEBI compliance):** The `/api/optimizer/[study_id]/approve` Route Handler must extract the FM's authenticated identity from Supabase `auth.uid()` and write it to `approved_by`. Unauthenticated requests return 403. `approved_by` must store a stable user identifier (Supabase user UUID), not a free-text string — this is the audit trail for SEBI algo threshold change logging.

**Rollback:** FM can revert within 7 days. Revert is **server-enforced**, not just a UI button: the `/api/optimizer/[study_id]/revert` Route Handler checks `(NOW() - approved_at) <= INTERVAL '7 days'` before writing. If outside the window, the Route Handler returns 409 with `"Revert window has expired (7 days)"`. The "Revert" button is hidden in the UI after 7 days, but the server check is the enforcement layer.

Revert reads `old_value` from the corresponding `atlas_threshold_history` row and writes it back to `atlas_thresholds.threshold_value`, appending a new history row with `change_reason = "reverted from M7 optimizer study #{id}"` and `changed_by = FM auth.uid()`.

---

## 6. New DB Tables (8 Alembic migrations, numbered 013-020)

Note: Migration 012 (`012_widen_fund_state_columns.py`) already exists. New M7 migrations start at 013.
`atlas_threshold_history` and `atlas_benchmark_returns_cache` **already exist** (migration 007). No re-migration needed.

```sql
-- Migration 013
atlas.strategy_configs           -- 15 strategy definitions (config as JSONB)
  id UUID PK DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  tier TEXT NOT NULL,              -- stocks_only | stocks_etf | mf_only
  archetype TEXT NOT NULL,
  variant TEXT NOT NULL,
  config JSONB NOT NULL,           -- full YAML as JSON
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()

-- Migration 014
atlas.strategy_paper_portfolios  -- current holdings per strategy
  id UUID PK DEFAULT gen_random_uuid(),
  strategy_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
  instrument_id TEXT NOT NULL,
  instrument_type TEXT NOT NULL,   -- stock | etf | fund
  weight_pct NUMERIC(10,4) NOT NULL,
  entry_date DATE NOT NULL,
  entry_signal_type TEXT NOT NULL, -- which signal triggered entry
  notional_value NUMERIC(20,4) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(strategy_id, instrument_id)  -- one active position per instrument per strategy
  -- Re-entry policy: if a strategy re-enters an instrument already held,
  -- UPDATE the existing row (weight_pct, notional_value, updated_at).
  -- Do NOT insert a second row. Record the re-entry as an action='rebalance'
  -- row in strategy_paper_trades with the new notional_value.
  -- Position history lives in paper_trades; paper_portfolios = current state only.

-- Migration 015
atlas.strategy_paper_trades      -- every simulated trade with full signal context
  id UUID PK DEFAULT gen_random_uuid(),
  strategy_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
  instrument_id TEXT NOT NULL,
  instrument_type TEXT NOT NULL,
  action TEXT NOT NULL,            -- enter | exit | rebalance
  signal_type TEXT NOT NULL,       -- transition | breakout | exit_rs | exit_momentum | etc.
  price NUMERIC(20,4) NOT NULL,
  weight_pct NUMERIC(10,4) NOT NULL,
  notional_value NUMERIC(20,4) NOT NULL,
  trade_date DATE NOT NULL,
  regime_at_trade TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()

-- Migration 016
atlas.strategy_paper_performance -- daily P&L per strategy
  id UUID PK DEFAULT gen_random_uuid(),
  strategy_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
  date DATE NOT NULL,
  total_value NUMERIC(20,4) NOT NULL,
  daily_return NUMERIC(10,6) NOT NULL,
  benchmark_nifty500_return NUMERIC(10,6),   -- from atlas_benchmark_returns_cache
  benchmark_naive_atlas_return NUMERIC(10,6), -- computed from default-threshold investable set
  regime TEXT NOT NULL,
  positions_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(strategy_id, date)

-- Migration 017
atlas.strategy_overlap_daily     -- pairwise portfolio overlap (105 rows/day: upper triangle only)
  -- Canonical direction: strategy_a_id < strategy_b_id (PostgreSQL UUID string comparison).
  -- **Python must enforce this before insert** — `overlap.py` must sort the pair:
  --   a, b = (id_x, id_y) if str(id_x) < str(id_y) else (id_y, id_x)
  -- The CHECK constraint catches bugs but is not the primary enforcement.
  -- Diagonal (strategy vs itself, Jaccard=1.0) is omitted — trivially known.
  -- Frontend queries: SELECT * WHERE strategy_a_id = X OR strategy_b_id = X
  id UUID PK DEFAULT gen_random_uuid(),
  date DATE NOT NULL,
  strategy_a_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
  strategy_b_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
  jaccard_similarity NUMERIC(6,4) NOT NULL,
  common_instruments INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(date, strategy_a_id, strategy_b_id),
  CHECK (strategy_a_id < strategy_b_id)  -- catches Python-side ordering bugs

-- Migration 018
atlas.strategy_backtest_results  -- vectorbt output per strategy or custom portfolio
  id UUID PK DEFAULT gen_random_uuid(),
  strategy_id UUID REFERENCES atlas.strategy_configs(id),    -- null for custom portfolios
  custom_portfolio_id UUID,  -- null for standard strategies; declared WITHOUT FK constraint here
  -- FK added in migration 020 via ALTER TABLE:
  --   op.create_foreign_key('fk_backtest_custom_portfolio',
  --     'strategy_backtest_results', 'strategy_fm_custom_portfolios',
  --     ['custom_portfolio_id'], ['id'], source_schema='atlas', referent_schema='atlas')
  -- This is intentional: strategy_fm_custom_portfolios does not exist yet at migration 018.
  backtest_type TEXT NOT NULL,     -- full | walk_forward | custom
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  sharpe_ratio NUMERIC(10,4),
  max_drawdown NUMERIC(10,4),
  total_return NUMERIC(10,4),
  alpha_vs_nifty500 NUMERIC(10,4),
  alpha_vs_naive_atlas NUMERIC(10,4),
  walk_forward_oos_sharpe NUMERIC(10,4),   -- null for non-walk-forward runs
  regime_breakdown JSONB,                  -- {risk_on: {sharpe, return, max_dd}, ...}
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()

-- Migration 019
atlas.strategy_optimization_runs -- Optuna results per regime+archetype study
  id UUID PK DEFAULT gen_random_uuid(),
  regime TEXT NOT NULL,
  archetype TEXT NOT NULL,
  study_name TEXT NOT NULL,        -- matches Optuna study_name in optuna schema
  best_params JSONB NOT NULL,      -- {threshold_key: value}
  param_importances JSONB,         -- fANOVA importance scores {threshold_key: score}
  oos_sharpe NUMERIC(10,4) NOT NULL,
  oos_alpha_vs_nifty500 NUMERIC(10,4),
  walk_forward_windows INT NOT NULL,
  trial_count INT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected | reverted
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()

-- Migration 020
atlas.strategy_fm_custom_portfolios  -- FM-designed portfolios
  id UUID PK DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  instruments JSONB NOT NULL,       -- [{instrument_id, instrument_type, weight_pct}]
                                    -- weights must sum to 100% ± 0.01% (enforced in builder.py)
  backtest_id UUID REFERENCES atlas.strategy_backtest_results(id),
                                    -- nullable: FM can save without backtesting,
                                    -- but paper_trading_active cannot be set to TRUE
                                    -- until backtest_id is populated
  paper_trading_active BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (paper_trading_active = FALSE OR backtest_id IS NOT NULL)
    -- DB-level enforcement: cannot activate paper trading without backtest
```

### Required Indexes (add to each migration)

Time-range queries on these tables are the dominant access pattern (nightly writes, frontend date-range reads). Without composite indexes, every `/strategies/[id]` page load does a full table scan.

```sql
-- Migration 014 (strategy_paper_portfolios)
CREATE INDEX idx_paper_portfolios_strategy ON atlas.strategy_paper_portfolios(strategy_id);

-- Migration 015 (strategy_paper_trades) — date range + strategy filter
CREATE INDEX idx_paper_trades_strategy_date
  ON atlas.strategy_paper_trades(strategy_id, trade_date DESC);

-- Migration 016 (strategy_paper_performance) — primary read path: date range per strategy
CREATE INDEX idx_paper_perf_strategy_date
  ON atlas.strategy_paper_performance(strategy_id, date DESC);

-- Migration 017 (strategy_overlap_daily) — frontend: last N days of overlap
CREATE INDEX idx_overlap_date ON atlas.strategy_overlap_daily(date DESC);
-- frontend queries: WHERE strategy_a_id=X OR strategy_b_id=X
CREATE INDEX idx_overlap_a ON atlas.strategy_overlap_daily(strategy_a_id, date DESC);
CREATE INDEX idx_overlap_b ON atlas.strategy_overlap_daily(strategy_b_id, date DESC);

-- Migration 018 (strategy_backtest_results)
CREATE INDEX idx_backtest_strategy ON atlas.strategy_backtest_results(strategy_id)
  WHERE strategy_id IS NOT NULL;
CREATE INDEX idx_backtest_custom ON atlas.strategy_backtest_results(custom_portfolio_id)
  WHERE custom_portfolio_id IS NOT NULL;

-- Migration 019 (strategy_optimization_runs) — optimizer dashboard: filter by status
CREATE INDEX idx_optim_status ON atlas.strategy_optimization_runs(status, created_at DESC);
CREATE INDEX idx_optim_regime_archetype
  ON atlas.strategy_optimization_runs(regime, archetype, created_at DESC);
```

All FK columns also get `index=True` per project database conventions (`~/.claude/CLAUDE.md`).

---

## 7. Custom Portfolio Builder (builder.py)

### Validation Rules

Before accepting a custom portfolio, `builder.py` enforces:

```python
def validate_custom_portfolio(instruments: list[InstrumentWeight]) -> None:
    # 1. Minimum 2 instruments
    if len(instruments) < 2:
        raise ValidationError("Portfolio must have at least 2 instruments")

    # 2. All instruments must exist in an Atlas universe table
    # exists_in_universe(instrument_id, instrument_type) checks:
    #   stock → atlas.atlas_universe_stocks WHERE instrument_id=X (any row, active or historical)
    #   etf   → atlas.atlas_universe_etfs WHERE instrument_id=X
    #   fund  → atlas.atlas_universe_funds WHERE instrument_id=X
    # Returns True if found in the appropriate table. Batch the check across all instruments
    # in a single IN query rather than N individual queries.
    for inst in instruments:
        if not exists_in_universe(conn, inst.instrument_id, inst.instrument_type):
            raise ValidationError(f"{inst.instrument_id} not found in Atlas universe")

    # 3. Weights must sum to 100% ± 0.01%
    total = sum(i.weight_pct for i in instruments)
    if abs(total - 100.0) > 0.01:
        raise ValidationError(f"Weights sum to {total:.4f}%, must be 100% ± 0.01%")

    # 4. No single instrument > 40% weight
    for inst in instruments:
        if inst.weight_pct > 40.0:
            raise ValidationError(f"{inst.instrument_id} weight {inst.weight_pct}% exceeds 40% limit")
```

**Optional weight suggestion (PyPortfolioOpt):** When the FM selects instruments but doesn't specify weights, `builder.py` offers two auto-weight options:
- **Equal weight** (default, no library needed)
- **Min-variance weights** via `PyPortfolioOpt.EfficientFrontier` — uses historical returns from JIP price data to minimize portfolio volatility. Only offered when portfolio has ≤ 30 instruments (EfficientFrontier is numerically unstable on larger covariance matrices). Equal weight is recommended and used for >30 instruments.

---

## 8. M7 Frontend Routes (in M6 Next.js app)

```
/strategies                      Strategy comparison board
                                 PRIMARY: sortable strategy ranking table (full-width)
                                   Columns: Name, Tier, Sharpe (sort default desc), Return%,
                                   Drawdown%, Active Positions, Regime Status badge
                                   (Active / Paused / Scaled-0.4×)
                                   Row click → /strategies/[id]
                                 SECONDARY (below fold, section anchor "Overlap"): 15×15
                                   Jaccard heatmap — full-width, --radius-card: 2px cells
                                 PAGE HEADER: current regime badge + nightly run timestamp
                                 FILTER: tier tabs (All / Stocks-only / Stocks+ETF / MF-only)
                                 EMPTY STATE (day 1, no paper trading run yet):
                                   "Paper trading starts tonight — check back after the
                                   nightly run (approx. 11:30 PM IST)."

/strategies/[id]                 Strategy detail
                                 — current holdings table
                                 — P&L history chart (1M/3M/6M toggle, --color-teal series)
                                 — regime-split performance (4-column breakdown)
                                 — recent trades (last 30 days)

/strategies/[id]/backtest        Backtest results
                                 — walk-forward chart (OOS vs IS Sharpe per window)
                                 — performance table × regime
                                 — vs Nifty500 AND vs naive Atlas baseline

/portfolios/custom               FM custom portfolio builder — SPLIT PANEL layout:
                                 LEFT PANEL (50%): instrument search input + results list
                                   (name, type badge, current Atlas state, add button)
                                 RIGHT PANEL (50%): portfolio composition
                                   — instrument rows with inline weight % input
                                   — live weight bar (e.g. "73.5% / 100%")
                                   — total weight validation: green ✓ at 100% ±0.01%,
                                     amber warning when > 100%, red error when outside ±0.01%
                                   — "Suggest equal weights" + "Suggest min-variance weights"
                                     (min-variance only enabled when ≤ 30 instruments)
                                   — "Run Backtest" button (disabled until weights = 100%)
                                 SUBMIT: redirect immediately to /portfolios/custom/[id]
                                   with skeleton loading state; page polls every 5s until
                                   backtest_results populated
                                   MAX POLL TIME: 5 minutes (60 polls). After timeout,
                                   show error: "Backtest is taking longer than expected.
                                   Refresh to check status, or contact support."
                                   ERROR STATE: if /api/portfolios/[id]/status returns
                                   status='failed', show: "Backtest failed — [error_message].
                                   Try again or contact support."

/portfolios/custom/[id]          Custom portfolio detail + backtest results
                                 — Shows "Backtest running…" skeleton until results arrive
                                 — "Start paper trading" button
                                   (enabled only when backtest_id is set)
                                 — Portfolio list at /portfolios/custom shows "Pending"
                                   status badge for portfolios awaiting backtest

/optimizer                       Optimization results dashboard
                                 PRIMARY: 5×4 study status grid (archetype rows × regime cols)
                                   Each cell: last run date, OOS Sharpe, trial count
                                   Pending approval count badge on cell (e.g. "2 pending")
                                   Click cell → /optimizer/[study_id]
                                 SECONDARY: approved promotions with "Revert" option
                                   (Revert button visible for 7 days after approval)
                                 EMPTY STATE (no pending approvals):
                                   Checkmark icon + "All caught up — no threshold changes
                                   awaiting your approval." + "Next optimization run:
                                   [next Sunday 2:00 AM IST]" (computed from last_run_at)

/optimizer/[study_id]            Study detail
                                 — Optuna trial history chart (Sharpe per trial,
                                   --color-teal line, --color-paper-rule axes)
                                 — parameter importance bar chart (fANOVA scores)
                                 — "Approve promotion" triggers confirmation modal:
                                   "Approve [threshold_key]: [old] → [new]?
                                   Takes effect on tonight's Atlas compute run.
                                   You can revert within 7 days." [Confirm] [Cancel]
                                   Modal: focus-trapped, Escape = cancel, Enter = confirm
                                   aria-label="Approve threshold promotion for [key]"
                                 — "Reject" removes from pending queue (no confirmation)
```

### 8.1 API Route Handlers (Next.js App Router)

The polling pattern on `/portfolios/custom/[id]` requires a Route Handler — Server Components cannot be polled from the client side. Three Route Handlers needed:

```
app/api/portfolios/[id]/status/route.ts
  GET → { backtest_id: string | null, status: 'pending' | 'complete' | 'failed' }
  Polls every 5s from the Client Component on /portfolios/custom/[id]
  Returns 200 with status='pending' while backtest is running; 200 status='complete' once
  backtest_id is populated on strategy_fm_custom_portfolios; 200 status='failed' on error.

app/api/strategies/[id]/performance/route.ts
  GET ?from=YYYY-MM-DD&to=YYYY-MM-DD
  → { daily: [{date, total_value, daily_return, regime, benchmark_nifty500_return, benchmark_naive_atlas_return}] }
  Drives P&L chart on /strategies/[id] (1M/3M/6M toggle → different date params)

app/api/optimizer/[study_id]/approve/route.ts
  POST { threshold_key: string, new_value: number }
  → 200 { approved_at: string } | 409 { error: 'already_approved' } | 403 (auth check)
  Writes to atlas_thresholds + atlas_threshold_history; updates optimization_runs.status
  This is the only write Route Handler — all others are read-only.
```

All Route Handlers use the existing `createServerClient` Supabase pattern from M6. No new auth infrastructure.

### 8.2 UI Design Decisions (plan-design-review, 2026-05-08)

| # | Screen | Decision | Rationale |
|---|--------|----------|-----------|
| D1 | /strategies | Table primary (full-width), Jaccard heatmap below fold with section anchor | Heatmap (15×15) is diagnostic context, not daily read; table needs full width for 7 columns |
| D2 | /portfolios/custom | Live canvas split-panel (search left, composition right) | FM needs live weight total while allocating — linear wizard prevents this |
| D3 | /optimizer | Study status grid (5×4) primary; pending approvals as count badges on cells | FM wants system health overview first; action items discoverable via badge count |
| D4 | /optimizer empty | "All caught up" + next scheduled run date | Prevents FM from thinking system is broken when no approvals are pending |
| D5 | Threshold approval | Confirmation modal with "tonight's compute" impact disclosure + 7-day revert notice | Production threshold write — fat-finger protection outweighs one extra click |
| D6 | Backtest loading | Redirect to /portfolios/custom/[id] immediately; skeleton + 5s polling until done | FM lands on the result page URL (bookmarkable); backtest runs in background |
| D7 | Navigation | Grouped nav: **Research** (Sectors, Stocks, ETFs, Funds) / **Simulation** (Strategies, Portfolios, Optimizer) | 10+ flat nav items overflow at 1440px |
| D8 | Mobile | Desktop-only — show "Atlas Simulation is optimized for desktop" at < 768px viewport | Heatmap and split-panel cannot be made mobile-friendly without separate layouts |

**Design system constraints (all M7 routes):**
- All colors from `globals.css` tokens only. No new CSS variables.
- Chart series: `--color-teal` (#1D9E75) for primary, `--color-signal-pos` for positive return, `--color-signal-neg` for negative return, `--color-paper-rule` for axes/gridlines.
- Card/cell radius: `--radius-card: 2px` throughout, including heatmap cells.
- Fonts: `--font-sans` (Inter) for data, `--font-serif` (Source Serif 4) for large metric display.
- All numerical data: `font-variant-numeric: tabular-nums` (class `tabular` or `data-numeric` attribute).

---

## 9. Library Stack

| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| vectorbt | 0.26.x | Backtesting + walk-forward | **Python 3.11 only.** Check newer releases before considering alternatives on 3.12. |
| optuna[postgres] | ≥3.0 | Bayesian threshold optimization | RDB storage requires direct (non-pooled) URL |
| PyPortfolioOpt | ≥1.5 | Optional min-variance weights in custom builder | Only used for weight suggestion, not required path |
| empyrical-reloaded | (already installed) | Sharpe, Calmar, alpha, drawdown | — |

Add to `pyproject.toml` under optional dependencies:
```toml
[project.optional-dependencies]
simulation = [
    "vectorbt>=0.26,<0.27",
    "optuna[postgres]>=3.0",
    "PyPortfolioOpt>=1.5",
]
```

---

## 10. Implementation Phases

**Phase 1 — Core infrastructure (prerequisite for all)**
- Alembic migrations 013–020
- `signal_adapter.py` (JIP prices + Atlas signals → SignalMatrix)
- `backtest/engine.py` (vectorbt wrapper with `InsufficientHistoryError` guard)
- `backtest/walk_forward.py`
- `metrics.py` (empyrical + regime-split + overlap math)

**Phase 2 — Strategy Engine (15 strategies + paper trading)**
- `strategies/configs/*.yaml` (15 YAML configs)
- `strategies/loader.py` + `strategies/runner.py`
- `paper_trader.py` (nightly state machine, cold-start behavior)

**Phase 3 — Custom Portfolio Builder**
- `custom/builder.py` (validation + optional PyPortfolioOpt weight suggestion)
- `custom/portfolio.py`
- `/portfolios/custom` frontend routes

**Phase 4 — Auto-Optimizer**
- `optimizer/regime_optimizer.py` (Optuna study + direct PostgreSQL URL)
- `optimizer/results.py` (param importance via Optuna fANOVA + results storage)
- `/optimizer` frontend routes + threshold promotion workflow + revert button

**Phase 5 — Frontend (all strategy-facing routes)**
- `/strategies` and `/strategies/[id]` depend on `strategy_paper_performance` (migration 016) being populated by at least one nightly paper trading run (Phase 2). Frontend for these routes cannot be meaningfully developed until Phase 2 runs at least once.
- **Mock data fixture:** To unblock frontend work before Phase 2 runs, add `scripts/m7_seed_mock_data.py` — inserts one week of synthetic paper performance rows for all 15 strategies. Run against a dev database only. Purge with `DELETE FROM atlas.strategy_paper_performance WHERE created_by = 'mock'` before going to production.
- `/portfolios/custom` and `/optimizer` routes have no Phase 2 dependency and can be built in parallel with Phase 3/4 backend work.

---

## 11. Critical Pre-Implementation Checks

```sql
-- 1. Historical signal depth (need ≥12M for walk-forward to produce ≥3 OOS windows)
SELECT MIN(date), MAX(date), COUNT(DISTINCT date)
FROM atlas.atlas_stock_decisions_daily;

-- 2. JIP schema access (must return a row)
SELECT COUNT(*) FROM de_ohlcv_daily LIMIT 1;

-- 3. Benchmark data availability
SELECT benchmark_code, MIN(date), MAX(date), COUNT(*)
FROM atlas.atlas_benchmark_returns_cache
WHERE benchmark_code = 'NIFTY500'
GROUP BY benchmark_code;
```

```bash
# 4. vectorbt on Python 3.11
python3.11 -c "import vectorbt as vbt; print(vbt.__version__)"

# 5. Optuna PostgreSQL storage (replace with actual direct URL)
python3.11 -c "
import optuna
optuna.create_study(
    study_name='test',
    storage='postgresql+psycopg2://user:pw@host/db?options=-csearch_path=optuna',
    load_if_exists=True
)
print('Optuna PostgreSQL storage OK')
"
```

---

## 12. Performance Constraints

**Runtime environment:** EC2 t3.large (2 vCPU, 8 GB RAM).

**Nightly paper trading:** `fetch_decisions` called once per tier (3 calls total), not 15 times. Bulk writes via `execute_values`. Target: ≤ 60 seconds for full 15-strategy pass.

**vectorbt memory ceiling:** Never hold more than one Portfolio object in memory. `walk_forward.py` must `del pf; gc.collect()` after extracting each OOS window's metrics. Failure = OOM during optimizer's 100-trial loop.

**Optimizer scheduling:** Keep `n_jobs=1` — parallel vectorbt instances OOM on t3.large (8 GB). Weekly = current regime (5 studies, ~3.5 hrs). Monthly = all regimes (20 studies, ~14 hrs). Run as separate script `scripts/m7_optimize.py`, not part of nightly compute. Schedule: Sunday 2:00 AM IST.

**DB scale:** 15 strategies × 365 days = ~5,500 rows/year in `strategy_paper_performance`. Composite index `(strategy_id, date DESC)` is sufficient — no partitioning needed at this scale.

---

## 13. Testing Requirements

**Target:** 80% coverage on new code (`~/.claude/rules/testing.md`). All test files mirror source paths: `atlas/simulation/core/paper_trader.py` → `tests/unit/simulation/test_paper_trader.py`.

**Unit tests (no DB) — `tests/unit/simulation/`:**
- `test_paper_trader.py`: `apply_strategy_filter`, `compute_trades` — pure function behavior for all regime stances, threshold overrides, exit priority ordering, cold start
- `test_builder.py`: `validate_custom_portfolio` — weight validation, universe existence, concentration limits
- `test_overlap.py`: Jaccard similarity math, upper-triangle pair generation (C(15,2)=105), UUID ordering
- `test_walk_forward.py`: `InsufficientHistoryError` at <547 days, window count formula (12M→4, 18M→10), no IS/OOS data leakage
- `test_loader.py`: YAML loading, invalid tier/threshold_override keys raise `ValidationError`

**Integration tests (transaction-rollback) — `tests/integration/simulation/`:**
- `test_paper_trader_integration.py`: full nightly pass for one strategy against fixture data; `MissingAtlasDecisionsError` and `StaleJIPDataError` paths
- `test_optimizer_integration.py`: Optuna study create/persist (mock objective); FM approval write path; revert path

**Not tested here:** vectorbt internal correctness, Optuna convergence, empyrical metric math — upstream library responsibilities.

---

## 14. GSTACK Review Report

**Reviews completed:** `/plan-design-review` (2026-05-08) + `/plan-eng-review` (2026-05-08)

**Design review outcome (8 binding decisions):** See Section 8.2. All 8 decisions confirmed by FM. Notable: D3 (optimizer primary view = study grid, not pending list) was FM-selected opposite to recommendation — rationale: FM wants system health overview first.

**Engineering review outcome:**
- Architecture: 5 issues found and fixed (E1 sync/async, E2 seeding, E3 indexes, E4 Route Handlers, E5 FK ordering)
- Code quality: 3 improvements (CQ1 paper_trader decomposition, CQ2 fetch_decisions batching, CQ3 overlap.py split)
- Performance: Section 12 added (memory ceiling, n_jobs constraint, DB scale)
- Tests: Section 13 added (unit + integration coverage diagram)
- Outside voice: 15 issues reviewed; 13 addressed (2 were false positives — reviewer confused async/sync state before fixes were in place)

**Spec score:** Started at 6/10 (pre-design-review). After all review passes: estimated 9/10. Remaining risk: walk-forward OOS window serial correlation (documented in Section 4.3, mitigated by 547-day guard, no further mitigation available without non-overlapping windows which would require >24M history).

**Status:** Ready for `/writing-plans` — implementation plan can be written from this spec.

---

## 15. Deferred to M8+

- Live execution (requires SEBI algo trader registration)
- Real-time strategy updates (streaming)
- Strategy versioning (V1 vs V2 performance comparison)
- Multi-period optimization (multiple regimes simultaneously)
- Alert/notification when a paper strategy underperforms for N consecutive days
- Natural language strategy description ("show me strategies that work in Risk-Off")
- Threshold A/B testing (run old and new thresholds in parallel on paper portfolios)

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
# SQLAlchemy 2.0 async pattern (matches atlas/compute/_session.py conventions)
from sqlalchemy import text

# Abort if JIP data hasn't landed yet for today
jip_max_date = await session.scalar(text("SELECT MAX(date) FROM de_ohlcv_daily"))
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

**Python/library compatibility note:** vectorbt 0.26.x is confirmed working on **Python 3.11**. It has known issues with NumPy 2.x on Python 3.12. This module must be deployed on Python 3.11. If the runtime is 3.12, use `bt` (https://pmorissette.github.io/bt/) as a drop-in backtest alternative — its API is similar; the engine.py adapter abstracts this boundary.

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

### 4.4 Paper Trading State Machine (nightly, async, separate from vectorbt)

`paper_trader.py` is fully async (`async def` throughout), matching `atlas/compute/_session.py` conventions. The nightly runner is an async coroutine invoked by the compute orchestration loop. All `await session.scalar(...)` calls in this section are valid async calls.

**Preflight: Atlas decisions existence check (runs before position processing):**
```python
decisions_today = await session.scalar(
    text("SELECT COUNT(*) FROM atlas.atlas_stock_decisions_daily WHERE date = :d"),
    {"d": today}
)
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

### 4.5 Regime-Split P&L

**Nifty500 benchmark data source:** `atlas.atlas_benchmark_returns_cache` (already in DB, populated by M3+ compute pipeline). Use `benchmark_code = 'NIFTY500'`.

**Naive-Atlas baseline definition:** For each date, include every instrument where `entry_trigger = TRUE` OR `investable = TRUE` in that date's Atlas decisions. Equal-weight across all such instruments. No threshold overrides — pure default Atlas output. This baseline answers: "did the strategy config add alpha beyond what raw Atlas investability produces?"

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

study = optuna.create_study(
    study_name=f"atlas_{regime}_{archetype}",
    direction="maximize",               # maximize OOS Sharpe
    sampler=optuna.samplers.TPESampler(seed=42),
    storage=optuna.storages.RDBStorage(
        url=OPTUNA_DB_URL,
        engine_kwargs={"connect_args": {"options": "-csearch_path=optuna"}},
    ),
    load_if_exists=True,                # resume if study already exists
)
```

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
  ↓
Next Atlas compute uses updated thresholds (no code deploy needed — thresholds are
read at compute time from atlas_thresholds, not hardcoded)
```

**Rollback:** FM can revert within 7 days. `/optimizer` shows each promoted change with a "Revert" button. Revert reads `old_value` from the corresponding `atlas_threshold_history` row and writes it back to `atlas_thresholds.threshold_value`, appending a new history row with `change_reason = "reverted from M7 optimizer study #{id}"` and `changed_by = FM identity`.

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
  UNIQUE(strategy_id, instrument_id)  -- one position per instrument per strategy

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
  -- Canonical direction enforced: strategy_a_id < strategy_b_id (lexicographic UUID).
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
  CHECK (strategy_a_id < strategy_b_id)  -- enforce canonical upper-triangle ordering

-- Migration 018
atlas.strategy_backtest_results  -- vectorbt output per strategy or custom portfolio
  id UUID PK DEFAULT gen_random_uuid(),
  strategy_id UUID REFERENCES atlas.strategy_configs(id),    -- null for custom portfolios
  custom_portfolio_id UUID,  -- null for standard strategies (FK added in migration 020 after strategy_fm_custom_portfolios is created)
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
    for inst in instruments:
        if not exists_in_universe(inst.instrument_id, inst.instrument_type):
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
                                 — all 15 ranked by regime-adjusted Sharpe
                                 — 15×15 overlap heatmap (Jaccard)
                                 — filter by tier (stocks/blend/mf)

/strategies/[id]                 Strategy detail
                                 — current holdings table
                                 — P&L history chart (1M/3M/6M toggle)
                                 — regime-split performance (4-column breakdown)
                                 — recent trades (last 30 days)

/strategies/[id]/backtest        Backtest results
                                 — walk-forward chart (OOS vs IS Sharpe per window)
                                 — performance table × regime
                                 — vs Nifty500 AND vs naive Atlas baseline

/portfolios/custom               FM custom portfolio builder
                                 — instrument search + weight assignment
                                 — real-time weight validation (sum to 100%)
                                 — triggers vectorbt backtest on submit

/portfolios/custom/[id]          Custom portfolio detail + backtest results
                                 — "Start paper trading" button
                                   (enabled only when backtest_id is set)

/optimizer                       Optimization results dashboard
                                 — pending promotions (threshold change + delta alpha)
                                 — approved promotions with "Revert" option (7-day window)
                                 — per-regime study status (last run, OOS Sharpe, trial count)

/optimizer/[study_id]            Study detail
                                 — Optuna trial history chart (Sharpe per trial)
                                 — parameter importance bar chart (fANOVA scores)
                                 — "Approve promotion" and "Reject" buttons
```

---

## 9. Library Stack

| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| vectorbt | 0.26.x | Backtesting + walk-forward | **Python 3.11 only.** Use `bt` as fallback on 3.12. |
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
- Can start in parallel with Phase 3 once migration 012-016 are stable

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

## 12. Deferred to M8+

- Live execution (requires SEBI algo trader registration)
- Real-time strategy updates (streaming)
- Strategy versioning (V1 vs V2 performance comparison)
- Multi-period optimization (multiple regimes simultaneously)
- Alert/notification when a paper strategy underperforms for N consecutive days
- Natural language strategy description ("show me strategies that work in Risk-Off")
- Threshold A/B testing (run old and new thresholds in parallel on paper portfolios)

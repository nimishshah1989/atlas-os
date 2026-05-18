# Atlas Strategy Lab — Design Specification

**Generated:** 2026-05-14  
**Status:** DRAFT — awaiting user approval  
**Scope:** India-only (Nifty 500 universe), Phase 1  
**Replaces:** No prior spec (first design on this surface)

---

## 1. Problem Statement

Atlas already answers: *"Is this stock worth owning right now?"*  
It produces conviction scores, entry/exit triggers, and regime state — all IC-validated and production-grade.

The unsolved question is: **given those signals, which combination of (a) how you define states from raw metrics and (b) how you act on those states, produces the best risk-adjusted after-tax returns?**

The current Atlas compute pipeline has fixed thresholds and fixed decision rules. Those thresholds and rules are assumptions — not validated by actual portfolio outcomes. If the RS "Leader" cutoff is set at the 70th percentile but the optimal cutoff is 62nd, every downstream rule built on "Leader" state is miscalibrated. No amount of optimizing entry/exit rules on top of wrong state definitions fixes that.

**This system optimizes both layers simultaneously:**

- **Layer 1 (Perception):** The threshold values that convert raw metrics into state labels (what RS percentile = "Leader", what breadth % = "Risk-On", what vol ratio = "Elevated")
- **Layer 2 (Decision):** The rules that convert states into actions (when to enter, how much to size, when to exit)

A **Strategy Genome** = `{Layer 1 thresholds + Layer 2 rules}`. The engine runs 100–150 genomes in parallel, each managing a virtual ₹1 crore Indian equity portfolio with full after-tax, after-cost accounting. Nightly evolutionary selection promotes winners, kills losers, breeds offspring. The top 3–5 promoted strategies surface as actionable replication guides.

---

## 2. Core Design Decisions

### 2.1 What is being optimized

**Optimizing variable:** After-tax, after-cost Sortino ratio on walk-forward out-of-sample data (rolling 1-year optimization window, 3-month out-of-sample test). Secondary objective: Calmar ratio (annualized return / max drawdown) to filter strategies that recover quickly.

**Not optimized by exhaustive grid search.** Optuna (Bayesian TPE) intelligently searches the genome space, focusing trials on promising parameter regions. After convergence, DEAP evolutionary crossover breeds offspring from top performers.

### 2.2 India-first, but architecture is geography-agnostic

All broker-specific, tax-specific, and universe-specific parameters live in a configurable `PortfolioConfig` object, not in strategy logic. Adding IBKR global later = new `PortfolioConfig` with different tax rules and universe. No code change required in the genome or simulation engine.

### 2.3 Idle cash = LiquidBees, never zero

When a strategy holds cash (regime = Risk-Off, heat cap hit, or no investable stocks), idle capital is assumed invested in Nippon India ETF Liquid BeES (NSE: LIQUIDBEES). This earns the configured yield (default: 6.7% p.a., MIBOR-linked) and is taxed at the user's income tax slab rate. Cash drag is eliminated from all simulations.

### 2.4 All performance is after-tax and after-cost

STCG, LTCG (with annual exemption tracking), LiquidBees income tax, brokerage, STT, exchange charges — all deducted before computing any performance metric. Every Sortino ratio, every Calmar, every alpha number shown to the user is the honest number.

### 2.5 Survivorship bias is handled at data load

The simulation loads the historical Nifty 500 universe as it existed at each point in time, not today's composition. Stocks that were delisted, merged, or removed are included in the period they were active. Point-in-time universe membership is tracked in `atlas_universe_membership_daily` (new table).

---

## 3. The Strategy Genome

A genome is a JSON record defining a complete, self-contained theory of the market. It has no hard-coded constants — every value is a genome parameter subject to optimization.

```json
{
  "genome_id": "uuid",
  "version": 1,
  "parent_ids": ["uuid", "uuid"],
  "born_at": "2026-05-14T20:00:00Z",

  "layer1_perception": {
    "rs_leader_cutoff_pct":    70,
    "rs_strong_cutoff_pct":    55,
    "rs_average_cutoff_pct":   35,
    "rs_weak_cutoff_pct":      20,
    "rs_timeframe_weights": {
      "1w": 0.35, "1m": 0.30, "3m": 0.20, "6m": 0.10, "12m": 0.05
    },
    "regime_risk_on_breadth_pct":     60,
    "regime_constructive_breadth_pct": 45,
    "regime_cautious_breadth_pct":    30,
    "regime_risk_on_vix_ceiling":     18,
    "momentum_accel_ema_ratio":       1.020,
    "momentum_decel_ema_ratio":       0.990,
    "vol_elevated_ratio":             1.40,
    "vol_high_ratio":                 1.75,
    "state_velocity_lookback_days":   10
  },

  "layer2_decision": {
    "risk_on": {
      "min_conviction_to_enter":    0.55,
      "tier_sizing_gradient":       "moderate",
      "base_position_pct":          4.5,
      "exit_rs_drop_tiers":         2,
      "exit_momentum_collapse":     true,
      "profit_target_pct":          null,
      "time_stop_days":             null,
      "trailing_stop_from_peak_pct": null,
      "min_hold_days":              5,
      "max_sector_concentration_pct": 25
    },
    "constructive": {
      "min_conviction_to_enter":    0.65,
      "tier_sizing_gradient":       "conservative",
      "base_position_pct":          3.5,
      "exit_rs_drop_tiers":         1,
      "exit_momentum_collapse":     true,
      "profit_target_pct":          null,
      "time_stop_days":             30,
      "trailing_stop_from_peak_pct": 12.0,
      "min_hold_days":              7,
      "max_sector_concentration_pct": 20
    },
    "cautious": {
      "min_conviction_to_enter":    0.75,
      "tier_sizing_gradient":       "flat",
      "base_position_pct":          2.5,
      "exit_rs_drop_tiers":         1,
      "exit_momentum_collapse":     true,
      "profit_target_pct":          15.0,
      "time_stop_days":             20,
      "trailing_stop_from_peak_pct": 8.0,
      "min_hold_days":              5,
      "max_sector_concentration_pct": 15
    },
    "risk_off": {
      "action": "full_cash_to_liquidbees"
    }
  }
}
```

**Genome parameters subject to Optuna optimization (searchable ranges):**

| Parameter | Type | Range |
|---|---|---|
| `rs_leader_cutoff_pct` | int | 60–80 |
| `rs_strong_cutoff_pct` | int | 45–65 |
| `rs_timeframe_weights.1w` | float | 0.10–0.60 |
| `rs_timeframe_weights.1m` | float | 0.10–0.50 |
| `regime_risk_on_breadth_pct` | int | 50–70 |
| `regime_constructive_breadth_pct` | int | 35–55 |
| `vol_elevated_ratio` | float | 1.2–1.8 |
| `momentum_accel_ema_ratio` | float | 1.010–1.040 |
| `min_conviction_to_enter` (per regime) | float | 0.35–0.80 |
| `base_position_pct` (per regime) | float | 2.0–6.0 |
| `exit_rs_drop_tiers` (per regime) | int | 1–3 |
| `profit_target_pct` (per regime) | float\|null | null, 10–30 |
| `time_stop_days` (per regime) | int\|null | null, 10–45 |
| `trailing_stop_from_peak_pct` (per regime) | float\|null | null, 5–20 |
| `min_hold_days` (per regime) | int | 3–15 |
| `max_sector_concentration_pct` | int | 15–35 |
| `state_velocity_lookback_days` | int | 5–20 |

**Estimated genome space:** ~15,000–50,000 meaningful combinations. Optuna explores this intelligently — not exhaustively. Typically converges on high-quality regions within 300–500 trials.

---

## 4. The Tax and Cost Layer

### 4.1 Portfolio Configuration (user-defined, not hardcoded)

```python
@dataclass
class PortfolioConfig:
    # Capital
    starting_capital: Decimal = Decimal("10000000")  # ₹1 crore

    # Tax — Indian equity (post Budget 2024 defaults)
    stcg_rate: Decimal = Decimal("0.20")             # 20% if held < 365 days
    ltcg_rate: Decimal = Decimal("0.125")            # 12.5% if held ≥ 365 days
    ltcg_annual_exemption: Decimal = Decimal("125000")  # ₹1.25L per financial year
    income_tax_slab_rate: Decimal = Decimal("0.30")  # For LiquidBees income

    # Cash equivalent
    liquidbees_annual_yield: Decimal = Decimal("0.067")  # 6.7% p.a. default
    liquidbees_ticker: str = "LIQUIDBEES"

    # Transaction costs (Zerodha delivery defaults)
    brokerage_rate: Decimal = Decimal("0.005")       # 0.5% per side
    stt_rate_sell: Decimal = Decimal("0.001")        # 0.1% sell side
    exchange_charge_rate: Decimal = Decimal("0.000325")
    sebi_charge_rate: Decimal = Decimal("0.000001")

    # Risk limits (hard constraints, not genome variables)
    max_position_pct: Decimal = Decimal("0.05")      # 5% max per stock
    max_portfolio_heat_pct: Decimal = Decimal("0.20") # 20% max invested
    drawdown_circuit_breaker_pct: Decimal = Decimal("0.25")  # 25% = halt entries

    # Universe
    universe: str = "nifty500"
    rebalancing_frequency: str = "weekly"

    # Geography (for future IBKR extension)
    geography: str = "india"
    currency: str = "INR"
```

### 4.2 Per-trade net P&L computation

```
gross_pnl     = (exit_price - entry_price) × shares
brokerage     = (entry_value + exit_value) × brokerage_rate
stt           = exit_value × stt_rate_sell
exchange_fees = (entry_value + exit_value) × (exchange_charge_rate + sebi_charge_rate)
holding_days  = exit_date - entry_date (calendar days)

if holding_days < 365:
    tax = gross_pnl × stcg_rate  (if gross_pnl > 0)
elif holding_days >= 365:
    taxable = max(0, gross_pnl - remaining_ltcg_exemption)
    tax = taxable × ltcg_rate
    remaining_ltcg_exemption -= min(gross_pnl, remaining_ltcg_exemption)

net_pnl = gross_pnl - brokerage - stt - exchange_fees - tax
```

LTCG exemption resets on 1 April each financial year. Each strategy tracks its own exemption bucket independently.

### 4.3 LiquidBees daily accrual

```
idle_cash = starting_capital - (sum of all equity position values)
daily_liquidbees_income = idle_cash × (liquidbees_annual_yield / 365)
daily_liquidbees_tax = daily_liquidbees_income × income_tax_slab_rate
net_daily_liquidbees = daily_liquidbees_income - daily_liquidbees_tax

# Portfolio heat definition (explicit):
equity_value = sum(all equity position market values)
portfolio_heat = equity_value / total_portfolio_value
# LiquidBees is NOT equity — it is the cash equivalent.
# Heat cap (20%) applies to equity_value only.
# LiquidBees always = total_portfolio_value - equity_value
```

Accrues every simulation day. Appears as a named position ("LiquidBees") in the virtual portfolio. The heat cap constraint `max_portfolio_heat_pct` governs equity exposure only — LiquidBees is always the complement and is never constrained.

---

## 5. The Simulation Engine

### 5.1 Tech stack

| Component | Tool | Role |
|---|---|---|
| Raw metrics source | Postgres (`atlas_stock_metrics_daily`) | 45 cols per stock per day, 10 years |
| Portfolio simulation | **vectorbt** | Vectorized multi-asset backtest, thousands of combos simultaneously |
| Genome optimization | **Optuna** (TPE Bayesian) | Intelligent search over genome space, pruning, parameter importance |
| Evolutionary breeding | **DEAP** | Crossover + mutation of top performers |
| Insight narration | Groq Llama (existing SP07) | Plain-English insight feed from optimization results |
| Genome storage | Postgres (new tables) | Genome registry, performance history, evolution log |
| Orchestration | Python (`atlas.trading.incubator`) | New bounded context, ~1,200 lines |

### 5.2 Nightly run sequence (after existing Atlas compute completes)

```
1. Load atlas_stock_metrics_daily into numpy matrix (all stocks × all days)
   RAM estimate: ~2.1GB for Nifty 500 × 10Y × 45 cols @ float32

2. Load atlas_market_regime_daily (regime state per day)
   Load atlas_sector_states_daily (sector states per day)
   Load atlas_universe_membership_daily (point-in-time universe)

3. For each active genome (Optuna trial):
   a. Apply Layer 1 thresholds → derive state matrices in-memory
      (do NOT read atlas_stock_states_daily — those use fixed thresholds)
   b. Compute blended RS score using genome's timeframe weights
   c. Compute conviction score using genome's weights on 11 signals
   d. Apply Layer 2 regime-conditional rules → entry/exit signal matrices
   e. Run vectorbt portfolio simulation with PortfolioConfig constraints
   f. Compute after-tax, after-cost Sortino + Calmar on walk-forward window
   g. Return (sortino, calmar) to Optuna as objective

4. Optuna suggests next genome to try (TPE). Repeat 3.

5. After N trials (default: 200 Optuna trials/night across the active gene pool):
   Note: "200 trials/night" = Optuna evaluations. "Gene pool" = 100–150 genomes
   persisted in atlas_strategy_genomes. Trials evaluate existing genomes + new
   candidates suggested by Optuna. Pool size is maintained independently of trial count.

   a. Identify top-K genomes by Pareto frontier (Sortino × Calmar)
   b. DEAP crossover: breed offspring from top-2 pairs
   c. DEAP mutation: perturb 1–3 parameters ±10–20% on top performers
   d. Kill bottom-20% of gene pool (status → 'killed', logged to evolution log)
   e. Add offspring + random immigrants to maintain diversity (target pool: 100–150)

6. Persist genome performance to atlas_strategy_performance_daily
7. Update atlas_strategy_leaderboard (top-5 promoted strategies)
8. Run Groq insight generation on optimization deltas

Total estimated runtime: 45–90 minutes on EC2 t3.large
```

### 5.3 Walk-forward validation

No in-sample self-reporting. Every performance metric shown to the user comes from the out-of-sample window.

```
Rolling walk-forward protocol:
  Optimize on: days [0, 252]        → Test on: days [252, 342]
  Optimize on: days [90, 342]       → Test on: days [342, 432]
  Optimize on: days [180, 432]      → Test on: days [432, 522]
  ...continues rolling forward...

Reported metrics = average of all out-of-sample windows
Walk-forward equity curve = stitched out-of-sample periods only
```

If in-sample Sortino is >0.5 above out-of-sample Sortino for a genome: flag as potential overfit, deprioritize in promotion.

### 5.4 Tournament evaluation for promotion

Genomes must pass all three rounds to be promoted to the leaderboard:

```
Round 1: Last 90 days out-of-sample — Sortino > 0.7 to advance
Round 2: Prior 90-day window — Sortino > 0.5 to advance (consistency check)
Round 3: Stress test on historical regimes:
  - March 2020 (COVID crash): max drawdown < 25%
  - Jan–Jun 2022 (rate-hike bear): Sortino > 0 (no money lost)
  - 2023–24 bull run: Sortino > 1.0 (participated in upside)
Finals: Top 5 Pareto-optimal on (Sortino, Calmar) are PROMOTED
```

---

## 6. Additional Intelligence Layers

### 6.1 State velocity signal

Beyond current state, the simulation tracks state transition velocity. Two stocks both "Leader RS" today are different if one has been Leader for 90 days (mature/extended) versus 3 days (fresh breakout). Velocity signals:

- `rs_days_in_current_state`: consecutive days in current RS state
- `rs_direction`: improving (state upgraded in last N days) or decelerating
- `momentum_velocity`: EMA ratio rate of change over `state_velocity_lookback_days`

These are fed into conviction score as additional inputs, weighted by genome parameters.

### 6.2 Factor interactions (non-linear signals)

The conviction score extends from a weighted sum to include interaction terms:

```python
base_score = weighted_sum(11_signals, genome_weights)
rs_momentum_synergy = rs_pctile_3m_rank × momentum_state_rank  # multiplicative bonus
vol_rs_penalty = vol_ratio_63 × rs_pctile_3m_rank              # high vol discounts RS
conviction = base_score × (1 + synergy_weight × rs_momentum_synergy)
                         × (1 - penalty_weight × vol_rs_penalty)
```

`synergy_weight` and `penalty_weight` are genome parameters (range 0.0–0.3).

### 6.3 Portfolio-level drawdown adaptation

Each strategy monitors its own virtual portfolio drawdown. When the portfolio itself is in drawdown (independent of market regime), risk rules tighten:

```
portfolio_drawdown < 10%: normal rules apply
portfolio_drawdown 10–15%: halt new entries, tighten exits by 1 tier
portfolio_drawdown 15–20%: halt new entries, exit any position at 1-tier RS drop
portfolio_drawdown > 20%: liquidate all equity → full LiquidBees, reassess next cycle
```

Thresholds are genome parameters. This self-protective layer fires even in Risk-On markets if the portfolio is going wrong.

### 6.4 Tax harvesting signal

Generated nightly, separate from genome optimization. For each open position in each promoted strategy:

```
if gross_pnl > 0 AND holding_days < 365 AND (365 - holding_days) < 60:
    ltcg_saving = gross_pnl × (stcg_rate - ltcg_rate)
    signal_strength = current_exit_trigger_score  # 0–1
    if ltcg_saving > 5000 AND signal_strength < 0.6:
        emit TaxHarvestingAlert(position, ltcg_saving, days_to_ltcg, signal_strength)
```

Surfaces in the replication guide as an explicit tradeoff: "hold N more days to save ₹X in tax vs exit now on signal discipline."

### 6.5 Insight feed (Groq Llama narration)

After each nightly optimization run, a structured diff of genome parameters across the top-20 strategies is passed to Groq Llama with a fixed prompt template:

```
INPUT: parameter_importance_report (Optuna), top20_genome_delta (week-over-week)
OUTPUT: 3–5 plain-English insight bullets
  - What the engine is learning about signal weights
  - Which genome parameters are driving performance
  - Regime-specific patterns emerging
  - Any anomalies or warnings
```

Output is stored in `atlas_strategy_insights` and displayed in the Insight Feed panel. The LLM is not making trading decisions — it is narrating optimization results in human language.

---

## 7. Data Model (new tables)

### `atlas_strategy_genomes`
```sql
id              UUID PRIMARY KEY
parent_ids      UUID[]
genome_json     JSONB NOT NULL        -- full genome definition
born_at         TIMESTAMPTZ NOT NULL
status          TEXT CHECK IN ('active', 'promoted', 'killed', 'archived')
kill_reason     TEXT
generation      INT DEFAULT 0
```

### `atlas_strategy_performance_daily`
```sql
genome_id         UUID REFERENCES atlas_strategy_genomes(id)
date              DATE NOT NULL
sortino_insample  NUMERIC(10,4)
sortino_oos       NUMERIC(10,4)       -- out-of-sample (the honest one)
calmar_oos        NUMERIC(10,4)
alpha_vs_nifty500 NUMERIC(10,4)
max_drawdown      NUMERIC(10,4)
portfolio_heat    NUMERIC(10,4)
ltcg_exemption_used NUMERIC(20,4)
total_trades      INT
turnover_pct      NUMERIC(10,4)
PRIMARY KEY (genome_id, date)
```

### `atlas_strategy_positions_daily`
```sql
genome_id         UUID
date              DATE
instrument_id     INT REFERENCES atlas_instruments(id)
position_type     TEXT CHECK IN ('equity', 'liquidbees')
entry_date        DATE
entry_price       NUMERIC(20,4)
shares            NUMERIC(20,4)
current_value     NUMERIC(20,4)
unrealized_pnl    NUMERIC(20,4)
holding_days      INT
tax_status        TEXT CHECK IN ('stcg', 'ltcg_eligible', 'liquidbees')
entry_signals     JSONB             -- which signals fired on entry
PRIMARY KEY (genome_id, date, instrument_id)
```

### `atlas_strategy_leaderboard`
```sql
rank              INT PRIMARY KEY
genome_id         UUID REFERENCES atlas_strategy_genomes(id)
strategy_name     TEXT              -- human-readable label
promoted_at       TIMESTAMPTZ
sortino_oos       NUMERIC(10,4)
calmar_oos        NUMERIC(10,4)
alpha_30d         NUMERIC(10,4)
regime_breakdown  JSONB             -- {risk_on, constructive, cautious} sortino each
```

### `atlas_strategy_insights`
```sql
id              UUID PRIMARY KEY
generated_at    TIMESTAMPTZ
insight_bullets JSONB               -- array of plain-English insight strings
parameter_importance JSONB          -- Optuna importance scores
top_genome_deltas    JSONB          -- week-over-week parameter shifts
```

### `atlas_universe_membership_daily`
```sql
instrument_id   INT REFERENCES atlas_instruments(id)
date            DATE
universe        TEXT                -- 'nifty500', 'nifty100', 'nifty50'
was_member      BOOLEAN
PRIMARY KEY (instrument_id, date, universe)
```

### `atlas_strategy_evolution_log`
```sql
id              UUID PRIMARY KEY
genome_id       UUID REFERENCES atlas_strategy_genomes(id)
event_at        TIMESTAMPTZ NOT NULL
event_type      TEXT CHECK IN ('born', 'killed', 'promoted', 'demoted', 'mutated', 'crossover')
parent_ids      UUID[]
final_sortino   NUMERIC(10,4)       -- Sortino at time of kill/promotion
final_calmar    NUMERIC(10,4)
kill_reason     TEXT                -- e.g. 'bottom_quartile', 'stress_test_fail'
generation      INT
parameter_delta JSONB               -- which params changed from parent (for mutations)
```

### `atlas_portfolio_config`
```sql
id              UUID PRIMARY KEY
created_at      TIMESTAMPTZ
config_json     JSONB               -- PortfolioConfig as JSON
is_active       BOOLEAN DEFAULT false
label           TEXT                -- e.g. "30% slab HNI profile"
```

---

## 8. Frontend Design

### 8.1 Design principles

- **Progressive disclosure:** Three layers. Morning Brief (default) → Strategy Explorer (on demand) → Engine Room (power users).
- **Decisions, not data:** Every panel answers "what should I do?" not "here are metrics."
- **Plain English first:** LLM-generated narratives are the primary content. Numbers are secondary.
- **After-tax always:** Every number shown is post-tax, post-cost. No asterisks.
- **Nothing is hardcoded in the UI:** Tax rates, LiquidBees yield, brokerage — all editable in the configurator. UI renders from `atlas_portfolio_config`.

### 8.2 Layer 1: Morning Brief

Default landing page. Reads in 90 seconds.

**Sections:**
- Market context card: regime state + one-sentence narrative ("Broad breadth strong. VIX calm at 13.4.")
- Top strategy spotlight: name, after-tax Sortino, 30d P&L vs benchmark, max drawdown
- Today's signals: N new entries, N exits, LiquidBees daily income, LTCG exemption status
- Navigation to Layer 2 and Layer 3

**No tables. No charts on this page.** Just the brief.

### 8.3 Layer 2: Strategy Explorer

**Left panel:** Leaderboard (sortable by Sortino, Alpha, Calmar, Drawdown, Tax efficiency)
- Each row: rank, strategy name, Sortino (OOS), 30d alpha, max drawdown, regime indicator
- Bottom quintile rows visually fade — they're dying
- Top 5 rows highlighted as "Promoted"
- Filter by regime performance (e.g., "show me strategies that work in Cautious")

**Right panel:** Selected strategy detail
- Genome radar chart (8 dimensions, visual DNA)
- Equity curve vs Nifty 500 (walk-forward only)
- Regime breakdown table (Sortino per regime)
- Current positions list with entry signals, P&L, tax status, days held
- Walk-forward honesty chart (in-sample vs out-of-sample gap)
- Tax summary: STCG realized YTD, LTCG realized YTD, exemption remaining, LiquidBees income YTD
- Button: "View Replication Guide"

### 8.4 The Replication Guide

Full-screen view for any promoted strategy.

**Sections:**
- **Hold** (no action): positions where all signals intact
- **Watch** (caution): positions with any softening signal — highlighted amber
- **Buy today**: entry signals fired, target weight, conviction score, entry trigger reason
- **Sell today**: exit signals fired, with tax impact calculation (STCG vs LTCG) and tax harvesting note if applicable
- **LiquidBees allocation**: freed cash → park here until next entry
- **Tax summary for today's trades**: gross P&L, tax owed, net P&L, LTCG exemption update
- **Portfolio heat after trades**: equity % + LiquidBees %

### 8.5 Tax Harvesting Alert (inline in Replication Guide)

When a position has a taxable gain and is within 60 days of LTCG threshold:

```
TAX OPPORTUNITY
Holding Titan Company for 318 more days converts this STCG gain
(₹62,000 × 20% = ₹12,400 tax) to LTCG (₹62,000 × 12.5% = ₹7,750 tax).
Potential saving: ₹4,650.

Signal strength today: WEAK (0.32/1.0 — borderline exit)
Recommendation: Consider holding. Signal is not urgent.

[Hold — Save Tax]  [Exit Now — Follow Signal]
```

### 8.6 Layer 3: Engine Room

Accessed via explicit navigation. Not the default.

**Four panels:**

**Evolution Tree:** Phylogenetic genome lineage. Which strategies descended from which. Color: green = promoted, grey = evolving, red = killed.

**Insight Feed:** Nightly LLM-generated plain-English learnings. "1W RS weight has risen to 0.43 in top strategies (was 0.28 six weeks ago). Short-term momentum matters more in trending regimes."

**Walk-Forward Chart:** Two lines — in-sample Sortino (blue) vs out-of-sample Sortino (orange). If they track closely: engine is not overfitting. Prominent label: "Orange line is the honest one."

**Gene Pool Health:** Diversity score (0–1), active genomes, kill rate this cycle, IC trend, in-vs-out gap, last optimization timestamp. Alert if diversity < 0.5 (converging — inject immigrants).

**Parameter Importance Chart:** Optuna's output — which genome parameters drive Sortino most. Horizontal bar chart. "1W RS weight: 0.43 importance. Exit tier threshold: 0.31 importance. Vol elevated cutoff: 0.18 importance." This tells the user, empirically, which assumptions matter most.

### 8.7 Strategy Lab Configurator

**Accessible from:** Settings icon on Morning Brief.

**Step-by-step wizard (first launch) or panel (subsequent):**

```
Step 1: Starting Capital
  ₹ [1,00,00,000]

Step 2: Tax Profile
  Income tax slab: [10%] [20%] [30%] [Custom ___]
  STCG rate: 20%  (editable)
  LTCG rate: 12.5%  (editable)
  LTCG annual exemption: ₹1,25,000  (editable)

Step 3: Cash Management
  Idle cash deployed as: LiquidBees (LIQUIDBEES) ✓
  LiquidBees annual yield assumption: [6.7%]  (editable)
  LiquidBees income taxed at: [30%] (your slab rate, auto-filled)

Step 4: Transaction Costs
  Brokerage preset: [Zerodha Delivery ✓] [Flat 0.1%] [Custom]
  Brokerage rate: 0.50%
  STT (sell side): 0.10%
  Exchange + SEBI: 0.0334%

Step 5: Universe & Rebalancing
  Universe: [Nifty 50] [Nifty 100] [Nifty 500 ✓]
  Rebalancing: [Daily] [Weekly ✓] [Monthly]

Step 6: Hard Risk Limits
  Max position: 5%
  Max portfolio heat: 20%
  Drawdown circuit breaker: 25%

  [Save Configuration]
```

Changing any parameter triggers a re-evaluation banner: "Your cost/tax assumptions changed. Re-running simulation with new parameters (~45 minutes). Leaderboard will update tonight."

---

## 9. Integration with Existing Atlas Pipeline

**Dependency: runs AFTER existing compute pipeline.**

```
Existing nightly sequence (unchanged):
  stocks.py → regime.py → sectors.py → decisions.py → conviction.py

New sequence appended:
  incubator.py (this system)
    ↓ reads: atlas_stock_metrics_daily (raw metrics, not pre-computed states)
    ↓ reads: atlas_market_regime_daily (regime context)
    ↓ reads: atlas_sector_states_daily (sector context)
    ↓ reads: atlas_universe_membership_daily (point-in-time universe)
    ↓ writes: atlas_strategy_genomes, atlas_strategy_performance_daily
    ↓ writes: atlas_strategy_positions_daily, atlas_strategy_leaderboard
    ↓ writes: atlas_strategy_insights
```

**Bounded context rule:** `atlas.trading.*` does not import from `atlas.compute.*` or `atlas.intelligence.*`. It reads only from the database (shared kernel). No cross-context imports.

**EC2 compute estimate:**
- Data load: ~3 min (Nifty 500 × 10Y into RAM)
- 200 Optuna trials × ~15 sec each: ~50 min
- DEAP breeding: ~2 min
- Insight generation: ~3 min
- Total: ~60–75 min on t3.large (within nightly window)

---

## 10. What is NOT in scope (Phase 1)

| Item | Rationale |
|---|---|
| Broker integration (Kite/IBKR order placement) | Paper trading validates before live execution |
| IBKR global portfolio | India-first. Architecture is geography-agnostic for future extension |
| Intraday execution timing | EOD entry/exit is correct for momentum/RS strategy style |
| Options or derivatives | Equity only, Nifty 500 universe |
| Multi-user portfolio configs | Single user config for now |
| SEBI algo registration | Not needed during paper trading phase |

---

## 11. Success Criteria

The system is working when:

1. **Walk-forward equity curve tracks in-sample** — gap between in-sample and out-of-sample Sortino stays below 0.3 for promoted strategies
2. **Top-5 strategies beat Nifty 500 alpha** — all promoted strategies generate positive after-tax alpha over rolling 90-day periods
3. **Gene pool stays diverse** — diversity score above 0.5, indicating the engine is exploring the parameter space, not monoculturing
4. **Insight feed generates surprising-but-verifiable learnings** — findings like "1W RS matters more in trending regimes" are independently validated against the data
5. **Tax harvesting alerts save real money** — at least 3 LTCG conversion opportunities surfaced per quarter, with demonstrated tax savings

---

## 12. Open Questions

1. **Survivorship bias data availability:** Does Atlas's historical price data include delisted stocks? If not, `atlas_universe_membership_daily` must be bootstrapped from NSE historical index composition files.
2. **vectorbt RAM ceiling:** Nifty 500 × 10Y × 45 cols at float32 = ~313MB (500 stocks × 3,650 days × 45 cols × 4 bytes). Well within t3.large's 8GB. Multiple working copies during simulation (state matrices, signal matrices, portfolio arrays) may reach ~1.5GB total — still comfortable. No special memory management required.
3. **Genome naming:** Auto-generated genome IDs are not human-readable. Consider naming top promoted strategies descriptively ("RS-Aggressive-Regime-A") based on their dominant parameters.
4. **LiquidBees tax classification:** Post-April 2023 debt fund tax changes may classify LiquidBees income differently. Legal review recommended before treating as "income tax slab rate."

---

## 13. Premises (agreed during brainstorming)

1. The two-layer optimization problem (perception + decision) is the correct framing — optimizing only decision rules on fixed state definitions is insufficient.
2. After-tax, after-cost Sortino on walk-forward out-of-sample data is the honest performance metric.
3. Idle cash deployed in LiquidBees is the correct assumption for Indian equity portfolios.
4. vectorbt + Optuna + DEAP is the right tool stack — Atlas provides the validated signal pipeline, industry tools handle simulation and search.
5. India-first; architecture is geography-agnostic for future extension.
6. Progressive disclosure frontend (three layers) prevents the "scary dashboard" problem.
7. Nothing is hardcoded — all tax rates, costs, and universe parameters live in `PortfolioConfig`.

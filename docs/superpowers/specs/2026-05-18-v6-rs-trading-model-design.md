# v6 RS Trading Model — Design Spec

**Status:** Draft for review · **Author:** brainstorming session 2026-05-18 · **Branch:** `feat/v6-trading-model` (worktree at `../atlas-os-v6` off `main`)

---

## 1. Context & objective

Build a comprehensive Relative-Strength-based equity trading model for Indian markets that maximizes risk-adjusted alpha subject to hard risk constraints. "Relative strength" is interpreted broadly: not just trailing returns, but residual momentum, 52-week-high proximity, smoothness of trend, industry-decomposed RS, low-vol tilt, and quality — a multi-signal composite, not a single ranker.

### 1.1 Stated objective (operationalized)

> Maximize **Calmar (CAGR / |MaxDD|)** subject to:
> - annualized vol ≤ 0.9 × benchmark vol
> - max drawdown ≤ 0.7 × benchmark MDD
> - monthly win-rate ≥ 50%
> - alpha t-stat ≥ 1.5
> - per-signal OOS-IC retention ≥ 70% of in-sample IC
> - realistic capacity ≥ ₹1,500 crore
> - annualized turnover ≤ 200%
> - DD compliance ≥ 60% of OOS years (port_DD ≤ bench_DD that year)

Crisis behavior: the strategy is engineered to *make money in hard times* via a cross-asset crisis-alpha sleeve, not just go to cash. v0.1 ships with a partial sleeve (gold + G-Sec); full multi-asset TSMOM is v0.2.

### 1.2 Realistic expectations (do not exceed in claims)

| Metric | v0.1 target | v0.2 target | Benchmark (Nifty 500 TR) |
|---|---|---|---|
| Net CAGR | 20–24% | 22–28% | ~14–15% |
| Max drawdown | 22–28% | 16–22% | ~38–45% |
| Annualized vol | 13–15% | 11–14% | ~17–19% |
| Net Sharpe | 1.1–1.4 | 1.3–1.7 | ~0.7 |
| Calmar | 0.8–1.1 | 1.2–1.6 | ~0.35 |
| Win rate (monthly) | 52–56% | 52–58% | n/a |
| Realistic capacity | ₹1,500–2,000 cr | ₹1,500–2,000 cr | n/a |

Anything beyond v0.2 targets on backtest indicates overfitting or look-ahead bias — investigate before celebrating.

### 1.3 What materially differentiates this from existing Indian momentum products

| Differentiator | Why it matters |
|---|---|
| Residual momentum (Fama-French residualization) | ~2× Sharpe vs raw RS, materially less crashy. No retail product in India does this. |
| 9-module signal composite (vs single 12M return) | Diversification across orthogonal momentum-adjacent signals reduces single-factor failure risk. v0.1 = 3 v5-carry + 5 new + 1 price-based quality proxy (replaced by full quality composite in v0.2). |
| HRP portfolio construction | Avoids covariance-inversion blowups on the correlation-clustered momentum cohort; OOS Sharpe 30-40% better than equal-weight. |
| Cross-asset crisis sleeve (gold + G-Sec via TSMOM) | Positive P&L during equity drawdowns; products like N200M30 and Quant MF have zero crisis alpha. |
| Indian governance hard exclusions | Pledge/auditor/F&O ban filters — Quant MF's Adani saga is the cautionary tale. |
| Monthly rebalance with opportunistic intra-month adds | Matches Indian momentum's 3-4mo half-life; N200M30's semi-annual cadence is too slow. |
| Walk-forward + untouched 3y hold-out | Singleton-write enforced; can examine hold-out exactly once. Prevents the standard backtest curve-fit. |

---

## 2. Decisions captured (Q1-Q8 + architecture + branching)

| # | Decision |
|---|---|
| Q1 — Scope | Parallel rebuild in `atlas/trading/v6/` (clean module structure; v5 evolutionary lab stays on its branch as a comparator). |
| Q2 — Universe | Nifty 500 with point-in-time membership; ADV ≥ ₹5 crore floor. |
| Q3 — Hedging structure | Long equity + ETF crisis sleeve (gold + G-Sec) via cross-asset TSMOM. PMS-compatible, no F&O on the equity side. |
| Q4 — Objective function | Maximize Calmar subject to hard constraints (see §1.1). |
| Q5 — Signal stack | Full 7-signal addition target. v0.1 ships 5 of 7 (skip earnings revision + full quality until fundamentals data lands). |
| Q6 — Risk overlays | Full stack: HRP construction + Indian governance hard exclusions + issuer/sector caps + per-name and portfolio trend gates + square-root slippage. |
| Q7 — OOS protocol | Walk-forward rolling 36+12 across 2010-2022; untouched 3y hold-out 2023-2025 examined exactly once. OOS-IC retention ≥ 70% gate per signal. |
| Q8 — Cadence | Monthly rebalance with opportunistic intra-month adds (composite > 0.85 only); buffer zones to control turnover. |
| Architecture | Approach C — thin orchestrator + bounded-context modules per atlas-os "modular monolith" rule. |
| Branching | Worktree at `../atlas-os-v6` on new branch `feat/v6-trading-model` off `main`. |
| Data plan | Tier 1 + Tier 2 prerequisite data chunks (D1-D6) ship before any v6 code. Tier 3 (analyst consensus, fundamentals, P/B history) deferred to v0.2. |

---

## 3. Scope: v0.1 vs v0.2

### In scope for v0.1

- 9 signal modules (8 real signals + 1 placeholder):
  - Tier A (v5 carry, 3): `natr_14`, `beta_alpha_63d`, `mom_low_vol`
  - Tier B (new price-derivative, 3): 52WH proximity, FIP smoothness, industry-decomposed RS
  - Tier C (constructed factor, 2): residual momentum (3-factor Market+Size+WML, no HML), BAB low-beta tilt
  - Placeholder (1): price-based quality proxy (replaced with full quality composite in v0.2)
- HRP portfolio construction with per-name 5% cap, sector 25% cap, issuer-group 5% cap
- 5-signal macro regime composite with gross multiplier 0.20-1.10
- Vol-targeted gross exposure (12% annualized target)
- Per-name + portfolio 200dMA trend gates
- Cascaded drawdown circuit breaker (-8/-14/-20/-25)
- Cross-asset crisis sleeve: gold ETF (GOLDBEES) + G-Sec ETF (LIQUIDBEES or BHARAT BOND), 5-15% of book by regime
- Indian governance hard exclusions (pledge>30%, auditor quality, F&O ban, SME, group cap, audit qualifications)
- Square-root slippage model
- Walk-forward harness + Calmar-with-constraints goal-post + 3y untouched hold-out

### Deferred to v0.2 (explicit out-of-scope for v0.1)

- Signal 7: Earnings revision momentum (SUE + analyst revisions) — needs analyst consensus data
- Signal 9: Full quality composite (ROIC + GP/A + leverage + accruals) — needs quarterly fundamentals
- HML (value) factor in residual momentum — needs P/B history
- USDINR in crisis sleeve — needs futures wiring (or USD-equity ETF proxy)
- Counter-trend mean-reversion sub-strategy during extreme drawdowns
- Liquidity-provision premium harvesting
- LLM (SP07 Hermes) qualitative veto/promotion overlay on top-quintile names
- Long-short via stock futures
- ML-based signal combination (Gu-Kelly-Xiu approach)

### Explicit non-goals

- Beating any specific peer product
- Replacing the v5 evolutionary lab (v5 stays on `feat/atlas-strategy-lab` as comparator)
- Daily rebalance (cadence chosen as monthly + opportunistic intra-month adds)
- Pre-IPO / SME / unlisted exposure
- Crypto / commodities beyond gold ETF
- Custom indexing or factor exposures for clients

---

## 4. Module architecture & data flow

```
atlas/trading/v6/
├── __init__.py                  # public exports
├── lab.py                       # thin orchestrator (<250 LOC target)
├── universe.py                  # PIT Nifty 500 + ADV floor
├── signals/
│   ├── __init__.py
│   ├── v5_carry.py              # natr_14, beta_alpha_63d, mom_low_vol (lifted by copy)
│   ├── price_signals.py         # 52WH, FIP smoothness, industry-RS
│   ├── residual_momentum.py     # 3-factor (Mkt+SMB+WML) residualization, 12-1 cumulant
│   ├── bab.py                   # betting-against-beta (low-beta rank)
│   └── quality.py               # price-based quality proxy (v0.1 placeholder)
├── governance.py                # Indian hard-exclusion filters
├── composite.py                 # z-score blend, sector-neutralize, top-quintile selector
├── regime.py                    # 5-signal macro regime composite → gross multiplier
├── portfolio.py                 # HRP optimizer + caps
├── risk.py                      # vol-target, trend gates, DD circuit breaker, sqrt slippage
├── crisis_sleeve.py             # cross-asset TSMOM on gold + G-Sec ETFs
├── simulator.py                 # backtest engine
├── validator.py                 # walk-forward + OOS-IC retention + goal-post + hold-out gate
└── tax_engine.py                # STCG/LTCG (lifted from v5 — no changes)

tests/trading/v6/                # mirrors source tree, one test file per module
```

### Cross-context discipline

- v6 imports from `atlas.primitives`, `atlas.db`, `atlas.config` only
- No imports from `atlas.api`, `atlas.simulation`, or v5 internals
- v5 signal math copied into `signals/v5_carry.py` (not imported) to preserve modulith isolation
- File-size limits per CLAUDE.md: source ≤ 600 LOC, tests ≤ 800 LOC. Orchestrator `lab.py` target ≤ 250 LOC.

### Data flow at each rebalance date

```
1.  universe.get_investable(date)              → list[instrument_id]  (PIT + ADV)
2.  governance.apply_exclusions(list, date)    → filtered list        (pledge, auditor, F&O, SME, group)
3.  signals.compute_panel(list, date)          → (N × 8) signal matrix
4.  composite.score(panel)                     → sector-neutral composite score per name
5.  composite.select(scores, date)             → top-quintile cohort (~30-60 names)
                                                  + per-name 200dMA gate + buffer zones
6.  portfolio.allocate_hrp(cohort, history)    → HRP per-name weights (sum=1)
7.  portfolio.apply_caps(weights)              → capped (5% name, 25% sector, 5% issuer)
8.  regime.gross_multiplier(date)              → scalar 0.20-1.10
9.  risk.vol_targeted_gross(...)               → gross_after_vol_target ∈ [0.30, 1.10]
10. crisis_sleeve.allocate(date)               → sleeve weights (5-15% of book)
11. lab.merge_books(...)                       → final orders (equity book + crisis sleeve)
                                                  + slippage applied via square-root model
```

### Public API surface

- `lab.run_backtest(start, end, **opts) -> BacktestResult` — full walk-forward
- `lab.live_rebalance(date) -> list[Order]` — monthly production rebalance
- `lab.intramonth_scan(date) -> list[Order]` — only emits BUY orders when a NEW name crosses composite > 0.85. Intra-month adds are held until next monthly rebalance regardless of subsequent composite drift (no intra-month exits from opportunistic adds, except governance forced-exits and per-name 200dMA breach). Daily limit: max 2 opportunistic adds per day.
- `validator.evaluate_goal_post(strategy_id) -> dict` — replaces existing `goal_post.check_goal_post`

---

## 5. Signal computation

### 5.1 Tier A — v5 carry-over (3 signals, alphalens-validated)

Lifted by copy from `atlas/trading/data_loader.py` into `signals/v5_carry.py`. Unchanged math:

| Signal | Formula | DB columns |
|---|---|---|
| `natr_14` | ATR(14) / close × 100 | high, low, close |
| `beta_alpha_63d` | r_stock_63d − β · r_bench_63d | close, nifty500_close |
| `mom_low_vol` | ret_12m × (1 − vol_rank_cross_sectional) | ret_12m, realized_vol_63 |

### 5.2 Tier B — New price-derivative signals (3)

**52-week-high proximity (George-Hwang 2004):**
```
pct_from_52wh[i,t] = close[i,t] / max(close[i, t-251 : t+1])
rank_52wh = cross_sectional_pct_rank(pct_from_52wh)
```

**Frog-in-the-Pan smoothness (Gray & Vogel 2014):**
```
fip[i,t]    = (n_up_days - n_down_days) / 252      # over formation window
fip_signal  = fip × (ret_12m_1m > 0)               # only "smooth winners", not "smooth losers"
rank_fip    = cross_sectional_pct_rank(fip_signal)
```

**Industry-decomposed RS (Moskowitz-Grinblatt 1999):**
```
industry_rs[i,t] = ret_3m[i,t] - ret_3m_sector[sector(i), t]
rank_industry_rs = cross_sectional_pct_rank(industry_rs)
```
Sector returns come from `atlas_sector_metrics_daily`.

### 5.3 Tier C — Constructed factor signals (2)

**Residual momentum (Blitz-Huij-Martens 2011), 3-factor v0.1:**

Step 1 — build Indian factor returns daily series (stored in new table `atlas_factor_returns_daily`):
- `MKT` = Nifty 500 daily return − 91d T-bill
- `SMB` = top-200-mcap quintile-1 return − quintile-5 return (recomputed monthly)
- `WML` = top-decile-12-1 momentum return − bottom-decile (recomputed monthly)
- `HML` deferred to v0.2 — needs P/B history

Step 2 — per-stock residual:
```python
# On date t, for each stock i: regress trailing 252d daily returns
r_i = α_i + β_mkt·MKT + β_smb·SMB + β_wml·WML + ε_i
# Cumulate residual over 12-1 window
resid_12_1[i,t] = sum(ε_i[t-252 : t-21])
rank_residual = cross_sectional_pct_rank(resid_12_1)
```

**BAB low-beta tilt (Frazzini-Pedersen 2014):**
```
bab[i,t]   = -1 × cross_sectional_rank(beta_63d[i,t])
rank_bab   = cross_sectional_pct_rank(bab)
```

### 5.4 v0.1 quality proxy (placeholder for Signal 9)

```
quality_proxy[i,t] = -0.5 × rank(realized_vol_63)
                   - 0.3 × rank(max_drawdown_252d)
                   + 0.2 × rank(ret_consistency_252d)
```
Where `ret_consistency = ret_12m / |ret_12m_worst_quarter|`. Replaced with real fundamentals-based composite in v0.2.

### 5.5 Computation cadence

- All signals computed at **monthly rebalance EOD** for selection
- 52WH, FIP, industry-RS, BAB also computed **daily** to support intra-month opportunistic adds
- Residual momentum: **monthly only** (too expensive for daily)
- Intra-month adds rely on the 7 cheap signals; new names crossing composite > 0.85 trigger an opportunistic buy

### 5.6 API contract per signal module

Each signal module exposes one function:
```python
def compute(panel: pd.DataFrame, date: pd.Timestamp) -> pd.Series:
    """Return cross-sectionally-ranked signal in [0, 1], indexed by instrument_id."""
```
Common input shape; ranked output ready for composite blending.

---

## 6. Composite scoring, selection, HRP construction

### 6.1 Per-signal z-scores, sector-neutralized

```
raw_z[i, s, t] = (signal[i, s, t] - μ_signal_in_sector[sector(i), s, t])
                 / σ_signal_in_sector[sector(i), s, t]
```
Winsorize at ±3.

### 6.2 Signal weights (priors)

| Tier | Signals | Default weight (each) | Sum |
|---|---|---|---|
| A | natr_14, beta_alpha_63d, mom_low_vol | 0.15 | 0.45 |
| B | residual_momentum, 52wh, industry_rs | 0.13 | 0.39 |
| C | fip_smoothness, bab, quality_proxy | ~0.05 | 0.16 |

Total = 1.0. These are priors; SP04 Stage 4a-style Bayesian shrinkage on rolling OOS IC tunes them annually.

### 6.3 Composite score

```
composite[i, t] = Σ w[s] × z_clipped[i, s, t]       (range approx [-3.5, +3.5])
```

### 6.4 Selection

In order:
1. Re-apply liquidity floor (20d median traded value ≥ ₹5 crore)
2. Apply `governance.is_excluded(name, date)` — excluded → score = -∞
3. Per-name trend gate — `close[i,t] >= 200dMA[i,t]` required for entry
4. Top-quintile cohort by composite (with ~350-name universe, ~70 candidates)
5. Buffer zones (turnover control):
   - rank ≤ 30 → enter if not held
   - rank ≤ 50 → stay if held
   - rank > 50 → exit
6. Target 25-40 final holdings (HRP then trims to keeps post-floor)

### 6.5 HRP portfolio construction (López de Prado 2016)

Three steps on the selected cohort (~30 names):

```python
# 1. Cluster
corr           = panel.pct_change().tail(252).corr()
dist           = np.sqrt(0.5 * (1 - corr))
linkage_matrix = scipy.cluster.hierarchy.linkage(dist, method='single')
order          = quasi_diagonalize(linkage_matrix)

# 2. Recursive bisection (allocate by inverse cluster-variance)
def recursive_bisection(cov, items):
    weights = pd.Series(1.0, index=items)
    clusters = [items]
    while clusters:
        new = []
        for c in clusters:
            if len(c) <= 1: continue
            left, right = c[:len(c)//2], c[len(c)//2:]
            v_l, v_r = cluster_variance(cov, left), cluster_variance(cov, right)
            α = 1 - v_l / (v_l + v_r)
            weights[left]  *= α
            weights[right] *= (1 - α)
            new.extend([left, right])
        clusters = new
    return weights  # sums to 1.0

# 3. Apply caps in order
#   i.   single-name      ≤ 5%
#   ii.  sector            ≤ 25%
#   iii. issuer group      ≤ 5%
#   iv.  floor             drop names with weight < 0.5%, re-normalize
# Excess from binding cap redistributes to uncapped names in same cluster.
```

### 6.6 Sanity checks (become tests)

| Check | Expected |
|---|---|
| Σ weights | 1.000 ± 1e-6 |
| max single weight | ≤ 0.05 |
| max sector sum | ≤ 0.25 |
| max issuer-group sum | ≤ 0.05 |
| min weight (post-floor) | ≥ 0.005 |
| number of holdings | 20–45 |
| sum of dropped-below-floor | < 0.05 (else HRP isn't working) |

---

## 7. Risk overlays, regime composite, crisis sleeve

### 7.1 Governance hard exclusions

Six fail-open filters in `governance.py`. Missing data is *not* a reason to exclude.

| Filter | Rule | Data source |
|---|---|---|
| Promoter pledge | pledge_ratio > 30% → exclude | Chunk D5 |
| Auditor quality | mcap > ₹5,000cr AND auditor not in top-10 list → exclude | Chunk D6 |
| F&O ban | in F&O ban list → exclude from selection AND force-exit if currently held (sell at next-day open after ban-list publication) | Chunk D4 |
| SME segment | exchange_segment == 'SME' → exclude | master data |
| Group concentration | sum of weights in promoter_group > 5% → cap and redistribute | Chunk D6 |
| Audit qualification | qualification + auditor change in last 12mo → exclude | Chunk D6 |

Every exclusion appended to `atlas_v6_exclusions_log` for transparency.

### 7.2 Macro regime composite (5 signals)

| Signal | Bearish trigger | Refresh |
|---|---|---|
| Nifty 500 trend | close < 200dMA | daily |
| Breadth | % stocks above own 200dMA < 30% | daily |
| VIX term structure | India VIX 1m > 3m | daily |
| FII cash flow | trailing 3-week cumulative FII cash equity flow < -₹10,000cr | weekly |
| DXY strength | DXY 20d return > +2σ | daily |

`regime_score = sum_of_firing_signals (0..5)` → `gross_multiplier`:

| Score | Gross multiplier | Behavior |
|---|---|---|
| 0 | 1.10 | calm — slight over-invest |
| 1 | 1.00 | normal |
| 2 | 0.80 | yellow |
| 3 | 0.55 | orange |
| 4 | 0.35 | red |
| 5 | 0.20 | crash |

Hysteresis: regime must hold ≥ 3 trading days before stepping down; ≥ 5 days before stepping up (asymmetric — faster de-risk than re-risk).

### 7.3 Vol-targeted gross exposure

```
target_portfolio_vol = 12% annualized
recent_realized_vol  = EWM std of daily portfolio returns, λ=0.94, 63d
vol_scalar           = target_portfolio_vol / recent_realized_vol
gross_after_vol_target = clip(vol_scalar × regime_gross_multiplier, 0.30, 1.10)
```

### 7.4 Drawdown circuit breaker (portfolio-level)

| Portfolio peak-to-current | Action |
|---|---|
| -8% | halt new entries; existing positions tightened on stop loss |
| -14% | trailing stop 15% → 10%; exit rank-cutoff 50 → 35 |
| -20% | gross equity slashed to 30% over 3 days; sleeve to its ceiling |
| -25% | gross equity to 0 for 20 days; require user override to re-engage |

### 7.5 Per-name stops and trend gates

```
stop_distance[i] = max(15% × peak_price[i], 2.5 × ATR_14[i])
```
Triggered on close, not intraday.

Per-name trend gate (intra-month forced exit): name closing BELOW its 200dMA for 2 consecutive days → exit at next open.

### 7.6 Crisis sleeve (cross-asset TSMOM)

**v0.1 sleeve assets:** GOLDBEES (gold proxy), LIQUIDBEES or BHARAT BOND ETF (G-Sec proxy). USDINR deferred to v0.2.

**Allocation per asset (Moskowitz-Ooi-Pedersen 2012):**
```
signal[a]              = sign(12m_return[a]) × target_asset_vol / realized_vol_63[a]
positive_signal[a]     = max(signal[a], 0)    # long-only sleeve in v0.1
sleeve_asset_weight[a] = positive_signal[a] / Σ positive_signal
```
If both signals are zero, sleeve goes to cash (acceptable corner case).

**Sleeve sizing as % of book:**
```
sleeve_pct = 0.05 + 0.10 × (regime_score / 5)
```
Calm regime → 5% sleeve. Crash regime → 15% sleeve.

### 7.7 Square-root slippage model

```
slippage_bps[i, order_value] = 5 + 30 × sqrt(order_value / 20d_median_traded_value[i]) + 15
                              (capped at 100 bps)
```
The `+ 15` is explicit costs (STT 10 + exchange/GST/SEBI/stamp 5). Round-trip = entry + exit slippage.

### 7.8 Final order construction

```python
equity_book = equity_cohort_weights × (1 - sleeve_pct) × gross_after_vol_target
sleeve_book = sleeve_weights        × sleeve_pct       × gross_after_vol_target
cash_pct    = 1 - sum(equity_book) - sum(sleeve_book)
orders      = diff(current_positions, equity_book ∪ sleeve_book)
              with slippage_bps applied to each line
```

### 7.9 Sanity checks (become tests)

| Check | Expected |
|---|---|
| Σ(equity_book) + Σ(sleeve_book) + cash_pct | 1.000 ± 1e-6 |
| Σ(equity_book) | ≤ 1.10 |
| cash_pct when regime_score=5 | ≥ 0.50 |
| sleeve_book when both 12m returns ≤ 0 | == 0 |
| Names in F&O ban list at next rebalance | weight == 0 |
| gross_after_vol_target | ∈ [0.30, 1.10] |

---

## 8. Validation: walk-forward, OOS-IC, goal-post, hold-out

### 8.1 Walk-forward windows (2010-01 → 2025-12)

```
Train       : 2010-01 → 2014-12  (60 months)
OOS-1       : 2015-01 → 2015-12  (refit on 2010-2014)
OOS-2       : 2016-01 → 2016-12  (refit on 2010-2015)
…
OOS-8       : 2022-01 → 2022-12  (refit on 2010-2021)
HOLD-OUT    : 2023-01 → 2025-12  (3y, examined exactly once at end)
```

Annual refit: at each year-end (last trading day of the calendar year, IST close), run weight optimization (Bayesian shrinkage on rolling 36mo OOS IC). New weights are written to `atlas_signal_weights` with `effective_from = first_trading_day_of_next_year` and applied from that date.

### 8.2 OOS-IC retention gate

```
OOS_IC / IS_IC ≥ 0.70    (per signal, computed on 21d forward returns)
```
A signal failing this gate for 2 consecutive refits → auto-shelved (weight forced to 0) until recovery.

### 8.3 Hold-out singleton enforcement

`atlas_v6_strategy_runs.holdout_examined_at` is a singleton timestamp. Examining hold-out before all 8 OOS windows are exhausted raises. After examination, weights are frozen and cannot be re-optimized using hold-out results — that path is closed off in code, not just convention.

### 8.4 Goal-post (replaces existing `atlas/trading/goal_post.py`)

Primary objective: **Calmar**. Hard constraints (all must pass):

| # | Constraint | Threshold |
|---|---|---|
| C1 | Calmar | ≥ 1.0 |
| C2 | Annualized vol | ≤ 0.9 × benchmark |
| C3 | Max drawdown | ≤ 0.7 × benchmark MDD |
| C4 | Monthly win rate | ≥ 50% |
| C5 | Alpha t-stat | ≥ 1.5 |
| C6 | OOS-IC retention | ≥ 70% per signal |
| C7 | Realistic capacity | ≥ ₹1,500 crore |
| C8 | Annualized turnover | ≤ 200% |
| C9 | DD compliance | ≥ 60% of OOS years (port_DD ≤ bench_DD) |

Plus: ≥ 10 HIGH-confidence (composite > 0.85) recommendations on latest date (retains the v5 final criterion).

---

## 9. Database schema additions

Migration 080 creates the following in `atlas` schema:

```sql
atlas_index_membership (
    index_name TEXT,             -- 'NIFTY_500', 'NIFTY_100', etc.
    instrument_id UUID,
    valid_from DATE,
    valid_to DATE,               -- NULL = currently a member
    PRIMARY KEY (index_name, instrument_id, valid_from)
)

atlas_factor_returns_daily (
    date DATE PRIMARY KEY,
    mkt_excess NUMERIC(10,6),
    smb        NUMERIC(10,6),
    wml        NUMERIC(10,6),
    hml        NUMERIC(10,6)     -- NULL in v0.1
)

atlas_macro_daily (
    date DATE PRIMARY KEY,
    usdinr                  NUMERIC(10,4),
    dxy                     NUMERIC(10,4),
    india_10y_yield         NUMERIC(8,4),
    risk_free_91d           NUMERIC(8,4),
    fii_cash_equity_flow_cr NUMERIC(14,2),
    breadth_pct_above_200dma NUMERIC(5,2)
)

atlas_governance_master (
    instrument_id            UUID PRIMARY KEY,
    promoter_group           TEXT,
    auditor_name             TEXT,
    auditor_is_top_10        BOOLEAN,
    last_auditor_change_date DATE,
    last_qualified_audit_date DATE
)

atlas_governance_daily (
    instrument_id        UUID,
    date                 DATE,
    pledge_ratio_pct     NUMERIC(6,2),
    in_fno_ban_list      BOOLEAN,
    PRIMARY KEY (instrument_id, date)
)

atlas_v6_strategy_runs (
    run_id                  UUID PRIMARY KEY,
    strategy_name           TEXT,
    signal_weights          JSONB,
    is_period               TSRANGE,
    oos_period              TSRANGE,
    calmar                  NUMERIC,
    vol_ratio               NUMERIC,
    mdd_ratio               NUMERIC,
    win_rate                NUMERIC,
    alpha_t_stat            NUMERIC,
    oos_ic_retention        NUMERIC,
    capacity_cr             NUMERIC,
    turnover_annual         NUMERIC,
    dd_compliance           NUMERIC,
    passes_all_constraints  BOOLEAN,
    constraint_failures     TEXT[],
    holdout_examined_at     TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW()
)

atlas_v6_exclusions_log (
    instrument_id  UUID,
    date           DATE,
    reason         TEXT,
    weight_before  NUMERIC,
    weight_after   NUMERIC,
    PRIMARY KEY (instrument_id, date, reason)
)

atlas_v6_recommendations_daily (
    date             DATE,
    instrument_id    UUID,
    composite_score  NUMERIC,
    weight_in_book   NUMERIC,
    rank             INT,
    confidence_band  TEXT,         -- 'HIGH' (>0.85), 'MED' (>0.65), 'LOW'
    PRIMARY KEY (date, instrument_id)
)
```

No backward-incompatible changes to v5 tables. v6 is additive.

---

## 10. Prerequisite data chunks (D1-D6)

Ship before any v6 signal code.

| Chunk | Scope | Lift | Output |
|---|---|---|---|
| D1 — PIT Nifty 500 membership | Scrape NSE historical reconstitution semi-annual (2010-present); fill `atlas_index_membership` | 1-2 days | Membership 2010-2025 |
| D2 — ETF coverage gap-fill | Confirm GOLDBEES + LIQUIDBEES + BHARAT BOND in `atlas_etf_metrics_daily` with ≥10y history; backfill from Yahoo/NSE if gaps | 0.5 day | Sleeve ETFs ready |
| D3 — Macro daily series | USDINR (RBI), DXY (Yahoo), India 10Y (CCIL), 91d T-bill (RBI), FII flows (NSE/SEBI), breadth computed | 1 day | `atlas_macro_daily` populated |
| D4 — F&O ban daily | NSE EOD ban list; daily cron + historical backfill from NSE archive | 1 day | `atlas_governance_daily.in_fno_ban_list` populated |
| D5 — Promoter pledge quarterly | NSE/BSE quarterly shareholding pattern parse + load | 1.5 days | `atlas_governance_daily.pledge_ratio_pct` (forward-filled) |
| D6 — Auditor + promoter group | One-time scrape (Screener.in + NSE) + annual refresh job | 1 day | `atlas_governance_master` populated |

**Total prerequisite work: ~5-6 working days of plumbing.** No synthetic data — global rule.

---

## 11. Build sequence (input to writing-plans)

```
Phase 0 — Prerequisites              (5-6 days, parallelizable)
  D1, D2, D3, D4, D5, D6
  Migration 080

Phase 1 — Foundation                 (3-4 days)
  universe.py (PIT + ADV floor)
  signals/v5_carry.py
  signals/price_signals.py (52WH, FIP, industry_RS)
  signals/bab.py
  signals/quality.py (price-based proxy)

Phase 2 — Residual momentum          (2-3 days)
  signals/residual_momentum.py
  Factor returns daily compute job

Phase 3 — Composite + selection      (2 days)
  composite.py + per-name trend gate + buffer zones

Phase 4 — Portfolio construction     (2-3 days)
  portfolio.py (HRP + caps)

Phase 5 — Risk overlays              (3 days)
  governance.py, regime.py, risk.py

Phase 6 — Crisis sleeve              (2 days)
  crisis_sleeve.py (gold + G-Sec TSMOM)

Phase 7 — Orchestrator + simulator   (3 days)
  lab.py + simulator.py

Phase 8 — Validator + walk-forward   (3 days)
  validator.py + walk-forward harness + hold-out singleton enforcement

Phase 9 — Initial run + IC check     (2 days)
  Run 2010-2022 walk-forward; identify failing signals

Phase 10 — Weight optimization       (3 days)
  Bayesian shrinkage optimizer; candidate weight sets

Phase 11 — Hold-out evaluation       (1 day, terminal)
  Examine 2023-2025 exactly once; final report

Total v0.1: ~30-35 working days
```

v0.2 (earnings revision + full quality composite + HML factor + USDINR + LLM overlay) is a separate spec.

---

## 12. Testing strategy

Three layers under `tests/trading/v6/`:

**Layer 1 — unit tests, fixture data, fast (<1s):**
- Each signal: known-input → known-output golden test
- HRP: 5-name cohort with hand-computed correlation matrix
- Governance: each filter triggered on synthetic edge case (pledge 30.01% / 29.99%)
- Regime composite: each of 5 signals fired individually
- Sanity-check assertions from Sections 6.6 and 7.9

**Layer 2 — integration tests, sample DB (~30s):**
- 30 instruments × 252 days, real (anonymized) OHLC
- Full `lab.run_backtest()` end-to-end
- Verify DB writes + schema constraints
- Regression: v5 signal numbers must match pre-carry-over outputs exactly

**Layer 3 — full backtest validation (nightly):**
- Full 16y on PIT Nifty 500 universe
- Goal-post evaluation, write to `atlas_v6_strategy_runs`
- Regression alert if Calmar / MDD ratio drift > 5% vs prior run

**Coverage target:** 80% on new code (global rule).

---

## 13. Open questions / known unknowns

1. **GOLDBEES + G-Sec ETF coverage** — chunk D2 will confirm; if either has < 10y history, the sleeve OOS window shrinks and the crisis-alpha case weakens. Mitigation: use Yahoo `^GLD` and a G-Sec yield proxy until ETF history matures.
2. **Promoter group source reliability** — Screener.in is the cheapest source but not authoritative on edge cases (private placements between group entities). Plan: cross-check NSE for top 50 groups, accept Screener for tail.
3. **Buffer-zone tuning (30/50 vs 25/40 vs 35/60)** — academic default chosen. Walk-forward should be insensitive across this range; if not, re-examine.
4. **HRP correlation window (252d vs 63d vs 504d)** — 252d default. May test 63d in v0.2 for regime-adaptive HRP.
5. **Intra-month opportunistic-add threshold (composite > 0.85)** — picked to limit to ~1-2 names/month average. Will tune in Phase 9 if too noisy or too quiet.
6. **Stage 4a Bayesian weight optimizer reuse** — assumed compatible with v6 panel format; needs validation in Phase 10.

---

## 14. Out of scope (explicit)

- Pre-IPO, SME, unlisted, mid-cycle delisted names
- F&O on the equity side (futures appear only in v0.2 sleeve via USDINR)
- Daily rebalance
- ML-based signal combination (Gu-Kelly-Xiu approach) — flagged for v0.3+
- LLM (SP07 Hermes) qualitative overlay — v0.2 candidate
- Long-short via stock futures
- Multi-currency exposure beyond gold ETF and v0.2 USDINR

---

## 15. Acceptance for sign-off on this spec

This spec is the input to `superpowers:writing-plans`. Before transitioning:

- [ ] User reviews the document end-to-end
- [ ] Open questions in §13 noted as Phase-9 decisions (acceptable)
- [ ] Realistic expectation table (§1.2) accepted as the truth
- [ ] Tier-3 deferrals (§3) accepted

Sign-off line below:

```
Approved by: ___________________   Date: ___________
```

# Atlas v4 — Build Blueprint (the comprehensive view, before the loop)

> One engine, every lens, every altitude. Built **inside** current Atlas as a bounded
> context — a **strict superset** of today: better on every axis, losing nothing.
> The FM already trusts the current surfaces, so we **evolve and clean**, never redesign.
> This is the goal the gated build-loop drives toward; nothing builds until it's signed off.

---

## 1. The spine — a flow of information

```
REGIME  (market state: Risk-On … Risk-Off + deploy multiplier)
  │   sets context / risk appetite
  ▼
SECTOR  (22 actionable NSE sectors)         ← 6-lens sector vector + breadth + dispersion
  │   which sectors lead, on which lens
  ▼
INSTRUMENT
   ├─ STOCK   = the ATOM (6-lens vector, the unit of truth)
   ├─ ETF     = holdings-weighted roll-up of stock lenses + tracking quality
   ├─ FUND    = holdings-weighted roll-up + active tilt vs benchmark
   └─ INDEX   = its constituents (stocks) aggregated
  │   rank within sector/type → drill to the instrument
  ▼
PORTFOLIO  (model portfolios + 25y backtest, built on the same lens vectors)
```

Every page is a step in this drill: **Regime+Pulse → Sector → Sector deep-dive → instrument
type (stock/ETF/fund) ranking → instrument deep-dive → build/backtest a portfolio.**

## 2. The atom — the daily instrument object (the baseline)

For each of ~2,000 stocks, recomputed **daily**: **6 lenses, each a composite of 3–5
orthogonal subcomponents (~20–24 readings total)** + a transparent overall composite +
conviction tier + visible risk flags. Stored in `atlas.atlas_lens_scores_daily`
(instrument_id, date, the 6 lens scores, every subcomponent, composite, tier, risk_flags,
evidence refs). **The same vector is fractal** — it rolls up unchanged to sector
(cap-weight + breadth + dispersion), to ETF/fund (holdings-weight + active-tilt-vs-benchmark),
and indices (constituent aggregation). One object, three altitudes.

## 3. The six lenses (final, de-duplicated) — see `atlas-six-lens-data-spec.md` for fields

| # | Lens | Subcomponents | Source |
|---|---|---|---|
| 1 | **Technical** | Trend (EMA stack) · Relative Strength (vs N500 + sector) · Volatility Contraction (ATR/BB) · Volume/Participation | Kite `technical_daily` ✅ |
| 2 | **Fundamental** | Profitability (ROCE/ROE) · Margin trajectory · Growth · Balance-sheet | TV levels (daily) + **NSE XBRL** trends (P&L quarterly / BS annual) |
| 3 | **Valuation** | Relative cheapness (vs sector median) · Absolute cheapness | TV `tv_metrics` ✅ |
| 4 | **Catalyst** | Earnings · Capital actions · Governance — recency-weighted | NSE/BSE filings |
| 5 | **Flow** | Promoter/insider · Institutional Δ · Smart-money/bulk deals | NSE/BSE PIT + shareholding + deals |
| 6 | **Policy** | Sector tailwind | Registry |
| ⚑ | Risk flags | auditor/CFO/downgrade · pledge spike · solvency | derived — *visible, never hides* |

Metric-level double-counting eliminated (ROCE/margin/200-DMA counted once); the merged
Fundamental lens replaces Theta's quality+op-leverage. Valuation is a **neutral descriptor**.

## 4. Scoring, conviction, learned weights

- Subcomponents → lens composite (smooth functions, no cliff edges) → overall composite
  (renormalized over lenses-with-data → graceful partial coverage) + convergence on
  *orthogonal* agreement → **conviction tier**.
- **Every score is evidence-linked** — it carries its contributing events/metrics and their
  point contribution. A Flow 80 *is* "Promoter +₹50Cr (15-Jun) · superstar entry · FII +1.3%";
  a Catalyst score links the actual filing. Big events surface as flags + a daily "what changed" feed.
- **Two views over one vector:** Discovery (Flow/Fundamental/Policy-led) and Momentum
  (Technical/RS-led). The composite and 2×2 are **views you sort** — never gates.
- **Weights live in `atlas_thresholds`** and are **learned via the IC loop** (priors → IC
  attribution vs forward returns → walk-forward validated), **bootstrapped on 25y at build time.**

## 5. Strict superset of current Atlas — preserve / improve map

*(from the live capability inventory — nothing on the left is dropped)*

| Current Atlas capability | In v4 |
|---|---|
| **22 actionable sectors** + `atlas_sector_rollup` (8 thin-tail merges) | **Preserved** as the roll-up key; sector gains the full 6-lens vector |
| **Drift ×4** (signal-call Z, weight-set IC auto-revert, component-validation badges, validator distribution) | **Preserved**; the IC loop *is* the natural home for #2–3; drift feeds risk flags + recalibration |
| **Regime ×2** (v6 4-state + legacy deploy-multiplier) | **Preserved** — it's the top of the spine (sets context) |
| **Conviction** (verdict + 0–100 + ELI5 + rule decomposition) | **Becomes the composite** — keep the ELI5 + decomposition; now evidence-linked across 6 lenses |
| **RS 7-tier + breadth** (market & sector) | **Preserved** — Technical-lens subcomponents (RS, breadth) |
| **ETF/fund scorecards** (TE, holdings conviction, style, cost) | **Preserved + reframed** as the holdings-weighted 6-lens roll-up + tracking quality |
| **IC / walk-forward / 24-cell / CTS** | **Reused as the learning loop** — lenses become signals in the existing IC/weight machinery |
| **Calls / ledger / paper-portfolio** (realized win-rate per cell, drift status) | **Preserved** — the accountability spine; lens conviction stays trackable to realized excess |
| **Intraday (Kite WS) / TV signals / discovery** | **Preserved** |
| **Thresholds-in-DB, audit immutability, SEBI ledger-public** | **Preserved** (hook-enforced) |

## 6. Frontend — evolve & clean, don't redesign (FM familiarity is a feature)

The 6-lens data flows into the **existing** surfaces; navigation/look stays. Per surface:

| Surface | Keep | Enrich with lenses | Debt to clean |
|---|---|---|---|
| **Home: Regime + Pulse** | regime hero, breadth, RS leaders | regime sets the lens context strip | **merge Pulse into Home** + drop Participation/old charts (already specced in `markets-today-redesign.md`) |
| **Sectors + deep-dive** | RRG, heatmap, constituents | sector **6-lens vector** + breadth + dispersion; lead-lag by lens | consolidate duplicate sector panels |
| **Stocks / ETFs / Funds** | tables, sparklines, gates, peer matrix | **ranking by any lens/composite** + deep-dive = the lens vector + **evidence drill-down** | de-dupe overlapping list/detail components |
| **Calls** | win-rate matrix, ledger | calls tagged with the lens vector at trigger | — |
| **Portfolios** | KPIs, equity curve, policy | **model portfolios + 25y backtest** on lens signals | unify static/rule-based shells |
| **Health / Admin** | validator, freshness, thresholds, IC weight-perf | lens-feed freshness + lens IC weight-proposals | — |

**Debt cleanup is an explicit step (W0.5):** a frontend-debt audit identifies redundant/dead/
duplicate components to remove (starting from the inventory + the `markets-today-redesign` cuts),
so v4 ships *leaner* than today, not heavier. Ponytail enforces minimalism per-commit.

## 7. The two loops

- **Build loop** — orchestrated, gated waves; each stage has a written goal + a test gate; agents
  loop until green; human checkpoints at boundaries. (W0→W7 below.)
- **Runtime IC loop** — weights & signal-selection learned from forward-return attribution,
  walk-forward gated, **bootstrapped on 25y at build time** (the engine ships calibrated, then
  refines nightly). Reuses Atlas's existing `atlas_signal_ic` / `atlas_signal_weights` machinery.

## 8. Build plan (waves → gates)

| Wave | Goal | Gate |
|---|---|---|
| **W0** | this blueprint signed off | human approval |
| **W0.5** | frontend-debt audit + lock cleanup list | reviewed list |
| **W1** | `atlas/lenses` context + `atlas_lens_scores_daily` + thresholds + migrations | schema applies clean |
| **W2** | 6 lens scorers (pure, ported from Theta + new Technical) | each passes unit tests *(6 agents parallel)* |
| **W3** | composite + fractal roll-up (sector/ETF/fund/index) | golden-case tests |
| **W4** | feeds: XBRL fetcher+parser, NSE/BSE catalyst+flow, widen `tv_metrics`→2000+nightly | coverage + harness green |
| **W5** | IC calibration on 25y journal → learned weights | walk-forward IC ≥ floor |
| **W6** | frontend: lens vector into existing surfaces + evidence drill-down + what-changed feed | visual/contract tests |
| **W7** | nightly pipeline: all feeds daily + recompute all lenses + refresh views + alerts | end-to-end dry-run |

## 9. Decisions to lock before the loop
1. **Frontend-debt audit scope** — run W0.5 as a dedicated audit pass? (recommend yes)
2. **Sector aggregation** — cap-weighted (recommend) vs equal-weight, and fund-holdings cadence (monthly).
3. **IC objective** — forward risk-adjusted return at 1m/3m/6m (recommend), per-lens horizon calibration.
4. **Cutover** — run v4 behind a flag in parallel, switch when the core is green (tomorrow-night target).

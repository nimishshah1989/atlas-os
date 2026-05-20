# Atlas Strategy Marketplace — v1 Design Spec

**Date:** 2026-05-20
**Worktree:** atlas-os-consolidation · branch `feat/atlas-consolidation`
**Status:** Design — pending user review
**Builds on:** [Decision Engine](2026-05-20-atlas-decision-engine-design.md) (Waves 1-3), [State Engine](2026-05-18-atlas-state-engine-design.md)

## What this is

A self-running marketplace of trading strategies. A generator produces a large
population of strategies — hundreds to thousands. Every strategy runs on a paper
book from Day Zero. The marketplace surfaces to the fund manager the few that
have *earned trust*: consistent live performance across regimes, plus a clean,
inspectable, decision-by-decision audit trail. Strategies that decay are
retired; the generator replenishes. No real-money execution in v1 — paper only.

## Why

The fund manager is starting to trust Atlas. He will deploy a strategy only
after he can interrogate its **consistency across regimes, its logic, and the
audit trail behind every decision** — not because a leaderboard ranks it #1.
The marketplace runs many strategies cheaply and honestly, and surfaces the ones
an experienced manager can build conviction in.

## The core distinction (the discipline that keeps this honest)

- **Generation is broad.** Thousands of strategies generated and running. Cheap
  — the compute is not the constraint.
- **Surfacing is disciplined.** What reaches the fund manager is ranked and
  filtered by **live forward performance** and **consistency across regimes** —
  never by backtest rank. A backtest is a starting credential, not a selector.
  At any moment only a handful are *surfaced as trusted* — that is an output of
  the filter, not a cap on what runs.

## Scope — v1

**In:**
- **Generator** — produces a large population of strategies by sampling the
  Policy-field space (entry states, RS/rank thresholds, sizing caps, exits,
  universe, cadence). Each strategy is a Policy row. Origin `system` or `manual`.
- **A generic, Policy-parameterized, vectorized strategy engine** — runs any
  generated Policy through the 6-step decision flow, batched across the whole
  population. This is the core build (see "The engine" below).
- **Paper-trading from Day Zero** — every strategy holds a paper book, marked to
  market each cadence.
- **Day-Zero credential** — a regime-segmented backtest per strategy, shown
  explicitly as "backtested — not yet live-proven."
- **Live surfacing** — a marketplace page ranking/filtering by live performance
  + regime consistency; the trusted few surface, the population runs behind.
- **Retirement** — strategies that fail to beat their benchmark over a
  configurable window (default: 3-6 months live) are retired; the generator
  refills the freed slots.
- **Audit trail** — per strategy, a decision-by-decision log: every BUY / TRIM /
  EXIT with the triggering signal. Core scope, not polish.

**Out (later / never in v1):**
- Real-money / broker execution. Atlas proposes; v1 stays paper.
- Fund-manager-authored strategies via a UI builder (v1 `manual` strategies are
  authored as config/seed; a UI builder is a later phase).

## The engine — the core build

`atlas/trading/lab.py` today runs only `V5-RP-TREND` with four flag modes; it
does not consume a parameterized strategy. v1's central engineering is a
**generic strategy engine** that:
1. Takes any Policy as input.
2. Runs the 6-step decision flow under it (regime cap → sector targets →
   instrument selection by entry rules → conviction → act → deterioration).
3. Is **vectorized** — evaluates the whole population over the OHLCV/state panel
   in batch, so thousands of strategies backtest and paper-update cheaply.
4. Emits, per strategy per cadence, the trades AND the audit-trail rows.

Everything else (generator, surfacing page, retirement rule) is lighter and
sits around this engine.

## Data model

- A strategy **is a Policy** — `atlas_portfolio_policy` (migration 092) plus new
  columns: `name`, `origin` (`system`/`manual`), `lifecycle_status`
  (`candidate` / `surfaced` / `retired`), `generated_at`.
- Each strategy owns a **paper portfolio** — built on the Decision Engine Wave 3
  portfolio model + the Wave 4 paper book.
- **Decision audit log** — every BUY/TRIM/EXIT per strategy with the triggering
  signal. Reuse where possible: `atlas_strategy_recommendations_daily` and
  `atlas_state_action_log` already carry per-decision rows; extend/join rather
  than duplicate. A dedicated `atlas_strategy_decision_log` is the likely home
  (resolved in the plan).
- **Performance + ranking** — reuse `atlas_strategy_leaderboard` (incl. the
  `regime_breakdown` JSONB) and `atlas_strategy_validation` (per-year backtest).
- Backtest credential: reuse the genome/validation tables; the new vectorized
  engine replaces the V5-only `lab.py` path.

## Day Zero vs ongoing

- **Day Zero:** the generator seeds the population; each strategy is backtested
  over available history (~10y), regime-segmented. The marketplace page ranks by
  this backtest credential — explicitly labelled "backtested, not yet
  live-proven." (`V5-RP-TREND`, already proven, seeds as a `manual` strategy.)
- **Ongoing:** every strategy paper-trades forward. Live performance accumulates
  and **the ranking shifts from backtest credential to live track record.** The
  page always shows both, with live flagged as the one that counts. Retirement
  and replenishment run on the live record.

## The inspectable surface

The marketplace page, and per strategy:
1. **The rules** — plain-language statement of the Policy.
2. **Regime-segmented track record** — backtest (labelled) + live paper, by
   regime.
3. **The audit trail** — chronological, filterable: every decision, the
   instrument, the date, the state transition / signal that triggered it, the
   position size and which caps bound it.
4. **The current paper book** — what the strategy holds now.
5. **Filters** — regime, horizon, universe, origin (`system`/`manual`),
   consistency window. System vs manual visually distinguished.

## Surfacing must be breadth-aware

With thousands running, "best over a short window" contains luck even on live
data. The surfacing filter therefore requires **consistency across more than one
regime** and scales the required live track-record length to the population
size. This is a tunable parameter of the ranking, not a separate feature — it is
the live-data form of the discipline above.

## Dependencies

Decision Engine Waves 1-3 must land first (Policy model, portfolio/paper model,
the 6-step flow). The marketplace is effectively Decision Engine Wave 4 — the
generator, the vectorized engine, the surfacing page, retirement — built on that
foundation.

## Success criteria

1. The generator seeds and maintains a population of hundreds+ strategies, all
   paper-trading.
2. The marketplace page surfaces strategies ranked by live performance, filtered
   by regime consistency; the fund manager sees the trusted few.
3. Any strategy can be opened and every paper decision traced to its signal.
4. Backtest vs live-paper is unambiguous everywhere.
5. Decaying strategies retire automatically; the generator replenishes.

## Open questions

1. **Generator sampling** — pure random over Policy-space, grid, or mutate
   live-winners (genetic). v1 can start with random + grid; mutation later.
2. **Vectorized engine boundaries** — how much of the 6-step flow vectorizes
   cleanly vs needs a per-strategy loop. An implementation-plan decision.
3. **Audit-log storage** — dedicated `atlas_strategy_decision_log` vs extending
   `atlas_strategy_recommendations_daily`. An implementation-plan decision.

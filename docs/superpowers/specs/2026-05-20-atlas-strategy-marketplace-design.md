# Atlas Strategy Marketplace — v1 Design Spec (the Strategy Shelf)

**Date:** 2026-05-20
**Worktree:** atlas-os-consolidation · branch `feat/atlas-consolidation`
**Status:** Design — pending user review
**Builds on:** [Decision Engine](2026-05-20-atlas-decision-engine-design.md) (Waves 1-3), [State Engine](2026-05-18-atlas-state-engine-design.md)

## What this is

A **shelf of 3-5 hand-authored trading strategies** the fund manager can inspect, build conviction in, and later deploy. Each strategy is a Policy run through the Decision Engine's 6-step flow on a paper book. v1 is the wedge of a larger "Strategy Marketplace" vision — the generator agent and marketplace dynamics come later. v1's only job: earn the fund manager's trust in a small, fully-inspectable set.

## Why

The fund manager is starting to trust Atlas. He will deploy a strategy only after he can interrogate its **consistency across regimes, its logic, and a decision-by-decision audit trail** — not because a leaderboard ranks it #1. v1 makes a few strategies that interrogable.

## Scope — v1

**In:**
- 3-5 hand-authored strategies. One wraps the proven `V5-RP-TREND`; 2-4 more are deliberately authored (each is a Policy row).
- Per strategy: a **regime-segmented backtest** track record — the Day-Zero credential.
- Per strategy: **paper-traded from Day Zero forward**; a live track record accumulates and becomes the primary trust signal over time.
- Per strategy: an **inspectable surface** — the rules in plain language, and a decision-by-decision audit log.
- A **shelf page**: the 3-5 strategies, each with its regime-segmented record and a link into its audit trail.

**Out (later phases, explicitly deferred):**
- The generator agent (hundreds/thousands of strategies).
- Marketplace dynamics — strategies competing, auto-retiring, filter UI.
- Real-money execution.
- Fund-manager-authored strategies via UI (v1 strategies are authored as config/seed).

## Locked premises

1. v1 is a small hand-authored set (3-5), **not** a generator. The generator is a later phase.
2. v1 is a **strategy shelf**, not a live marketplace — no competing/retiring dynamics. The name "Marketplace" is kept for the vision; v1 delivers the shelf.
3. On Day Zero the only evidence is a backtest. That is acceptable **only if labelled honestly** — "backtested, not yet live-proven." Live paper results accrue from Day Zero and progressively become the trusted signal.
4. The audit trail is **core scope**, not polish — it is the adoption gate.
5. This **depends on Decision Engine Waves 1-3** (the Policy model, the portfolio/paper model, the 6-step flow).

## Data model

- A strategy **is a Policy** — `atlas_portfolio_policy` (migration 092) plus three new columns: `name` (text), `origin` (`system` / `manual`), `lifecycle_status` (`shelf` for v1; the generator will later use other values).
- Each strategy runs a **paper portfolio** — the Decision Engine Wave 3 portfolio model + the Wave 4 paper book.
- New: a **decision audit log** — every BUY / TRIM / EXIT a strategy's engine takes, with the triggering signal. Partly reusable: `atlas_strategy_recommendations_daily` and `atlas_state_action_log` already carry per-decision rows; v1 extends/joins these per strategy rather than inventing a new table where they suffice.
- Backtest: reuse `atlas/trading/lab.py`, `atlas_strategy_validation` (per-year results), and `atlas_strategy_leaderboard.regime_breakdown` (JSONB) for the regime segmentation.

## How a strategy runs

Each strategy is the Decision Engine's 6-step flow executed under its own Policy. On the Policy's cadence: regime deployment cap → sector targets → instrument selection (entry rules) → conviction check → paper "act" → deterioration check. **Every step's decision is written to the audit trail** with the signal that drove it.

## Day Zero vs ongoing

- **Day Zero:** backtest each of the 3-5 over the available history (~10y), segmented by regime. Shown as a credential, explicitly labelled "backtested — not yet live-proven."
- **Ongoing:** each strategy paper-trades from Day Zero. The shelf page shows the backtest record **and** the accumulating live-paper record side by side; the live record is clearly flagged as the one that counts.

## The inspectable surface (the core deliverable)

Per strategy, the fund manager can see:
1. **The rules** — a plain-language statement of the Policy (entry states, RS/rank thresholds, sizing caps, exits, universe, cadence).
2. **Regime-segmented track record** — backtest (labelled) and live paper (as it accumulates), broken out by regime.
3. **The audit trail** — a chronological, filterable log: every BUY / TRIM / EXIT, the instrument, the date, the state transition or signal that triggered it, the position size and which caps bound it.
4. **The current paper book** — what the strategy holds now.

## Dependencies

Decision Engine Waves 1-3 must land first (Policy model, portfolio/paper model, the 6-step flow). v1 is effectively "Decision Engine Wave 4, scoped to 3-5 hand-authored strategies, plus a shelf page."

## Forward-compatibility

The shelf is designed so the generator can later feed it with **zero rework**: a generated strategy is just another Policy row with `origin='system'`. The marketplace dynamics (competition, retirement, filters) become a later phase layered on the same data model.

## Success criteria

1. The fund manager opens the shelf page and sees 3-5 strategies, each with a regime-segmented record.
2. He can open any strategy and trace **every** paper decision it made, with the triggering signal.
3. Backtest vs live-paper is unambiguous — he is never misled about which is which.
4. A strategy's live-paper record visibly accumulates over time.

## Open questions

1. **How many of the 2-4 non-V5 strategies, and authored by whom** — does Nimish hand-author them, or are they derived from State-Engine action presets? (Resolve before the plan.)
2. **Audit-log storage** — extend `atlas_strategy_recommendations_daily` in place, or a dedicated `atlas_strategy_decision_log` table. (An implementation-plan decision.)

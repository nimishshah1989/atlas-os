# Atlas Desk — rank-driven system portfolios + agentic trading desk

**Status:** approved design (FM, 2026-07-04) · **Owner:** FM + Claude
**Supersedes:** the three "Atlas Alpha" EMA-policy system portfolios (retired as replicas
of the rule-based EMA portfolios — a walk-forward search over bare-EMA knobs degenerated
to exact copies of hand-written strategies).

## Context

Atlas has a portfolio layer (engine, costs, FIFO tax, nightly marks, validation gate —
PRs #155–#160) and a scoring layer (six lenses, composite, sector ranks, conviction,
point-in-time since 2019). The FM wants system-generated portfolios that (a) genuinely
use Atlas's intelligence — ranks, not bare moving averages; (b) behave like a trader —
evaluated daily, balancing churn against taxation, not calendar-rebalanced; (c) get
smarter with experience; and (d) are measured head-to-head against the FM's own basket
with the explicit goal of beating it. Backtesting stays first-class: every system
strategy presents backtest results alongside its forward track, with bias disclosed.

**Honesty constraint (peer-reviewed):** LLM agents cannot be honestly backtested — the
model's training data contains the "future" of any historical window ("Profit Mirage",
arXiv:2510.07920). Resolution (FM-approved): every desk shows its **charter backtest**
(deterministic skeleton, honest point-in-time replay) overlaid with its **forward live
curve**; the gap measures the agents' added judgment. Agent-distilled rules that are
mechanizable get re-backtested before promotion. The agent layer itself is never
presented as backtested.

## Decisions log (FM)

1. Both phases; **systematic first** (benchmark + candidate generator for the desk).
2. Charters: **Sector Leaders, Conviction Concentrate, Quality-Momentum, Rotation** — all four.
3. **Concentrated** books (~10–12 names, 8–10% cap).
4. **Daily evaluation with hysteresis**, not calendar rebalance; tax/churn-aware exits.
5. System slots **go live only if the backtest beats NIFTY 500 OOS with lower maxDD**;
   otherwise dormant with an honest "no edge found yet — re-searching weekly" state.
6. Agents sit **on top of Atlas's structured layer** (ranks/lenses/conviction), drilling
   into raw data only for names in play — never re-deriving the analyst work.
7. Backtests stay first-class for every system portfolio (charter backtest + forward).

## Phase A — rank-driven systematic strategies (backtestable benchmark)

One new strategy class `atlas/portfolio/strategies/rank_policy.py` producing **target
sets** (not EMA events): on each session, given point-in-time composite/sector ranks:

- **Sector Leaders** — top `n_sectors` (3) by aggregate constituent conviction → top
  `n_per_sector` (3) names each.
- **Conviction Concentrate** — top `n_names` (10) by composite market-wide, ≤`sector_cap`
  (3) per sector.
- **Quality-Momentum** — Conviction Concentrate ∩ (RS 3m vs N500 > 0) ∩ above 200-EMA.
- **Rotation** — sectors with best rank *improvement* over `lookback` (63d) from below-median
  base → top names within them.

**Hysteresis (the daily-trader behavior, deterministically):** enter when a name is in
the target set; exit only when it falls below `exit_rank_buffer` (e.g. entered top-10,
exits below rank-15/out of qualifying sectors) OR its invalidation (risk flag, regime).
Tax awareness: an exit that would realize STCG on a gain, where the name sits between
target and buffer, is deferred unless urgency (hard invalidation) — encoded as a rule,
journaled. Regime gate: Risk-Off/dislocation → no new entries (Conviction/Quality also
raise cash; parameters per charter). All knobs live in `atlas_thresholds`
(`portfolio_rank_*`), engine mechanics (events→targets diffing) added to the existing
engine as a second entry mode: `replay(..., targets=...)` diffs target vs held per
session and books the difference. Costs/tax/NAV/gate: unchanged, reused.

Backtest 2019→now (lens history floor) + 5y where data allows; go-live rule per
decision #5. These four retire the Atlas Alpha replicas (archive rows, keep journals).

## Phase B — the Atlas Desk (agentic, forward-only)

New context `atlas/desk/` (prompts, JSON schemas, memory retrieval — pure) +
`scripts/foundation/desk_run.py` (orchestrator; nightly after `lens_daily`). Each desk =
`portfolio_master` row (`origin='system'`, `strategy_key='desk'`, charter in params).
Agents DECIDE; the existing engine EXECUTES (next-close fills, costs, FIFO tax) — agents
can never invent a price (rule #0). Malformed/rule-breaking agent output ⇒ desk does
nothing that day. ~6–10 Anthropic API calls/desk/night (Sonnet; weekly reflection on a
stronger model). **Prerequisite: `ANTHROPIC_API_KEY` in `.env` (FM to provision).**

### Roles (core goals + condensed prompts)

- **Scout** — *"what changed, what deserves attention?"* Inputs: charter, holdings with
  tax clocks + invalidation conditions, Atlas snapshot (sector ranks, top-40 conviction
  with lens vectors/RS/EMA/risk-flags), 5-day rank deltas, regime, Phase-A target sets,
  retrieved lessons. Prompt mandates: cite specific Atlas numbers; ≤5 proposals
  {symbol, add/trim/exit/watch, evidence[], urgency}; **"most days nothing material
  changes, and saying so is a correct output"** (anti-churn).
- **Bull/Bear debate** — only for contested moves (exit of a winner, soft-limit breach,
  Risk disagreement; 0–3/day). Opposite mandates on the same evidence pack; 3 strongest
  points + confidence each; transcript to PM. Purpose: kill impulsive churn.
- **Risk & Tax officer** — hard layer in CODE (position/sector caps, ≤20%/day turnover,
  Risk-Off = no entries); soft layer prompt: compute tax bucket of each sale (STCG now
  vs LTCG in N days), round-trip cost, concentration → approve / resize / **defer until
  LTCG vests unless urgent** / veto with reason.
- **Portfolio Manager** — final call, only on Risk-approved proposals. Every order
  carries a written **thesis + falsifiable invalidation condition** (checked daily by
  the Scout thereafter). "Doing nothing is a decision — record why."
- **Reflection (weekly)** — reads closed decisions with outcome stamps; writes ≤3 tagged
  lessons; lesson confidence rises/decays with future confirmation. Mechanizable lessons
  are re-expressed as deterministic filters and **backtested before promotion** into the
  desk's standing constraints (the agent→backtest validation loop).

### Memory (the "smarter every day" loop)

Tables in `atlas_foundation`:
- `desk_journal` — immutable per-cycle record: inputs snapshot, each agent's output,
  PM theses. Audit trail + learning substrate; rendered on the portfolio page.
- outcome stamps — nightly job marks past decisions: P&L at T+5/T+20/T+60, whether the
  invalidation triggered, opportunity cost of vetoed/deferred trades.
- `desk_lessons` — distilled, tagged (symbol/sector/regime/action), confidence-weighted,
  decaying. Retrieval: top-K lessons matching today's tags (recency×confidence) injected
  into each agent's prompt. FinMem-style layered memory grounded ONLY in forward outcomes.

### Charters

Same machinery, four mandates mirroring Phase A (Sector Leaders / Conviction /
Quality-Momentum / Rotation). Phase-A deterministic twins keep running as the yardstick:
the leaderboard isolates exactly what agent judgment adds over the same philosophy.

## Scoreboard

Live head-to-head on /portfolios (compare chart + a leaderboard row-set): each desk vs
its Phase-A twin vs NIFTY 500 vs the FM's actual basket — identical costs and tax.
"Beats the fund manager" is only ever claimed from this forward record. Desk pages show
charter backtest (labeled, bias-disclosed) + forward overlay + Learning log
(journal/lessons) + the existing How-this-strategy-works explainer extended for desks.

## Build order

1. **A1**: `rank_policy` strategies + targets mode in engine + hysteresis/tax rules +
   thresholds + backtests + go-live gate; retire Alpha replicas; board wiring.
2. **A2**: FM-basket-as-benchmark row on the leaderboard.
3. **B1**: desk tables + orchestrator + Scout/Risk/PM (no debate/reflection yet), one
   desk (Sector Leaders) live forward.
4. **B2**: debate + outcome stamps + weekly reflection + lessons retrieval; remaining
   desks; lesson→backtest promotion loop.

Each step ships via the standard gates (validate_portfolios extended to desks; producer
registry; CI).

## Non-goals / honesty notes

- No historical backtest of LLM decisions, ever (Profit Mirage). No claim of model
  self-training; "learning" = accumulated forward experience shaping prompts.
- No real-money execution. Paper only, prices = stored EODs.
- Desk does not re-derive lens analysis from raw filings (decision #6).

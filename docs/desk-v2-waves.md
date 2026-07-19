# Desk v2 — wave charter and goal-loop protocol

Desk v2 extends the Atlas Desk (`atlas/desk` + `scripts/foundation/desk_run.py`)
into a human-in-the-loop trading desk that learns from its own stamped outcomes.
This file is the standing charter: every wave has ONE goal, ONE runnable success
gate, and stays open until the gate is green. It is the source of truth for what
is being built next and why.

## The goal-loop protocol

1. A wave is **open** while its gate is missing or red.
2. Every gate is a check in `scripts/foundation/validate_desk.py`, run nightly by
   `atlas_daily.sh` after `desk_run`. Gates assert on REAL produced output
   (rule #0) — journals, queue rows, outcome stamps — never on fixtures.
3. A wave **closes** after its gate holds green for **5 consecutive trading
   days**. Close = flip its status here + append a row to `decisions.jsonl`.
4. A red gate on a closed wave reopens it and becomes the top priority of the
   next build session. Nothing from a later wave ships while an earlier gate
   is red.
5. Roles: FM approves trades (queue) and merges PRs; build sessions (Claude)
   implement exactly one open wave at a time; the nightly pipeline is the
   tester of record.

## Waves

### Wave 1 — every decision is a complete, auditable trade card · **status: gate live, closing window running**

**Goal.** No desk order exists without thesis, invalidation, and (for buys) a
code-verified plan: entry ref, stop, target, R:R ≥ `desk_min_rr` — all grounded
in real levels. Human-gated desks queue cards for approval instead of booking.

**Built.** EXECUTION TRADER agent, `desk_pending_orders` queue + settlement +
expiry, `desk_approve.py`, nightly Telegram memo, `--dry-run` (PR #183).

**Gate.** `validate_desk.py` checks:
- A: every active desk journaled the last cycle date
- B: every plan on a booked/queued buy satisfies stop < entry < target and
  R:R ≥ `desk_min_rr` (re-verified from the journal, not the agent's claim)
- C: queue state machine sound (no over-age pending, no unsettled approved,
  booked ⇒ booked_at, decided ⇒ decided_at)
- D: every booked order ≥ 15 days old has a T+5 outcome stamp
- E: trader liveness — recent cycles with booked buys produced ≥ 1 plan

### Wave 1b — approval and monitoring reach the human in time · **status: open, next**

**Goal.** Approve/reject from the board in under a minute; a stop or
invalidation breach on an open desk position alerts within 10 minutes during
market hours.

**Build.** /portfolios queue UI + API route; intraday monitor reusing the
sector-RS cron pattern (`kite.quote` on open desk positions → breach rows →
Telegram via `atlas/intraday/notify.py`).

**Gate (to add as checks F/G).** F: every queue decision taken via the API has
an audit row and settled correctly at next cycle. G: every breach row
corresponds to a real quote crossing the stored stop/invalidation level;
no open position with a plan lacks monitoring coverage on a session with
intraday data.

### Wave 2 — decisions weighted by measured credibility · **status: open**

**Goal.** The PM sees, for every proposal, the rolling stamped track record
(hit rate + T+20 alpha vs Nifty 500) of the agent/charter/sector that produced
it, and sizes or abstains accordingly (TrustTrade-style selective consensus;
Safe/Neutral/Risky risk stances; 5-tier conviction on every agent output).

**Build.** `desk_credibility` builder from `desk_outcomes`; alpha-vs-N500
columns on stamps (not raw %); conviction field in agent contracts; abstain/
size-down rule enforced in code.

**Gate.** Credibility table rebuilt nightly from ≥ real stamped decisions and
injected into the PM payload (provable from `inputs_digest`); every agent reply
carries a valid conviction tier; calibration report (stated conviction vs
realized T+20 alpha) generated weekly. Outcome metric reviewed at close:
high-credibility cohort alpha > low-credibility cohort over the trailing 60
sessions.

### Wave 3 — the desk remembers and learns contrastively · **status: open**

**Goal.** Weekly reflection diffs the best vs worst stamped closed positions
and writes layered lessons (fast/medium/slow decay) that are retrieved into
SCOUT/PM prompts by scored relevance (FinCon CVRF + FinMem layering); a
code-enforced CVaR tripwire de-risks the desk when drawdown velocity spikes.

**Gate.** Every weekly reflection cites ≥1 best and ≥1 worst real closed
position; every lesson row has layer + decay and stale lessons auto-retire
(observed, not asserted-in-theory); tripwire state computed nightly from the
real NAV series and journaled.

### Wave 4 — the desk improves its own methodology · **status: open**

**Goal.** A hypothesis loop (RD-Agent(Q) pattern) proposes one falsifiable
threshold/lens change per week, walk-forward tests it via the existing
champion/challenger harness, and journals promote/reject with evidence.
Charters/prompts move to DB (admin-editable). A masked-ticker audit proves
decisions come from Atlas data, not memorized priors.

**Gate.** ≥1 hypothesis journaled with a walk-forward verdict per week; the
masked-ticker control run diverges from the named run below an agreed
threshold; a charter edit via /admin changes the next cycle's prompt with an
audit trail.

## Deferred

- SMP-500 (small/mid-cap) universe expansion — parameterize universe +
  within-universe deciles first. Deferred by FM 2026-07-19.

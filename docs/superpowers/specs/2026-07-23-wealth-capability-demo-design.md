# Wealth Capability Demo — client intelligence engine + RM frontend

**Date:** 2026-07-23 · **Status:** DESIGN (approved sections below, pending user review)
**Supersedes:** the two current dashboard artifacts as the primary surface (they stay
live as the analyst deep-dive; this is the new front door).

## Purpose

One product that does three jobs with the data we already hold (219 valuation clients +
210,634 ledger transactions, ₹439 cr, 1989–2026 — treated as *the entire universe*):

1. **Demonstrate to management** what Jhaveri can offer that no platform in the country
   offers: analytics that tell a client how they themselves behave (things they don't
   know), and a continuously-running recommendation engine.
2. **Give RMs a working tool** for meeting prep and proactive calls.
3. **Prove the engine** end-to-end so the case for wider data access makes itself
   (explicitly OUT of scope to pitch that here — the demo speaks, we don't).

Audience decisions (locked): built for **RMs/advisors** (internal content allowed,
plain language mandatory), **book first → drill to client**, delivered as an
**app-like artifact** (private claude.ai link, same PII posture as today).

## The three-part engine (concept names used everywhere)

- **PROFILE** — who this client is, from what they did: crash behaviour, rally-chasing,
  SIP discipline, dividend leakage, winner-selling/loser-holding, engagement trend.
  Computed per client from `wealth.client_behaviour`, `behaviour_gap`,
  `client_churn_risk`. Presented as a plain-words behavioural profile ("Sold in every
  major crash · never missed a SIP in 8 years · takes dividends as cash").
- **PREDICT & PREVENT** — timed warnings derived from profile + conditions:
  crash-seller call list (fires on drawdown), SIP-fragility list, chaser redirection
  notes, disengagement risk. Surfaced as "Who to call, and what to say" — every row a
  reason in words, with that client's own history as the script.
- **PRESCRIBE** — the per-client **Audit Pack**: seven named checks in the voice of the
  stockizen prompt series, every number computed deterministically by our engines, the
  LLM used only to narrate and to read fund documents:
  1. **The Map** — what you own, one clean picture (holdings, weights, AMCs, plans).
  2. **The Label Check** — does each fund do what its name says (category truth,
     equity/debt split vs label; from Morningstar look-through).
  3. **The Overlap Trap** — pairwise fund overlap, true top-10 stock exposure in ₹,
     "how many genuinely different bets you own" (effective N — already computed).
  4. **What You Actually Pay** — fees in rupees/year, closet-index detection, the
     certain saving (existing fee engine).
  5. **Did You Beat the Market?** — exact ledger-flow replay vs Nifty-50 fund
     (existing `client_benchmark`), said in one sentence.
  6. **Your Habits** — the PROFILE section, with ₹ costs from counterfactuals
     (what crash-selling / stopped SIPs / dividend leakage cost *you*). The section
     no factsheet-reading prompt can produce — our moat, stated as such.
  7. **The Action List** — keep/trim/switch/do-nothing with exact tax cost and
     unwind order from `wealth.lots`; "bought recently — do nothing" honoured.
     Sourced from the existing rules-engine flags + lots; every action carries its
     evidence line.

## What gets BUILT (delta over what exists)

**New computations (deterministic, `scripts/wealth/`):**
- `build_overlap.py` — pairwise holdings overlap per client's funds + true stock-level
  exposure + effective-bets count, from existing Morningstar holdings tables →
  `wealth.client_overlap` (+ per-fund-pair detail).
- `build_label_check.py` — per held fund: actual large/mid/small/debt split vs its
  SEBI category expectation; drift across the last four disclosures where history
  exists → `wealth.fund_label_check`.
- `build_audit_packs.py` — assembles per-client JSON: all seven sections' numbers from
  the tables above + benchmark/lots/behaviour/counterfactual/rules tables. Pure
  assembly, no new math. Output: `wealth.audit_packs` (client_id, section, payload
  jsonb, computed_asof).
- **LLM narration layer** (`narrate_audit_packs.py`): takes each pack's numbers →
  plain-language paragraphs per section in the fixed voice; STRICT rule: no number may
  appear in prose that is not present in the payload (validator enforces by regex
  match); temperature-0, per-section templates with the model filling connective
  prose. Runs via claude CLI on this box, batch. Output stored alongside payload.
  Manager/mandate-change reading (prompt-6 style "Bloat Check") is **deferred** — it
  needs fund-document ingestion we don't have; the Audit Pack ships with 7 sections
  now, Bloat Check slot designed but marked "coming".
- **PREDICT lists** (`build_call_lists.py`): materialise the three standing lists
  (crash-sellers ranked by panic history & book size; SIP-fragile; disengagement top
  20 with reasons) → `wealth.call_lists`, regenerated on each run.

**The frontend (new artifact, replaces nothing until approved):**
- Single HTML app-like artifact, own visual identity (NOT the current dossier look),
  data embedded as JSON exactly like today (build script → verify in headless browse →
  publish). New builder: `build_capability_app.py`.
- **Screen 1 — The Book (6 chapters, one idea per screen, scroll or arrow):**
  1. The book (220 families, ₹439 cr, records to 1989)
  2. Did clients make money? (13.5%/yr typical; ₹10L → what it became)
  3. Honest comparison (exact replay; 8 of 10 ahead of the index fund)
  4. What habits cost (3 story cards: crashes ₹27.8 cr locked · SIPs stopped ₹67 cr
     missed · dividends ₹24 cr never compounded — each opens the client list)
  5. Our advice, marked honestly (switch scoreboard + push waves, internal candour)
  6. **What this makes possible** — the management chapter: PROFILE/PREDICT/PRESCRIBE
     stated in three sentences each, with live links into the demo ("this is running
     on our book today").
- **Screen 2 — Who to call this week:** the PREDICT lists, each row = name, ₹, reason
  in words, one-line script. Filter by list. Click → client page.
- **Screen 3 — Client page = Audit Pack:** search/pick client → seven sections, each:
  one plain sentence (the narration), one big number, one simple visual, and a
  collapsed "how we know this" (2-line method note). Ends with The Action List.
- Language rules (global): no XIRR/alpha/disposition/PGR-PLR anywhere visible —
  "yearly growth", "ahead of/behind the index fund", "sells winners, keeps losers".
  Every jargon term that must exist gets a hover/expander definition. No table on
  first sight anywhere; tables only inside expanders.
- Both themes, Indian number formatting (₹, L/cr), `tabular-nums`.

## Data flow

```
wealth.* tables (already built)
   + build_overlap / build_label_check          (new numbers)
   → build_audit_packs → narrate_audit_packs    (packs + prose, validated)
   + build_call_lists                           (PREDICT lists)
   → build_capability_app --out app.html        (embeds everything as JSON)
   → headless-browse verify → publish as NEW artifact (new URL, own favicon)
```
Re-run order is one make-style script (`run_wealth_engine.sh`) so refreshes are one
command. Existing dossier artifacts untouched.

## Error handling & honesty rails

- Packs for clients with incomplete data (no benchmark, approx flows, missing scheme
  NAV) render the section with an explicit "we can't say this honestly for you yet —
  here's why" line, never a silent blank or a guessed number.
- LLM narration validator: any numeral in prose not found in payload → hard fail for
  that section, falls back to template-only text. No forward-return claims anywhere;
  counterfactual sections carry their upper-bound caveats in the visible text.
- The 5-departure survivorship fact stays stated wherever churn-ish claims appear.

## Testing

- Unit: overlap math on real Morningstar rows (rule #0 — real records); label-check on
  known funds (a flexi-cap behaving large-cap); narration validator (payload with a
  number absent from prose passes, prose with an invented number fails).
- Integration: build packs for 3 named clients end-to-end and assert every section
  present, every number traceable to its source table.
- `validate_wealth_app.py`: post-build gate — JSON parses, no NaN, all 220 clients
  resolvable in the app, zero console errors in headless browse.

## Out of scope (explicit)

- 3,000-cr rollout narrative, RTA feed ingestion, per-RM auth.
- Auto-sending anything to clients (RM approves; suitability stays human).
- Bloat Check fund-document ingestion (slot designed, deferred).
- Uplift/causal models (need tracked outcomes first — the advice-ledger loop starts
  accumulating them the day RMs use the call lists).

## Success criteria

1. A non-technical RM can open the artifact and, unaided, explain any client's pack
   back to us in their own words.
2. Management sees chapters 1–6 and the client page and understands the three
   capabilities without a single term being explained verbally.
3. Every number on screen traces to a `wealth.*` table; the narration validator passes
   for all published packs.

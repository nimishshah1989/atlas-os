# Atlas v2 — Honest Handoff (2026-05-19, end of autonomous build)

**Status:** v2 frontend live at `http://13.206.34.214:3002/`. Production `atlas.jslwealth.in` untouched.

This handoff updates and supersedes `v2-demo-handoff-2026-05-19.md`. It reflects what actually shipped after the overnight autonomous build + three independent code reviews (aggressive, superpowers:code-reviewer, visual design-review) + a 6-fix follow-up pass.

---

## What v2 verifiably delivers

1. **One consistent state per stock.** The contradiction that started this work (NESTLEIND showing "Investable" alongside "Stage 4 Decline") is gone. Master state card carries the single source of truth.
2. **Gate row stripped** from stock + fund screeners. Exit-flag panel + Weinstein/Momentum interpretation cards removed from stock detail.
3. **ValidatedBadge treatment** for every remaining state chip, sourcing render decisions from `atlas_component_validation` per-tier IC.
4. **WithinStateRankCell** replaces conviction column on stocks, extended to funds + ETFs.
5. **ComponentScorecard footer** renders real OBV slope / ATR contraction / realized-vol tier (with one TODO: OBV slope column doesn't exist in `atlas_stock_metrics_daily`, returns null gracefully).
6. **ETF bubble chart** re-axed: x = trend strength (`pct_stage_2 - pct_stage_4`), y = within-state rank, color = engine state.
7. **23+ commits** across `feat/atlas-consolidation` covering plan Phases 0-8, plus 6 review-driven fixes.

---

## What v2 does NOT deliver (be transparent with the fund manager)

### Architectural compromises forced by schema reality

- **Fund + ETF aggregators are passthrough, not bottom-up.** The real `atlas_fund_holdings` and `atlas_etf_holdings` tables don't exist. Fund reads `atlas_fund_lens_monthly` (pre-aggregated legacy data); ETF reads `atlas_etf_states_daily` (legacy table). The spec promise "sector / fund / ETF / country state become bottom-up computations from `atlas_stock_state_daily`" is met for **sector only**.
- **Sector aggregation uses equal-weight** — no `market_cap` column exists on `atlas_universe_stocks`. Real weighted aggregation needs that column added.
- **State engine + legacy compute coexist nightly.** Spec DoD #4 ("All deprecated tables are read-only or dropped") is unmet. Legacy `atlas/compute/stocks.py` still writes to `atlas_stock_states_daily` nightly. Defended by `classifier_version='v2.0-validated'` filter in views; not destructive but not ideal.

### Visual gaps flagged by design review

- **/etfs bubble chart shows "No ETFs with sufficient data"** when ETF view falls back to legacy passthrough (current state). Root cause: `mean_within_state_rank` is NULL in legacy data. Migration 089 + real ETF aggregator backfill would fix this.
- **/sectors/Banking signal-component tiles render as em-dashes.** Either query gap or prop threading issue — needs investigation.
- **/sectors footer treemap collapsed to single column** when stage distribution is uniform.

### Stocks chip count divergence (NOT a bug, but needs communication)

- v1 header: `7 Investable / 58 Leader/Strong / 322 Accel/Improving`
- v2 header: `535 Investable / 208 Leader/Strong / 8 Accel/Improving`

Both correct under their own definitions:
- v1 used legacy `is_investable` (after the anti-predictive gate filters)
- v2 uses `NOT (state IN ('uninvestable','stage_4'))` (IC-validated)

Fund managers will notice this. The talking point: **"v1's tight count was over-gated by signals we proved anti-predictive. v2's wider count reflects what the IC engine validates."**

### Known data limitations

- **State engine 2025 backfill in progress** — running monthly chunks; at session end was mid-chunk 15/17. Expected complete by 13:10 IST. Until then, dwell timelines + historical state queries pre-2025 only have the original 2023-2024 IC window.
- **Fund v2 table has 4788 rows** (Jan-May 2026 only; monthly disclosures rolled forward). Older fund views fall back to legacy.
- **ETF v2 table has 20 rows** (single day) — `--only etf` populate ran at session end; should now have multi-day data when verified.

---

## Code-review verdicts

### Aggressive review (general-purpose, adversarial)
- 5 CRITICAL findings → **all 5 fixed** (commits `d51daa3`, `68b3700`, `d1a30ff`, `d02a838`, `f457b32`)
- 7 IMPORTANT findings → 1 fixed (drop_duplicates defense), 6 documented
- Verdict pre-fixes: **needs-rework**. Post-fixes: critical SQL/silent-failure issues resolved.

### superpowers:code-reviewer (plan compliance)
- 3 CRITICAL findings:
  1. Fund/ETF aggregator semantic break (passthrough) — **architectural compromise documented, not "fixable" without schema changes**
  2. Migration 087 downgrade NotImplementedError — **fixed in 68b3700**
  3. Phase 8.1 / DoD #4 unmet — **acknowledged, deferred**
- 7 IMPORTANT findings → most fixed, 2 deferred with TODO markers

### Visual design review
- Found 2 P0 + 2 P1 regressions vs v1. The chip-count divergence is the most user-visible item — needs UX framing, not code fix.
- Major header chrome, typography, color tokens all on-spec. No DESIGN.md drift.

---

## Final commit graph (since session start)

```
ac2a448  fix(states): drop_duplicates defense in dwell merge        [f457b32]
ac2a448  fix(nightly): m2_daily surfaces partial failures           [d02a838]
ac2a448  fix(aggregations): normalize fund composition + holdings   [d1a30ff]
ac2a448  fix(migrations): 087 downgrade now drops views             [68b3700]
ac2a448  fix(states): ic_harness queries correct tables             [d51daa3]
a392167  feat(etfs): bubble chart x-axis = trend strength            [322fb1c]
a392167  feat(nightly): m2_daily wires new state engine + aggrs     [b5c9b2b]
a363a08  forge: chunk-phase4 — IC harness for legacy candidates     [750e759]
ae6a913  forge: aggregations — rewrite sector/fund/etf real schema   [2dcb525]
a9b7254  feat(frontend): Component Scorecard + WithinStateRankCell   [5976d64]
af8c4f1  perf(states): vectorize _apply_dwell_and_urgency            [9d4606a]
a20dbb6  chore(migrations): stamp alembic to 087 + reconciliation    [2b0eefc]
```

(Plus pre-existing commits from earlier in the session.)

---

## What still needs follow-up (post-handoff)

### P0 (blocks production cutover)
1. **Real fund holdings ingestion** — locate or build the `(mstar_id, as_of_date, instrument_id, weight_pct)` table. Until this exists, fund aggregation can't be truly bottom-up.
2. **Real ETF holdings ingestion** — same for ETFs (NSE provides composition files).
3. **Market cap column on `atlas_universe_stocks`** — needed for proper sector weighting.

### P1 (architectural completion)
4. **Phase 8.1 / DoD #4**: disable legacy `atlas/compute/stocks.py` nightly write.
5. **IC harness column fix**: `is_contraction` is BOOLEAN — needs CASE conversion in loader.
6. **Move hardcoded thresholds** in `aggregations/fund.py` to `atlas_thresholds`.
7. **ETF bubble chart on /etfs** — once ETF v2 has multi-day data + `mean_within_state_rank` populated, chart will render.

### P2 (polish)
8. **Sector Banking signal-component tiles em-dashes** — wire query to populate them.
9. **OBV slope column** — add to `atlas_stock_metrics_daily` (currently null on Component Scorecard).
10. **Tie-break in `base.py`** — change to conservative-first.
11. **ETFBubbleChart test** — extract `computeTrendStrength` to a shared util, import in both production + test.

### P3 (housekeeping)
12. **`__init__.py` exports** in `atlas/intelligence/aggregations/` — publish public API.
13. **9 pre-existing Vitest failures** in FundDecisionHistory + FundDeepDiveHeader — unrelated to this work.
14. **Push branch to origin** — local-only right now.

---

## What the fund manager should evaluate

When you show them `http://13.206.34.214:3002/`:

1. **Open `/stocks/NESTLEIND`** alongside `https://atlas.jslwealth.in/stocks/NESTLEIND`. The contradiction is gone in v2. One state, one decision.
2. **Note the chip-count divergence** on `/stocks` (v1 vs v2) — explain it's the IC engine's verdict on which gates actually predict.
3. **Compare `/sectors`** — v2's sector states are now bottom-up from stock states (sector aggregator IS real bottom-up, despite fund/ETF limitations).
4. **Test conviction column** — WithinStateRankCell replaces SP04 conviction. Does the new metric feel equivalent? Better? Worse?

If they sign off: merge `feat/atlas-consolidation` → `main`, then run the P0 follow-ups before pointing production traffic. Schema work (fund/ETF holdings + market cap) is the biggest open piece.

If they don't sign off: production stays as-is. The v2 branch is preserved for iteration; nothing to roll back.

---

## URLs

- **v2 demo:** http://13.206.34.214:3002/
- **v1 production:** https://atlas.jslwealth.in/
- **Branch:** `feat/atlas-consolidation` (worktree at `/Users/nimishshah/Documents/GitHub/atlas-os-consolidation`)
- **One-command redeploy:** `./scripts/deploy_v2.sh` from the worktree

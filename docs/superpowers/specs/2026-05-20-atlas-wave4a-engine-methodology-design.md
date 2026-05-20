# Atlas v2 — Wave 4A: Engine Methodology Fix — Design Spec

**Date:** 2026-05-20
**Branch:** feat/atlas-consolidation
**Status:** Design approved via brainstorming; pending writing-plans.
**Anchors:** [Decision Engine spec](2026-05-20-atlas-decision-engine-design.md). Wave 4A is the first of two Wave 4 sub-projects; [Wave 4B](2026-05-20-atlas-wave4b-information-architecture-design.md) is the information-architecture rework.

## Problem

A data audit found the v2 sector and fund classifiers collapse to a single constant label. All 25 sectors classify as `Neutral` (0 Overweight, 0 Underweight); all 1298 funds classify as `Reduce`. The cause is two-fold:

1. **Absolute thresholds with no headroom.** The sector `sector_state` (migration 084) needs `pct_stage_2 ≥ 0.50` for Overweight — but market-wide `pct_stage_2` is ~0.01 (only 9 of 747 stocks are Stage 2A). It is mathematically unreachable. The fund `derive_fund_recommendation()` short-circuits to `Reduce` whenever `holdings_state == "Weak-Holdings"`, and `holdings_state` is `Weak-Holdings` for 100% of funds because the `strong_aum_pct < 0.40` bar is unreachable when strong stocks barely exist.
2. **Possible upstream under-classification.** The entire downstream collapse traces to one number — 9 of 747 stocks in Stage 2A. Whether that is a genuine thin-breadth market or the state engine's Stage-2 entry thresholds being too strict is unverified.

A classifier that emits one constant label gives the fund manager zero signal. Even in a genuinely weak market it must still *rank* — some sectors are less bad, some funds hold up better.

## Goals

- The sector and fund classifiers always discriminate — they never collapse to one label, in any market regime.
- They stay honest about absolute conditions — they do not cry "Overweight" / "Recommended" in a genuine bear market.
- The Stage-2 entry thresholds are audited with evidence; the IC-validated state engine itself is NOT modified in this wave.

## Non-goals

- No change to the IC-validated stock state engine / classifier. Wave 4A audits the Stage-2 thresholds and reports; it does not re-tune them. If the audit finds genuine under-classification, that becomes a separate task with its own IC re-validation.
- No change to the 4-label vocabularies (`Overweight / Neutral / Underweight / Avoid`; `Recommended / Hold / Reduce / Exit`).
- No frontend redesign — the sector/fund pages already render whatever label the data carries.

## Part 1 — Stage-2 threshold audit (report-only)

A diagnostic pass, output as a written audit in `docs/audits/`. It must determine, with evidence, whether today's 9/747 Stage-2A count is a genuine thin-breadth market or the state engine under-classifying. Evidence to gather:

- The state engine's Stage-2A/2B/2C entry conditions, and how many of the 747-stock universe each individual gate admits/rejects.
- The 2023–2026 historical distribution of the Stage-2 share — is ~1% an outlier or within range for weak tapes?
- How many stocks sit *just below* each Stage-2 boundary (a large near-miss cohort suggests a too-strict gate).
- The current distribution of the underlying inputs (breakout ratio, SMA-50/150/200 stack, ATR contraction) across the universe.

**Verdict:** *genuine thin market* (no further action) or *under-classifying* (name the exact threshold(s) to revisit — handed off as a separate IC-validated tuning task). No engine code changes in Wave 4A.

## Part 2 — Hybrid sector classifier

Replace the absolute-threshold `sector_state` derivation (migration 084's CASE expression) with a **hybrid rank + absolute floor** model.

**Daily cross-sectional rank.** Each day, all sectors are scored together on a composite strength score built from the bottom-up signal — `pct_stage_2`, `mean_within_state_rank`, and sector RS. Sectors are then ranked and assigned a label by **percentile band**:

| Band | Label |
|---|---|
| Top quintile (≥ 80th pct) | Overweight |
| 50th–80th | Neutral |
| 20th–50th | Underweight |
| Bottom quintile (< 20th) | Avoid |

(Exact band cut-points are an implementation detail; the principle is a guaranteed full spread.) Because the assignment is relative, the classifier can never collapse to one label.

**Absolute floor.** A sector may *hold* the `Overweight` label only if its absolute breadth clears a minimum bar (a floor on `pct_stage_2`, calibrated from the audit in Part 1). If the relative-best sector fails the floor, its label caps at `Neutral`. Symmetrically, the floor prevents a falsely-reassuring label in a genuinely weak field — the ranking is still visible underneath, but the label stays honest. The regime layer continues to govern overall deployment %.

## Part 3 — Hybrid fund classifier

Remove the single-condition short-circuit in `derive_fund_recommendation()` (`holdings_state == "Weak-Holdings" → Reduce`) that flattened every fund.

Replace with the same hybrid model: a **daily cross-sectional rank** of all funds on a composite (NAV state, holdings quality / `strong_aum_pct`, fund RS) → percentile bands → `Recommended / Hold / Reduce / Exit`. An **absolute floor** caps the top label (`Recommended`) so a fund cannot be Recommended unless it clears a minimum absolute quality bar.

## Architecture

The hybrid rank is inherently cross-sectional — it needs every sector (or fund) computed together for one date — so it is a **daily compute step**, not a per-row SQL `CASE`.

- **Sector:** rework `atlas/intelligence/aggregations/sector.py` to compute the cross-sectional rank + floored label as part of the daily aggregation; a new migration replaces migration 084's `sector_state` derivation in `atlas_sector_signal_unified` so the view reads the computed label instead of recomputing a CASE.
- **Fund:** rework `derive_fund_recommendation()` in `atlas/intelligence/aggregations/fund.py` and the `Weak-Holdings` short-circuit path in `atlas/compute/lens_holdings.py`; the fund cross-sectional rank computed in the daily fund aggregation.
- Both ranking computations run inside the existing `nightly_v2.sh` aggregator step — no new schedule.

## Testing

The hybrid ranker is a pure function and gets unit tests asserting:
- Given varied per-entity scores, it always produces a full label spread — never all-one-label (the core regression guard).
- The absolute floor caps the top label when breadth is poor (a relative-best entity below the floor gets `Neutral` / `Hold`, not `Overweight` / `Recommended`).
- Percentile-band assignment matches hand-computed expected labels for a fixed input vector.

All thresholds (floor values, band cut-points) live in `atlas.atlas_thresholds`, not hardcoded. Decimal for all weights. Zero synthetic data — the Part 1 audit is evidence-based against real DB rows.

## Definition of done

1. The Stage-2 audit is written to `docs/audits/` with an evidence-backed verdict.
2. `atlas_sector_signal_unified` shows a genuine spread of sector labels (not all Neutral) on the current date.
3. The fund recommendation shows a genuine spread (not all Reduce) on the current date.
4. In a simulated thin-breadth input, the classifiers still produce a ranked spread, and the absolute floor keeps the top label honest (no false Overweight/Recommended).
5. The hybrid ranker unit tests pass, including the never-collapses regression guard.

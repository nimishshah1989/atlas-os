# Atlas v4 — master execution backlog (2026-06-25)

Single source of truth for "everything left." Goal: drive
`scripts/foundation/validate_data_integrity.py` to **15/15 GREEN** and clear the
frontend §3/§6 follow-ups, in one monitored autonomous pass. The gate is the
falsifiable definition of done — **never edit it to pass; fix the pipeline.**

Baseline confirmed 2026-06-25: **12/15 FAIL** (3 PASS are staleness artifacts).

Legend: ☐ todo · ◐ in progress · ☑ done+gate-verified. Commit per item.

---

## STAGE A — deterministic, gate-verifiable, NO methodology change (autonomous)

- ☐ **A1 · breadth → EMA21.** `atlas/compute/sectors.py`: add `pct_above_ema21` +
  `pct_above_ema200` computed from canonical `technical_daily.above_ema_21`/`above_ema_200`;
  add to `METRICS_COLUMNS`; call `compute_breadth_per_sector` in `_run_pipeline`. Rename
  the MV column ema20→ema21 (migration 103). Frontend rename: `sectors.ts`,
  `SectorBreadthMVPanel`. → greens 3 gate rows (EMA21 col · EMA21 populated · EMA200 populated).
- ☐ **A2 · 368 unmapped stocks.** COALESCE fallback in universe/sector assignment
  (`de_instrument.sector` / industry→sector / index→`atlas_sector_master.primary_nse_index`)
  OR extend the curated universe. → greens "every active stock has a sector."
- ☐ **A3 · `atlas_sector_rollup` (D13 fold 29→21).** Create + seed the tiny mapping table
  (fold map locked in CONTEXT.md L955-983). Add `canonical_sector = COALESCE(parent, sector_name)`
  to sector MVs + universe assignment. → greens "sector rollup table exists."
- ☐ **A4 · sector returns.** Store true `bottomup_ret_12m` (`mv_sector_cards`, migration 102);
  backfill NIFTY-500 12m; audit the |6m|>80% outlier (Defence — `close_approx` constituent).
  → greens "ret_12m populated" + "returns in sane range."

## STAGE B — METHODOLOGY redesign — FM before/after sign-off REQUIRED (RULE #0)

Implement + generate empirical before/after on REAL names; **do NOT consolidate to the
frontend read layer until signed off.** Each greens one "real (>N distinct)" gate row.

- ☐ **B1 · fund_profitability** — `fundamental.py::_profitability` (replace 5-bucket ROE step;
  revive the ROIC bonus dead-set in `fundamental_pit.py`).
- ☐ **B2 · val_pe_vs_sector** — `valuation.py::_score_pe_vs_sector` (replace 5-bucket step;
  handle NULL sector-median PE for thin/unmapped sectors).
- ☐ **B3 · flow_institutional** — `flow.py::_score_institutional` (wire real FII/DII/MF delta
  from `public.de_mf_holdings`, latest 2026-05-04; kill the modal 50.0).
- ☐ **B4 · policy_tailwind** — expand beyond the 15 seeded policies (migration 124 `_POLICY_SEEDS`).
- ☐ **B-gate · ONE batched before/after artifact** → FM sign-off → then ship.

## STAGE C — run the chain + close the staleness root cause (monitored; DB-heavy)

- ☐ **C1 · run chain to 06-24** — `compute_all.py` → `lens_daily.py` → `m2_daily.py` →
  `m3_daily.py` → MV refresh → `consolidate_tables.py`. → greens "technicals fresh."
- ☐ **C2 · wire `lens_daily` + `consolidate` into nightly cron** — after `compute_all`, before
  MV refresh. This is the actual staleness root cause; without it the gate re-reds tomorrow.
- ☐ **C3 · wire the gate into nightly + CI** — bad data can never silently ship again.
- ☐ **C4 · drive gate to 15/15 GREEN; verify frontend both themes.**

## FRONTEND — §3/§6 follow-ups (some blocked on backend above)

- ☐ **F1 · breadth EMA21 rename** (paired with A1) — `sectors.ts`, `SectorBreadthMVPanel`.
- ☐ **F2 · RRG rotation trail** — `mv_sector_rrg.trail_6w` (JSONB) is empty; MV must compute the
  6-week trail. Render is already correct + theme-aware.
- ☐ **F3 · breadth table extra periods** (−3m/−6m/−1y) — extend `getBreadthTable`.
- ☐ **F4 · sectors improving vs deteriorating** — MoM sector-strength delta.
- ☐ **F5 · Nifty regime chart** w/ 21/50/200-EMA overlays — wire Nifty-500 index price series.
- ☐ **F6 · card → filtered stock list** — add "above-EMA" boolean to `getStocksDecileList` rows.
- ☐ **F7 · Admin re-skin** — finish (was in progress).

## HYGIENE — DB sprawl audit (FM approves any DROP; no new tables beyond A3)

- ☐ **H1 · catalogue redundant/dead objects** — e.g. `de_equity_ohlcv_y2000..y2031` yearly
  partitions, overlapping MVs → propose drops. Keep `foundation_staging` as the single
  frontend read surface. No table/MV proliferation; ALTER/reuse otherwise.

---

## ⚠ BLOCKER surfaced 2026-06-25 — D13 fold map ≠ live taxonomy (A2/A3)
The locked CONTEXT.md D13 fold map (L962-973) is written against a **GICS-style vocabulary**
(`Hospitality`→`Consumer Discretionary`, `Aquaculture`→`Consumer Staples`, …) whose source AND
parent names **do not exist in the live DB**. So the seeded `atlas_sector_rollup` (A3 commit) is a
**no-op** against real data. The live taxonomy is **NSE names**: `de_instrument`/`atlas_sector_master`
carry 31; `instrument_master` shows 21 actionable; the 10 non-actionable live buckets are
`Diversified, Conglomerate, Services, EV & Auto, Telecom, Rural, MNC, Consumption, Power, Housing`.

The 368 unmapped = **242** with an actionable `de_instrument.sector` (safe COALESCE, 0 new distinct)
+ **~15** thin-tail (Services/Diversified/Telecom/MNC/Power) + **111** with no `de_instrument` row
(no raw sector at all). Fully greening "every active stock has a sector" + "≤21 canonical" needs:
(a) the REAL 31→≤21 fold map over live NSE names [METHODOLOGY — FM], and (b) a source for the 111
(industry / index-membership / extend-universe / or gate-exclude) [FM]. Also: gate says **≤21**,
CONTEXT.md says **22** — reconcile. Held for FM decision; safe-242 COALESCE can proceed now.

## Autonomy contract for this pass
- Stage A · C · Frontend (unblocked) · Hygiene-catalogue → **autonomous**, commit per item,
  re-run the gate after each, push, keep flag-off byte-identical.
- Stage B scorers → implemented but **held at B-gate for ONE FM before/after sign-off**.
- Any DROP → proposed, not executed, until FM approves.
- Surface only at: the Stage B gate, a DROP proposal, or a genuine blocker. Otherwise: keep going.

ultracode

# AUTONOMOUS LOOP B — ETF/index roll-up + sector fold-up (the plan)

**FIRST read `scripts/loops/GUARDRAILS.md` and obey it absolutely.** Branch `feat/v4-six-lens`.
**DEPENDS ON LOOP A** — it rolls up Loop A's instrument-level lens vectors. If stock scores are
incomplete (< full universe, no history), STOP and report; do not fabricate roll-ups.

## THE GATE (your only definition of done — do NOT weaken or edit it)
`python scripts/foundation/validate_lenses.py --check B` must exit 0 + `pytest` green.
You may NOT modify `validate_lenses.py`. Commit/push per GUARDRAILS; STOP only when green.

## The model (the fractal vector — same 6 lenses at every altitude)
A stock is the atom. An **ETF and an index are the SAME thing — a weighted basket of stocks**;
their lens vector is the holdings-weighted average of their constituents' lens vectors. A
**sector** is the basket of its member stocks. So everything maps to sectors:
instrument→sector, ETF→sector, index→sector.

## Data already available (reuse — do not re-fetch)
- ETF holdings: `public.de_etf_holdings` (ticker → constituents + weights)
- Index constituents: `public.de_index_constituents` (index_code, instrument_id, weight_pct, effective_from/to)
- Sector master: `public.de_instrument.sector` (raw) + `atlas.atlas_sector_master`; the 22-actionable
  rollup logic lives in `atlas/universe/sectors.py` (consolidate thin sectors — reproduce it, no "Other").
- Stock lens vectors: `atlas.atlas_lens_scores_daily` (asset_class='stock') from Loop A.

## Tasks
1. **Sector mapping (complete, no nulls).** Map every stock to one of the ~22 actionable sectors.
   Add a `sector` column to `foundation_staging.instrument_master` (or a mapping table) and populate it.
   Map each ETF and index to a sector: a sector-tracking basket → that sector; a broad/multi-sector
   basket → its dominant-weight sector (and flag breadth). (Gate: instrument→sector complete.)
2. **ETF lens roll-up.** For each ETF in `de_etf_holdings`: ETF lens vector = Σ(weight ×
   holding's stock lens vector), per lens + composite. Write to `atlas.atlas_lens_scores_daily`
   with `asset_class='etf'`. (Gate: ETF coverage ≥90% of ETFs-with-holdings.)
3. **Index lens roll-up.** Same from `de_index_constituents` (use `weight_pct`, point-in-time via
   effective_from/to). Write `asset_class='index'`. (Gate: index coverage.)
4. **Sector fold-up.** For each actionable sector + date: cap-weighted (default) average of member
   stocks' lens vectors → the sector's 6-lens vector + **breadth** (% of members strong on each lens)
   + **dispersion** (spread). Write to a new `atlas.atlas_sector_lens_daily`
   (sector, date, 6 lenses, composite, breadth_*, dispersion_*, n_constituents). Migration + table.
   (Gate: ≥20 sector vectors, all scores in 0–100.)
5. **Historical.** Roll up across the SAME dates as Loop A's journal so ETF/index/sector also
   carry history. Chunked + resumable (≤6 workers, shared box).
6. **Tests.** Add unit tests for the roll-up math (a known basket → known weighted result) and a
   golden sector case. `pytest` green.

## Accuracy discipline
Before each commit: run `validate_lenses.py --check B` + `pytest`, and hand-verify one ETF
(its weighted roll-up equals Σ weight×holding-score) and one sector (matches its members).
Strict SUPERSET — preserve the existing 22-sector mapping + sector surfaces (blueprint §5).

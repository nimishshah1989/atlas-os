ultracode

# AUTONOMOUS LOOP 3 — FRONTEND (evolve, don't redesign)

**FIRST read `scripts/loops/GUARDRAILS.md` and obey it absolutely** — review before every
commit, push to `feat/v4-six-lens` (flag OFF = prod UI byte-identical), keep `SUMMARY.md` current.

You are running unattended. GOAL, then STOP. Do NOT deploy, do NOT merge to main, do NOT
switch the production surface. Work only on branch `feat/v4-six-lens`, behind a FEATURE FLAG.
DEPENDS ON LOOP 2 (`atlas.atlas_lens_scores_daily`). If it's absent, stop and report.

## Read first
- docs/atlas-v4-blueprint.md §6 (frontend — evolve & clean), docs/markets-today-redesign.md,
  the current-Atlas capability inventory in the blueprint §5, CLAUDE.md.

## GOAL (definition of done)
The 6-lens vector is surfaced inside the EXISTING Atlas frontend (the FM's familiar
surfaces — NOT a redesign), behind a feature flag, with frontend debt cleaned. The app
builds, type-checks, lints, and contract/component tests pass. Stop when green.

## Tasks
1. **Frontend-debt audit** (W0.5): from the capability inventory + markets-today-redesign cuts,
   produce a concrete remove/merge list (redundant/dead/duplicate components) and apply the safe ones.
2. **Wire the lens vector into existing surfaces** (preserve navigation + look):
   - Stocks / ETFs / Funds: ranking by any lens or the composite + a deep-dive showing the
     6-lens vector with EVIDENCE drill-down (the actual filing/deal behind each qualitative score).
   - Sectors: the sector 6-lens vector + breadth + dispersion alongside the existing RRG/heatmap.
   - Home: the merged Regime + Pulse per markets-today-redesign; a daily "what changed" feed
     (big deals / filings above a materiality threshold).
3. **Feature-flag everything** (e.g. NEXT_PUBLIC_LENS_V4): production paths unchanged when off.
4. Reads come from `atlas.atlas_lens_scores_daily` via the API layer (extend, don't duplicate).

## GATE (stop condition)
`next build` succeeds; `tsc`/lint clean; component/contract tests pass; flag OFF leaves the
current UI byte-identical. Then commit and STOP. Log a summary of surfaces touched + the
debt removed + anything deferred.

## Rules
- Branch `feat/v4-six-lens` + feature flag only. No deploy, no main, no production switch —
  the FM must see no change until a human flips the flag.
- Preserve FM familiarity (do not restyle/re-navigate). Reuse components; minimal new code
  (ponytail). Ship LEANER than today, not heavier.

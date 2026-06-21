# Atlas v4 six-lens — HANDOFF / STATE (for the next session)

**Branch:** `feat/v4-six-lens` (all work here; nothing on main; lens UI behind `NEXT_PUBLIC_LENS_V4`, OFF).
**Read first:** `GUARDRAILS.md`, `DECISIONS.md` (D1–D16), then this. The active spec is
`loopC_atom_complete.md`. State scorecard: `docs/atlas-six-lens-coverage-map.md`. IC spec:
`docs/atlas-ic-and-step-goals.md`.
**Gate:** `python scripts/foundation/validate_lenses.py --check A` (immutable). Loop C adds a new
independent `validate_loopC.py` (build it — see the spec's C1–C8).

## Where we are (2026-06-21)
- **Loop A — DONE** (calendar fix, RULE #0 real-data tests, journal cleaned to 276 NSE sessions).
- **Data layer (Phase 1a/1b) — DONE.** All six lenses' INPUT sources are in place and deep
  (numbers below). The big former gap — historical fundamentals incl. balance sheet — is filled.
- **Loop C (Phase 1c–1e) — NEXT, the active work.** Wire lenses to PIT data + fix 2 blockers →
  rebuild journal → IC. This flips `atlas_lens_scores_daily` from C+ → **A**. NOT started.
- **Roll-ups (sector → ETF/index → MF) + front-end — GATED** (D12/D15); framework discussed (sector
  2×2 = momentum×IC-conviction; free-float weighting; IC per altitude). Build only after the atom is A.

## Data layer — real coverage (instrument %) + TIME coverage + depth
| Lens | instrument coverage | time range | median depth/stock |
|---|---|---|---|
| Technical | trend/RS 91%, ATR/BB/vol/52w 100% | 2000→2026 (25y) | ~2,437 days |
| Fundamental | income 97%, balance sheet 86% | income 2005→2026-03; BS 2002→2026 | ~39 quarters / ~12y BS |
| Valuation | PE/EV 100% | ⚠️ **SNAPSHOT — today only, 0 history** | — (built in Loop C) |
| Catalyst | 96% | 2002→2026 | deep |
| Flow | shareholding 96%, insider 78% | 2001→2026 / 2008→2026 | deep |
| Policy | sector-mapped 96% | static | — |

**Two honest holes still at the data layer (fold into Loop C):** sector-RS (`rs_*_sector` = 0%) and
P/B (0% — `tv_metrics.market_cap` is unit-unreliable; do it unit-safe in Loop C). Valuation has NO
time history yet — it is reconstructed in Loop C from 25y price + as-of EPS/equity.

## Key files
- Lens engine: `atlas/lenses/{pipeline.py, data/adapters.py, compute/*.py, calibration.py}`
- Feeds: `scripts/foundation/ingest_{screener,xbrl,insider,filings,shareholding}.py`, `compute_all.py`, `technicals.py`
- Journal rebuild: `scripts/foundation/backfill_lenses.py`. Gates: `validate_lenses.py` (immutable), `validate_loopC.py` (to build).

## The 2 blockers Loop C must fix FIRST (cheap, provable on the current journal)
1. `compute_composite` reads NESTED `lens_weights`/`conviction_tiers`; `load_thresholds()` returns FLAT
   `lens_weight_*` → DB/IC weights silently ignored.
2. `calibration._load_fwd_returns` uses `technical_daily.ret_*` (TRAILING) as "forward" → IC is a tautology.

## Gotchas
- DB from `scripts/foundation/`: `python3 -c "import _db; ..."`. Postgres `NaN > 0` is TRUE.
- Destructive DB deletes get blocked by the safety classifier — need explicit FM approval each time.
- `count(distinct ...)` over `technical_daily` (6.9M rows) is slow / can time out — sample or add an index.
- `nohup python3 X &` → kill the actual python PID (`ps -eo pid,cmd | grep '[i]ngest_'`), not the wrapper.
- 6 corrupt insider rows (year 2924) still present — harmless (excluded by as_of filter), optional purge.

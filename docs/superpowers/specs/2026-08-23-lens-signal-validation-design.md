# Project 5 — Lens signal validation

Status: **designed, SHELVED until projects 1–4 land** (FM decision, 2026-08-23)
Programme: `2026-08-23-atlas-next-programme.md`

Do not start this before the stock universe is final. The baseline freeze is
universe-dependent; freezing it early means throwing it away and refreezing.

## Problem

Atlas can prove its numbers are **computed correctly**. It cannot prove they are
**worth anything**.

- `validate_lenses.py` is a real gate, but it validates plumbing: every stock has a
  score, the math is right, catalyst is not zero where filings exist. It never asks
  whether a high score precedes a higher return.
- `decile_core.py` ranks. It never scores the ranking.
- Grep across `atlas/`, `scripts/foundation/`, `scripts/ops/` for forward returns,
  rank-IC, Spearman or decile spread returns **nothing**. The SP01/SP04 IC work lived
  in the previous repo and never migrated into `atlas-os`.

Meanwhile the conviction scores are already read with a pinch of salt.

## What makes this measurable today

| Ingredient | Status |
|---|---|
| Daily point-in-time lens scores | `atlas_lens_scores_daily` — 1,895 dates, 2019-01-01 → 2026-08-18 |
| Forward returns | `ohlcv_stock.close_adj` (6.1M rows) |
| Cohort-correct decile cutter | `decile_core.add_deciles()` |

**Corporate-action adjustment verified 2026-08-23** — this was the make-or-break and it
passed:

```
source                 rows       adj_factor != 1
KITE               6,083,458                   0   <- Kite candles arrive pre-adjusted
NSE_UDIFF_CM           3,583                   0
seed:de_equity_ohlcv   1,089                 118   <- legacy seed, 1k rows, ignorable

close_adj day-over-day jumps >35%, last 3y: 32 across 30 names (0.0015% of rows)
```

The previous system failed this badly (204 of 500 Nifty-500 names). `close_adj` is a
trustworthy forward-return base.

## Design

**1. Forward returns in SQL, not Python.**
`lead(close_adj, h) over (partition by instrument_id order by date) / close_adj - 1`,
as a CTE. ~2.2M rows in the eval window; per the data-engineering rule (>1M → SQL with
indexes) Postgres computes, Python only aggregates. No materialised table.

**2. `atlas/compute/signal_eval.py` — the engine.** One pure, universe-agnostic function:

```
eval_signal(scores_df, fwd_df, cohort_map, horizons)
    -> per (date, lens, horizon, cohort): rank_ic, n, decile_spread
```

Inputs are only *(score table, id column, cohort rule, price source)*, so extending to
funds is a call-site change, not a rewrite. Reuses `decile_core.add_deciles()` — a
cohort-correct decile cutter already exists and a second one must not be written.

**3. `atlas_signal_ic_daily` — the journal.**
`as_of_date · lens · horizon_d · cohort · universe_n · rank_ic_252d · ic_hit_rate ·
decile_spread · computed_at`

Each nightly row is the **trailing 252-day** IC as of that date. Single-day
cross-sectional IC is near-pure noise; a gate on it would fire constantly.

**4. `scripts/foundation/eval_signal.py` — the driver.** Modes: `--backfill` (full
history, once) · nightly default (append today's window) · `--baseline` (freeze
per-(lens, horizon, cohort) baseline into `atlas_thresholds`, rule #4) · `--gate`
(compare latest vs baseline, non-zero exit on regression).

**5. `/admin/signal-quality`** — the glass-box scorecard. Per lens: trailing IC vs
baseline, hit rate, decile spread, and the plain-English line: *"top-decile technical
beat bottom-decile by 6.2% over 3 months, in 63% of rolling windows."*

## Methodology

| Decision | Choice | Why |
|---|---|---|
| Correlation | Spearman **rank**-IC | Scores are ordinal 0–100, not cardinal |
| Horizons | 21d / 63d / 126d | Composite is medium-term; 1d IC measures noise |
| Cohort | Within **cap bucket × date** | Never pool across dates — the classic error that inflates IC 3–5x |
| Universe | As of each date, from `atlas_universe_snapshot` | Handles the 2,093 → 498 → 745 → 1,050 discontinuities |
| Reporting | Per era, never one blended figure | A blended 2019–2026 number is uninterpretable across universe changes |
| Nulls | Excluded, never 0 | NULL in a financial calc produces NULL |
| Significance | `mean(IC) / (std(IC)/sqrt(n_dates))` | `ponytail:` plain t-stat; overlapping windows autocorrelate so it reads optimistic — upgrade to Newey–West if a lens sits within 0.01 of the bar |

## The bar (FM to confirm at build time)

- **Carries signal:** abs(IC) ≥ 0.03 sustained. 0.02–0.05 is real for equity factors;
  anything reporting 0.15 is a bug, not an edge.
- **Hit rate:** IC > 0 on ≥ 55% of dates
- **Decile spread:** > 0 in ≥ 60% of rolling windows
- **Regression trigger:** trailing-252d IC below baseline − 0.02 for 10 consecutive days

**Failure mode (locked): baseline + ratchet.** The gate hard-fails only on a
*regression* below a lens's own frozen baseline, never on merely-low IC. A lens that
has always been weak goes amber on `/admin`, not blocking. Mirrors the repo's existing
pyright ratchet and avoids one noisy day halting the board.

## Chunks

| # | Deliverable | Machine-checkable exit |
|---|---|---|
| C1 | Forward-return CTE | Hand-reproduce 21d return for 3 real names incl. one split date, match to 4dp |
| C2 | `signal_eval.py` engine | On a real 2024 slice, IC of a **shuffled** score column ≈ 0 (±0.01) — the null test |
| C3 | Migration + full backfill | `atlas_signal_ic_daily` populated for 6 lenses × 3 horizons × 4 cohorts; first real report |
| C4 | **PIT audit** | Prove backfilled 2019–24 scores used no future data; quarantine any lens that fails |
| C5 | Baseline freeze + nightly `step` in `atlas_daily.sh` | Baselines in `atlas_thresholds`; nightly row appends |
| C6 | `/admin/signal-quality` | Page renders real IC for every lens |
| C7 | Promote `step` → `gate` | After a clean fortnight — the repo's own idiom (`portfolio_alerts` carries the same note) |

**C4 can kill the result.** The 2019–2024 scores were backfilled. If that backfill used
restated financials or post-hoc index membership, IC will look excellent and be fake —
the exact failure mode rule #0 exists for. `fundamental_pit.py` shows PIT was
*considered*; that is not the same as *verified*.

## Two outcomes to brace for

1. **IC may come back near zero.** Then the methodology needs fixing before any further
   scaling. This design deliberately does not assume a pass.
2. **This measures the lenses, not the desk.** `desk_run.py` is forward-only by design
   (Profit Mirage, spec 2026-07-04). Nothing here backtests the agent, and nothing should.

## Out of scope

Auto-demotion of lens weights (rejected — a data outage looks identical to signal decay).
Funds, ETFs, sectors (engine is written to extend; call sites come later).
Newey–West standard errors (add only if a lens sits near the bar).

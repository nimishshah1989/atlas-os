# Signal Discovery Engine (SDE) — Design Spec v1

Date: 2026-05-20
Supersedes: v6 RS Trading Model (retired — tag `v6-retired-2026-05-20`)

## Objective

Build an autonomous bot that behaves like a systematic trader: it discovers
which factors predict cross-sectional equity returns, composes them into
strategies, paper-trades those strategies, and *learns* by promoting the ones
that hold up and retiring the ones that decay. No real-money execution in v1 —
the bot acts like a trader on a paper book.

## Non-goals (v1)

- Real-money / broker execution.
- Sector-rotation and market-timing layers (separate later specs).
- LLM agent swarm — v1 is a deterministic script.
- Custom backtest / IC / cross-validation engines — we adopt libraries.

## Guiding principle — integration, not invention

Our unique asset is the data and the backend; we already have both. Everything
else is a solved problem with mature, widely-used open-source libraries. The
custom-code budget for v1 is **~500 lines of glue**. If any component needs
more than that, we are using the wrong library. v6's failure mode was building
a bespoke 960-line simulator and a custom validation cathedral — v1 does not
repeat it.

## The library stack

| Concern | Library | What we write |
|---|---|---|
| Factor / indicator generation | `pandas-ta` (130+ indicators) | config: which families to sweep |
| Factor evaluation — IC, IC decay, quantile spreads, turnover | `alphalens-reloaded` | ~0 lines (direct calls) |
| Backtesting + parameter sweeps | `vectorbt` | ~80 lines |
| Performance / risk reporting | `quantstats` | ~0 lines (one call → HTML tearsheet) |
| Orchestration | plain Python + cron | thin lifecycle loop |

## Definitions

- **Universe at date T:** equities whose trailing-60-day median traded value
  is at or above a configurable floor, computed from `atlas.atlas_v6_clean_ohlcv`.
  Liquidity-defined and self-PIT-correct — survivorship bias is eliminated by
  construction (a stock liquid in 2015 and delisted in 2018 is correctly in the
  2015 universe and correctly absent in 2019). No index-membership data needed.
- **Label:** each instrument's forward return *ranked relative to the universe*,
  measured at 3-month, 6-month, and 12-month horizons (overlapping windows).
- **Factor:** any `pandas-ta` indicator, parameterized (lookbacks, smoothing).
- **Composite:** a z-scored blend of the factors that survive validation.
- **Strategy:** a composite + top-N selection + rebalance schedule + cost model.

## Strategy lifecycle — the bot's spine

A Postgres table `atlas_sde_strategy` with a `status` column. The bot moves
rows through these states each cycle:

```
HYPOTHESIS -> BACKTESTED -> VALIDATED -> PAPER -> CONVICTION -> RETIRED
```

- **HYPOTHESIS** — a composite has been formed, not yet tested.
- **BACKTESTED** — has historical numbers.
- **VALIDATED** — survived the held-out split; the bot believes it is not noise.
- **PAPER** — live on a simulated paper book, tracked daily.
- **CONVICTION** — paper-confirmed over a configurable window (default 3
  months); surfaced to the fund manager.
- **RETIRED** — decayed or failed; row keeps a death-reason (the graveyard).

That movement *is* the self-learning: a growing graveyard the bot never
re-tests, and a curated stable it keeps refining.

## Pre-flight checks (run before Phase 0 — gate)

1. Verify `atlas_v6_clean_ohlcv` prices are total-return / corporate-action
   adjusted (splits, bonuses, dividends). If they are not, fix this first —
   every return and factor downstream is invalid otherwise.
2. Verify delisted stocks retain their historical rows in the OHLCV source.
   If dead stocks were purged, survivorship bias re-enters silently.

## Phase 0 — The Spike (~1 day, ~100 lines)

A single script / notebook:

1. Pull the universe + ~5 years of OHLCV from Postgres.
2. Generate ~20 factors via `pandas-ta`.
3. Run `alphalens` on each factor: IC, IC decay, quantile spread.
4. Output a ranked table — which factors, if any, show out-of-sample IC with a
   stable sign and a magnitude worth trading.

**Decision gate:** if at least one factor shows out-of-sample IC worth trading
→ proceed to Phase 1. If none do → stop. The edge is not in plain price/volume
factors, and we learned it in a day instead of weeks.

## Phase 1 — The Thin Bot (~500 lines)

The lifecycle loop, deterministic, run on a schedule:

1. **Generate** factors with `pandas-ta` from a config-driven family list.
2. **Evaluate** with `alphalens` on the train split; keep factors above an IC
   floor. Log every factor tested to the ledger.
3. **Compose**: z-score and average the survivors into a composite; persist as
   HYPOTHESIS.
4. **Backtest** the composite as a strategy with `vectorbt` (top-N, rebalance,
   cost model) → BACKTESTED.
5. **Validate**: re-run `alphalens` + backtest on the held-out test split. If
   the IC sign holds and net-of-cost Sharpe stays positive → VALIDATED.
6. **Paper**: append daily composite scores + a simulated book to the paper
   table → PAPER.
7. **Review**: compare realized paper IC against predicted. Decaying → RETIRED;
   holding up over the configurable window (default 3 months) → CONVICTION.
8. **Report**: a `quantstats` tearsheet plus a top-N picks list for the fund
   manager.

## Validation discipline — simple and honest

- **Single time-based split**: train = older 70%, test = newest 30%. The test
  split is never touched during factor selection or composition.
- **Search-count haircut**: log how many factors and parameter combinations
  were tried, and report IC discounted by a simple conservative haircut for
  that count. Not a nested cross-validation cathedral — a small honest
  correction beats an elaborate one.
- **Net of cost**: every headline metric is computed net of a configurable
  transaction-cost model (bps).
- **Per-sub-period IC**: report IC broken out by sub-period so non-stationarity
  (alpha decay) is visible rather than averaged away.

## Data / schema

- **Read:** `atlas.atlas_v6_clean_ohlcv` — the existing corrupt-row-filtered
  view, the one v6 artifact the SDE keeps.
- **New (one migration):**
  - `atlas_sde_strategy` — lifecycle rows (status, composite definition,
    stats, death-reason).
  - `atlas_sde_paper_book` — daily paper positions and composite scores.
  - `atlas_sde_factor_ledger` — every factor ever tested, its IC, and its
    death-reason. The graveyard.
- `Decimal` for any money column; `float` is acceptable for research math
  (IC, returns) since no currency value is involved.

## What v1 explicitly defers

- LLM agents (Scout / Builder / Skeptic / Portfolio Manager / Analyst) — a
  later phase, only after the deterministic loop is trusted.
- Sector-rotation and market-timing layers — separate specs, same stack.
- Walk-forward continuous re-selection — a later phase.
- Real-money execution — out of scope until the paper book proves out.

## Success criteria

- **Phase 0:** a clear yes/no on whether any factor carries tradeable
  out-of-sample IC, delivered in one day.
- **Phase 1:** a running bot that, on schedule, produces a paper book and an
  FM-facing top-picks list, backed by honest net-of-cost validated statistics
  and a growing factor ledger.

## Honest framing

This engine is a *filter and a paper trader*, not an alpha factory. Its most
valuable output may be an honest null result. The discipline above exists so
that — unlike v6 — the numbers it reports can be trusted, whether they are
good news or bad.

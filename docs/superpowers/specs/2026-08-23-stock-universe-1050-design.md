# Project 1 — Stock universe: one liquidity floor

Status: **design, awaiting FM approval** · 2026-08-23 (rev 2 — simplified on FM instruction)
Programme: `2026-08-23-atlas-next-programme.md`

## Problem

Atlas scores 739 stocks. The universe is index membership —
`NIFTY 500 ∪ NIFTY MICROCAP250`, set in `build_universe.py:118`.

1. **It caps at 750.** Those two indices *are* NSE's Nifty Total Market. All 35 index
   families in `de_index_constituents` were enumerated; nothing is larger.
2. **Membership has no history.** Every row is `effective_to IS NULL` (500 live of 500
   total). Today's membership is applied to 2019 data — survivorship bias that will
   inflate project 5's IC.
3. **It ignores data already paid for.** Atlas ingests ~2,400 stocks and scores 739.

## The rule

> **A stock is in the universe if its trailing 60-day median daily traded value is at
> least ₹2.5 crore.**

That is the entire rule. No eligibility tests, no top-N ranking, no index carve-out.

### It already exists in the database

`atlas_thresholds.liquidity_min_traded_value_inr` — *"Minimum trailing 60-day median
daily traded value for liquidity gate"*, category `gate`, methodology §3.3, bounds
₹1 cr – ₹25 cr, currently **₹5 cr**.

**Nothing in the repo reads it.** Grep across `atlas/`, `scripts/`, `frontend/src/`
returns zero hits. It is a declared methodology threshold with no code behind it. This
project wires it up and sets its value to ₹2.5 cr — a threshold edit through
`/admin/thresholds`, which is exactly how architectural rule #4 intends methodology
numbers to move.

### Why ₹2.5 cr and not the ₹5 cr already stored

Measured on the trailing 60-day median, 2026-08-23:

| Floor | Universe | Current active names evicted |
|---:|---:|---|
| **₹2.50 cr** | **1,271** | **2** — AHLUCONT, PRSMJOHNSN |
| ₹4.00 cr | 1,131 | ~15 |
| ₹5.00 cr *(stored today)* | 1,037 | 35 — incl. BLUEDART, CERA, KANSAINER, WESTLIFE, EIHOTEL, CENTURYPLY |

₹5 cr lands nearest a 1,050 target but evicts 35 genuine Nifty-500 mid-caps. The
target was itself reverse-engineered from a liquidity floor; the floor is the real
rule, and 1,271 clears the coverage goal.

### Why 60 days and not two weeks

FM proposed a two-week window. Measured directly — same floor, membership compared
across consecutive months:

| Window | Members | Entered | Exited | Monthly churn |
|---|---:|---:|---:|---|
| 2 weeks | 1,305 | 148 | 65 | **213 (16%)** |
| 60 days | 1,258 | 51 | 14 | **65 (5%)** |
| 60 days + hysteresis | 1,258 | 35 | 3 | **38 (3%)** |

Near-identical member count, three times the churn. A two-week median moves on a single
block deal; every entrant costs a two-year lens backfill and every exit orphans scores
and breaks historical comparison. 60 days is already what §3.3 declares.

*Median, not mean* — one block deal must not promote an illiquid name.

*Recomputed weekly* — `build_universe.py` already runs in `atlas_weekly.sh`, so this
needs no scheduling change. Weekly re-evaluation of a 60-day median is not daily thrash:
measured churn is ~5% per month, so ~1% per weekly run.

### Two one-line additions (FM to accept or drop)

- **Hysteresis:** enter at ≥ ₹2.5 cr, remain while ≥ ₹2.0 cr. Measured to cut monthly
  churn from 65 names to 38. One extra comparison; a second threshold row.
- **Held names never drop out:** a stock held in any `portfolio_trades` book stays in
  the universe regardless of liquidity. Today no held name is below the floor, so this
  changes nothing — it prevents a book position from silently losing its conviction
  score if it later goes illiquid, which would blind the desk agents to a live holding.

### Why no eligibility tests

An earlier revision gated on OHLCV history, financials and filings. That was wrong
twice over: measured against the current 747 it would have **evicted 94 of them** (82
failing a two-year OHLCV floor — recent listings), and it duplicated a guard that
already exists.

`compute_composite()` ([atlas/lenses/compute/composite.py:156](atlas/lenses/compute/composite.py#L156))
does a **coverage-adjusted weighted average**: a NULL lens does not participate,
weights renormalise over the active set, and `min_lenses` gates the conviction tier. A
liquid microcap with no financials gets a NULL fundamental lens — not a fabricated
score (rule #0).

**Liquidity decides who is on the board. Data sufficiency decides which lenses may
speak.** The second half is already built.

## Universe history

New table `atlas_universe_snapshot`:

```
date · instrument_id · in_universe · adv_median_60d · liquidity_rank · computed_at
```

Appended **daily** (~2,400 rows/day), independent of the monthly membership recompute.
Every date's membership and the reason for it becomes reconstructable.

Chunk 1, ahead of everything else: it starts the history clock, and the record it
creates cannot be backfilled later.

## Cap cohort — the real prerequisite

Production buckets caps by index membership, in **frontend SQL**:

```sql
-- frontend/src/lib/queries/stock_lens.ts:107 (and sector_lens.ts:86)
WHEN bool_or(index_code='NIFTY 100')        THEN 'large'
WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small'
ELSE 'micro'
```

Every one of the ~520 new names is in no index, so every one becomes `micro`. That
cohort goes 250 → ~770. Deciles are cut *within* cohort, so every micro decile, the
Leader badge and the `/stocks` cap filter change meaning — silently, no error anywhere.

Fix: derive cap from **market-cap rank**, which the index rule was approximating:

| Rank by full market cap | Cap |
|---|---|
| 1–100 | large |
| 101–250 | mid |
| 251–500 | small |
| 501+ | micro |

Matches SEBI, matches `decile_core.py`'s existing thresholds, and matches what the
index rule already produces for the current 750 — which makes it regression-testable.

Blocker: `equity_marketcap` covers **302 of 2,411** stocks. `fetch_marketcap.py`
(Screener, rate-limited, resumable) must backfill first.

Four tiers retained. A `nano` split at 751+ is deferred — ~770 micro names still gives
77 per decile.

## Risks

| | Risk | Severity | Handling |
|---|---|---|---|
| R1 | Cap cohort collapses to `micro` | **High** | C2+C3, prerequisite chunks |
| R2 | ~520 new names lack sectors — `validate_lenses` asserts every active stock has one of ≤21 canonical sectors | High | C5, gated |
| R3 | Compute runtime +72% on every lens (739 → 1,271) | **High** | Measured in C6 *before* the flip; must fit the 16:00 IST cron budget |
| R4 | Thin microcaps score off very little evidence | Medium | Already handled by coverage-adjusted composite + `min_lenses`; C7 verifies rather than builds |
| R5 | Frontend/MVs assume ~750 (`mv_stock_landscape` = 747 rows) | Medium | C8 |
| R6 | Screener rate-limits during market-cap backfill | Low | Fetcher is already resumable |

**Noted, not touched:** `scripts/foundation/decile_core.py` has no callers anywhere in
the repo — production decile logic lives in the frontend SQL above. Pre-existing;
flagged per the standing rule, not deleted. If C3 changes cap derivation,
`decile_core.cap_bucket()` should change in step so the two do not diverge further.

## Chunks

Exit criteria assert on **real produced output**, never fixtures (rule #0).

**C1 — Universe snapshot table + daily writer**
1. Migration creates `atlas_universe_snapshot`; `schema_gate.py` stays 0
2. One row per stock per run; a second run the same day is idempotent
3. Row count == `instrument_master` stock count, verified by query
4. Wired into `atlas_daily.sh` as `step` (non-blocking)

**C2 — Market-cap backfill**
1. `equity_marketcap` covers ≥ 1,271 stocks (from 302)
2. Top 10 by `market_cap_cr` are recognisably India's largest listed companies
3. Zero NULL or zero `market_cap_cr` among names above the liquidity floor

**C3 — Cap cohort from market-cap rank**
1. New rule applied to the **current** 747: ≥ 95% keep their existing cap label
2. Every disagreement enumerated with both labels and an explanation
3. `stock_lens.ts`, `sector_lens.ts` and `decile_core.cap_bucket()` share one rule
4. Cohort sizes at 1,271: large=100, mid=150, small=250, micro=771

**C4 — Wire the threshold in `build_universe.py`**
1. `is_active` derives from `liquidity_min_traded_value_inr`, read from
   `atlas_thresholds` — no literal in code (rule #4; a pre-commit hook enforces this)
2. Threshold value set to ₹2.5 cr via `/admin/thresholds`, `last_modified_by` = FM
3. `--dry-run` diff prints every name entering and leaving, with its ADV
4. Universe size 1,271 ± 15; exactly 2 current active names drop (AHLUCONT, PRSMJOHNSN),
   or 0 if the held-names clause is accepted
5. Re-running with the floor set to ₹5 cr reproduces 1,037 — proves the threshold is
   genuinely driving the rule and not a coincidence

**C5 — Sectors for new names**
1. All universe members have a non-null sector
2. Distinct sectors ≤ 21 (canonical set)
3. `validate_lenses.py --check A` passes

**C6 — Flip + full recompute**
1. `compute_all.py` completes over the full universe
2. Wall-clock recorded against the 739 baseline; still fits the 16:00 IST cron budget
3. `atlas_lens_scores_daily` scores ≥ 99% of universe members for the run date

**C7 — Validation + composite coverage**
1. `validate_lenses.py --check A/B/C` all pass at the new size
2. Distribution of `lenses_active` reported for new vs existing names
3. Zero new names carry a conviction tier below `min_lenses`
4. Each lens's score distribution over new vs existing names reported — a wildly
   different new-name distribution is a defect signal, not a finding

**C8 — MVs + frontend**
1. `mv_stock_landscape` refreshes to the full universe
2. `/stocks`, `/sectors`, `/today` render with correct cap counts
3. No page regresses on load time
4. Board deploys through `atlas_daily.sh` with all gates green

## Out of scope

ETFs (323 active, currently zero rows in `atlas_lens_scores_daily` — separate defect),
funds (project 2), a `nano` cap tier, and any change to how a lens score is computed.
This project changes who is on the board, not how they are scored.

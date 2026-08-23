# Project 1 — Stock universe 739 → 1,050

Status: **design, awaiting FM approval** · 2026-08-23
Programme: `2026-08-23-atlas-next-programme.md`

## Problem

Atlas scores 739 stocks. The universe is defined by index membership —
`NIFTY 500 ∪ NIFTY MICROCAP250`, set in `build_universe.py:118`.

Three things are wrong with that:

1. **It caps at 750.** Those two indices *are* NSE's Nifty Total Market. All 35
   index families in `de_index_constituents` were enumerated; nothing is larger.
   1,050 is unreachable by any index rule.
2. **Membership has no history.** Every `de_index_constituents` row is
   `effective_to IS NULL` (500 live of 500 total). Today's membership is applied to
   2019 data — survivorship bias that will inflate project 5's IC.
3. **It ignores data we already pay for.** Of 1,673 inactive stocks, **994** already
   meet a full data floor. Atlas ingests ~2,400 and scores 739.

## Measured baseline (2026-08-23)

Of the 1,673 `is_active = false` stocks:

```
1,651  have OHLCV                    1,333  have >=8 quarters financials
1,438  have current OHLCV            1,425  have filings
  994  meet ALL four
```

The 994 ranked by median daily traded value (trailing 6m):

| Rank | Symbol | Median ADV |
|---:|---|---:|
| 100 | NELCO | ₹7.62 cr |
| 200 | MANGLMCEM | ₹4.48 cr |
| **303** | **BALAJITELE** | **₹2.77 cr** ← the 1,050 cutoff |
| 400 | ESABINDIA | ₹1.68 cr |
| 500 | DJML | ₹0.87 cr |
| 994 | ABMINTLLTD | ₹0.00 cr |

747 active + top 303 eligible = 1,050, at a **₹2.77 cr/day** floor. Below rank ~500
the pool is sub-₹1 cr — a decile there is noise and nothing is executable. 1,050 is
where liquidity stops being credible, not a round number.

## Design

### Universe rule

Universe = **index union (kept whole) ∪ top-N eligible non-index names by liquidity**.

Index membership is an **automatic pass**. Any name in `NIFTY 500 ∪ NIFTY MICROCAP250`
stays in the universe regardless of trading history — NSE has already vetted it on
free-float and liquidity, and the alternative evicts recent IPOs, which are exactly the
names an FM most wants covered.

*This correction came out of spec self-review.* An eligibility-only rule was measured
against the current 747 and would have **evicted 94 of them** — 82 failing a 2-year
OHLCV floor (recent listings), 39 failing 8 quarters of financials, 2 with no filings;
only 653 passed all four. A rule that shrinks coverage of new large listings while
claiming to widen coverage is the wrong rule.

So eligibility and liquidity rank govern the **expansion** only — the ~300 names being
added from outside the indices.

*Eligibility for expansion candidates* (all four, else excluded):
- ≥ 500 OHLCV rows (~2y of trading)
- most recent OHLCV within 5 trading days of the run
- ≥ 8 quarters in `financials_quarterly`
- ≥ 1 row in `lens_filings`

*Rank:* `percentile_cont(0.5)` of `close_adj * volume` over the trailing 126 trading
days. Median, not mean — one block deal must not promote an illiquid name.

*N:* total universe target 1,050, stored in `atlas_thresholds` (architectural rule #4 —
no hardcoded methodology numbers; FM-editable at `/admin/thresholds`). Expansion slots =
1,050 − index-union size (750 today), so ~300. The index union floats with NSE
reconstitution; the expansion absorbs the difference and the total stays at target.

*Cadence:* recomputed **monthly**, not daily. Daily would thrash membership around the
cutoff and churn every downstream decile.

### Universe history

New table `atlas_universe_snapshot`:

```
date · instrument_id · in_universe · adv_median_126d · elig_ohlcv · elig_current
     · elig_financials · elig_filings · liquidity_rank · computed_at
```

Appended **daily** (cheap: 2,400 rows/day), independent of the monthly membership
recompute. Every date's membership and the reason for it becomes reconstructable.
This is chunk 1 and lands before anything else — it starts the history clock, and
the record it creates cannot be backfilled later.

### Cap cohort — the prerequisite

Production buckets caps by index membership, in **frontend SQL**:

```sql
-- frontend/src/lib/queries/stock_lens.ts:107 (and sector_lens.ts:86)
WHEN bool_or(index_code='NIFTY 100')       THEN 'large'
WHEN bool_or(index_code='NIFTY MIDCAP 150')THEN 'mid'
WHEN bool_or(index_code='NIFTY SMLCAP 250')THEN 'small'
ELSE 'micro'
```

All 303 new names are in no index, so all 303 become `micro`. That cohort goes
250 → 553. Deciles are cut *within* cohort, so every micro decile, the Leader badge
and the `/stocks` cap filter change meaning — silently, with no error anywhere.

Fix: derive cap from **market-cap rank**, which is what the index rule was
approximating all along:

| Rank by full market cap | Cap |
|---|---|
| 1–100 | large |
| 101–250 | mid |
| 251–500 | small |
| 501+ | micro |

Matches SEBI's definition, matches `decile_core.py`'s existing thresholds, and matches
what the index rule already produces for the current 750 — which makes it *regression
testable*: the existing 747 must keep their labels.

Blocker: `equity_marketcap` covers **302 of 2,411** stocks. `fetch_marketcap.py`
(Screener, rate-limited, resumable) must backfill the full universe first.

Four tiers retained. A `nano` split at 751+ is deferred — 550 names still gives
55 per decile, which is statistically fine. Add it if micro-cohort deciles prove
unstable.

## Risks

| | Risk | Severity | Handling |
|---|---|---|---|
| R1 | Cap cohort collapses to `micro` | **High** | C2+C3, prerequisite chunks |
| R2 | 303 new names lack sectors — `validate_lenses` asserts every active stock has one of ≤21 canonical sectors | High | C5, gated |
| R3 | Compute runtime +42% on every lens | Medium | Measured in C6 before the flip |
| R4 | Microcap data is thin — a lens scoring off 2 filings looks identical to one scoring off 200 | **High** | C7 per-lens data-sufficiency guards; below minimum → NULL, never a default score (rule #0) |
| R5 | Frontend/MVs assume ~750 (`mv_stock_landscape` = 747 rows) | Medium | C8 |
| R6 | Screener rate-limits during the market-cap backfill | Low | Fetcher is already resumable |
| R7 | An eligibility-only rule evicts 94 current names (82 recent listings) | **Resolved in design** | Index union is an automatic pass; eligibility governs expansion only |

**Noted, not touched:** `scripts/foundation/decile_core.py` has no callers anywhere in
the repo — production decile logic lives in the frontend SQL above. Pre-existing; flagged
per the standing rule, not deleted. If C3 changes cap derivation, `decile_core.cap_bucket()`
should be changed in step so the two do not diverge further.

## Chunks

Each chunk's exit criteria assert on **real produced output**, never fixtures (rule #0).

**C1 — Universe snapshot table + daily writer**
1. Migration creates `atlas_universe_snapshot`; `schema_gate.py` stays 0
2. Writer appends one row per stock per run; second run same day is idempotent
3. Row count == `instrument_master` stock count, verified by query
4. Wired into `atlas_daily.sh` as `step` (non-blocking)

**C2 — Market-cap backfill**
1. `equity_marketcap` covers ≥ 1,050 of the target universe (from 302)
2. Top 10 by `market_cap_cr` are recognisably India's largest listed companies
3. Zero NULL/zero `market_cap_cr` among the top 1,050 by liquidity

**C3 — Cap cohort from market-cap rank**
1. New rule applied to the **current** 747: ≥ 95% keep their existing cap label
2. Every disagreement is enumerated with both labels and an explanation
3. `stock_lens.ts`, `sector_lens.ts` and `decile_core.cap_bucket()` all use one rule
4. Cohort sizes at 1,050: large=100, mid=150, small=250, micro=550

**C4 — Universe rule in `build_universe.py`**
1. `--dry-run` diff prints exactly which names enter and leave, with ADV
2. Threshold rows (`universe_target_n`, eligibility minimums) present in `atlas_thresholds`
3. Universe size == 1,050 ± 0; expansion liquidity floor ≥ ₹2.5 cr
4. **Zero evictions** — all 747 current active names are retained (index union is an
   automatic pass, so this is a hard assertion, not a best-effort one)
5. Every added name is outside `NIFTY 500 ∪ NIFTY MICROCAP250` and passes all four
   eligibility tests — verified by query, not by inspection

**C5 — Sectors for new names**
1. All 1,050 have a non-null sector
2. Distinct sectors ≤ 21 (canonical set)
3. `validate_lenses.py --check A` passes

**C6 — Flip + full recompute**
1. `compute_all.py` completes over 1,050
2. Wall-clock recorded and compared against the 739 baseline
3. `atlas_lens_scores_daily` has ≥ 1,040 stocks scored for the run date
4. Nightly window still fits inside the 16:00 IST cron budget

**C7 — Validation + data-sufficiency guards**
1. `validate_lenses.py --check A/B/C` all pass at 1,050
2. Each lens declares a minimum-input threshold; below it the score is **NULL**
3. Zero new names carry a non-null score on a lens whose inputs are below minimum
4. Distribution of each lens over new vs existing names reported — a new-name
   distribution that is wildly different is a defect signal, not a finding

**C8 — MVs + frontend**
1. `mv_stock_landscape` refreshes to 1,050 rows
2. `/stocks`, `/sectors`, `/today` render with correct cap counts
3. No page regresses on load time
4. Board deploys through `atlas_daily.sh` with all gates green

## Out of scope

ETFs (323 active, currently zero rows in `atlas_lens_scores_daily` — separate defect),
funds (project 2), `nano` cap tier, and any change to lens methodology. This project
widens the universe; it does not touch how a score is computed.

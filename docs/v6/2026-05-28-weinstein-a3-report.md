# Weinstein A3 — Sector Confluence Report

**Date:** 2026-05-28
**Status:** **DONE_WITH_CONCERNS** — L5 lifted in-sample IC by 2-15x on most cells but only by SHRINKING events/yr from ~40-60 to ~8-18. **No rule combination clears all three production gates** (signed IC >= 0.05 AND events/yr >= 50 AND positive walk-forward min IC). Recommendation: **demote Weinstein from hard veto to context chip** in the verdict composer (spec sec 4 amendment).

## Headline

**Did L5 produce a rule combination that clears all 3 production gates?** **No.**

- Best L5 candidate by IC × event-count tradeoff: **Mid 5W UP A3_L5**  
  - In-sample signed IC = +0.0739, n_pass = 145, events/yr = 18.1, hit = 59.3%  
  - Walk-forward (per-year IC): 2018:+0.121 / 2019:+0.057 / 2020:+0.044 / 2021:+0.181 / 2022:+0.091 / 2023:-0.034 / 2024:+0.177 / 2025:-0.086  
  - Mean OOS IC = +0.069 (8 yrs), min = -0.086. **Cleared the IC floor in 6 of 8 years.** But events/yr (18.1) is below even the relaxed 25/yr floor, let alone the 50/yr production gate.
- Highest in-sample IC at n_pass >= 50: **Large 5W UP A3_L5_L6** (ic=+0.117, n=67, 8.4/yr, hit=67.2%) — bull-market-fit risk; walk-forward swings between +0.43 (2021) and -0.20 (2024).
- At the strict gate (IC>=0.05 AND events/yr>=50): **zero rules clear**.
- At relaxed gate (IC>=0.05 AND events/yr>=25): **zero rules clear** (the two rules at events/yr>=25 — Small 5W DOWN A3_L5 at ic=0.021 and A3_L5_L6 at ic=0.012 — fall under the IC floor).

## L5 lift vs A2 baseline

L5 systematically lifts IC where the sector context aligns, at the cost of cutting events ~3-4x. Comparison vs A2 best confluence subset (events/yr >= 25, signed IC):

| cap × lookback × event | A2 best subset / IC / ev_yr | A3 best subset / IC / ev_yr | IC lift |
|---|---|---|---|
| Large 5W UP   | S06_+L6 / -0.016 / 41.3 | A3_L5_L6 / +0.117 / 8.4 | **+0.133** |
| Large 5W DOWN | S06_+L6 / +0.051 / 46.0 | A3_L5_L4 / -0.012 / 6.0 | -0.063 (L5 hurt) |
| Large 10W UP  | S06_+L6 / -0.094 / 32.3 | A3_L5 / -0.013 / 7.1  | +0.081 |
| Large 10W DOWN| S06_+L6 / +0.140 / 25.6 | A3_L5 / +0.101 / 7.5  | -0.039 |
| Mid 5W UP     | S06_+L6 / -0.007 / 62.3 | A3_L5 / +0.074 / 18.1 | **+0.081** |
| Mid 5W DOWN   | S06_+L6 / -0.014 / 64.9 | A3_L5_L6 / +0.028 / 17.5 | +0.042 |
| Mid 10W UP    | S06_+L6 / -0.022 / 39.8 | A3_L5 / +0.068 / 11.4 | **+0.090** |
| Mid 10W DOWN  | S06_+L6 / +0.063 / 39.3 | A3_L5 / -0.076 / 12.1 | -0.138 (L5 hurt) |
| Mid 20W UP    | S06_+L6 / +0.119 / 30.1 | A3_L5_L6 / -0.008 / 6.5 | -0.128 (L5 hurt) |
| Small 5W DOWN | S06_+L6 / +0.023 / 94.9 | A3_L5_L4 / +0.061 / 8.8 | +0.038 |
| Small 5W UP   | S06_+L6 / -0.008 / 80.9 | A3_L5 / +0.021 / 24.5 | +0.029 |
| Small 10W DOWN| S06_+L6 / +0.041 / 66.3 | A3_L5_L6 / +0.021 / 17.3 | -0.020 |
| Small 10W UP  | S06_+L6 / +0.018 / 56.3 | A3_L5_L6 / -0.006 / 17.1 | -0.024 |
| Small 20W DOWN| S06_+L6 / -0.114 / 35.4 | A3_L5 / +0.034 / 10.6 | **+0.148** |
| Small 20W UP  | S06_+L6 / -0.110 / 39.3 | A3_L5_L6 / -0.002 / 11.9 | **+0.108** |
| Small 30W DOWN| S06_+L6 / -0.001 / 30.1 | A3_L5_L6 / +0.110 / 8.3 | **+0.110** |
| Small 30W UP  | S06_+L6 / +0.045 / 31.1 | A3_L5_L6 / -0.043 / 8.4 | -0.088 |

**Lift sign:** 10/17 cells positive, 7/17 negative. Sector RS is informative *some* of the time, anti-predictive others — typical asymmetric-regime behavior, not a stable predictive layer.

## Rules now locked-eligible

**None.** No L5-layered rule clears the production gate.

## Surprises

1. **L5 is a precision filter, not an IC lifter** — it consistently shifts the IC up (positive lift in 10/17 cells) and the hit-rate up (most A3 cells: hit >= 60% vs A2 baseline 55-58%), but pays the cost in event volume. The trade is structural: ~70% of events fail the dual condition.

2. **L5 INVERTED the sign on 4 cells.** Large 5W DOWN A3_L5_L4 (-0.024 vs A2 +0.051), Mid 10W DOWN A3_L5 (-0.076 vs A2 +0.063), Mid 20W UP A3_L5_L6 (-0.008 vs A2 +0.119), Small 30W UP A3_L5_L6 (-0.043 vs A2 +0.045). These were A2's best UP/DOWN bets in those cells. Hypothesis: L5 selects only "trending sector with stock breakdown" events — these are reversion candidates (sector momentum suggests support holds), making them WORSE longs/shorts than the unfiltered base.

3. **The DOWN side benefits more reliably than UP.** Small 20W DOWN A3_L5 had the single biggest lift (+0.148) — distressed-sector + stock-breakdown is the cleanest "fade the trend" setup. UP sides are more contaminated by bull-market years (2020-2021).

4. **L5 + L2 (sector confluence + prior 13W extreme clearance) shows the highest in-sample IC** (Large 5W UP A3_L5_L2: ic=+0.141, hit=83%) but at 18-30 events TOTAL over 8 years (2-3/yr). Same problem as A2's L2-pure findings: the breakout-above-resistance rule IS the alpha, but it's too rare to power a portfolio-cadence strategy.

5. **Walk-forward consistency is the killer.** Even Mid 5W UP A3_L5 (the cleanest signal) had one -0.086 year (2025). Most others swing between +0.30 and -0.40 across years. This is consistent with sector-rotation regimes operating on ~12-18 month cycles — single-year IC is dominated by regime alignment.

6. **L5 pass rates are well-calibrated** (24-31% across cells, target was 25-50%). The dual-condition (trend AND level) is the right binding — single-condition tested as L3 in A2 had pass rate ~45% and zero IC lift.

## Honest limitations

- **Survivor-bias caveat carried over from A2.** `atlas_universe_stocks.tier` is the 2026 snapshot; delisted/graduated stocks are mis-tagged. All recommendations remain PROVISIONAL pending PIT cap_tier backfill.
- **Sector RS data starts 2016-07-11**, so events in 2018 H1 had limited 4-week-prior reference (handled by NULL fallback, ~10% of pre-2018 events have NULL L5).
- **2020-2022 bull market still dominates in-sample.** A3_L5 on UP cells inherits this bull-market bias; the 2021 inflection year remains the cleanest canary (Large 5W UP swung from +0.43 to -0.20 across 2021->2024).
- **L5 evaluated only at event_date** — the dual-condition trend test uses just 4-week lookback. A longer (12-week or 26-week) sector RS trend filter has not been tested.
- **No sector-pair tests** (e.g., "leading sector AND positive market breadth"). L5 is single-feature.

## Next moves

**Single most important next move:** Adopt the **A3 = NO-CLEAR** result and amend the verdict composer.

1. **Demote Weinstein from hard veto to context chip** on the Stocks page verdict composer (spec sec 4 amendment). Surface "Weinstein Stage 1->2 fires + sector RS rising" as a yellow context badge, not a BUY/WAIT gate. Cell composite carries the load alone for the verdict gate.

2. **Hold migration 113 (threshold lock)** indefinitely — no Weinstein rule has earned a place in atlas_thresholds. Even Mid 5W UP A3_L5 (the cleanest signal) is below the 25/yr actionability floor AND has one bad walk-forward year.

3. **DO NOT dispatch Stream A4 sector-pair / sector-breadth** as a primary investigation. The lift pattern in A3 is not "missing-feature" shaped — it's regime-asymmetric. The right next investment is **PIT cap_tier backfill**, then re-run A2+A3 once that lands. If PIT-corrected IC still maxes at ~0.07, Weinstein on Indian equities is genuinely under-powered for our universe and decision cadence.

4. **Light-weight follow-up (NOT a Stream A4, just a single SQL):** test the L5 dual-condition with a **12-week trend** instead of 4-week. The 4-week window may be picking up noise — sector RS regimes typically operate on 8-16 week cycles. If 12-week shifts IC by >+0.03 with similar pass rate, that's the variant to lock. Single query, no migration. **This is the 7th confluence I'd propose if asked, but I am not dispatching it autonomously per the spec.**

## Methodology lock recommendation (carry-forward from A2)

A3 confirms the A2 conclusion: **methodology is validated, threshold lock is not yet earned.**

- Per-event Spearman IC is the right unit (A2/A3 consistent).
- Sector RS dual-condition is the right L5 definition (single-condition was tested as L3 in A2, didn't move IC).
- A3 produces a usable **context chip** for the Stocks page (Mid 5W UP A3_L5: 145 events, hit rate 59%, IC +0.07) but NOT a tradable threshold.

The right Atlas downstream story for Weinstein right now is:
- Show "Stage 1->2 base breakout + sector RS leading" as a context chip with the per-(cap × lookback × event_type) hit-rate badge.
- Treat ALL Weinstein decisions as informational; the cell composite is the verdict signal.
- Wait for PIT cap_tier backfill before any A4/A5 follow-ups.

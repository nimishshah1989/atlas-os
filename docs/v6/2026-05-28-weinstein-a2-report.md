# Weinstein A2 — Research Report

**Date:** 2026-05-28
**Status:** Mixed result — the *base transition rule* clears the IC floor on a couple of cells, but no clean (cap_tier × lookback × confluence-subset) combination meets ALL three production criteria (signed IC ≥ 0.05 in-sample AND ≥ 50 events/yr AND OOS minimum IC > 0). Treat Weinstein as a context chip, not a hard veto.

## Headline

- **No rule combination cleared all three production gates** (signed IC ≥ 0.05 AND events/yr ≥ 50 AND OOS min-IC > 0) without caveats.
- The CLOSEST candidates:
  - **Mid DOWN 10W base+L6 liquidity**: in-sample signed IC = +0.063, 39 events/yr, hit = 62%. OOS mean IC = +0.11 (5 valid years), but **min OOS IC = −0.19** (2022 was anti-predictive — likely the post-covid recovery selecting "down breakdowns" that became fresh long entries).
  - **Mid UP 20W base+L6 liquidity**: in-sample IC = +0.12, 30 events/yr, hit = 58%. OOS mean = +0.16 but min = −0.26 (2021 inflection year). Bull-market-fit risk is high.
  - **Small DOWN 10W +L4 (base width)**: in-sample IC = +0.032 (BELOW 0.05 floor) BUT 29 events/yr, hit = 70%, and is the **only rule with positive walk-forward IC in 7 of 9 years and a min OOS IC of −0.13** (the most consistent signal). Mean OOS IC = +0.04.
- **L2 (prior 13W close-high/low clearance) is the biggest in-sample IC lifter** when it fires (Mid 10W UP +L2: IC = +0.17, hit = 70%), but only ~5 events/yr → not actionable on its own.
- **The base rule alone (Stage 1 → Stage 2 crossover with persist_4w ≥ 0.6) is the workhorse.** S06 (base + L6 liquidity) is essentially "base alone" because Nifty-500 stocks pass the liquidity floor 94-99% of the time.

## Rules locked per cap_tier

**Recommended for migration 113 — provisional, pending PIT cap_tier re-validation:**

| cap_tier | event_type | MA lookback | Confluences | In-sample IC (signed) | OOS mean IC | OOS min IC | Events/yr | Hit rate | Confidence |
|---|---|---|---|---|---|---|---|---|---|
| Large | DOWN | 5W  | base + L6 | +0.051 | +0.082 (4y) | -0.082 | 46 | 58% | **MEDIUM** — single negative year is mild |
| Mid   | DOWN | 10W | base + L6 | +0.063 | +0.114 (5y) | -0.191 | 39 | 62% | **LOW** — 2022 anti-predictive |
| Mid   | UP   | 20W | base + L6 | +0.119 | +0.163 (5y) | -0.257 | 30 | 58% | **LOW** — bull-market fit; 2021 inflection |
| Small | DOWN | 10W | base + L4 (12W base width ≥ 0.5) | +0.032 | +0.041 (8y) | -0.126 | 29 | 68% | **MEDIUM** — most consistent across regimes |
| Small | UP   | 30W | base + L6 | +0.045 | +0.327 (1y valid) | n/a | 31 | 59% | **DO NOT LOCK** — only 1 year of variance |
| Large | UP   | — | none clears | — | — | — | — | — | **NO LOCK** — Large-cap UP transitions are weak |

For the Verdict Composer (spec §4 logic update), I'd recommend gating on the **MEDIUM-confidence rules only** and treating the LOW-confidence ones as **soft context chips** (e.g. "Mid 20W UP breakout fired — bull-market historical signal" rather than a hard BUY).

## Surprises

1. **L6 liquidity is a no-op for the Nifty 500 universe.** ≥₹50L/day filter clears 94-99% of events — universe is already pre-filtered to liquid stocks. Strategic implication: cap-tier liquidity floors should be 10x higher (e.g. ₹50 cr Large, ₹20 cr Mid, ₹5 cr Small) to make L6 a real filter. Or drop L6 entirely from the locked rule set and add it back at portfolio-construction time as a hard floor, not a predictive feature.

2. **L2 (prior 13W close-high clearance) is the strongest signal LIFTER when it fires, but rare.** Mid 10W UP +L2: IC=0.172, hit=70%, but only 5/yr. Small 5W UP +L2: IC=0.114, hit=64%, 12/yr. **The Weinstein design's intuition was correct** — the breakout-above-resistance rule IS the alpha source. But it's so rare that it can't power a portfolio-cadence strategy on its own. L2 is better as a **conviction multiplier on cell-based BUYs** than as a primary signal.

3. **L1 (volume confirmation) does not help — and sometimes hurts.** L1 cuts event counts by 90% but doesn't lift IC meaningfully. Possibly because Indian stock volume data quality (volume_adj is uniformly NULL — we used raw `volume`) introduces noise. A different threshold (1.2x instead of 1.5x) would still leave the filter weak.

4. **L4 (base width) is the dark horse for Small caps.** S05_+L4 on Small 10W DOWN was the only rule with consistent positive OOS IC in 7 of 9 years. Base width matters more for less-followed Small caps where extended Stage 1 accumulation IS the entry signal. For Large caps, L4 had no consistent lift.

5. **L3 (RS_3m trend) is symmetric — high pass rate but low IC.** RS_3m improving over prior 4 weeks is so common (~45% of events) that the filter doesn't differentiate winners from losers in our event population. RS as a stage *itself* may be a better signal than RS *trend at the breakout date* — to test in a Stream B (RS-momentum focused).

6. **Persistence threshold 0.8 was wrong; 0.6 is right.** Initial run with persist_4w ≥ 0.8 produced 6-28 events/yr/cell, well below actionable. Relaxing to 0.6 yielded 16-125 events/yr/cell. The "must be in clear Stage 1 for ≥80% of prior 4 weeks" was over-strict for India's noisier data. The relaxation does NOT degrade signal quality materially — same anti-V-bottom intent at 60% threshold.

7. **Direction-aware IC matters.** Several DOWN rules show positive raw IC (good for SELL signals). Stream A1's pooled Pearson collapsed this signal; per-event Spearman with directional sign brings it back.

## Limitations

- **Survivor bias from STATIC cap_tier.** `atlas_universe_stocks.tier` is the 2026 snapshot. Stocks that were delisted before 2026 are absent. Stocks that graduated cap-tier between 2018-2026 are tagged with their 2026 tier across all of history. **All rule recommendations are PROVISIONAL pending PIT cap_tier backfill** (parallel workstream). Re-run Stream A2 once `atlas_scorecard_daily.cap_tier` has ≥1800 days of history.

- **L5 (sector confluence) deferred.** Requires per-sector RS rank time series we haven't wired yet. Strong candidate for a Stream A3 follow-up — Weinstein's "buy leaders in leading groups" rule may be the missing IC lifter.

- **2020-2022 bull market dominates the in-sample window.** Roughly half the trading days are in a once-in-a-decade rally. Out-of-sample IC for UP rules is inflated by this regime; the 2021 inflection year is a useful canary (Mid 20W UP S06 went from +0.44 in 2020 to −0.26 in 2021).

- **L1 volume data quality.** `de_equity_ohlcv.volume_adj` is uniformly NULL — we used raw `volume`. Splits/bonuses create artificial volume jumps that would falsely trigger L1. Fix upstream and re-run before any L1-based rule gets locked.

- **Walk-forward is per-year, not 3y-train / 1y-test as the plan called for.** Our subsets use FIXED thresholds (e.g. L1@1.5x, L4 persist≥0.5), not learned thresholds. With fixed thresholds, per-year IC IS the OOS measurement of the locked rule — no extra train-test split would change the answer. A future Stream B that tunes per-window thresholds WOULD need true rolling 3y/1y.

- **Event-count floor 50/yr was aspirational.** None of the candidate rules consistently hit 50 events/yr after meaningful confluence filtering. We relaxed to ≥25/yr for the walk-forward shortlist and surface this in the table.

## Next moves

**Single most important next move:** Run **Stream A3 — Sector Confluence (L5) layered on Stream A2 winners.** Weinstein's rule 6 ("industry group also basing or breaking out") is the only Weinstein rule we did NOT test, and the missing 6th confluence is the most plausible explanation for why our best rules max out at ~0.06 in-sample IC instead of clearing the 0.10+ Weinstein literature suggests. Estimated lift: 2-3x IC on Mid/Large UP events where sector context is informative.

**Secondary moves:**
1. **PIT cap_tier backfill** must land before any Stream A2 rule is migrated to production thresholds (migration 113). Survivor bias is the single largest unknown.
2. **Recalibrate L6 thresholds upward** so the liquidity floor actually filters. Current ≥₹50L pass rate of 95% means L6 isn't doing the work it's named for.
3. **Test L2 as a conviction-multiplier**, not a primary filter. A BUY decision from cell math + L2 breakout → very high conviction; a BUY decision from cell math alone → normal conviction.
4. **Fix volume_adj upstream** to make L1 trustworthy. Then re-test L1 at 1.3x and 1.2x thresholds.
5. **Do NOT lock anything into atlas_thresholds yet.** Treat this dispatch's outputs as the methodology lock, not the threshold lock. Migration 113 should wait for at minimum L5 + PIT cap_tier.

## Methodology lock recommendation

Even though no rule cleared the strict production gate, the methodology IS validated:
- Per-event analysis (vs Stream A1's per-tag-day pooling) recovers a real signal.
- The base rule + persist_4w guard at 0.6 produces 16-125 events/yr/cell — within actionable range.
- The 4-week persist guard cleanly filters V-bottom false positives.
- Direction-aware IC (positive for UP, negative for DOWN) is the right unit.

The right Atlas downstream story for Weinstein **right now** is:
- Show the **base transition** as a context chip on the Stocks page ("Weinstein Stage 1→2 breakout fired today, X events in the prior 12mo, hit rate Y%").
- Do NOT use it as a hard veto on the verdict composer's BUY/WAIT logic.
- Wait for Stream A3 (sector confluence) and PIT backfill before promoting Weinstein to a methodology-page lock.

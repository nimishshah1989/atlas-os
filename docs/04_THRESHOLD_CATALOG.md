# Atlas — Threshold Catalog

**Document:** 04_THRESHOLD_CATALOG
**Status:** v0
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**References:**
- `00_METHODOLOGY_LOCK.md` (defines what each threshold controls)
- `02_DATABASE_SCHEMA.md` (defines the `atlas_thresholds` table that stores these values)

---

## Purpose of This Document

Atlas is a **deterministic, rule-driven, threshold-based** classification system. Every state classification, every gate, every decision reduces to a comparison of a measured value against a threshold.

This document catalogs every tunable threshold across the framework — what it does, what its default value is, what range it's allowed to take, and what changing it affects. This is:

1. **The fund manager's reference** — what can be tuned, how to think about each parameter
2. **The seed data for `atlas_thresholds`** — populated at Atlas-M1 with the values listed here
3. **The transparency contract** — every state pill in the UI traces back to thresholds in this document

**Editable, not hardcoded.** All these values live in the `atlas_thresholds` table. Code reads from the database at run start. To change a threshold, the fund manager updates the value via the UI admin page; the change is logged in `atlas_threshold_history`; an explicit "Apply & Reclassify" action triggers state recomputation across the full 12-year history.

**Re-classification, not re-computation.** Threshold changes only re-classify states; the underlying primitive metric values (returns, RS, EMAs, etc.) don't change. Re-classifying ~2.25M state rows takes minutes, not hours.

---

## 1. Scope of What's Tunable

### 1.1 In Scope (Tunable)

These are values where reasonable people might disagree on the right number. Fund manager can tune:

- Quintile cutoffs for RS classification (top quintile, bottom quintile)
- Risk state boundaries (extension percentages, vol ratio bands)
- Volume state boundaries (expansion thresholds, effort ratios)
- Sector state boundaries (participation thresholds)
- Market regime boundaries (breadth percentages, VIX cutoffs)
- Mutual fund lens boundaries (AUM percentage thresholds)
- Pre-classification gate values (liquidity threshold, history minimum)
- Decision rule margins (proximity gates, ATR multipliers)
- Override conditions (Weinstein slope tolerance, dislocation multiplier)

### 1.2 Out of Scope (Structural — Methodology Changes)

These are NOT tunable through the threshold system. Changing them is a methodology revision requiring sign-off:

- **Time horizons** — 1W=5, 1M=21, 3M=63 trading days. These are the windows; changing them is changing what "1 month" means.
- **Number of states** — 7 RS states, 5 momentum states, 5 risk states, 5 volume states, 4 sector states, 4 market regime states. Adding/removing a state is methodology.
- **Choice of benchmarks** — adding/removing user benchmarks is methodology.
- **Choice of primitives** — using something other than EMA-ratio for momentum is methodology.
- **State name labels** — calling "Leader" something else is methodology.
- **Numéraire choices** — adding silver as a numéraire is methodology.
- **Sector taxonomy source** — switching from NSE to GICS is methodology.

Methodology revisions require: written change proposal, fund manager + architect sign-off, version bump, downstream document review, full historical recompute (not just reclassify).

### 1.3 Threshold Count

35 thresholds total in v0. Distributed across:

| Category | Count |
|---|---|
| Pre-classification gates | 2 |
| RS classification | 2 |
| RS momentum classification | 3 |
| Risk classification | 5 |
| Volume classification | 4 |
| Weinstein gate | 1 |
| Stage-1 base detection | 2 |
| Sector classification | 3 |
| Market regime classification | 8 |
| Mutual fund lens classification | 4 |
| Decision engine margins | 1 |
| **Total** | **35** |

---

## 2. Pre-Classification Gates

Per methodology Section 3.3.

### 2.1 `liquidity_min_traded_value_inr`

**Default:** 50,000,000 (₹5 crore)
**Allowed range:** 10,000,000 (₹1 cr) to 250,000,000 (₹25 cr)
**Units:** INR (rupees)
**Methodology section:** 3.3
**Description:** Minimum trailing 60-day median daily traded value (close × volume) for an instrument to pass the liquidity gate. Below this, instrument is classified `ILLIQUID` and surfaced separately rather than in the main investability output.
**Affects:** Stock and ETF classification eligibility.
**Tuning rationale:** Lower threshold includes more micro-caps but adds noise; higher threshold restricts universe to higher-conviction names only.

### 2.2 `history_min_trading_days`

**Default:** 252
**Allowed range:** 180 to 504
**Units:** trading days
**Methodology section:** 3.3
**Description:** Minimum trading days of OHLCV history required before any state classification. Below this, instrument classified `INSUFFICIENT_HISTORY`.
**Affects:** Newly listed stocks become eligible for classification only after meeting this threshold.
**Tuning rationale:** 252 = 1 trading year; minimum needed for 12-month return windows. Lower threshold (180) admits stocks faster post-IPO but with less basis for momentum signals; higher (504) demands two full years for higher conviction.

---

## 3. RS Classification Thresholds

Per methodology Section 7.1.

### 3.1 `rs_quintile_top`

**Default:** 0.80
**Allowed range:** 0.70 to 0.90
**Units:** percentile (0.0–1.0 scale)
**Methodology section:** 7.1
**Description:** Top-quintile cutoff for RS percentile rank within tier. Stocks with `rs_pctile_<window>` ≥ this value are "top quintile" for that window.
**Affects:** Eligibility for Leader, Strong, Consolidating, Emerging classifications.
**Tuning rationale:** 0.80 = top 20%, the standard quintile definition. Lowering to 0.70 widens the leader pool (top 30%) — more inclusive but less selective. Raising to 0.90 narrows to top decile — sharper signal but fewer candidates per day.

### 3.2 `rs_quintile_bottom`

**Default:** 0.20
**Allowed range:** 0.10 to 0.30
**Units:** percentile
**Methodology section:** 7.1
**Description:** Bottom-quintile cutoff. Stocks with `rs_pctile_<window>` ≤ this value are "bottom quintile" for that window.
**Affects:** Eligibility for Weak and Laggard classifications.
**Tuning rationale:** Symmetric counterpart to `rs_quintile_top`. Tighter (0.10) catches only the weakest names; looser (0.30) flags more names as Weak/Laggard.

---

## 4. RS Momentum Classification Thresholds

Per methodology Section 7.2.

### 4.1 `momentum_flat_band_pct`

**Default:** 0.02 (2%)
**Allowed range:** 0.01 to 0.05
**Units:** decimal (proportion)
**Methodology section:** 7.2
**Description:** "Flat" classification fires when `|ema_10_ratio - 1| ≤ this value`. Above threshold = directional; below threshold = flat.
**Affects:** Distinguishes Flat from Improving/Deteriorating.
**Tuning rationale:** 2% ratio band is reasonable for daily classification on Indian equities. Tighter band (1%) makes Flat rarer; looser (5%) makes Flat dominant for sideways markets.

### 4.2 `momentum_ema_convergence_pct`

**Default:** 0.01 (1%)
**Allowed range:** 0.005 to 0.03
**Units:** decimal
**Methodology section:** 7.2
**Description:** "Flat" also fires when EMA10 and EMA20 are within this proportion of each other. Captures sideways consolidation.
**Affects:** Same as above.
**Tuning rationale:** Tight band (1%) catches genuine convergence; loose band over-classifies as Flat.

### 4.3 `momentum_breakout_lookback_days`

**Default:** 20
**Allowed range:** 10 to 50
**Units:** trading days
**Methodology section:** 7.2
**Description:** Lookback window for "ema_10_ratio at 20-day high/low" detection. Used for Accelerating and Collapsing classifications.
**Affects:** How recently EMA10 must hit a high/low to qualify as Accelerating/Collapsing.
**Tuning rationale:** 20 days = standard "month" lookback. Shorter window (10) classifies more stocks as Accelerating but with thinner basis; longer (50) requires more sustained breakouts.

---

## 5. Risk Classification Thresholds

Per methodology Section 7.3.

### 5.1 `risk_extension_low_max_pct`

**Default:** 25
**Allowed range:** 15 to 35
**Units:** percent
**Methodology section:** 7.3
**Description:** Maximum extension % above 200-EMA for Low/Normal risk classification. Above this enters Elevated zone.
**Affects:** Boundary between Low/Normal and Elevated risk.
**Tuning rationale:** 25% extension is a typical "moderately stretched" benchmark for Indian equities. Lower threshold (15%) classifies more stocks as Elevated earlier; higher (35%) is more permissive.

### 5.2 `risk_extension_high_min_pct`

**Default:** 40
**Allowed range:** 30 to 60
**Units:** percent
**Methodology section:** 7.3
**Description:** Minimum extension % for High risk classification. Above this, no new entries permitted.
**Affects:** When stocks become "Avoid Entry" on extension grounds.
**Tuning rationale:** 40% extension is meaningfully stretched. Below 40% is an entry-permissible zone; above 40% historically precedes mean reversion. Lower threshold (30%) is more conservative; higher (60%) allows holding through extended moves.

### 5.3 `risk_vol_ratio_normal_max`

**Default:** 1.25
**Allowed range:** 1.10 to 1.50
**Units:** ratio
**Methodology section:** 7.3
**Description:** Maximum vol ratio (stock vol / benchmark vol) for Normal risk. Above enters Elevated.
**Affects:** Boundary between Normal and Elevated on volatility dimension.
**Tuning rationale:** 1.25 = stock 25% more volatile than benchmark. Tighter (1.10) catches volatility expansion earlier; looser (1.50) allows more volatile names in Normal.

### 5.4 `risk_vol_ratio_high_min`

**Default:** 1.6
**Allowed range:** 1.4 to 2.0
**Units:** ratio
**Methodology section:** 7.3
**Description:** Minimum vol ratio for High risk classification.
**Affects:** Volatility-based exclusion for new entries.
**Tuning rationale:** 1.6 = stock 60% more volatile than benchmark — meaningfully risky. Lower (1.4) is more conservative; higher (2.0) allows volatile growth names.

### 5.5 `risk_vol_ratio_low_max`

**Default:** 1.0
**Allowed range:** 0.80 to 1.10
**Units:** ratio
**Methodology section:** 7.3
**Description:** Maximum vol ratio for Low risk classification. At or below benchmark vol = Low risk.
**Affects:** Boundary between Low and Normal risk.
**Tuning rationale:** Anything ≤ 1.0 means stock is no more volatile than its benchmark — by definition low-risk. Slight tolerance to 1.05 acceptable; below 0.80 too restrictive.

---

## 6. Volume Classification Thresholds

Per methodology Section 7.4.

### 6.1 `volume_accumulation_expansion_min`

**Default:** 1.2
**Allowed range:** 1.05 to 1.5
**Units:** ratio
**Methodology section:** 7.4
**Description:** Minimum 20d/252d volume ratio for Accumulation. Volume must be at least 20% above its long-run baseline.
**Affects:** Triggers Accumulation classification.
**Tuning rationale:** 1.2 = 20% volume expansion, the canonical "noticeable institutional interest" threshold. Tighter (1.05) classifies more days as Accumulation — noisier but earlier signal; looser (1.5) demands stronger confirmation.

### 6.2 `volume_accumulation_effort_min`

**Default:** 1.3
**Allowed range:** 1.1 to 1.8
**Units:** ratio
**Methodology section:** 7.4
**Description:** Minimum 63-day up-volume / down-volume ratio for Accumulation. Buying pressure must dominate selling pressure.
**Affects:** Triggers Accumulation classification (in conjunction with expansion).
**Tuning rationale:** 1.3 = up-day volume 30% higher than down-day. Confirms institutional bias to buy. Tighter (1.1) is barely above neutral; looser (1.8) demands strong bias.

### 6.3 `volume_distribution_effort_max`

**Default:** 0.8
**Allowed range:** 0.6 to 0.9
**Units:** ratio
**Methodology section:** 7.4
**Description:** Maximum effort_ratio_63 for Distribution classification. Below this, sellers dominate.
**Affects:** Triggers Distribution.
**Tuning rationale:** 0.8 = down-volume 25% higher than up-volume. Below 0.8 suggests genuine selling pressure. Higher (0.9) more permissive, lower (0.6) catches only severe distribution.

### 6.4 `volume_heavy_distribution_effort_max`

**Default:** 0.6
**Allowed range:** 0.4 to 0.7
**Units:** ratio
**Methodology section:** 7.4
**Description:** Maximum effort ratio for Heavy Distribution. Combined with rising volume — institutions exiting on size.
**Affects:** Triggers Heavy Distribution (worst volume state).
**Tuning rationale:** 0.6 = down-volume 67% higher than up-volume on average — clear institutional dumping. Lower (0.4) catches only crashes; higher (0.7) blurs into ordinary Distribution.

---

## 7. Weinstein Gate Threshold

Per methodology Section 7.1.

### 7.1 `weinstein_slope_sigma_min`

**Default:** -0.5
**Allowed range:** -1.0 to 0.0
**Units:** standard deviations (σ)
**Methodology section:** 7.1
**Description:** Minimum 30-week MA slope (4-week change, σ-normalized against 252-day stdev) for the "flat or rising" condition. Slope below this fails the Weinstein gate.
**Affects:** Whether stocks can be classified Leader, Strong, Consolidating, or Emerging.
**Tuning rationale:** -0.5σ allows mild downward drift in the MA — captures stocks in late-stage basing where MA is just turning. Tighter (0.0) requires actively rising MA; looser (-1.0) admits stocks with notable downtrend.

---

## 8. Stage-1 Base Detection Thresholds

Per methodology Section 7.1.

### 8.1 `stage1_weak_weeks_min`

**Default:** 8
**Allowed range:** 6 to 10
**Units:** weeks
**Methodology section:** 7.1
**Description:** Minimum number of weekly closes (out of last 10) where stock was classified in {Average, Weak, Laggard} for Stage-1 base qualification.
**Affects:** Eligibility for Emerging classification.
**Tuning rationale:** 8/10 means a clear basing pattern (only 2 weeks of strength out of 10). Tighter (10/10) demands perfect base; looser (6/10) admits stocks with brief midway rallies.

### 8.2 `stage1_ma_flat_sigma_max`

**Default:** 0.5
**Allowed range:** 0.3 to 1.0
**Units:** σ
**Methodology section:** 7.1
**Description:** Maximum absolute σ-normalized slope of 30-week MA for "flat" base condition. Together with weak-weeks count, qualifies a Stage-1 base.
**Affects:** Eligibility for Emerging classification (in conjunction with weak-weeks count).
**Tuning rationale:** ±0.5σ defines a flat MA. Tighter (±0.3σ) requires very flat MA; looser (±1.0σ) admits mildly trending MAs.

---

## 9. Sector Classification Thresholds

Per methodology Section 10.5.

### 9.1 `sector_overweight_participation_min_pct`

**Default:** 50
**Allowed range:** 35 to 70
**Units:** percent
**Methodology section:** 10.5
**Description:** Minimum percentage of stocks in sector classified in {Leader, Strong, Emerging} for Overweight classification.
**Affects:** Triggers Overweight sector state (combined with bottom-up RS state and momentum).
**Tuning rationale:** 50% means at least half of sector constituents are showing strength — clearly broad-based leadership. Lower threshold (35%) admits narrower sector leadership; higher (70%) demands very broad participation.

### 9.2 `sector_underweight_participation_max_pct`

**Default:** 30
**Allowed range:** 20 to 45
**Units:** percent
**Methodology section:** 10.5
**Description:** Maximum percentage participation for Underweight classification. Below this, breadth is weak.
**Affects:** Triggers Underweight sector state.
**Tuning rationale:** Below 30% means majority of sector is not in strong states. Tighter (20%) requires very weak breadth; looser (45%) is more conservative.

### 9.3 `sector_avoid_participation_max_pct`

**Default:** 25
**Allowed range:** 15 to 35
**Units:** percent
**Methodology section:** 10.5
**Description:** Maximum percentage participation for Avoid classification (combined with Laggard bottom-up RS).
**Affects:** Triggers Avoid sector state — exit signal.
**Tuning rationale:** Below 25% is severe weakness. Adjust based on tolerance for staying invested in struggling sectors.

---

## 10. Market Regime Classification Thresholds

Per methodology Section 11.4.

### 10.1 `regime_risk_on_breadth_min_pct`

**Default:** 60
**Allowed range:** 50 to 75
**Units:** percent
**Methodology section:** 11.4
**Description:** Minimum `pct_above_ema_50` for Risk-On regime.
**Affects:** Triggers Risk-On regime (1.0× deployment multiplier).
**Tuning rationale:** 60% breadth = strong majority of Nifty 500 above 50-EMA. Tighter (75%) is very rare regime; looser (50%) too easily declares Risk-On.

### 10.2 `regime_constructive_breadth_min_pct`

**Default:** 50
**Allowed range:** 40 to 60
**Units:** percent
**Methodology section:** 11.4
**Description:** Minimum `pct_above_ema_50` for Constructive regime (lower bound of the [50%, 60%] band).
**Affects:** Triggers Constructive regime (0.7× multiplier).
**Tuning rationale:** Boundary between Cautious and Constructive. Adjust together with `regime_risk_on_breadth_min_pct`.

### 10.3 `regime_risk_off_breadth_max_pct`

**Default:** 40
**Allowed range:** 25 to 50
**Units:** percent
**Methodology section:** 11.4
**Description:** Maximum `pct_above_ema_50` for Risk-Off regime.
**Affects:** Triggers Risk-Off regime (0.0× multiplier — full exit).
**Tuning rationale:** Below 40% breadth = clear bear regime. Tighter (25%) requires deep weakness; looser (50%) declares Risk-Off too readily.

### 10.4 `regime_risk_on_vix_max`

**Default:** 18
**Allowed range:** 14 to 22
**Units:** VIX points
**Methodology section:** 11.4
**Description:** Maximum India VIX for Risk-On regime.
**Affects:** Volatility ceiling for Risk-On — high VIX precludes full deployment regardless of breadth.
**Tuning rationale:** VIX < 18 historically corresponds to calm markets in India. Higher threshold admits more volatile periods as Risk-On.

### 10.5 `regime_constructive_vix_max`

**Default:** 22
**Allowed range:** 18 to 28
**Units:** VIX points
**Methodology section:** 11.4
**Description:** Maximum India VIX for Constructive regime.
**Affects:** Volatility ceiling for Constructive.

### 10.6 `regime_cautious_vix_max`

**Default:** 28
**Allowed range:** 24 to 35
**Units:** VIX points
**Methodology section:** 11.4
**Description:** Maximum India VIX for Cautious regime. Above this, Risk-Off engaged.
**Affects:** Boundary between Cautious and Risk-Off on volatility dimension.

### 10.7 `regime_near_200ema_band_pct`

**Default:** 2
**Allowed range:** 1 to 5
**Units:** percent
**Methodology section:** 11.4
**Description:** Width of "near EMA 200" band for Cautious regime trigger. Nifty 500 within ±this percent of 200-EMA = potentially Cautious.
**Affects:** When market hovering around 200-EMA gets flagged Cautious vs cleanly above/below.
**Tuning rationale:** ±2% gives a meaningful boundary zone; tighter (±1%) makes Cautious rare; looser (±5%) makes Cautious frequent.

### 10.8 `dislocation_vol_multiplier`

**Default:** 4.0
**Allowed range:** 2.5 to 6.0
**Units:** multiplier
**Methodology section:** 11.5
**Description:** Multiple of 252-day median volatility above which dislocation override activates. When 5-day realized vol exceeds this multiple, all classifications suspend.
**Affects:** Triggers system-wide DISLOCATION_SUSPENDED state.
**Tuning rationale:** 4× vol is a clear dislocation event (e.g., March 2020 COVID, October 2008). Lower threshold (2.5×) triggers more often (false alarms); higher (6×) only triggers on extreme events.

---

## 11. Mutual Fund Lens Classification Thresholds

Per methodology Section 12.

### 11.1 `fund_aligned_aum_min_pct`

**Default:** 70
**Allowed range:** 60 to 85
**Units:** percent
**Methodology section:** 12.2
**Description:** Minimum AUM in {Overweight, Neutral} sectors for Lens 2 = Aligned classification.
**Affects:** Triggers Aligned composition state.
**Tuning rationale:** 70% AUM in good sectors = clearly regime-aligned manager. Lower (60%) more permissive; higher (85%) demands very tight alignment.

### 11.2 `fund_avoid_aum_max_pct`

**Default:** 10
**Allowed range:** 5 to 20
**Units:** percent
**Methodology section:** 12.2
**Description:** Maximum AUM in Avoid sectors for Aligned classification.
**Affects:** Excludes managers from Aligned if too much in deteriorating sectors.

### 11.3 `fund_strong_holdings_min_pct`

**Default:** 60
**Allowed range:** 50 to 75
**Units:** percent
**Methodology section:** 12.3
**Description:** Minimum AUM in stocks classified {Leader, Strong, Emerging} for Lens 3 = Strong-Holdings.
**Affects:** Triggers Strong-Holdings classification.
**Tuning rationale:** 60% in strong stocks = quality manager. Lower (50%) more permissive; higher (75%) demands top-quartile holdings.

### 11.4 `fund_weak_holdings_max_pct`

**Default:** 25
**Allowed range:** 15 to 35
**Units:** percent
**Methodology section:** 12.3
**Description:** Maximum AUM in {Weak, Laggard} stocks before triggering Weak-Holdings classification.
**Affects:** Boundary between Decent and Weak-Holdings.

---

## 12. Decision Engine Thresholds

Per methodology Section 13.

### 12.1 `entry_breakout_proximity_max_pct`

**Default:** 5
**Allowed range:** 2 to 10
**Units:** percent
**Methodology section:** 13.3
**Description:** Maximum distance from 20-EMA (as percent) for breakout trigger. Stock must be within this distance for entry to fire — entry on retest, not chase.
**Affects:** When breakout triggers fire vs are blocked by extension.
**Tuning rationale:** 5% from 20-EMA is a reasonable retest zone. Tighter (2%) demands very precise entries; looser (10%) admits chasing.

---

## 13. Tuning Discipline (Important — Read Before Adjusting)

The thresholds above are tunable, but tuning has consequences. Some discipline:

**1. Don't tune to fit recent data.**
If you change `risk_extension_high_min_pct` from 40 to 50 because "lately stocks have been running further before reverting," you're over-fitting. The threshold framework is supposed to express the methodology's view of risk, not chase what recently worked.

**2. Tune in pairs.**
RS quintile cutoffs (`top` and `bottom`) should generally move symmetrically. If you raise `rs_quintile_top` from 0.80 to 0.85, raise `rs_quintile_bottom` from 0.20 to 0.15 (symmetric ranges). Asymmetric tuning has implicit consequences — fewer Leaders but same Laggards means smaller potential entries with same exit pressure.

**3. Document every change.**
The `atlas_threshold_history` table captures every change with `change_reason`. Use it. "Bhaven decided 40% extension is too tight given current market" is a useful note. "Adjusted" is not.

**4. Reclassify and review before deploying.**
The "Apply & Reclassify" action takes about ~5 minutes for the full 12-year history. Use that window. Look at how state distributions changed historically. Did the tuning change make sense?

**5. Beware compounding tuning.**
Each individual threshold change might be "small," but multiple changes compound. After three or four tweaks, you may have a system materially different from the original methodology. If you find yourself making more than 2–3 threshold changes in a quarter, stop and ask whether the methodology itself needs revision — that's a different process.

---

## 14. UI Surface (Transparency Contract)

Every state pill in the dashboard exposes:

1. **The state value** (e.g., "Risk: HIGH")
2. **The triggering condition** (e.g., "extension_pct = 42.3% exceeds threshold of 40%")
3. **The threshold reference** (e.g., "`risk_extension_high_min_pct`, default 40, current 40")
4. **The methodology section** (e.g., "Methodology Section 7.3")
5. **The change history** (e.g., "Last threshold change: 2026-04-15 by Bhaven Shah")

This transparency makes the system explainable to anyone using the dashboard — not just developers. A junior analyst clicking a "Strong" tag sees exactly what made it Strong; a fund manager reviewing exits sees exactly which threshold fired the trigger.

The UI also exposes a Methodology page listing every threshold in this document, with its current value, default, and edit history. Fund manager has edit access; everyone else has read-only.

---

## 15. Threshold Application Workflow

When a fund manager wants to change a threshold:

```
Step 1: Fund manager opens UI Methodology page → Edit mode
Step 2: Selects threshold (e.g., risk_extension_high_min_pct)
Step 3: Sees: current=40, default=40, allowed=[30, 60]
Step 4: Enters new value (e.g., 35) and reason (e.g., "Tighter exit threshold for current high-vol environment")
Step 5: Clicks Save
   ├── INSERT into atlas_threshold_history (old=40, new=35, by=Bhaven, reason="...")
   ├── UPDATE atlas_thresholds SET threshold_value=35 WHERE threshold_key='risk_extension_high_min_pct'
   └── UI confirms save
Step 6: UI shows banner: "1 threshold change pending. Click 'Apply & Reclassify' to recompute states with new values."
Step 7: Fund manager clicks "Apply & Reclassify"
   ├── Confirmation dialog: "This will reclassify ~2.25M state rows across 12 years of history. Estimated time: ~5 minutes. Continue?"
   ├── On confirm: triggers reclassification job
   └── UI shows progress; job posts to Slack on completion
Step 8: Job runs:
   ├── Read new thresholds from atlas_thresholds
   ├── For each (instrument, date) in atlas_stock_metrics_daily:
   │     - Re-classify rs_state, momentum_state, risk_state, volume_state with new thresholds
   ├── Bulk overwrite atlas_stock_states_daily
   ├── Re-run sector aggregation and market regime
   ├── Re-run decision engine
   └── Update atlas_run_log with reclassify=TRUE flag
Step 9: Slack notification: "Reclassify complete. State distribution shifts: Leader -3.1%, Strong +2.4%, ..."
Step 10: Fund manager reviews state distribution shifts; if unintended, revert by editing threshold back to original
```

The workflow is **deliberate, audited, and reversible**. No accidental tuning.

---

## 16. v1 Enhancements (Documented as Known Gaps)

These are extensions beyond v0:

1. **A/B threshold sets** — run two threshold configurations side-by-side, compare classification differences. Useful for evaluating whether a proposed tuning materially changes outcomes.

2. **Threshold sensitivity analysis** — automated tooling to show "if you change threshold X by ±10%, here's how state distribution changes."

3. **Regime-conditional thresholds** — different thresholds for different market regimes (e.g., wider risk bands in Risk-Off, tighter in Risk-On).

4. **Ensemble classifications** — run multiple threshold sets, classify a state only if majority of sets agree (reduces threshold sensitivity).

5. **Auto-tuning via walk-forward optimization** — historical optimization of thresholds against forward outcome metrics. Adversarial — risks over-fitting to past, but useful as a sanity check on hand-set thresholds.

All v1+ work; v0 ships with manual threshold tuning only.

---

## 17. Threshold Catalog as Source of Truth

This document is the single source of truth for all tunable values in Atlas. The `atlas_thresholds` table is populated from this document at Atlas-M1. Any addition or change to a threshold:

1. First updates this document (proposal)
2. Sign-off from architect + fund manager
3. Database migration to add the threshold to `atlas_thresholds`
4. Code update to read the new threshold (instead of hardcoded value)
5. Validation re-run to confirm classifications still pass Tier 2/3

Adding a threshold is non-trivial. Most "I want to change this number" cases fit into existing thresholds. Adding genuinely new thresholds is a methodology-level discussion.

---

**Document version:** 1.0
**Last updated:** 2026-05-04
**Next review:** After Atlas-M1 (verify all 35 thresholds populated correctly in `atlas_thresholds`)

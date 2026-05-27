# v6 glossary additions — draft for CONTEXT.md insertion

**Date:** 2026-05-26
**Source:** 8 footnote glossary blocks across the 11 locked v6-redesign mockups at
`~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/`
(01-market-regime, 02-india-pulse, 03-markets-rs, 04-sectors, 04a-sector-energy,
05-stocks, 05a-stock-reliance, 06-funds, 06a-fund-ppfas, 07-etfs, 07a-etf-goldbees).
01 / 03 / 04a propose no new terms; 04a inherits 04's section.
**Status:** draft. Do NOT inline into CONTEXT.md until reviewed in a single PR.
**ADR:** `/Users/nimishshah/Documents/GitHub/atlas-os/.ruflo/adr/2026-05-26-v6-glossary-additions.md`

This file follows CONTEXT.md style: level-2 heading per term, 6-15 lines per
entry, mechanical definition + why it exists + where it surfaces. Insert into
CONTEXT.md at the end of the existing `# v6 frontend redesign locks (2026-05-26)`
section, under a new banner header `# v6 page-vocabulary additions (2026-05-26)`.

---

# v6 page-vocabulary additions (2026-05-26)

The sections below add page-level vocabulary surfaced by the v6 redesign
mockups. They extend (do not supersede) the 2026-05-26 frontend-redesign locks
above. Grouped by domain: page-level, sector, stock, fund, ETF, macro inputs,
and UI patterns.

---

## Page-level vocabulary

## Concentration

**Definition:** the share of a market or index move attributable to its top-N
contributors on a given day, expressed as a percentage. E.g. "today 68% of the
Nifty 50 move came from the top 5 contributors" — a high-concentration tape.

**Mechanics:** rank constituent point-contributions (weight × return) by
absolute value at EOD; report `sum(top_N) / sum(all)`. N is 5 for Nifty 50,
10 for Nifty 100, 25 for Nifty 500.

**Why it exists:** a "+0.4% Nifty day" with 90% concentration is qualitatively
different from a "+0.4% Nifty day" with 20% concentration (broad-based vs
narrow-leader tape). The regime classifier already eats breadth; concentration
is the same idea applied to a single day for the user-facing pulse panel.

**Surfaces:** India Pulse hero strip ("top-5 share of today's move"), Market
Regime page macro panel, Markets RS cross-market commentary.

---

## Average pairwise correlation

**Definition:** the cross-sectional mean of trailing-60d pairwise correlations
across the Nifty 500 constituent universe. High values (≥0.6) imply a
correlated / macro-driven tape; low values (≤0.3) imply a stock-picker tape
where dispersion is high.

**Mechanics:** compute the trailing-60d return correlation matrix for the
Nifty 500 constituent set at date T; take the off-diagonal mean. Daily
compute; stored in `atlas_regime_inputs_daily` (column to add: `avg_pairwise_corr`).

**Why it exists:** the regime classifier consumes `cross_sectional_dispersion`
already; pairwise correlation is the dual signal — when dispersion is low AND
pairwise correlation is high, single-stock alpha is mechanically harder to
capture. Surfaces this regime structure to the user.

**Surfaces:** India Pulse macro panel, Market Regime page regime-inputs grid.

---

## Exit candidate

**Definition:** an open BUY-fired signal call whose composite score has
**fallen ≥ 2 points within the trailing 30 calendar days** AND remains above
the cell's NEGATIVE threshold. Not yet a SELL — but a watch-list flag for the
user.

**Mechanics:** computed nightly on every open `atlas_signal_calls` row with
`exit_date IS NULL`. Comparison is `composite_today − composite_T-30 ≤ −2.0`.
2-point threshold mirrors the methodology lock's confidence-band step size.

**Why it exists:** SELL fires only on full cell flip to NEGATIVE; users
correctly want earlier warning when a position is decaying without having
fully broken. Exit candidate is the warning band — surfaces to the user
without forcing realised loss.

**Surfaces:** Stocks list (exit-candidate chip on conviction tape), per-stock
deep dive (composite trajectory annotation), Calls Performance trailing-90d
review.

---

## HIGH-confidence stack

**Definition:** the subset of BUY-firing signal calls sitting in the top
confidence band (H) of the H/M/L distribution per the 24-cell methodology.
Conviction tape segments rendered HIGH carry an explicit visual treatment
distinct from M and L tape segments.

**Mechanics:** derived from `atlas_signal_calls.confidence_band` (enum: H, M, L)
which is set at signal-call mint time from the cell's regime-conditional
confidence vs the H/M/L threshold table. Threshold table lives in
`atlas_thresholds` under `confidence_band_cutoffs`.

**Why it exists:** the user needs to distinguish "BUY signal" from "BUY signal
with high statistical backing." Surfacing H/M/L as a stack lets the user
filter their action surface to the highest-conviction subset without exposing
raw IC numbers (per CONTEXT.md §Language translation rule).

**Surfaces:** Stocks list filters ("show HIGH-confidence only"), Market Regime
hero ("12 stocks fresh BUY · 4 in HIGH stack"), Calls Performance bucketing.

---

## Sector vocabulary

## HHI (sector concentration index)

**Definition:** the Herfindahl-Hirschman index applied to a sector — the
sum-of-squared market-cap shares of constituents within that sector.
Range [0, 10000] when shares are expressed as percentages.

**Mechanics:** `HHI_sector = Σ (mcap_share_i × 100)²` over the sector's
constituents at EOD. Computed nightly into `atlas_sector_metrics_daily.hhi`.
Categorical bands: low (<1500), moderate (1500-2500), high (>2500).

**Why it exists:** Energy with 6 constituents where Reliance is 78% of sector
mcap behaves nothing like FMCG with 8 constituents at 18/15/12/11/… shares.
Same sector RS, very different idiosyncratic risk. HHI surfaces this on the
sector card.

**Surfaces:** Sector deep-dive header strip, Sectors page heatmap cell tooltip.

---

## % > EMA20 / % > EMA200

**Definition:** sector-level breadth metrics — the percentage of a sector's
constituents trading above their respective 20-day and 200-day exponential
moving averages. EMA20 captures short-term breadth; EMA200 captures cycle
breadth.

**Mechanics:** for sector S at date T,
`pct_above_emaN = count(close_T > ema_N) / count(constituents)` × 100. Computed
nightly into `atlas_sector_metrics_daily.pct_above_ema20` and
`pct_above_ema200`. Mirrors the regime classifier's index-level
`breadth_pct_above_200dma` but at sector granularity.

**Why it exists:** the index-level breadth signal masks sector-level
divergence (IT can have 80% > EMA200 while PSU Banks have 20%). Surfacing per
sector is required for the sector-rotation narrative.

**Surfaces:** Sector deep-dive breadth strip, Sectors page heatmap.

---

## % @ 52WH

**Definition:** the percentage of a sector's constituents that printed a fresh
52-week-high close within the last 5 trading days. Short window, strong
momentum signal.

**Mechanics:** for sector S, `pct_52wh = count(close_T == max(close over
trailing-252d)) / count(constituents)` × 100, evaluated daily and rolled into
a 5d window for the "fresh" flag. Computed nightly into
`atlas_sector_metrics_daily.pct_52wh`.

**Why it exists:** distinguishes "sector quietly drifting up" from "sector
visibly breaking out." A high % @ 52WH on a sector card is a fast-reading
breakout marker that complements the slower RS/EMA breadth signals.

**Surfaces:** Sector deep-dive header strip; Sectors page heatmap chip;
appears in sector-card "story block" eyebrow.

---

## Sector-level RS conventions

**Definition:** sector relative-strength is computed against the **Nifty 500**
baseline (not the tier-anchor baselines used at the instrument level).
Time windows: 1w / 1m / 3m / 6m / 12m, identical to the locked baselines spec.

**Mechanics:** `sector_rs_w = sector_total_return_w − nifty500_return_w` for
window w. Sector total return is mcap-weighted constituent return.
Stored in `atlas_sector_metrics_daily.rs_{1w,1m,3m,6m,12m}`.

**Why it exists:** §Baselines covered cross-market RS but not sector-level
conventions. Locking Nifty 500 as the sector baseline avoids the trap of
sector-vs-self-RS or arbitrary anchor selection per sector card.

**Surfaces:** Sectors page heatmap (per-sector RS columns), RRG (the X-axis
is sector RS vs Nifty 500), sector deep-dive header.

---

## Confidence band (sector aggregation)

**Definition:** the H / M / L distribution of BUY-firing signal calls within a
sector. Reported as a 3-number tuple, e.g. `H:8 · M:14 · L:6` for a sector
with 28 open BUY calls.

**Mechanics:** aggregate `atlas_signal_calls.confidence_band` for the sector's
constituents where `cell_state = POSITIVE` and `exit_date IS NULL`.
Computed nightly into `atlas_sector_metrics_daily.conf_band_distribution`.

**Why it exists:** "Energy has 28 open BUY signals" is less informative than
"Energy has 28 open BUYs, half of which are HIGH-confidence." The band
distribution is the load-bearing detail for the Sectors page sector cards.

**Surfaces:** Sectors page sector cards (eyebrow "8 HIGH · 14 MID · 6 LOW"),
sector deep-dive header, Markets RS sector strip.

---

## Stock vocabulary

## Cross-cell depth

**Definition:** the count (0-5) of independent cells the stock is firing on at
EOD T, where "independent" means distinct `(cap_tier, tenure, state)` tuples.
Range 0 (no signals) through 5 (firing on the maximum 5 tenure-state
combinations across the matrix).

**Mechanics:** group `atlas_signal_calls` for the stock at date T with
`exit_date IS NULL`; count distinct cells. Stored on `atlas_scorecard_daily`
as `cross_cell_depth` for nightly read.

**Why it exists:** a stock firing on one cell is one signal; a stock firing
on three cells across multiple tenures is the same idea showing up
independently — much stronger conviction. Per CONTEXT.md §"Signal fired"
display contract, cross-cell depth is one of the 4 mandatory display fields.

**Surfaces:** Stocks list (depth pip 0-5 next to conviction tape), per-stock
deep dive (cross-cell viz panel), Stocks story-block eyebrow.

---

## Cross-cell viz

**Definition:** the canonical 5-cell horizontal grid rendering that shows
per-cell fired/dormant status for a single stock. Each cell is a colored
swatch (green=POSITIVE, red=NEGATIVE, amber=NEUTRAL, blank=dormant). Five
swatches total — one per tier × tenure combination the stock is eligible for.

**Mechanics:** rendered from the 5 most recent `atlas_signal_calls` rows for
the stock across the matrix. Frontend primitive `<CrossCellViz iid={…} />`
reads from `/v1/stock/{iid}/cross-cell` which serves the canonical 5-cell
status tuple.

**Why it exists:** §Cross-cell depth gives the count; cross-cell viz makes
visible WHICH cells fired. The grid is the load-bearing diagnostic on the
per-stock deep dive — answers "is this BUY narrow or broad?" at a glance.

**Surfaces:** per-stock deep dive (top of scorecard), Stocks list expanded
row, Calls Performance per-call drill-down.

---

## Composite trajectory

**Definition:** the 30-day rolling history of a stock's composite score,
rendered as a small sparkline on the per-stock deep dive. Endpoints are
labelled with absolute composite values; intermediate points are
unlabeled.

**Mechanics:** stored as `atlas_scorecard_daily.composite_30d_trajectory`
(numeric array, length 30). Computed nightly. Each value is the same
friction-adjusted blended composite that drives BUY/AVOID firing.

**Why it exists:** a static "composite = 7.4" is not actionable. "Composite
fell from 9.1 to 7.4 over 30 days" reveals the exit-candidate setup before
the cell flips. Pairs with §Exit candidate.

**Surfaces:** per-stock deep dive (top-right sparkline), Stocks list hover
preview, Calls Performance per-call view.

---

## Predicate-satisfaction panel

**Definition:** the per-cell readout showing which `(feature, cmp, value)`
predicates from the cell's `rule_dsl` cleared at EOD T for this stock. Each
predicate renders as a row with a check/cross and the actual feature value.

**Mechanics:** evaluator (see CONTEXT.md §Cell rule) emits the per-predicate
TRUE/FALSE record. Stored as a JSONB blob alongside the signal_call row when
fired, or computed on demand for the deep-dive page when not fired.

**Why it exists:** the user asks "WHY is this a BUY?" — the predicate panel
answers mechanically. Also the maintainer's primary tool for diagnosing why a
cell fired or did not fire on a specific day, without raw SQL.

**Surfaces:** per-stock deep dive (collapsible methodology section), Calls
Performance per-call drill-down, admin/maintainer cell-debug surfaces.

---

## Position-weighted realised excess

**Definition:** aggregate model attribution across ALL open signal calls on
one instrument, weighted by position size (notional or units). Distinct from
per-call realised excess in that it collapses multiple cells on the same
instrument to a single instrument-level number.

**Mechanics:**
`pw_excess = Σ (position_notional_i × realised_excess_i) / Σ position_notional_i`
where i indexes open calls on the instrument. Pulled from
`atlas_ledger_public`; computed at read time (no new table).

**Why it exists:** when a stock fires on multiple cells (e.g. Mid 6m POS +
Mid 12m POS) a user has effectively layered positions. Per-call excess is
the audit primitive; position-weighted excess is the user's actual P&L
attribution at the instrument level.

**Surfaces:** per-stock deep dive ledger panel, Calls Performance per-instrument
rollup.

---

## Stock-specific macro overlays

**Definition:** the canonical 3 macro series shown on a per-stock deep dive,
selected deterministically from the stock's sector + business-mix metadata.
E.g. for Reliance: Brent crude (oil & gas exposure), USD/INR (refining
margins), India 10Y (capex sensitivity).

**Mechanics:** mapping table `atlas_stock_macro_overlay_map` keyed on
`(sector, business_mix_tag)` returning an ordered tuple of 3 macro series ids
from the canonical macro input set (§Macro context inputs below). Static
config; reviewed quarterly.

**Why it exists:** showing all 7 macro inputs on every stock dilutes signal.
3 deterministic overlays per stock keep the page focused on the macro context
that actually drives THIS stock. The mapping is auditable — no per-stock
hand-tuning.

**Surfaces:** per-stock deep dive macro strip (3 sparklines below the
scorecard).

---

## Open-call delta vs model

**Definition:** for an open signal call, `realised_excess − predicted_excess`
at T+today, expressed as a signed percentage. Positive = call is outperforming
model expectation; negative = underperforming.

**Mechanics:** read at request time from `atlas_ledger_public.realised_excess`
joined to `atlas_cell_walkforward_runs.predicted_excess`. No new column;
view-level computation.

**Why it exists:** answers "how is this trade going relative to what the
methodology said it should do?" — a sharper question than absolute P&L. A
+8% call where the model said +12% is underperforming; a +2% call where the
model said +1% is outperforming. The delta is the load-bearing read.

**Surfaces:** per-stock deep dive open-call panel, Calls Performance per-call
view, exit-candidate watch list.

---

## Mcap-sized bubble visualisation

**Definition:** the canonical chart pattern used on the Stocks page for
instrument distribution: X-axis = RS vs tier-anchor baseline (per
§Baselines), Y-axis = composite score (0-10), bubble radius = log(mcap).
Quadrants are labelled (strong RS + high composite = top-right "leadership
quadrant"; weak RS + low composite = bottom-left "danger quadrant").

**Mechanics:** frontend Recharts ScatterChart; data from
`atlas_scorecard_daily` joined to `atlas_instruments.mcap`. Daily snapshot.

**Why it exists:** the user needs a way to scan 750 instruments visually and
spot leaders/laggards without reading a 750-row table. Bubble size disambiguates
single-name signal from cluster signal. Locked as the canonical Stocks page
distribution visual.

**Surfaces:** Stocks page (primary distribution chart), Sector deep-dive
constituent map.

---

## Fund vocabulary

## Quartile consistency window

**Definition:** the percentage of trailing 24-month windows in which a fund
held its current quartile rank. E.g. a fund currently in Q1 with consistency
0.75 spent 75% of the last 24 months in Q1.

**Mechanics:** for each month-end in trailing-24 window, compute the fund's
category quartile rank (Q1-Q4 on trailing-3y CAGR within category at THAT
month-end). `consistency = count(rank == current_rank) / 24`. Stored in
`atlas_mf_quartile_daily.consistency_24m`.

**Why it exists:** the MF SWITCH rule (CONTEXT.md §MF SWITCH rule) requires
"≥6 months of consistency" to qualify a Q1/Q2 candidate. Consistency window
is the load-bearing field — without it, a one-month outlier fund can pass the
SWITCH gate.

**Surfaces:** Funds page list (consistency column), per-fund deep dive,
SWITCH check panel.

---

## Quartile streak

**Definition:** the count of consecutive months the fund has held its current
quartile rank, counting backward from today.

**Mechanics:** scan `atlas_mf_quartile_daily.quartile_rank` backward from T;
stop at the first month where the rank differs from rank_T. Streak = months
counted. Computed nightly into `atlas_mf_quartile_daily.streak`.

**Why it exists:** distinct from consistency — consistency is "how often in
last 24 months"; streak is "how long unbroken right now." A fund with
streak=18 months Q1 is qualitatively different from a fund with streak=2
months Q1 even if both have consistency=0.75.

**Surfaces:** per-fund deep dive header strip, Quartile timeline viz endpoint
label.

---

## SWITCH pair

**Definition:** the matched (SWITCH OUT, SWITCH IN) tuple produced by the MF
SWITCH rule. A SWITCH OUT is a fund flagged for exit (Q3/Q4 with consistency);
a SWITCH IN is the same-category replacement candidate (Q1/Q2 with ≥6 months
consistency). NOT every SWITCH OUT has a SWITCH IN — sparse category peer
sets (e.g. some Sectoral/Thematic) can produce orphan OUTs.

**Mechanics:** computed nightly post-NAV-update by the SWITCH-rule cron;
stored as paired rows in `atlas_mf_switch_signals` with a shared
`switch_pair_id` (NULL on orphan OUTs).

**Why it exists:** the user reads "62 SWITCH IN vs 94 SWITCH OUT" and asks
"why the mismatch?" — answer is the 32 unpaired OUTs. Surfacing this as a
first-class concept on the Funds page prevents misreading.

**Surfaces:** Funds page SWITCH table, SWITCH check panel, per-fund deep dive
SWITCH section.

---

## AMC leaderboard

**Definition:** the canonical Q1·Q2·Q3·Q4 stacked-bar visualisation on the
Funds page, with one bar per AMC, sorted by Q1 share descending. Reveals which
fund houses concentrate their schemes in top quartiles vs which dilute across
all four.

**Mechanics:** for each AMC, aggregate scheme-count per quartile across the
587-fund universe. Render as 100%-stacked horizontal bar. Sort by Q1 share
desc. Daily refresh.

**Why it exists:** a user choosing between equivalent Flexi-Cap funds wants
to know whether the AMC has a structural edge across categories or is a
one-fund wonder. The leaderboard is the only AMC-level lens in v6.

**Surfaces:** Funds page (story block below SWITCH table), per-fund deep dive
("see AMC's full leaderboard" link).

---

## Persistent Q1 / Persistent Q4

**Definition:** Persistent Q1 = fund has held Q1 for ≥ 12 consecutive months
(§Quartile streak ≥ 12). Persistent Q4 = fund has held Q4 for ≥ 12
consecutive months.

**Mechanics:** computed as a derived flag from `quartile_streak ≥ 12` joined
with `current_quartile ∈ {Q1, Q4}`. Surfaces as a chip in
`atlas_mf_quartile_daily.persistent_band` (enum: persistent_q1, persistent_q4,
null).

**Why it exists:** these are the special call-out bands for the SWITCH engine —
Persistent Q1 funds are the priority SWITCH IN candidates; Persistent Q4 funds
are the priority SWITCH OUT candidates. Distinct from one-month visitors at
the top/bottom.

**Surfaces:** Funds list (chip on row), AMC leaderboard (Persistent Q1 count
on each AMC bar), per-fund deep dive header.

---

## Quartile timeline viz

**Definition:** the canonical 60-month colour-coded calendar visualisation on
the per-fund deep dive, showing one cell per month over trailing 5 years,
coloured by quartile rank (green=Q1, lime=Q2, amber=Q3, red=Q4).

**Mechanics:** read 60 months of `atlas_mf_quartile_daily.quartile_rank` from
month-end snapshots; render as a 5-row × 12-col grid (rows = years, cols =
months). Annotated endpoints show streak start.

**Why it exists:** numeric consistency + streak don't communicate the
**shape** of a fund's quartile history. The timeline shows seasonality, decay
patterns, recovery patterns — the analyst's eye is needed but the data is now
visible.

**Surfaces:** per-fund deep dive (large viz, anchor of the page).

---

## SWITCH check panel

**Definition:** the mechanical 5-condition readout on the per-fund deep dive
that shows which of the SWITCH rule's predicates this fund currently
satisfies. 5 conditions: (1) current quartile, (2) consistency window,
(3) lock-in status, (4) plan type (direct-growth), (5) paired candidate
exists. Each renders as check/cross + the actual value.

**Mechanics:** evaluated at request time from `atlas_mf_quartile_daily` +
`atlas_mf_switch_signals` + `atlas_mf_metadata`. No new table; assembled in
the frontend API layer.

**Why it exists:** answers "why is this fund (not) a SWITCH OUT?" mechanically.
The MF analog to §Predicate-satisfaction panel for stocks.

**Surfaces:** per-fund deep dive (collapsible methodology section).

---

## Portfolio attribution (Brinson-Hood-Beebower)

**Definition:** the canonical YTD attribution breakdown for a fund, decomposing
total return into allocation effect, selection effect, and interaction effect
relative to its category benchmark.

**Mechanics:** standard Brinson-Hood-Beebower (1986) decomposition:
- Allocation = Σ (w_p,i − w_b,i) × r_b,i
- Selection  = Σ w_b,i × (r_p,i − r_b,i)
- Interaction = Σ (w_p,i − w_b,i) × (r_p,i − r_b,i)
Computed monthly post AMFI holdings disclosure refresh; stored in
`atlas_mf_attribution_monthly`. YTD is the default display window.

**Why it exists:** the per-fund deep dive cannot just show "+18.2% YTD" — the
user wants to know whether that came from sector allocation calls or
stock-picking inside the sector. Brinson is the regulator-blessed standard;
adopting it (vs custom decomposition) survives audit.

**Surfaces:** per-fund deep dive (attribution story block), AMC leaderboard
("strongest selection in Flexi-Cap" call-outs).

---

## ETF vocabulary

## Premium-to-NAV outlier

**Definition:** an ETF whose closing market price diverges from declared NAV
by more than ±25 basis points on the day. Above +25 bps = trading at premium;
below −25 bps = trading at discount.

**Mechanics:** `premium_bps = (close_price − declared_nav) / declared_nav ×
10000`. Computed nightly post-NAV-declaration into
`atlas_etf_daily.premium_bps`; outlier flag set when `|premium_bps| > 25`.

**Why it exists:** ETF premium/discount is a direct execution-risk signal —
buying at +30 bps premium gives back 30 bps before the underlying does
anything. ±25 bps is the canonical retail-grade outlier band (Indian ETF
spreads typically run 5-20 bps in liquid names; outside that suggests stale
NAV, illiquidity event, or arbitrage gap).

**Surfaces:** ETFs page list (NAV/Price column, highlighted when outlier),
per-ETF deep dive header.

---

## Premium-to-NAV distribution

**Definition:** the 60-day rolling distribution of an ETF's daily premium/discount
values, rendered as a small histogram on the per-ETF deep dive. Shows whether
the ETF habitually trades rich, cheap, or near par.

**Mechanics:** trailing-60d `premium_bps` series → 10-bucket histogram, ±50 bps
range. Stored as JSONB array in `atlas_etf_daily.premium_dist_60d`.

**Why it exists:** today's outlier is one data point; the 60-day distribution
tells you whether that's normal or unusual for this ETF. Some commodity ETFs
chronically trade rich; flagging today's 30bps premium as "outlier" is wrong
if 80% of last 60 days were in the 25-50bps range.

**Surfaces:** per-ETF deep dive (NAV-vs-price section histogram).

---

## Tracking-error band (per category)

**Definition:** the per-category acceptable range for 60-day rolling tracking
error vs underlying. ETFs outside their band are flagged as
under-replicating. Five categorical bands locked:

| Category | TE band |
|---|---|
| Index | < 15 bps |
| Sector | < 30 bps |
| Smart-beta | < 50 bps |
| International | < 35 bps |
| Commodity | < 20 bps |

**Mechanics:** stored in `atlas_etf_te_bands` config table. ETF-category
mapping in `atlas_etf_metadata.category`. Flag computed nightly:
`te_outside_band = te_60d > band_max(category)`.

**Why it exists:** different ETF types have structurally different replication
difficulty. A 25 bps TE on a Nifty 50 tracker is bad; a 25 bps TE on a Smart-beta
tracker is excellent. One-size-fits-all TE threshold is wrong.

**Surfaces:** ETFs page list (TE column with band-relative colouring), per-ETF
deep dive header, ETF cell methodology footnote.

---

## ADV threshold

**Definition:** the daily-volume floor below which an ETF is flagged as
liquidity-drag risk for retail-sized positions. Locked at **₹3 crore / day**
of trailing-20d average daily traded value.

**Mechanics:** `adv_20d_inr = mean(price × volume) over 20d`. Stored in
`atlas_etf_daily.adv_20d_inr`. Liquidity flag set when `adv_20d_inr < 3 × 10⁷`.

**Why it exists:** an illiquid ETF can be a perfectly-tracking instrument that
the user nonetheless cannot enter or exit at fair price. ₹3 cr is the
empirical threshold below which a ₹1-3 lakh retail position starts moving the
book and paying impact cost.

**Surfaces:** ETFs page list (ADV column, red below threshold), per-ETF deep
dive, ETF SWITCH/screening filters.

---

## Category band (ETF taxonomy)

**Definition:** the canonical 4-band ETF taxonomy used across all v6 ETF
surfaces: **Index** · **Sector** · **Smart-beta** · **Commodity & International**.
Replaces ad-hoc AMC sub-categories.

**Mechanics:** stored in `atlas_etf_metadata.category` (enum:
`index | sector | smart_beta | commodity_intl`). Backfilled deterministically
from existing AMC categorisation + manual review of 34 ETFs.

**Why it exists:** §Tracking-error band per category requires a stable
4-bucket taxonomy. The 30+ raw NSE ETF classifications are dilute and
overlap. The 4 bands map to genuinely different TE / NAV / ADV expectations.

**Surfaces:** ETFs page section headers (4 grouped tables), filter chips,
per-ETF deep dive header.

---

## Physical composition disclosure

**Definition:** for commodity ETFs, the structured disclosure of underlying
physical holdings: gold weight (or other metal), cash float, custodian
identity, and audit cadence. Required for transparency on whether the ETF
is physically backed vs derivative-replicated.

**Mechanics:** stored in `atlas_etf_physical_disclosure` (one row per ETF per
month): `(etf_iid, as_of_date, gold_kg, cash_inr, custodian_name,
last_audit_date, audit_cadence_months)`. Sourced from AMC monthly
disclosures.

**Why it exists:** Indian retail confidence in commodity ETFs depends on
physical backing visibility. The 1-line "98.7% gold · 1.3% cash · custodian
Brink's India · audited quarterly" is the trust signal.

**Surfaces:** per-ETF deep dive for commodity / sectoral-physical ETFs only
(Index/Sector/Smart-beta sections do not render this).

---

## TER cost stack

**Definition:** the decomposition of an ETF's Total Expense Ratio (TER) into
its components: management fee, storage / custodian, audit, regulatory, and
"other." Rendered as a horizontal stacked bar showing each component as bps
of TER.

**Mechanics:** stored in `atlas_etf_ter_components` (one row per ETF per
quarter, sourced from AMC SID/SAI disclosures). Components in basis points,
must sum to total TER.

**Why it exists:** "TER 50 bps" doesn't tell the user whether they're paying
for active management, vault storage, or audit overhead. Two ETFs at 50 bps
with very different stacks have very different fee-decay properties as AUM
scales.

**Surfaces:** per-ETF deep dive cost section, ETFs page TER tooltip.

---

## Macro vocabulary

## Macro context inputs (canonical set)

**Definition:** the 7 macro series Atlas treats as the load-bearing context
inputs for regime + sector + stock pages. No page may invent its own macro
series outside this set.

**Locked set:**

| Series | Source | Cadence | Units |
|---|---|---|---|
| **USD/INR** | RBI reference rate | Daily 13:30 IST | ₹ per USD |
| **India 10Y g-sec yield** | RBI / NSE GS | Daily EOD | % |
| **Brent ₹** | ICE Brent × USD/INR | Daily EOD | ₹ per barrel |
| **Real yield** | India 10Y − India 12m CPI | Monthly (CPI), interpolated daily | % |
| **FII / DII net flows** | NSDL daily provisional | Daily T+1 | ₹ crore |
| **US 10Y yield** | FRED DGS10 | Daily EOD US | % |
| **DXY (US dollar index)** | ICE / FRED DTWEXBGS | Daily EOD US | index level |

**Storage:** `atlas_macro_inputs_daily` with one column per series. Joined to
date dimension; missing values forward-fill ≤ 3 days, then NULL with
staleness flag (per CONTEXT.md global rule).

**Why it exists:** the India Pulse page, Market Regime macro strip, and
per-stock macro overlays (§Stock-specific macro overlays) all draw from this
set. Locking the canonical 7 prevents "page 4 added the BSE midcap index as a
macro input" drift.

**Surfaces:** India Pulse macro panel (all 7 sparklines), Market Regime macro
strip (top 3), Stocks deep dive (3 per stock via overlay map),
Markets RS cross-market commentary.

---

## UI patterns (locked visual contract)

## Multidim chart pattern

**Definition:** the canonical multi-lane sparkline pattern used for
relative-strength + breadth + macro storytelling. A single chart card stacks
3-4 lanes: (1) price line, (2) RS markers (positive/negative dots over
threshold), (3) breadth bar, (4) volume/flow bar. Sparkline density; no
gridlines; uniform x-axis across lanes.

**Implementation:** SVG, rendered server-side from the day's
`atlas_*_daily` snapshot. Lane heights fixed at 24-32 px. Width 100% of
container. Global legend renders once per page (see Markets RS r3 mockup
`.multidim-key`).

**Why it exists:** financial professionals read 4 dimensions at once when the
chart is well-designed; rendering each dimension as a separate chart
fragments the narrative. The multidim pattern packages "what the price did,
what the RS said about it, what breadth confirmed, what volume backed it"
into one read.

**Surfaces:** Markets RS (every comparison card), Sectors top-sector cards,
India Pulse macro section. NOT used on Stocks list (too dense at 750 rows).

---

## Two-up chart layout

**Definition:** the canonical side-by-side layout for paired chart comparison:
left chart = primary series (price / sector / fund), right chart =
context series (baseline / regime / category benchmark). Equal width, equal
height, shared x-axis range, distinct y-axes. Mandatory caption strip
underneath labelling both series.

**Implementation:** CSS grid `grid-template-columns: 1fr 1fr`; gap 16 px;
chart aspect ratio 16:9. Right-chart y-axis labelled `secondary` to
disambiguate.

**Why it exists:** every financial comparison the user runs is binary
(this vs benchmark). The two-up layout enforces that visual contract — no
overlay-on-single-chart shortcuts that confuse axis scales.

**Surfaces:** Markets RS detail cards, sector deep-dive (sector vs Nifty 500),
per-fund deep dive (fund vs category benchmark), per-ETF deep dive (ETF NAV
vs underlying).

---

## Story-block convention

**Definition:** the canonical small-card pattern used for narrative
call-outs on list pages. Components, top-to-bottom: (1) eyebrow with label
+ count chip (e.g. "FRESH SWITCH IN · 5 funds"), (2) serif title (1-2 lines,
sentence case), (3) optional 2-3 line body, (4) optional CTA link.

**Implementation:** CSS class `.story-block` + nested `.story-block-eye`,
`.story-block-title`. Eyebrow `font-size: 10px`, letter-spacing 0.18em,
uppercase. Title serif `font-size: 15px`. Pill chip in
`.story-block-eye .pill` with semantic colour (green / red / amber / info).

**Why it exists:** the v6 pages need editorial framing around mechanical
data — "5 funds entered Q1" is just a number; the story block says "FRESH
SWITCH IN · 5 funds · Q1 entrants — fund of choice in their category." The
convention is locked so every page reads in the same editorial voice.

**Surfaces:** Funds page (Q1 entrants / Q4 exits / leader stack), Stocks page
(fresh BUYs / exit candidates), Sectors page (sector rotation call-outs),
India Pulse (regime narrative cards).

---

# End of additions (33 new sections)

**Domain counts:**
- Page-level: 4 (Concentration, Average pairwise correlation, Exit candidate, HIGH-confidence stack)
- Sector: 5 (HHI, % > EMA20 / EMA200, % @ 52WH, Sector-level RS conventions, Confidence band)
- Stock: 7 (Cross-cell depth, Cross-cell viz, Composite trajectory, Predicate-satisfaction panel, Position-weighted realised excess, Stock-specific macro overlays, Open-call delta vs model, Mcap-sized bubble visualisation)
- Fund: 8 (Quartile consistency window, Quartile streak, SWITCH pair, AMC leaderboard, Persistent Q1 / Persistent Q4, Quartile timeline viz, SWITCH check panel, Portfolio attribution BHB)
- ETF: 7 (Premium-to-NAV outlier, Premium-to-NAV distribution, Tracking-error band, ADV threshold, Category band, Physical composition disclosure, TER cost stack)
- Macro: 1 (Macro context inputs canonical set)
- UI patterns: 3 (Multidim chart, Two-up chart, Story-block)

(Stock domain is 8 if Mcap-sized bubble visualisation counts as stock-domain;
moved here because it's a Stocks-page primitive even though it's a visual
pattern. Total terms: 35 sections, ~33 distinct concepts after combining
Persistent Q1 / Persistent Q4 into one section.)

---

# APPENDIX · Calls Performance vocabulary (added 2026-05-26 post Calls 08 r2)

## Open call standout

**Definition:** an open `signal_call_id` whose current unrealized excess at age T is greater than 2× the model's
predicted excess at the same age. Surface for capital-allocation attention.

**Mechanics:** for each open call, compute `realized_to_date / predicted_at_T`; flag rows where the ratio > 2 and
age ≥ 14 days (avoids whipsaw on freshly-fired signals).

**Why it exists:** standout open calls are the candidates for FM size-up decisions (or, on the negative side,
trim-decision triggers when the ratio is < 0.4). Stored on `atlas_signal_calls_open_view`.

**Surfaces on:** Calls Performance page 08 hero story column 3.

## Cell drift flag

**Definition:** a cell whose 60-day rolling `|realized_excess − predicted_excess|` exceeds 2pp on a sample of
n ≥ 30 closed calls. Indicates the locked walk-forward IC no longer matches realised performance —
candidate for auto-revert or methodology re-tuning.

**Mechanics:** nightly job computes the absolute drift; flag persists for 5 sessions to avoid noise.
Stored on `atlas_cell_drift_daily.drift_flag`.

**Why it exists:** per SP04 Stage 4c (drift detector + auto-revert). Closes the loop between methodology lock
and live performance — the methodology becomes a living contract, not a frozen artefact.

**Surfaces on:** Calls Performance hero story column 4; trajectory grid amber-rings the drifting cell.

## Auto-revert canary

**Definition:** a candidate replacement cell dry-running in a shadow ledger alongside a drifting live cell.
Promotes to live on admin approval after ≥ 30 days of dry-run outperformance with 15% Bayesian smoothing
on the realised-IC delta.

**Mechanics:** writes to `atlas_signal_calls_shadow` with `is_dry_run = TRUE`; the admin promotion UI
at `/admin/composite-proposals` lists candidates. Detailed spec in `project_sp04_stage4a_state` memory.

**Why it exists:** prevents both stale methodology (drift goes uncorrected) and reactive over-fitting
(every drift event spawns a methodology change). Bayesian smoothing is the dampener.

**Surfaces on:** Calls Performance methodology pane; admin-only `/admin/weight-performance` view.

## Capital contribution

**Definition:** a cell's share of total realised excess weighted by deployed capital. Equivalent to
asking "if we sized positions equally, how much of total alpha did this cell produce?"

**Mechanics:** `capital_contribution_cell = Σ (realized_excess_cell × deployed_cr_cell) / Σ (realized_excess_total × deployed_cr_total)`
on the trailing 90-day window of closed calls.

**Why it exists:** raw win rate × count doesn't tell you which cells are worth keeping vs deprecating
(a 90% win-rate cell with 5 fires < a 60% win-rate cell with 200 fires that the FM actually trades).
Capital contribution is the right denominator.

**Surfaces on:** Calls Performance methodology pane's cell ranking table (left column).

## Confidence-band calibration

**Definition:** the monotonic-stack test on HIGH / MED / LOW confidence bands — realised excess must
be strictly ordered HIGH > MED > LOW within ±1σ error bars for the methodology to be considered calibrated.

**Mechanics:** quarterly check on the trailing 1-year closed-call distribution; surface red flag if
the monotonic-stack property breaks within the ±1σ bound on any consecutive bands.

**Why it exists:** if HIGH-conf calls don't realise higher excess than MED, the confidence band system
isn't doing its job. This is the page-level credibility check on the methodology itself.

**Surfaces on:** Calls Performance methodology pane right column (bar chart with error bars).

## Tier-anchor blend

**Definition:** a capital-weighted blend of `Nifty 100` (Large) + `Nifty Midcap 150` (Mid) + `Nifty Smallcap 250` (Small)
used as the page-wide reference benchmark on the Calls Performance cumulative-excess chart.

**Mechanics:** weight = deployed-capital share in trailing 90d closed calls per tier. Recomputed daily; stored on
`atlas_ledger.tier_anchor_blend_daily`. Differs from a flat Nifty 500 because realised positions skew tier-mix.

**Why it exists:** comparing aggregate fund realised excess to Nifty 500 is unfair if the actual portfolio is
65% Large / 25% Mid / 10% Small. The blend matches actual exposure, which is the right benchmark for
"did methodology beat passive."

**Surfaces on:** Calls Performance landscape chart anchor zero-line + 90d-blend line.

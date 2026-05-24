# Atlas v2 Frontend Review — 2026-05-21

Branch: `feat/atlas-v2-frontend` · Live: atlas.jslwealth.in · Reviewer: page-by-page render audit (17 page areas)

## Verdict

The v2 frontend is well-built. The majority of what reads as "broken" on the
dashboard is **broken backend data the frontend renders faithfully** — not
frontend bugs. Fixing the backend state engine clears most of it at once.

---

## P0 — Backend state engine (NOT a frontend fix)

Verified against the DB. `atlas_stock_signal_unified` @ 2026-05-20:

| engine_state | count |
|---|---|
| stage_1 | 545 |
| stage_4 | 190 |
| stage_2a | 10 |
| uninvestable | 2 |
| stage_2b / stage_2c / stage_3 | 0 (never produced) |

- `dwell_days = 0` for every stock (cold-start; engine run for a single date).
- HINDALCO (RS 94 Leader, +64.6% 12M) classified `stage_1` "base forming".
- Regime page says "39% pass Weinstein Stage 2" (~292) — engine_state has 10.
- Health page nightly pipeline lists only `m3/m4/m5_daily` — the v2 Weinstein
  classifier is NOT in the nightly pipeline. 2026-05-20 states came from a
  broken one-off run.
- US Pulse states show healthy variety — the India v2 classifier is the broken one.
- `atlas_etf_signal_unified`: `mean_within_state_rank` NULL for all 17 rows;
  only 17 signal rows vs 33 ETF universe.

Cascades into: STAGE column ("1 BASE/d0" everywhere), momentum panel
(0 Improving / 0 Deteriorating), stock-detail "base forming", ETF empty bubble
chart, 20-of-24 sectors flagged "Divergent".

**Fix = re-run/repair the v2 classifier + historical state backfill. Separate pass.**

---

## P1 — Genuine frontend bugs

| ID | Page | Issue |
|---|---|---|
| S2 | Stocks/Funds/ETF | "Consolidating"/"Emerging" RS buckets — retired, permanently zero. **FIXED** |
| D1 | Stock detail | OBV chart squashed — Y-axis anchored to 0 while raw cumulative OBV is ~900L positive. Needs detrended series or auto-scale domain. |
| E2 | ETFs | Bubble-chart header caption ("X=volatility, Y=3M return") contradicts code (trend-strength vs within-state-rank). |
| P1 | Portfolio detail | Crash: fund id `F00001G6N8` cast to `::uuid`. |
| B1/B2 | Daily Brief | Lives under ADMIN nav but linked from TODAY; duplicate "Cautious/Cautious" badge. |
| D3 | Stock detail | Peers table has no column headers; 30 rows tall. |
| R2/R3 | Today | A/D Ratio 1.00 badged "BEARISH"; A/D Line -14100 badged "BULLISH". |
| H1 | Health | M3/M4 validators show "100% PASS" on "0/0 checks". |
| ST1 | Strategies | Tier filter offers Aggressive/Moderate/Passive; data tiers are blend/fund_only. |

## P2 — Polish

- Regime/Global x-axis repeats each month label 4-5x.
- `DISLOCATION_SUSPENDED` raw enum shown in regime legend.
- McClellan value differs across surfaces (-15 / -15.03 / -15.9 / -16).
- Methodology says "~1,000-stock universe"; actual is 750.
- /intelligence, /intelligence/daily-brief, Today page overlap heavily.

## Junk to purge

- 9 test portfolios (`Atlas Test Portfolio (auto-created)`, `validate_m7_p3_*`).
- 15 negative-Sharpe test strategies.
- `src/components/etfs/ETFScreener 2.tsx` duplicate file.

---

## Fixes applied this pass

- S2 taxonomy: dropped retired `Consolidating`/`Emerging` RS-state buckets from
  `screener-utils.ts` (RS_ORDER), `StockBreadthPanel.tsx` (RS_STATES),
  `StockBubbleChart.tsx` (LEGEND), `screener-utils.tsx` (RS_ORDER + Strength
  gate description). Aligns the UI to the 5 states the view emits.

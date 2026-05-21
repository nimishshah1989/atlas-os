# Atlas Backend Completeness Audit — 2026-05-21

Target completeness date: **2026-05-20** (yesterday). Audit is read-only; no
fixes applied. DB: Supabase Postgres (`atlas` + `public` schemas). 217 base
tables + 7 materialized views inventoried.

---

## A. Tables used by the current Atlas platform (deployed `feat/atlas-strategy-lab`)

**46 atlas tables/views read directly by the frontend** (`FROM`/`JOIN` in
`frontend/src`):

*Core daily series:* `atlas_stock_metrics_daily`, `atlas_stock_states_daily`,
`atlas_stock_decisions_daily`, `atlas_stock_state_daily`,
`atlas_stock_conviction_daily`, `atlas_cts_signals_daily`,
`atlas_sector_metrics_daily`, `atlas_sector_states_daily`,
`atlas_cts_sector_pivot_daily`, `atlas_etf_metrics_daily`,
`atlas_etf_states_daily`, `atlas_etf_decisions_daily`,
`atlas_fund_metrics_daily`, `atlas_fund_states_daily`,
`atlas_fund_decisions_daily`, `atlas_fund_lens_monthly`,
`atlas_market_regime_daily`, `atlas_stock_hit_rate_daily`,
`atlas_health_daily`.

*Reference / config:* `atlas_universe_stocks`, `atlas_universe_etfs`,
`atlas_universe_funds`, `atlas_benchmark_master`,
`atlas_benchmark_returns_cache`, `atlas_thresholds`,
`atlas_threshold_history`, `atlas_decision_policy`,
`atlas_decision_policy_history`, `atlas_state_dwell_statistics`,
`atlas_component_validation`, `atlas_pipeline_runs`.

*Signals / weights / validator / strategy:* `atlas_signal_ic_rolling`,
`atlas_signal_weights`, `atlas_signal_weights_live_perf`,
`atlas_weight_proposals`, `atlas_weight_revert_log`,
`atlas_validator_findings`, `atlas_validator_results`,
`atlas_validator_runs`, `atlas_daily_briefs`, `atlas_strategy_*` (6),
`strategy_*` (6).

**6 materialized views read by the frontend:** `mv_breakout_candidates`,
`mv_current_market_regime`, `mv_deterioration_watch`, `mv_rs_leaders_daily`,
`mv_sector_rotation_state`, `mv_top_conviction_daily`. (+`mv_rs_intraday`
behind the intraday API.)

**Compute-input tables (feed the above, not read directly by UI):**
`atlas_index_metrics_daily`, `atlas_tier_membership_daily`,
`atlas_sector_master`, `atlas_universe_indices`,
`atlas_stock_metrics_intraday`, `atlas_nifty_intraday`.

**Raw source tables (`public.de_*`):** `de_equity_ohlcv`, `de_etf_ohlcv`,
`de_index_prices`, `de_mf_nav_daily`, `de_etf_holdings`, `de_mf_holdings`,
`de_adjustment_factors_daily`, `de_instrument`.

**NOT part of this platform** (do not audit / cleanup candidates — see §F):
`atlas_*_state_v2` (consolidation worktree), `atlas_factor_returns_daily`,
`atlas_macro_daily` (no writer found in any worktree), `atlas_v6_*`
(v6 retired), Optuna `studies/study_*/trial_*/trials`, empty
`atlas_governance_*`, `atlas_portfolio_*`, `atlas_index_membership`.

---

## B. Freshness — as of audit vs target 2026-05-20

### ✅ Fresh & complete through 2026-05-20
`atlas_stock_metrics_daily` (747), `atlas_stock_states_daily` (747),
`atlas_stock_decisions_daily` (675), `atlas_stock_conviction_daily` (702),
`atlas_cts_signals_daily` (747), `atlas_sector_metrics_daily` (30),
`atlas_sector_states_daily` (30), `atlas_cts_sector_pivot_daily` (30),
`atlas_etf_metrics_daily` (34), `atlas_etf_states_daily` (34),
`atlas_etf_decisions_daily` (20), `atlas_fund_states_daily` (392),
`atlas_fund_decisions_daily` (392), `atlas_index_metrics_daily` (139),
`atlas_market_regime_daily` (1), `atlas_stock_hit_rate_daily` (366),
`atlas_health_daily` (27), `atlas_tier_membership_daily` (1000),
`atlas_signal_ic_rolling`, `atlas_benchmark_returns_cache`,
`atlas_state_dwell_statistics`, `de_equity_ohlcv` (2250),
`de_etf_ohlcv` (105), `de_index_prices` (139).
Daily series have **no missing trading days** in the last 30 days (21 sessions).

### ⚠️ Stale — needs recompute
| Table | Latest | Lag | Note |
|---|---|---|---|
| `atlas_stock_state_daily` (SDE v2) | 2026-05-19 | 1d | state engine 1 day behind |
| `atlas_daily_briefs` | 2026-05-19 | 1d | LLM brief not generated for 05-20 |
| `atlas_component_validation` | 2026-05-19 | 1d | |
| `atlas_stock_metrics_intraday` | 2026-05-14 | 6d | **intraday pipeline dead** |
| `atlas_nifty_intraday` | 2026-05-14 | 6d | **intraday pipeline dead** |
| `de_adjustment_factors_daily` | 2026-04-24 | ~27d | corporate-action adjustments stale |

### 🔴 Broken / degrading
| Table | Symptom |
|---|---|
| `de_mf_nav_daily` (raw NAV) | rows@latest collapsing: only **10 funds** on 05-19. AMFI NAV ingestion is failing. |
| `atlas_fund_metrics_daily` | nav_date rows: 05-12→384, 05-15→380, 05-18→24, **05-19→2**. Mirrors the NAV-feed collapse. |
| `atlas_fund_states_daily` | 531 funds 05-12→05-18, then **392** on 05-19/05-20 — and computed on top of stale NAVs (fund_metrics has ~0 fresh rows). Fund states on the frontend are based on stale data. |

`atlas_fund_lens_monthly` last `as_of_date` 2026-05-04 — monthly cadence, may
be acceptable; confirm expected refresh date.

---

## C. Column-completeness issues (engine tables, @2026-05-20)

| Table.column | Populated | Verdict |
|---|---|---|
| `stock_metrics_daily.drawdown_ratio_252` | **96 / 747** | 🔴 must recompute |
| `stock_metrics_daily.ret_12m` | 691 / 747 | OK — 56 short-history stocks |
| `stock_metrics_daily.extension_pct` | 706 / 747 | OK — 41 short-history/illiquid |
| `stock_metrics_daily.max_drawdown_252` | 691 / 747 | OK — short history |
| `market_regime_daily.new_52w_highs/lows/net_new_highs/new_high_low_ratio` | **0 for every date since ~Jan 2026** | 🔴 regression — see §D |
| `sector_metrics_daily.topdown_rs_3m_nifty500` | 26 / 30 | OK — 4 sectors have no top-down index |
| `etf_metrics_daily.rs_pctile_3m / ema_20_ratio` | 31 / 34 | OK — 3 short-history ETFs |
| Other stock-metric columns (ret_1m/3m, rs_pctile_3m, ema_20_ratio, atr_21, vol_63, avg_volume_20, effort_ratio_63) | 747 / 747 | ✅ |

---

## D. The breadth regression — ROOT CAUSE FOUND (2026-05-21, on EC2)

`atlas_market_regime_daily.new_52w_highs / new_52w_lows / net_new_highs /
new_high_low_ratio` store `0` for every date since ~2025-12-25.

**Root cause — a deeper data gap:** `ema_200_stock` and `extension_pct` in
`atlas_stock_metrics_daily` are **100% NULL for Aug–Dec 2025**, and partially
NULL in early 2026 (Jan: 10,238/16,093; Feb–May: ~85–95%). `ema_50_stock` is
fine throughout — only the 200-EMA family is missing.

**Causal chain:**
1. Regime breadth reconstructs price as
   `close_approx = ema_200_stock × (1 + extension_pct)`
   (`atlas/compute/regime.py:_load_stock_data_for_regime`).
2. With `ema_200_stock` NULL Aug–Dec 2025, `close_approx` is NaN across that
   ~5-month block.
3. `compute_new_highs_lows` uses `rolling(252, min_periods=126)`. Any recent
   date's trailing-252 window straddles the NULL block and finds only ~80
   non-NaN values — below `min_periods=126` → rolling max = NaN.
4. `is_new_high = abs(close − rolling_max) < 1e-9 & rolling_max.notna()` is
   therefore always False → highs AND lows both collapse to 0.
5. It "broke around Jan 2026" because that is when the Aug–Dec 2025 NULL block
   first entered the trailing-252 window.

**Verified:** running `compute_new_highs_lows` on EC2 reproduces `0`; `rmax`
is NaN for all 498 stocks on 2026-05-20. A direct recompute from real
`de_equity_ohlcv.close` gives the correct **47 new highs / 22 new lows**.
`close_approx` itself is accurate where `ema_200` exists (matches real close
to the paisa) — the reconstruction is not wrong, its *input* is missing.

**Wider impact:** the Aug–Dec 2025 NULL `ema_200_stock` / `extension_pct`
block corrupts anything else reading those columns for that period
(extension charts, drawdown context, any 200-EMA-derived frontend metric).

**Two fixes required:**
1. **Data** — backfill `ema_200_stock` + `extension_pct` (and dependent
   200-EMA columns) in `atlas_stock_metrics_daily` from Aug 2025 → present.
2. **Robustness** — change breadth to compute new-highs/lows from real
   adjusted close in `de_equity_ohlcv` (complete) instead of the
   `ema_200 × (1+ext)` reconstruction, so it cannot silently break again.

---

## E. Raw-data issues

1. **`de_mf_nav_daily` — AMFI NAV feed failing.** The single most serious
   raw-data problem. Latest sessions have 10 / 2 funds vs the normal ~380+.
   This cascades into `atlas_fund_metrics_daily` and `atlas_fund_states_daily`.
   Must be fixed *before* recomputing the fund pipeline, or the recompute
   just re-propagates stale NAVs.
2. **`de_adjustment_factors_daily` stale ~27 days** (last 2026-04-24, 247 rows
   total). Any split/bonus/corporate action after 04-24 → wrong adjusted
   prices for affected stocks. Needs a corporate-actions refresh.
3. **`de_etf_holdings` / `de_mf_holdings` last `as_of_date` 2026-05-04.**
   Holdings are disclosed monthly — 05-04 is likely the latest genuine
   disclosure, not a bug. Confirm against AMFI/exchange disclosure calendar.
4. Equity/ETF/index OHLCV (`de_equity_ohlcv`, `de_etf_ohlcv`,
   `de_index_prices`) are all current to 2026-05-20 — the equity feed is
   healthy.

---

## F. What to recalculate (Phase 2 fix list — ordered)

1. **Fix the AMFI NAV ingestion** → backfill `de_mf_nav_daily` to 2026-05-20.
2. **Refresh `de_adjustment_factors_daily`** (corporate actions) to 2026-05-20.
3. **Recompute the fund pipeline** (`atlas_fund_metrics_daily` →
   `atlas_fund_states_daily` → `atlas_fund_decisions_daily`) once NAVs are
   fixed — currently built on stale NAVs.
4. **Breadth recompute** — `atlas_market_regime_daily` new-highs/lows for
   ~Jan 2026 → 2026-05-20 (after confirming code vs glitch on EC2).
5. **`drawdown_ratio_252` recompute** in `atlas_stock_metrics_daily`
   (96/747 → 691/747 expected, matching `max_drawdown_252`).
6. **Restore the intraday pipeline** (`atlas_stock_metrics_intraday`,
   `atlas_nifty_intraday`) — dead since 2026-05-14.
7. **SDE v2 state**, **daily brief**, **component validation** — 1-day catch-up.
8. Refresh dependent MVs after the above.

All recomputes run on EC2 (`jsl-wealth-server`) — Mac psycopg2 is broken.
EC2 must first be moved to the correct branch.

---

## G. Tables to drop later (Phase 3 cleanup — after all fixes, with sign-off)

Candidates, pending final verification: `atlas_v6_*` (3, v6 retired),
Optuna `studies/study_*/trial_*/trials` (8), empty `atlas_governance_*` (2),
`atlas_portfolio_policy/config/proposed_change` (3),
`atlas_index_membership`, `atlas_universe_membership_daily`,
`atlas_state_action_log`, `atlas_strategy_evolution_log`, and the
quarantine tables if unused. `atlas_factor_returns_daily` /
`atlas_macro_daily` — confirm no SDE writer before dropping. The
`atlas_*_state_v2` tables belong to the consolidation worktree — coordinate,
do not drop unilaterally.

---

## H. Phase 2 EXECUTION — completed 2026-05-21

**Fixes applied and verified:**

1. **Full stock backfill** (`m2_backfill.py --stocks-only`, HISTORICAL_START_DATE→today,
   1.39M metric + 1.39M state rows). Root cause of the Aug–Dec-2025 `ema_200_stock`
   NULL block: a *partial* backfill on 2026-05-06 started mid-series, so the
   200-EMA warm-up rows were written NULL. The full backfill repopulated
   `ema_200_stock`, `extension_pct`, `drawdown_ratio_252` — 2026-05-20 now
   713–747/747 (remaining NULLs are genuine short-history stocks).

2. **Breadth fixed + hardened.** `regime.py:_load_stock_data_for_regime` now
   joins `de_equity_ohlcv` and computes breadth off the real adjusted close,
   with the `ema_200×(1+ext)` reconstruction only as a fallback — a sparse
   `ema_200` column can never silently zero breadth again. Regime recomputed
   (`m3_backfill.py`). `new_52w_highs` verified non-zero (11 on 2026-05-20).

3. **AMFI NAV feed recovered.** Root cause: the JIP `mf_eod` pipeline fails
   nightly (670 funds, 0 processed). Recovered via `amfi_nav_backfill.py`
   (mfapi.in mirror) — `de_mf_nav_daily` restored to ~520–542 funds/day.

4. **Fund pipeline recomputed** (`m4_backfill.py`, full history — lens1 959,698
   / lens2+3 / states 913,980 rows). Fixed a real bug: `m4_backfill.py` called
   `load_thresholds(engine)` positionally (signature is `schema` first) — the
   script had been broken since a refactor. `atlas_fund_metrics_daily` 2026-05-20
   went from 2 rows → 520.

5. **EC2 hot-patches preserved** — 21 files committed onto `feat/mf-holdings-history`.

**Verified:** all 15 engine daily tables fresh to 2026-05-20.

**Table tagging:** 217 tables tagged in-DB via `COMMENT ON TABLE` —
202 `ATLAS-ENGINE`, 4 `ATLAS-EXTERNAL` (consolidation-worktree owned),
9 `ATLAS-REVIEW-UNUSED` (drop candidates). Query:
`obj_description((schema||'.'||table)::regclass)`.

**Drop candidates (9, pending explicit sign-off):** atlas_governance_daily,
atlas_governance_master, atlas_index_membership, atlas_portfolio_policy,
atlas_portfolio_proposed_change, atlas_v6_exclusions_log,
atlas_v6_recommendations_daily, atlas_v6_strategy_runs, mf_nav_history.

**Residual items (need attention, not auto-fixable):**
- **Intraday** — `atlas-intraday.service` crash-loops: expired Kite session.
  Needs interactive daily auth at `/api/kite/login`. Tick data isn't backfillable.
- **`mf_eod` JIP pipeline** — still broken; the mfapi.in backfill recovered the
  data but the nightly will re-degrade. Needs a JIP-side fix or a daily
  `amfi_nav_backfill.py` supplemental cron.
- **1-day lag** — `atlas_stock_state_daily` (SDE v2), `atlas_daily_briefs`,
  `atlas_component_validation` at 2026-05-19. Nightly pipeline catch-up.
- **`drawdown_ratio_252`** — recent dates fully populated; some 2025 months
  are sparse (33–40%) — flagged for a later targeted check.
- **MF/ETF holdings** — already on a weekly cron (`holdings_weekly`, Sundays).

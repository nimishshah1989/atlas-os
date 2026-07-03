# Atlas Refresh Schedule — TARGET (FM-directed, pending final sign-off)

**Status:** near-final — incorporates FM directives 2026-07-01. This is the G2 schedule gate.
**Principle:** Atlas-owned ingestion only (JIP retired, D5). One orchestrator per cadence, **stages sequential** (no races). Every source documented, idempotent, logged. Freshness guard fails LOUD. All writes → single schema `atlas_foundation`. Live code runs from `/home/ubuntu/atlas-os` (frontend: pm2 `atlas-frontend-v3`; backend: `run_atlas_nightly.sh`, `REPO=atlas-os`).

All times **IST** (NSE close 15:30).

## Cadence (FM-directed)
- **Weekdays (Mon–Fri):** daily job runs **sequentially from 19:30 IST** onwards.
- **Saturday:** all weekly refreshes (holdings, masters, fundamentals, shareholding).
- **Sunday:** RESERVED for the **weekly QA / health-audit** job (no ingestion) → emails FM if anything is off.
- **Intraday (Mon–Fri market hours):** **15-min live refresh** (indices + live sector calc), backend-first.

---

## A. `atlas_daily.sh` — Mon–Fri, sequential from 19:30 IST
Runs as an ordered chain; each stage must succeed (or log+continue with end-of-run alert). Kite token comes from the morning Telegram login (§E).

| Seq | Stage | Source/Script | → Table |
|---|---|---|---|
| 1 | Kite token check | `atlas/intraday/auth.get_valid_access_token` | (abort+alert if missing) |
| 2 | Stock + ETF OHLCV | **Kite** `ingest_kite.py` (full universe) | `ohlcv_stock`, `ohlcv_etf` |
| 3 | Index OHLCV | **Kite** `ingest_kite.py` (indices) | `index_prices` |
| 4 | Delivery % | NSE `fetch_delivery.py` | `delivery_daily` |
| 5 | Fund NAV | AMFI `ingest_nav.py` | `de_mf_nav_daily` |
| 6 | Filings / insider / bulk deals | BSE/NSE ingest | `lens_filings`, `lens_insider`, `lens_bulk_deals` |
| 7 | Macro (daily bits) | FRED/NSE ingest | `atlas_macro_daily` |
| 8 | Technicals (incremental by date) | `compute_all.py` | `technical_daily` |
| 9 | Index metrics (RS) | `build_index_metrics.py` | `atlas_index_metrics_daily` |
| 10 | Lens scores **+ deciles + leadership** | `atlas/lenses/pipeline.py` | `atlas_lens_scores_daily` |
| 11 | Sector roll-up + composite | `rollup_sectors.py` | `sector_lens_daily` |
| 12 | Fund roll-up + cat-rank (<12m gate) + metrics | `build_fund_rank_history.py --latest` | `fund_rank_daily` |
| 13 | ETF roll-up (NEW) | `build_etf_rank_history.py` | `etf_rank_daily` |
| 14 | Breadth | `build_breadth_series.py` | `breadth_nifty500_daily` |
| 15 | Regime | regime compute | `atlas_market_regime_daily` |
| 16 | Serving matviews | mv refresh | `atlas_foundation.mv_*` |
| 17 | **Gate:** lens validation | `validate_lenses.py` | assert (real output) |
| 18 | **Gate:** freshness guard | freshness check | assert + **loud alert** |
| 19 | Serving refresh | pm2 reload + clear cache | live site |

## B. `atlas_weekly.sh` — Saturday
| Stage | Source/Script | → Table |
|---|---|---|
| MF holdings | Morningstar `ingest_mf_holdings.py` | `de_mf_holdings` |
| Fund + ETF master | Morningstar `ingest_fund_master.py` | `de_mf_master`, `de_etf_master`, `atlas_universe_funds/etfs` |
| Fundamentals + ratios | screener `ingest_screener.py` | `financials_quarterly/annual`, `screener_ratios` |
| Shareholding pattern | BSE/NSE ingest | `lens_shareholding` |
| Instrument master + sectors | `build_universe.py` / `assign_sectors.py` | `instrument_master` |

## C. `atlas_sunday_qa.sh` — Sunday (weekly health audit; NO ingestion)
Detailed weekly check → **emails FM** (and/or health-check page) if issues. Asserts on REAL data (rule #0).
1. **Freshness:** every KEEP table's max-date is within its expected cadence (no stale feed).
2. **Completeness:** every stage ran this week; row-count deltas sane; universe coverage ≥ expected (e.g. ≥95% Nifty500 scored).
3. **Null/error scan:** no unexpected NULLs in scored columns; no error rows; lens coverage thresholds met.
4. **Outlier / sporadic-jump scan:** flag |1-day move| implausibly large (the FMCG +249% detector — `max_abs_log_jump`), decile discontinuities, composite jumps.
5. **Reconciliation:** recompute-and-diff a sample vs stored (the existing reconcile harness).
6. **Report:** email FM a pass/fail digest + specifics; write to health/data-status page.

## D. `atlas_intraday.sh` — Mon–Fri market hours, every 15 min
- Kite intraday quotes → live index + sector calc (`mv_rs_intraday` equivalent, in `atlas_foundation`).
- Backend-first (data available); frontend surfacing to follow.
- Reflects mainly in indices + live sector movement.

## E. Kite auth — Telegram daily login (champion-trader pattern; ALREADY BUILT)
- `scripts/kite_daily_notify.py` sends a Telegram message ~08:55 IST: if token valid → "already authed"; else → click-to-auth link. FM clicks → Kite OAuth → token stored (`atlas_kite_session`), valid to midnight IST. The 19:30 daily job uses it.
- **To finish (G2):** (a) confirm `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are set (NOT in atlas-os/.env today); (b) the login link `/api/kite/login` is not a Next route — confirm/route it to the FastAPI `atlas/api/kite_auth.py` OAuth start+callback (exchange→store); (c) freshness guard alerts if no token by 19:30 IST.
- TOTP auto-login stays only as an optional fallback; the Telegram click flow is primary (avoids the stale-TOTP lockout risk).
- Env codified: `talib` (needs C lib) + `pyotp` → `pyproject.toml`; `atlas_kite_session` → `atlas_foundation`.

## Removed (the 3-headed tangle)
JIP crontab (`jip_trigger.sh`, `jip_agent3.sh`, `nightly_compute`), `run_atlas_intelligence_nightly.sh` (retired IC), M2/M3/M4/M5 legacy steps, pg_cron `atlas.mv_*` refreshes (moved into `atlas_foundation` + intraday job), `mfwatch_daily`, us/global crons (`us_daily`/`global_daily`/`stooq`). Frontend healthcheck + auto-deploy stay.

## Confirmed decisions (2026-07-01)
- ✅ Daily sequential from 19:30 IST · ✅ Weekly = Saturday · ✅ Sunday = QA/health audit + email · ✅ 15-min intraday (indices+sector) · ✅ Kite = ALL OHLCV · ✅ Telegram daily login (existing flow).

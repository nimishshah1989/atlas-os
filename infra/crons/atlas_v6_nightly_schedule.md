# Atlas v6 — Nightly Schedule (Canonical)

Source of truth for every scheduled job that touches the v6 backend.
All times in **IST** (UTC+5:30). Mon-Fri unless noted.
Forward-only by design — no historic backfills on cron paths.

**Data-source policy:** Indian stocks/ETFs/indices from NSE bhavcopy only.
Global from Stooq/yfinance. MFs from AMFI + Morningstar API.
See memory entry `[[data-source-policy]]`.

---

## Pipeline order (one trading day)

```
   ┌─ 18:33  JIP bhavcopy EOD  ─────────────────────────┐
   │   ↓ de_equity_ohlcv_y2026 / de_etf_ohlcv (via JIP) │
   │ 19:00  JIP macro_daily (USDINR/DXY/…)              │
   │   ↓ atlas_macro_daily                              │
   │ 19:30  validate_ohlcv                              │
   │ 21:30  v2 nightly (state classify + brief)         │
   │ 22:30  JIP amfi_late                               │
   │   ↓ de_mf_nav_daily                                │
   │ 23:30  run_atlas_nightly.sh                        │
   │   ↓ atlas_stock/sector/index_metrics + states      │
   │   ↓ atlas_fund_states + atlas_etf_states +         │
   │   ↓ atlas_etf_metrics + atlas_etf_decisions        │
   │ 00:00+1 amfi_nav_backfill --stale-days 2           │
   │ 00:30+1 JIP nightly_compute                        │
   │ 01:30+1 run_atlas_intelligence_nightly.sh          │
   │   ↓ atlas_stock_conviction_daily                   │
   │   ↓ atlas_scorecard_daily                          │
   │   ↓ atlas_signal_calls + atlas_etf_signal_calls    │
   │   ↓ atlas_cts_signals_daily + hit_rates + IC       │
   │ 02:00+1 AMFI ETF iNAV ingest      (NEW)            │
   │   ↓ atlas_etf_scorecard.premium_bps                │
   │ 03:15+1 MV refresh chain          (NEW)            │
   │   ↓ all 14 v6 MVs refreshed CONCURRENTLY           │
   │ 03:30+1 atlas_health_check        (NEW)            │
   │   ↓ atlas_data_health (one row per critical table) │
   └────────────────────────────────────────────────────┘
```

---

## Cron table

| IST | UTC | Cadence | Job | Runner | Script / SQL | Writes |
|---|---|---|---|---|---|---|
| 18:33 | 13:03 | Mon-Fri | JIP EOD bhavcopy | EC2 | `$WRAPPER eod` | `public.de_equity_ohlcv_y*`, `public.de_etf_ohlcv`, `public.de_index_prices`, FII/DII rows |
| 19:00 | 13:30 | Mon-Fri | JIP macro daily | EC2 | `$WRAPPER macro_daily` | `atlas.atlas_macro_daily` (USDINR/DXY/India 10Y/Brent/CPI/VIX) |
| 19:30 | 14:00 | Mon-Fri | OHLCV validation | EC2 | `validate_ohlcv.sh` | log only |
| 19:30 | 14:00 | Mon-Fri | JIP filings daily | EC2 | `$WRAPPER filings_daily` | filings tables |
| 21:30 | 16:00 | Mon-Fri | Atlas v2 nightly | EC2 | `atlas-os-sl/scripts/nightly_v2.sh` | v2 state tables + brief |
| 22:30 | 17:00 | Mon-Fri | JIP AMFI late | EC2 | `$WRAPPER amfi_late` | `public.de_mf_nav_daily` |
| 23:30 | 18:00 | Mon-Fri | **Atlas main nightly** | EC2 | `run_atlas_nightly.sh` | M2/M3/M4/M5 + US/global ETF (12 steps) |
| 00:00+1 | 18:30 | Mon-Fri | AMFI NAV supplemental | EC2 | `scripts/amfi_nav_backfill.py --stale-days 2` | `public.de_mf_nav_daily` (stale top-up) |
| 00:30+1 | 19:00 | Mon-Fri | JIP nightly compute | EC2 | `$WRAPPER nightly_compute` | JIP intelligence |
| 01:30+1 | 20:00 | Mon-Fri | **Atlas intelligence** | EC2 | `run_atlas_intelligence_nightly.sh` | conviction + IC + CTS + validator |
| **02:00+1** | **20:30** | **Mon-Fri** | **AMFI ETF iNAV (NEW)** | **EC2** | `scripts/amfi_etf_inav_ingest.py --write` | `atlas.atlas_etf_scorecard.premium_bps` |
| **03:15+1** | **21:45** | **Mon-Fri** | **MV refresh chain (NEW)** | **pg_cron** | `mv_refresh_v6_all` | All 14 v6 MVs (CONCURRENTLY) |
| **03:30+1** | **22:00** | **daily** | **Health check (NEW)** | **EC2** | `scripts/atlas_health_check.py` | `atlas.atlas_data_health` |
| 23:33 | 18:03 | Sat-Sun | Weekend EOD | EC2 | `$WRAPPER eod_weekend` | catch-up |
| 19:33 | 14:03 | Sat-Sun | ETF global weekend | EC2 | `$WRAPPER etf_global` | US/global catch-up |
| Sun 03:00 | Sat 21:30 | weekly | Morningstar weekly | EC2 | `$WRAPPER morningstar_weekly` | MF master |

---

## Per-MV refresh schedule (after consolidation — migration 110)

All 14 canonical v6 MVs refresh in ONE chain at **21:45 UTC** (03:15 IST), inside a single pg_cron job `mv_refresh_v6_all`. Sequence respects dependencies (compute → leaf MVs → aggregate MVs).

| Order | MV | Page |
|---|---|---|
| 1 | mv_current_market_regime | Page 01 |
| 2 | mv_market_regime_landing | Page 01 |
| 3 | mv_india_pulse | Page 02 |
| 4 | mv_markets_rs_grid | Page 03 |
| 5 | mv_markets_rs_detail_charts | Page 03 |
| 6 | mv_sector_cards | Page 04 |
| 7 | mv_sector_breadth | Page 04 |
| 8 | mv_sector_rrg | Page 04 |
| 9 | mv_sector_deepdive | Page 04a |
| 10 | mv_stock_list_v6 | Page 05 (table) |
| 11 | mv_stock_landscape | Page 05 (bubble + matrix) |
| 12 | mv_stock_deepdive | Page 05a |
| 13 | mv_fund_list_v6 | Page 06 |
| 14 | mv_fund_deepdive | Page 06a |
| 15 | mv_etf_list_v6 | Page 07 |
| 16 | mv_etf_deepdive | Page 07a |
| 17 | mv_calls_performance | Page 08 |

(Supporting MVs — `mv_rs_leaders_daily`, `mv_breakout_candidates`,
`mv_deterioration_watch`, `mv_sector_rotation_state`, `mv_top_conviction_daily`,
`mv_rs_intraday` — already refreshed inside `run_atlas_intelligence_nightly.sh`.)

---

## Visibility (no Slack — query the table)

After the nightly chain finishes (≈03:30 IST), check status with:

```sql
-- Yesterday's run summary
SELECT
  category, schema_name, table_name,
  status, last_data_date, expected_data_date, freshness_days_lag,
  row_count, null_rate_critical, notes
FROM atlas.atlas_data_health
WHERE check_date = CURRENT_DATE
ORDER BY status DESC, freshness_days_lag DESC, table_name;

-- Reds across the last 7 days (trend)
SELECT check_date, COUNT(*) FILTER (WHERE status = 'RED') AS reds,
       COUNT(*) FILTER (WHERE status = 'YELLOW') AS yellows,
       COUNT(*) FILTER (WHERE status = 'GREEN') AS greens
FROM atlas.atlas_data_health
WHERE check_date >= CURRENT_DATE - 7
GROUP BY check_date ORDER BY check_date DESC;
```

---

## Status definitions

- **GREEN**: `last_data_date >= expected_data_date` AND `null_rate_critical < threshold` AND `row_count > expected_min`
- **YELLOW**: `last_data_date` is 1 day behind expected, or null rate slightly elevated. Frontend can render with caveat.
- **RED**: `last_data_date >= 2 days behind expected`, or `row_count = 0`, or `null_rate_critical > critical_threshold`. Investigate.

Per-table thresholds defined in `scripts/atlas_health_check.py` (TABLE_SPEC dict).

---

## Failure handling

Per user direction (2026-05-27): no Slack/email alerting. RED rows in `atlas_data_health` are the failure surface. Daily check:

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  'psql $ATLAS_DB_URL -c "SELECT table_name, status, notes FROM atlas.atlas_data_health WHERE check_date = CURRENT_DATE AND status = \"RED\";"'
```

When a RED appears, debug together — root-cause script + rerun for that day only.

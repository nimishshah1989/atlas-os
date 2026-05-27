# MV Sector Cards — Design Document

**Date:** 2026-05-27  
**MV name:** `atlas.mv_sector_cards`  
**Migration:** 102_mv_sector_cards.py  
**Cron:** `40 14 * * *` (20:40 IST = 14:40 UTC)

---

## 1. Row shape

ONE row per `(as_of_date, sector_name)`. Latest `as_of_date` serves the
live Sectors page (04). Historical rows support time-travel.

Expected rows: ~31 sectors × ~1,550 trading days (2020-01-01 to 2026-05-27) ≈ **48,050 rows**.

---

## 2. Source tables and actual scale

| Table | Rows | Key |
|-------|------|-----|
| `atlas.atlas_sector_metrics_daily` | 74,752 | (sector_name, date) — 31 sectors × ~2,412 trading days |
| `atlas.atlas_sector_states_daily`  | 74,752 | (sector_name, date) |
| `atlas.atlas_signal_calls`         | 363    | signal_call_id |
| `atlas.atlas_universe_stocks`      | 750    | (instrument_id, effective_from) |
| `atlas.atlas_stock_metrics_daily`  | large  | (instrument_id, date) — for vol_60d_ann |

Date spine driven by `atlas_sector_metrics_daily` filtered to 2020-01-01+.

---

## 3. Column source mapping

| Output column | Source | Notes |
|--------------|--------|-------|
| `as_of_date` | `atlas_sector_metrics_daily.date` | Date spine |
| `sector_name` | `atlas_sector_metrics_daily.sector_name` | 31 sectors |
| `constituent_count` | `COUNT(DISTINCT u.instrument_id) WHERE u.effective_to IS NULL` via atlas_universe_stocks | Live count |
| `ret_1w` | `atlas_sector_metrics_daily.bottomup_ret_1w` | NOTE: col rs_1w is RS; ret_1w column needs to be derived from LAG on ret_1m if not present |
| `ret_1m` | `atlas_sector_metrics_daily.bottomup_ret_1m` | Direct column |
| `ret_3m` | `atlas_sector_metrics_daily.bottomup_ret_3m` | Direct column |
| `ret_6m` | `atlas_sector_metrics_daily.bottomup_ret_6m` | Direct column |
| `ret_12m` | `atlas_sector_metrics_daily.bottomup_ret_12m` | NOTE: derived via LAG if not present; rs_12m exists |
| `rs_1m` | `atlas_sector_metrics_daily.rs_1m` | Added in migration 097 |
| `rs_3m` | `atlas_sector_metrics_daily.bottomup_rs_3m_nifty500` | Original column |
| `rs_6m` | `atlas_sector_metrics_daily.rs_6m` | Added in migration 097 |
| `vol_60d_ann` | AVG(stock.realized_vol_63) per sector per date | From atlas_stock_metrics_daily — annualised std; realized_vol_63 ≈ 63-day realized vol |
| `pct_above_ema20` | `atlas_sector_metrics_daily.pct_above_ema20` | Added in migration 097 |
| `pct_above_ema200` | `atlas_sector_metrics_daily.pct_above_ema200` | Added in migration 097 |
| `pct_at_52wh` | `atlas_sector_metrics_daily.pct_52wh` | Added in migration 097 |
| `hhi_concentration` | `atlas_sector_metrics_daily.hhi` | Added in migration 097 |
| `buy_signal_count` | COUNT(sc.signal_call_id) WHERE action='POSITIVE' AND exit_date IS NULL | From atlas_signal_calls, joined via universe_stocks for sector |
| `confidence_distribution` | `{"H": n, "M": n, "L": n}` JSONB — H=confidence>=0.70, M=0.50-0.70, L<0.50 | Computed from confidence_unconditional on signal_calls |
| `verdict` | `atlas_sector_states_daily.sector_state` | OW=Overweight, NW=Neutral, UW=Underweight |

---

## 4. Verdict mapping

`atlas_sector_states_daily.sector_state` values:
- `'Overweight'` → OW
- `'Neutral'` → NW
- `'Underweight'` or `'Avoid'` → UW
- `'DISLOCATION_SUSPENDED'` → NW (neutral fallback)

The MV stores the raw `sector_state` value. Display label (OW/NW/UW) is
rendered by the API/frontend layer. We also store a `verdict_abbr` computed
column for convenience.

---

## 5. Signal aggregation approach

Signal_calls → sector join path:
```sql
atlas_signal_calls sc
JOIN atlas_universe_stocks u ON u.instrument_id = sc.instrument_id
  AND u.effective_to IS NULL
WHERE sc.action = 'POSITIVE'
  AND sc.exit_date IS NULL
GROUP BY u.sector
```

This gives the **current active BUY signals** per sector. Since this is a
historical MV (one row per date), we need signal counts "as of" each
date. For historical dates, we join on `sc.date = as_of_date` (when the
signal was first triggered). This captures signals that were active on
that date (triggered on that date, not yet exited).

**Confidence H/M/L bands:**
- High (H): `confidence_unconditional >= 0.70`
- Medium (M): `confidence_unconditional >= 0.50 AND < 0.70`
- Low (L): `confidence_unconditional < 0.50`

---

## 6. vol_60d_ann computation

`atlas_stock_metrics_daily.realized_vol_63` is the 63-trading-day
annualised realised volatility per stock (already annualised per the
feature definition in scorecard_writer.py — `std(daily_ret) * sqrt(252)`).

We average this across all active sector constituents per date:
```sql
AVG(smd.realized_vol_63) over (sector stocks on that date)
```

If `realized_vol_63` is NULL (pre-backfill dates), the column is NULL in
the MV — this is explicit NULL handling, not 0.

---

## 7. Refresh strategy

- **Initial:** `WITH NO DATA` + `CREATE UNIQUE INDEX` + `REFRESH MATERIALIZED VIEW` (full build)
- **Nightly:** `REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_cards` at 20:40 IST (14:40 UTC)
- **Expected runtime:** ~30–60 seconds. The vol_60d CTE joins stock_metrics_daily but only reads 1 row per stock per date (no full table scan). Signal_calls has only 363 rows — trivially fast.

---

## 8. Unique index

```sql
CREATE UNIQUE INDEX uix_mv_sector_cards_date_sector
  ON atlas.mv_sector_cards (as_of_date, sector_name);
```

Required for `REFRESH CONCURRENTLY`.

---

## 9. Sample JSONB shape

```json
{
  "H": 6,
  "M": 5,
  "L": 3
}
```

This is `confidence_distribution` — a compact object with three integer
pip counts. The frontend renders this as a mini bar (filled segments).

---

## 10. Edge cases handled

| Case | Handling |
|------|---------|
| NULL rs_1w / rs_6m / rs_12m (pre-backfill dates before 2020) | `COALESCE(..., NULL)` — propagates NULL |
| NULL pct_above_ema20/200/52wh (pre-097 backfill) | Propagates NULL |
| NULL hhi (pre-097 backfill) | Propagates NULL |
| Sector with zero active signals | `buy_signal_count = 0`, `confidence_distribution = {"H":0,"M":0,"L":0}` |
| Sector with no state (sector_states_daily gap) | `verdict = NULL`, `verdict_abbr = NULL` |
| Stock with NULL realized_vol_63 | Excluded from AVG (SQL AVG ignores NULLs) |
| Sectors not in states table | LEFT JOIN — verdict NULL |

---

## 11. ReturnType note

All return columns stored as `NUMERIC` in source tables. The MV preserves
`NUMERIC` types — no float conversion. `confidence_distribution` is JSONB.
Integer counts (`buy_signal_count`, `constituent_count`) are INTEGER.

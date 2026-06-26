# Atlas clean data foundation — harness + ingest (PoC stage)

Implements the plan in [`docs/atlas-data-foundation.md`](../../docs/atlas-data-foundation.md):
a Supabase-native, NSE-Bhavcopy-sourced market-data backend with all technicals
via **TA-Lib**, validated by a quantifiable 3-axis harness, built on a **staging
schema** (`foundation_staging`) so live `de_*`/`atlas_*` are never mutated.

**Status:** verification harness + thin PoC complete and green. The full 10y
backfill loop is **not** started yet (awaiting review).

## Cost model
Scripts do the heavy work as plain Python (download Bhavcopy, run TA-Lib) and
print only small pass/fail summaries — ~0 model tokens regardless of data volume.

## Files
| file | role |
|---|---|
| `_db.py` | DB access (reads `ATLAS_DB_URL` from `frontend/.env.local`); bulk upsert |
| `psql.sh` | ad-hoc psql wrapper (extracts the URL at call time, no secret on disk) |
| `technicals.py` | **canonical TA-Lib** metrics (EMA 21/50/200, RSI14, returns, RS) — shared by compute + harness |
| `harness.py` | 3-axis verification harness (coverage / cleanliness / metrics), read-only |
| `staging_ddl.sql` | `foundation_staging` schema DDL (idempotent) |
| `ingest_bhavcopy.py` | download + parse one day of NSE Bhavcopy → staging raw |
| `compute.py` | compute technicals from staging OHLCV → `technical_stock` |
| `poc.py` | orchestrates the thin PoC end-to-end |

## Run
```bash
PY=../../.venv/bin/python
# Baseline against current live data (how far from all-green today):
$PY harness.py --profile live --metrics-sample 30
# Apply staging schema:
bash psql.sh -f staging_ddl.sql
# Thin PoC (seed deep history + real one-day ingest → TA-Lib → harness green):
$PY poc.py
# Harness against staging:
$PY harness.py --profile staging --symbols HCLTECH SUNPHARMA ...
```

## The 3 axes (definition of done = green_count == universe size)
1. **Coverage** — present, ≥10y deep (to 2016 or listing date), enough rows for the span.
2. **Cleanliness** — no null/≤0 closes, no calendar gaps (≥99% complete), ≤1 tday
   stale, no absurd 1-day jumps (>50% on adj close = unadjusted corp action).
3. **Metrics** — EMA21/50/200, RSI14, returns, RS(N50/N500 × 6 windows) present for
   every priced date, and a TA-Lib **recompute-and-diff matches stored**.

Trading calendar = dates present in the `NIFTY 50` reference series. Universe =
current Nifty 500 membership from `de_instrument` (current-membership-for-all-history,
per the locked decision).

## Operational notes (learned the hard way)
- NSE **archives** (`archives.nseindia.com`) static Bhavcopy/zip/CSV files are
  reachable from EC2; only the `www.nseindia.com/api/*` JSON endpoints are bot-blocked.
- The Supabase pooler enforces a **2-min statement timeout** and resets session
  `SET`s. Avoid SQL window functions / `ORDER BY` over the year-partitioned
  `de_equity_ohlcv` (cross-partition sort > 2 min); pull unsorted and sort in pandas.
- `de_equity_ohlcv.close_adj` is **not** reliably corporate-action-adjusted
  (e.g. ADANIENT 2015-06-03 −82.8% demerger is unadjusted) — this is why 244/500
  Nifty-500 names fail the cleanliness jump check.

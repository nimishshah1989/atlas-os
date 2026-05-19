# Chunk: NSE F&O Ban List Backfill 2017→Today

## Data scale
- Trading days from 2017-01-01 to 2026-05-18: **2,417 rows**
- atlas_universe_stocks: **750 rows** (symbol → instrument_id map)
- atlas_governance_daily: **does not yet exist** (migration 080 recorded at v086 but table missing — needs CREATE)
- Expected ban list size per day: 0–30 symbols typically

## Problem: atlas_instrument_master missing
The `FnoBanUpserter` in `fno_ban.py` queries `atlas.atlas_instrument_master` which does not exist in this DB. The v6 DB uses `atlas.atlas_universe_stocks` as the symbol→instrument_id reference. The script must override the resolver to query `atlas_universe_stocks` instead.

## Approach
- Create `atlas_governance_daily` table directly via DDL in the script (IF NOT EXISTS guard)
- Override symbol resolution to use `atlas_universe_stocks` via a custom upsert loop in the script (avoids modifying `fno_ban.py`)
- Pull trading days from `atlas_market_regime_daily` (2,417 days available from 2017)
- NSE archive URL pattern: `secban_DDMMYYYY.csv` for historical; `fo_secban.csv` for today
- Sleep 0.6s between requests (~24 min total runtime)
- Catch HTTP non-200 as miss (NSE archive gaps for old dates are expected)

## Edge cases
- NSE archive may 404 on some old dates (holiday files may not exist) → log as miss, continue
- Symbol on ban list but not in atlas_universe_stocks → skip (only universe stocks matter for the model)
- Empty ban list (zero symbols) is valid — still need to clear any stale true flags for that date
- today's date uses `fo_secban.csv` not the dated URL

## Expected runtime
~2,417 × 0.6s = 24 min on t3.large. Run via nohup in background.

## Files
- `scripts/v6_fno_ban_backfill.py` — new script

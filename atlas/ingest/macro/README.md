# atlas.ingest.macro — Macro Data Ingest

Fills 8 NULL columns on `atlas.atlas_macro_daily` from free public sources.

## Sources

| Column | Module | Source | Auth | Frequency |
|--------|--------|--------|------|-----------|
| `us_10y_yield` | `fred_ingest.py` | FRED `DGS10` | `FRED_API_KEY` env var | Daily |
| `india_10y_yield` | `fred_ingest.py` | FRED `INDIRLTLT01STM` | `FRED_API_KEY` env var | Monthly |
| `brent_usd` (temp) | `fred_ingest.py` | FRED `DCOILBRENTEU` | `FRED_API_KEY` env var | Daily |
| `risk_free_91d` | `fred_ingest.py` | FRED `INTGSB91D156N` | `FRED_API_KEY` env var | Weekly |
| `fii_cash_equity_flow_cr` | `nse_bhavcopy_ingest.py` | NSE FII/DII archive CSV | None (public) | Daily |
| `dii_flow` | `nse_bhavcopy_ingest.py` | NSE FII/DII archive CSV | None (public) | Daily |
| `cpi_yoy` | `mospi_cpi_ingest.py` | Bundled RBI/MOSPI data | None (bundled) | Monthly |
| `vix_9d` | `nse_vix_ingest.py` | NSE India VIX CSV | None (public) | Daily |
| `brent_inr` | `runner.py` | Derived: brent_usd × usdinr | — | Daily |

## Setup

```bash
# FRED API key (free at https://fred.stlouisfed.org/docs/api/api_key.html)
echo "FRED_API_KEY=your_key_here" >> .env
```

## Running

```bash
# Initial backfill (all history from 2016-01-01) — run once on EC2
python -m atlas.ingest.macro.runner --mode=backfill --start=2016-01-01

# Incremental update (last 7 days) — run nightly via pg_cron/EC2 cron
python -m atlas.ingest.macro.runner --mode=incremental
```

## Notes

### FRED API Key
Register a free key at https://fred.stlouisfed.org/docs/api/api_key.html.
Set as `FRED_API_KEY` in `.env`. Missing key = graceful degradation (FRED sources return 0 rows).

### NSE Data
NSE blocks direct unauthenticated requests. The ingest scripts send proper `User-Agent` + `Referer` headers. If NSE blocks the IP, download the CSV manually and pass via `--csv-path` override.

### MOSPI CPI
MOSPI has no stable API. CPI All-India Combined data (Base 2012=100) is bundled in `mospi_cpi_ingest.py` from RBI DBIE. Update the `_BUNDLED_CPI_RAW` list monthly when MOSPI publishes new figures (typically by the 12th of each month).

### vix_9d (Documented Proxy)
NSE publishes India VIX (30-day implied volatility) but not a 9-day variant. `vix_9d` is computed as a 9-period exponential moving average (`ewm(span=9, adjust=False)`) of the daily India VIX close. First 8 rows are NULL (insufficient warm-up). This is documented as a proxy in the approach doc.

### brent_inr Derivation
`brent_inr` = `brent_usd` × `usdinr`. Both values must be available in `atlas_macro_daily` for the cross to succeed. `usdinr` is populated by the main atlas compute pipeline; `brent_usd` is fetched from FRED and crossed in-memory before writing `brent_inr`.

### Historical Depth
| Source | Earliest available |
|--------|--------------------|
| US 10Y (FRED DGS10) | 1962-01-02 |
| India 10Y (FRED INDIRLTLT01STM) | 1960-01 |
| Brent USD (FRED DCOILBRENTEU) | 1987-05-20 |
| Risk-free 91d (FRED INTGSB91D156N) | 1997-01 |
| NSE FII/DII | ~2007 |
| MOSPI CPI | 2013-01 (Base 2012=100) |
| NSE India VIX | 2007-11-01 |

Atlas scope is 2016-01-01. All sources cover the full scope.

### pg_cron
Migration 099 registers `atlas_macro_nightly` at 14:45 UTC (20:15 IST) on weekdays.
Verify: `SELECT * FROM cron.job WHERE jobname = 'atlas_macro_nightly';`

Fallback (if pg_cron extension unavailable):
```crontab
45 20 * * 1-5 cd ~/atlas-os && source .venv/bin/activate && python -m atlas.ingest.macro.runner --mode=incremental >> /var/log/atlas/macro_nightly.log 2>&1
```

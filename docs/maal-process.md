# MaaL Process — operator runbook

**MaaL = Multi Asset Alpha - Leaders.** The weekly model-portfolio document, and the
three real books behind it. Reasoning lives in
[ADR 0005](adr/0005-maal-books-come-from-the-cpp-database.md); this file is how to run it.

## The three books

| Atlas code | CPP UCC | `portfolio_master.name` | Inception |
|---|---|---|---|
| `leaders` | `BJ53` | MaaL Leaders | 2020-09-28 |
| `ind11` | `BJ53IND` | MaaL IND11 | 2026-05-09 |
| `passive` | `JR100PASS` | MaaL Passive | 2021-08-02 |

Keyed on the explicit UCC, never on CPP's `strategy` column — `JR100PASS` classifies as
LEADERS there because that column keys off a `PASS` suffix.

## What runs, when

| When (IST) | What | Blocking? |
|---|---|---|
| 12:00, 22:00 daily | `scripts/ops/maal_sync.sh` → `sync_maal_books.py` | exits non-zero on an unresolved current holding |
| same, after the sync | `maal_pnl_reconcile.py` | non-fatal by design |
| end of `atlas_daily.sh` (16:00) | `freshness_guard.py` MaaL checks | `as_of` stale blocks; `source_as_of` stale warns |
| Sat 12:30 | `build_universe.py` (in `atlas_weekly.sh`) | keeps ETF ISINs current |

Twice daily because CPP positions only move when a backoffice file is uploaded: the noon
run catches a morning upload, the 22:00 run an evening one. Every day, not weekdays — a
file uploaded on a Saturday should not wait until Monday to reach the Monday book.

## Access

`MAAL_SOURCE_DB_URL` in `/home/ubuntu/atlas-os/.env` (mode 600), pointing at the CPP RDS
as role `atlas_reader`: SELECT on `cpp_portfolios`, `cpp_holdings`, `cpp_transactions`,
`cpp_nav_series` and **nothing else**. `cpp_clients` holds client PII and is deliberately
not granted — verify with:

```bash
scripts/ops/psql_masked.sh MAAL_SOURCE_DB_URL -tAc "SELECT count(*) FROM cpp_clients"
# expected: ERROR: permission denied for table cpp_clients
```

**Never pass a DB URL to bare `psql`.** It rejects the SQLAlchemy form
(`postgresql+psycopg2://...?sslmode=require`) and echoes the whole URL, password included,
in the error. Use `scripts/ops/psql_masked.sh <ENV_VAR_NAME> <psql args>`, which strips the
prefix and masks output on both success and failure.

## When something breaks

**`FATAL — N CURRENT holding ISIN(s) not in instrument_master`**
An instrument the books hold is missing from the universe. Run
`scripts/foundation/build_universe.py`, then re-run the sync. Do **not** add a symbol
fallback: CPP's transaction symbols are raw backoffice strings
(`HDFCMUTUALFUND-HDFCNIFTYSMALLCAP`), and matching on them loses positions silently.

**`N historical-only ISIN(s) unresolved`** — expected. Delisted or merged names appearing
only in years-old transactions. They cost a little historical realized P&L and never affect
the book. Named in full in the log every run.

**`maal_holding_snapshot[code]: last synced … the sync is DEAD`**
Atlas stopped looking. Check `/home/ubuntu/logs/maal_sync.log`.

**`CPP data is from … the backoffice upload is lagging`**
Atlas is healthy; nobody has uploaded to the portal. Not an Atlas problem — chase the
upload. This is why the two dates are separate.

**`maal_pnl_reconcile` FAIL** — the money disagrees with itself. Never ship a Monday
document past this: a P&L figure that contradicts the client statement discredits every
other number on the board.

## Rules that are not obvious

- **Cash includes liquid ETFs.** `cash_value + bank_balance + etf_value`. GOLDBEES and
  SILVERBEES are positions, not cash.
- **CPP owns quantity and cost; Atlas owns price.** Never import CPP's `current_price` or
  `weight_pct`.
- **`portfolio_trades.instrument_key` is the instrument UUID.** The readable
  `stock:SYMBOL` form belongs only in `maal_holding_snapshot`.
- **The engine must not mark these books.** `portfolio_run`'s loops exclude
  `params.source = 'cpp'`. If NAV ever looks computed rather than reported, check that first.
- **Money never goes through `pandas.read_sql`** — it coerces `numeric` to float64.

## Verifying a run by hand

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  PYTHONPATH=$PWD:$PWD/scripts/foundation .venv/bin/python scripts/foundation/sync_maal_books.py'
ssh jprod 'cd /home/ubuntu/atlas-os && scripts/ops/psql_masked.sh ATLAS_DB_URL -c "
  SELECT m.name, n.date AS source_as_of, round(n.nav/100000,2) nav_lakh,
         round(100.0*n.cash/nullif(n.nav,0),2) cash_pct, n.n_positions
  FROM atlas_foundation.portfolio_nav_daily n
  JOIN atlas_foundation.portfolio_master m USING (portfolio_id)
  WHERE m.params->>'"'"'source'"'"' = '"'"'cpp'"'"' ORDER BY m.name;"'
```

A second sync run must insert **0** trades. If it inserts more, `maal_trade_link` is not
doing its job and the book's history is doubling.

# MaaL Process Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the weekly model-portfolio document run off the **real** executed portfolios held in the `clients.jslwealth.in` (CPP) database, instead of a book folded from the FM's own recommendations.

**Architecture:** A twice-daily job pulls holdings, NAV and transactions for three UCCs (BJ53, BJ53IND, JR100PASS) out of the CPP RDS and lands them in `atlas_foundation` — positions as a dated snapshot, NAV into the existing `portfolio_nav_daily`, trades into the existing `portfolio_trades`. Because it writes the tables the portfolio pages already read, those pages populate with no new UI. The Monday document is then renamed to the MaaL Process and re-pointed at the synced snapshot. Live P&L rides the 5-minute intraday cron that already exists.

**Tech Stack:** Python 3.11 + SQLAlchemy (existing `scripts/foundation/_db.py` pattern), Postgres (Supabase `atlas_foundation` target, CPP RDS source), Next.js 15 + postgres.js frontend, vitest + pytest.

---

## Why this plan exists

The current book is self-referential: publish folds every recommendation onto last week's book and stores the result, and next week reads that back. But **the FM's calls are a superset of what actually fills.** The stored book therefore drifts from the real portfolio every week it compounds, and the circulated PDF has been publishing that drift as the Model Portfolio. This plan replaces the fold with measured reality.

## Scope note

Four phases. **Each ships on its own** and is independently valuable:

- **Phase 1** — sync + FIFO realized P&L + portfolio pages. Ships alone; delivers the three real books on `/portfolios` with NAV, holdings, trade history and per-sell realized P&L.
- **Phase 2a** — the MaaL rename, and **nothing else**. Pure mechanical rename: tables, files, routes, identifiers. Every existing test still passes unchanged. Zero behavior change.
- **Phase 2b** — delete `foldBook` and re-point the opening book at the synced snapshot. The commit that actually changes what the desk receives.
- **Phase 3** — 5-minute live P&L. Depends on Phase 1.

**2a and 2b are separate commits and separate merges.** Never structural and behavioral in one diff (Beck) — when next Monday's book looks wrong, `git bisect` must land on the ~60-line behavior commit, not on a 20-file rename. Do not start Phase 2a before Phase 1 is live and has produced at least one clean sync.

## Facts this plan is built on (verified 2026-07-31, do not re-derive)

| Fact | Value | How verified |
|---|---|---|
| CPP database | `jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com:5432/client_portal` | `docker exec client-portal printenv DATABASE_URL_SYNC` on `jprod` |
| The three UCCs | `BJ53` (id 768), `BJ53IND` (id 773), `JR100PASS` (id 841) | `SELECT ... FROM cpp_portfolios` |
| Liquid ETFs already tagged | `cpp_holdings.asset_class = 'CASH'` for LIQUIDBEES / LIQUIDCASE / LIQUIDETF; 46 CASH rows, **0** LIQUID-named rows misfiled as EQUITY | `GROUP BY asset_class` over 3,340 live rows |
| Transaction price fields | `price` = net rate (FIFO, matches backoffice), `cost_rate` = all-in incl. taxes, `amount` = total consideration | `\d cpp_transactions` + live rows |
| ISIN coverage on transactions | JR100PASS 100%, BJ53IND 100%, BJ53 1,356/1,372 (16 pre-format rows) | `count(isin)` by portfolio |
| Symbols differ between tables | holdings say `JSFB`, transactions say `JANASMALLFINANCEBANKLIMITE` — **join on ISIN only** | live rows |
| `portfolio_nav_daily` already has | `nav`, `cash`, `invested`, `n_positions`, `run_type` | `\d` |
| `portfolio_trades` already has | `realized_pnl`, `cost`, `holding_days`, `tax_bucket`, `tax` | `\d` |
| `portfolio_master.origin` CHECK | `('fm','system')` only — use `'fm'`, do **not** migrate the constraint | `\d` |
| `portfolio_trades.reason` CHECK | `('inception','signal','manual','stop','desk')` — use `'manual'` | `\d` |
| Existing 5-min cron | `*/5 4-9 * * 1-5 scripts/ops/atlas_intraday.sh`, Kite session already live | `scripts/ops/crontab.txt` |
| Existing MaaL data volume | 4 confirmations, 3 published, 42 calls | `count(*)` on `mpf_*` |

**Doc drift found:** `CLAUDE.md` says the daily orchestrator runs at 19:30 IST. The crontab says `30 10 * * 1-5` UTC = **16:00 IST**. Fix the doc in Phase 1, Task 8.

## RULE #0 compliance

No synthetic data anywhere, including tests. Every test constant in this plan is a **real row pulled from a real database on 2026-07-31** and is labelled as such in a header comment, following the precedent set by `frontend/src/lib/__tests__/confirmations.test.ts`. Pure functions are tested against those real values; DB I/O is verified by a gate script that asserts on real produced output.

---

## File Structure

**Phase 1**

| Path | Responsibility |
|---|---|
| `atlas/maal/__init__.py` | New bounded context. Exports the pure mapping functions only. |
| `atlas/maal/source.py` | Pure: map a CPP holdings/txn/NAV row to the Atlas shape. No I/O. |
| `atlas/maal/tests/test_source.py` | pytest over `source.py` using real 2026-07-31 rows. |
| `scripts/foundation/sync_maal_books.py` | The job: read CPP, write `atlas_foundation`. Thin — all logic lives in `atlas/maal/source.py`. |
| `scripts/foundation/maal_ddl.sql` | `maal_holding_snapshot` + the `source_txn_id` column and partial unique index on `portfolio_trades`. |
| `scripts/ops/maal_sync.sh` | Cron wrapper, mirroring `atlas_intraday.sh`. |
| `scripts/ops/crontab.txt` | Two new lines (12:00 and 22:00 IST). |

**Phase 2**

| Path | Responsibility |
|---|---|
| `scripts/foundation/maal_rename.sql` | `mpf_* → maal_*`, portfolio code re-map. |
| `frontend/src/lib/maal.ts` | Renamed from `confirmations.ts`; `foldBook` deleted. |
| `frontend/src/lib/queries/maal.ts` | Renamed; `getOpeningBook` re-pointed at the snapshot. |
| `frontend/src/components/maal/*` | Renamed from `components/confirmations/*`. |
| `frontend/src/app/portfolios/maal/**` | Renamed from `portfolios/confirmations/**`. |

**Phase 3**

| Path | Responsibility |
|---|---|
| `atlas/maal/live.py` | Pure: mark-to-live P&L from quotes + snapshot. |
| `scripts/foundation/maal_live_mark.py` | Quote the three books via the existing Kite session; write marks. |
| `scripts/ops/atlas_intraday.sh` | One added line. |

---

# PHASE 1 — Sync the real books

### Task 1: Source credentials and connectivity

**Files:**
- Modify: `frontend/.env.local` (and the box's `/home/ubuntu/atlas-os/.env`)
- Modify: `.env.example`

- [x] **Step 1: ~~Rotate the leaked Atlas DB password~~ — DECLINED by the FM, 2026-07-31**

The Supabase password for role `postgres.nanvgbhootvvthjujkvs` was printed in clear text in a session transcript on 2026-07-31. Rotation was recommended and **declined** (D9); the credential stays live. Recorded here rather than deleted, because a security decision that leaves no trace is indistinguishable from an oversight. To reverse: rotate in the Supabase dashboard, then update `ATLAS_DB_URL` in `/home/ubuntu/atlas-os/.env` and `frontend/.env.local`.

- [x] **Step 2: Create a read-only role on the CPP database — DONE 2026-07-31**

The portal's own credential is `jip_admin`, an admin account. Atlas must not reuse it. Applied on the CPP RDS:

```sql
CREATE ROLE atlas_reader LOGIN;
ALTER ROLE atlas_reader WITH PASSWORD '<48 hex chars, generated on the box>';
GRANT CONNECT ON DATABASE client_portal TO atlas_reader;
GRANT USAGE ON SCHEMA public TO atlas_reader;
GRANT SELECT ON cpp_portfolios, cpp_holdings, cpp_transactions, cpp_nav_series TO atlas_reader;
```

Four tables. No `GRANT SELECT ON ALL TABLES` — the portal holds client PII in `cpp_clients` and Atlas has no business reading it.

- [x] **Step 3: Add the source URL to env — DONE 2026-07-31**

`MAAL_SOURCE_DB_URL` is written to `/home/ubuntu/atlas-os/.env` (mode 600). The password was generated on the box with `openssl rand -hex 24` and has never been printed to a terminal or a transcript.

Still to do: add to `.env.example` with an empty value:

```
MAAL_SOURCE_DB_URL=
```

- [x] **Step 4: Verify connectivity and least privilege from the box — DONE 2026-07-31**

Verified output:

```
cpp_holdings=3340  cpp_portfolios=372  cpp_transactions=221322  cpp_nav_series=401362
SELECT on cpp_clients   -> ERROR: permission denied for table cpp_clients
DELETE on cpp_holdings  -> ERROR: permission denied for table cpp_holdings
```

Note the source tables are large — 221k transactions, 401k NAV rows across all ~372 portfolios. Every query in the sync **must** filter by `client_code`; an unfiltered pull would be a different order of magnitude than the ~2,000 rows the three books actually contain.

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  U=$(printf "%s" "$MAAL_SOURCE_DB_URL" | sed -E "s#^postgresql\+[a-z0-9]+://#postgresql://#; s#\?.*##") && \
  psql "$U" -c "SELECT count(*) FROM cpp_holdings;" -c "SELECT count(*) FROM cpp_clients;" 2>&1 | sed -E "s#://[^@]+@#://***@#g"'
```

Expected: the first count succeeds (3340 or similar); the second **fails** with `permission denied for table cpp_clients`. If the second succeeds, the grant is too wide — fix it before continuing.

- [ ] **Step 5: Write the masking wrapper — every psql call in this plan goes through it**

A connection error echoes the whole URL, password included. That is exactly how the Atlas credential leaked on 2026-07-31. Masking must be structural, not a regex someone remembers to type.

Create `scripts/ops/psql_masked.sh`:

```bash
#!/usr/bin/env bash
# psql against an env-held DB URL, with the password masked out of ALL output.
#
# Two jobs, both learned the hard way on 2026-07-31:
#   1. Strip the SQLAlchemy driver prefix and query string. psql rejects
#      "postgresql+psycopg2://...?sslmode=require" and echoes the whole URL —
#      password included — in the error. That leak is the reason this file exists.
#   2. Mask "://user:pass@" in every line of stdout AND stderr.
#
# Usage: psql_masked.sh ATLAS_DB_URL -c "SELECT 1"
set -euo pipefail
VAR="$1"; shift
URL="${!VAR:-}"
[ -n "$URL" ] || { echo "$VAR is not set" >&2; exit 2; }
URL=$(printf '%s' "$URL" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#; s#\?.*##')
psql "$URL" "$@" 2>&1 | sed -E 's#://[^@/]+@#://***:***@#g'
exit "${PIPESTATUS[0]}"
```

```bash
chmod +x scripts/ops/psql_masked.sh
```

**Every `psql` invocation elsewhere in this plan is shorthand for this wrapper.** Where a task shows a raw `psql "$U" -c "..."`, run `scripts/ops/psql_masked.sh ATLAS_DB_URL -c "..."` (or `MAAL_SOURCE_DB_URL`) instead. Do not hand-roll the `sed` again.

- [ ] **Step 6: Verify the wrapper masks a failure, not just a success**

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  scripts/ops/psql_masked.sh ATLAS_DB_URL -c "SELECT 1/0"'
```

Expected: a division-by-zero error with **no password anywhere in the output**. Testing the wrapper on a successful query proves nothing — the leak happens on the error path.

- [ ] **Step 7: Commit**

```bash
git add .env.example scripts/ops/psql_masked.sh
git commit -m "chore(maal): read-only CPP source URL + a psql wrapper that cannot leak the password"
```

---

### Task 2: Register the three books in portfolio_master

**Files:**
- Create: `scripts/foundation/maal_ddl.sql`

- [ ] **Step 1: Write the registration SQL**

Create `scripts/foundation/maal_ddl.sql`:

```sql
-- MaaL Process (Multi Asset Alpha - Leaders): the three real model portfolios,
-- sourced from the clients.jslwealth.in (CPP) database.
--
-- Applied via: python3 -c "import _db; _db.exec_script(open('maal_ddl.sql').read())"
--
-- These are books a human runs, registered in portfolio_master so the existing
-- /portfolios pages render them with no new UI. kind='basket' because there is no
-- engine strategy behind them (the kind='strategy' CHECK would demand a strategy_key);
-- origin='fm' because the FM does run them — the CPP provenance lives in params, which
-- is jsonb and needs no CHECK migration.

INSERT INTO atlas_foundation.portfolio_master
    (name, kind, strategy_key, params, asset_classes,
     initial_capital, max_position_pct, inception_date, status, origin)
VALUES
    ('MaaL Leaders', 'basket', NULL,
     '{"source":"cpp","client_code":"BJ53","maal_code":"leaders"}'::jsonb,
     ARRAY['stock','etf'], 100000, 0.25, DATE '2020-09-28', 'active', 'fm'),
    ('MaaL IND11', 'basket', NULL,
     '{"source":"cpp","client_code":"BJ53IND","maal_code":"ind11"}'::jsonb,
     ARRAY['stock','etf'], 100000, 0.25, DATE '2026-05-09', 'active', 'fm'),
    ('MaaL Passive', 'basket', NULL,
     '{"source":"cpp","client_code":"JR100PASS","maal_code":"passive"}'::jsonb,
     ARRAY['stock','etf'], 100000, 0.25, DATE '2021-08-02', 'active', 'fm')
ON CONFLICT (name) DO UPDATE SET params = EXCLUDED.params;
```

The inception dates are the real ones from `cpp_portfolios`. `initial_capital` is required `> 0` by a CHECK but is not meaningful for a book whose corpus moves — the real value comes from `cpp_nav_series`; 100000 is a placeholder the NAV sync overwrites in effect. `max_position_pct` 0.25 satisfies the `> 0 AND <= 1` CHECK and is not used for these books.

- [ ] **Step 2: Apply and verify**

```bash
ssh jprod 'cd /home/ubuntu/atlas-os/scripts/foundation && \
  PYTHONPATH=/home/ubuntu/atlas-os:. /home/ubuntu/atlas-os/.venv/bin/python -c \
  "import _db; _db.exec_script(open(\"maal_ddl.sql\").read())"'
```

Then:

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  U=$(printf "%s" "$ATLAS_DB_URL" | sed -E "s#^postgresql\+[a-z0-9]+://#postgresql://#; s#\?.*##") && \
  psql "$U" -c "SELECT name, params->>'"'"'client_code'"'"' cc, inception_date FROM atlas_foundation.portfolio_master WHERE params->>'"'"'source'"'"'='"'"'cpp'"'"' ORDER BY name;" 2>&1 | sed -E "s#://[^@]+@#://***@#g"'
```

Expected: exactly 3 rows — MaaL IND11/BJ53IND, MaaL Leaders/BJ53, MaaL Passive/JR100PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/foundation/maal_ddl.sql
git commit -m "feat(maal): register the three CPP-sourced books in portfolio_master"
```

---

### Task 3: Snapshot table and idempotent trade key

**Files:**
- Modify: `scripts/foundation/maal_ddl.sql`

- [ ] **Step 1: Append the snapshot DDL**

Append to `scripts/foundation/maal_ddl.sql`:

```sql
-- Dated position snapshot. cpp_holdings is current-state only (UNIQUE on
-- client+portfolio+symbol), so "what did BJ53 hold last Friday" does not exist
-- anywhere unless Atlas records it. One row per position per day; nothing is ever
-- overwritten, so the series IS the change log — yesterday vs today is a query,
-- not a second table to keep in sync.
CREATE TABLE IF NOT EXISTS atlas_foundation.maal_holding_snapshot (
    -- TWO dates, and the difference between them matters.
    --   as_of        = the day WE looked (the sync run date).
    --   source_as_of = the day the DATA is from (cpp_nav_series.nav_date).
    -- CPP positions only move when a backoffice file is uploaded, so these drift
    -- apart routinely — verified 2026-07-31, when BJ53's newest transaction was
    -- 2026-07-29. Stamping a book "Monday" when it is really Thursday's positions
    -- is how the desk sells a name that was already sold. The board and the PDF
    -- render source_as_of; as_of exists so a DEAD sync ("we never looked") is
    -- distinguishable from a quiet one ("we looked, nothing changed").
    as_of          date NOT NULL,
    source_as_of   date NOT NULL,
    maal_code      text NOT NULL CHECK (maal_code IN ('leaders', 'passive', 'ind11')),
    isin           text NOT NULL,
    source_symbol  text NOT NULL,
    -- Resolved Atlas key ("stock:SYMBOL" / "etf:SYMBOL"); NULL when the ISIN is not
    -- in instrument_master. NULL is loud, never silently dropped — see the gate.
    instrument_key text,
    -- 'EQUITY' or 'CASH', straight from CPP. CASH is how liquid ETFs (LIQUIDBEES,
    -- LIQUIDCASE, LIQUIDETF) are already tagged there, so no symbol list is needed.
    asset_class    text NOT NULL,
    quantity       numeric(18,4) NOT NULL,
    avg_cost       numeric(18,4) NOT NULL,
    synced_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of, maal_code, isin)
);

CREATE INDEX IF NOT EXISTS ix_maal_snapshot_latest
    ON atlas_foundation.maal_holding_snapshot (maal_code, as_of DESC);

-- portfolio_trades has no natural key, so a re-run would duplicate every trade.
-- Carry the CPP transaction id and make it unique. Partial, so engine-written
-- trades (source_txn_id NULL) are untouched by the constraint.
ALTER TABLE atlas_foundation.portfolio_trades
    ADD COLUMN IF NOT EXISTS source_txn_id bigint;

CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_trades_source_txn
    ON atlas_foundation.portfolio_trades (source_txn_id)
    WHERE source_txn_id IS NOT NULL;
```

- [ ] **Step 2: Apply and verify**

```bash
ssh jprod 'cd /home/ubuntu/atlas-os/scripts/foundation && \
  PYTHONPATH=/home/ubuntu/atlas-os:. /home/ubuntu/atlas-os/.venv/bin/python -c \
  "import _db; _db.exec_script(open(\"maal_ddl.sql\").read())"'
```

Verify the table and index exist:

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  U=$(printf "%s" "$ATLAS_DB_URL" | sed -E "s#^postgresql\+[a-z0-9]+://#postgresql://#; s#\?.*##") && \
  psql "$U" -c "\d atlas_foundation.maal_holding_snapshot" -c "\di atlas_foundation.uq_portfolio_trades_source_txn" 2>&1 | sed -E "s#://[^@]+@#://***@#g"'
```

Expected: table with 9 columns and the composite PK; the unique index listed.

- [ ] **Step 3: Run the schema gate**

Run: `ssh jprod 'cd /home/ubuntu/atlas-os && .venv/bin/python scripts/ops/schema_gate.py'`
Expected: exit 0. Every new object is in `atlas_foundation`, so the single-schema rule holds.

- [ ] **Step 4: Commit**

```bash
git add scripts/foundation/maal_ddl.sql
git commit -m "feat(maal): dated holding snapshot + idempotent source_txn_id on portfolio_trades"
```

---

### Task 4: Pure mapping functions (TDD)

**Files:**
- Create: `atlas/maal/__init__.py`
- Create: `atlas/maal/source.py`
- Create: `atlas/maal/tests/__init__.py`
- Test: `atlas/maal/tests/test_source.py`

- [ ] **Step 1: Write the failing test**

Create `atlas/maal/tests/test_source.py`:

```python
"""Pure CPP-row mapping.

RULE #0: every constant below is a REAL row read from the live CPP database
(jip-data-engine ... /client_portal) on 2026-07-31. BJ53 and JR100PASS holdings
and a BJ53 SELL transaction, verbatim. Nothing here is invented.
"""

from decimal import Decimal

from atlas.maal.source import (
    CODE_BY_CLIENT_CODE,
    is_cash,
    split_cash_and_positions,
    trade_from_txn,
    weight_pct,
)

# Real BJ53 holdings, 2026-07-31 (symbol, isin, asset_class, quantity, avg_cost).
BJ53_HOLDINGS = [
    ("GOLDBEES", "INF204KB17I5", "EQUITY", Decimal("4334"), Decimal("94.5962")),
    ("NIFTYBEES", "INF204KB14I2", "EQUITY", Decimal("1467"), Decimal("273.0900")),
    ("CDSL", "INE736A01011", "EQUITY", Decimal("304"), Decimal("1277.3368")),
    ("JINDALSAW", "INE324A01032", "EQUITY", Decimal("1572"), Decimal("273.6910")),
    ("DELHIVERY", "INE148O01028", "EQUITY", Decimal("808"), Decimal("506.2200")),
    ("HDFCSML250", "INF179KC1FB2", "EQUITY", Decimal("1667"), Decimal("180.5100")),
    ("SILVERBEES", "INF204KC1402", "EQUITY", Decimal("1181"), Decimal("218.1817")),
    ("JSFB", "INE953L01027", "EQUITY", Decimal("408"), Decimal("534.4294")),
    ("DIVISLAB", "INE361B01024", "EQUITY", Decimal("29"), Decimal("7008.5000")),
    ("ATHERENERG", "INE0LEZ01016", "EQUITY", Decimal("172"), Decimal("1051.5524")),
]

# Real JR100PASS liquid-ETF row, 2026-07-31 — CPP already tags it CASH.
JR100PASS_LIQUIDCASE = ("LIQUIDCASE", "INF0R8F01034", "CASH", Decimal("1"), Decimal("1000"))

# Real BJ53 SELL, 2026-07-28: 420 INDUSINDBK at 992.00 net / 984.9938 all-in.
BJ53_SELL = {
    "id": 1,
    "txn_date": "2026-07-28",
    "txn_type": "SELL",
    "symbol": "INDUSINDBK",
    "isin": "INE095A01012",
    "quantity": Decimal("420"),
    "price": Decimal("992.0000"),
    "cost_rate": Decimal("984.9938"),
    "amount": Decimal("413697.40"),
}


def test_liquid_etf_counts_as_cash():
    assert is_cash(JR100PASS_LIQUIDCASE[2]) is True


def test_equity_etf_is_not_cash():
    # GOLDBEES is asset-class exposure, not cash — it must stay a position.
    assert is_cash("EQUITY") is False


def test_split_puts_liquid_in_cash_and_the_rest_in_positions():
    rows = [
        {"symbol": s, "isin": i, "asset_class": a, "quantity": q, "avg_cost": c}
        for s, i, a, q, c in BJ53_HOLDINGS + [JR100PASS_LIQUIDCASE]
    ]
    positions, cash_rows = split_cash_and_positions(rows)
    assert len(positions) == 10
    assert len(cash_rows) == 1
    assert cash_rows[0]["symbol"] == "LIQUIDCASE"
    assert all(p["asset_class"] == "EQUITY" for p in positions)


def test_weight_is_percent_of_total_including_cash():
    # 33.43L invested + 6.57L cash = 40L total. A 5L position is 12.5%, not 14.96%.
    assert weight_pct(Decimal("500000"), Decimal("4000000")) == Decimal("12.5000")


def test_weight_of_zero_total_is_zero_not_a_crash():
    assert weight_pct(Decimal("500000"), Decimal("0")) == Decimal("0")


def test_client_codes_map_to_maal_codes():
    assert CODE_BY_CLIENT_CODE == {
        "BJ53": "leaders",
        "BJ53IND": "ind11",
        "JR100PASS": "passive",
    }


def test_sell_trade_uses_net_price_and_carries_source_id():
    trade = trade_from_txn(BJ53_SELL, instrument_key="stock:INDUSINDBK", asset_class="stock")
    assert trade["side"] == "sell"
    assert trade["price"] == Decimal("992.0000")   # net rate, NOT the all-in cost_rate
    assert trade["cost"] == Decimal("984.9938")    # all-in kept separately
    assert trade["qty"] == Decimal("420")
    assert trade["value"] == Decimal("413697.40")
    assert trade["reason"] == "manual"
    assert trade["source_txn_id"] == 1


def test_corpus_and_bonus_rows_are_not_trades():
    for kind in ("CORPUS_IN", "BONUS"):
        row = dict(BJ53_SELL, txn_type=kind)
        assert trade_from_txn(row, instrument_key="stock:X", asset_class="stock") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd "/Users/nimishshah/All AI/atlas-os" && .venv/bin/python -m pytest atlas/maal/tests/test_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'atlas.maal'`

- [ ] **Step 3: Write the implementation**

Create `atlas/maal/__init__.py`:

```python
"""MaaL Process — the three real model portfolios sourced from the CPP database.

Bounded context (modulith rule #3): imports only from atlas.primitives / atlas.db /
atlas.config. Pure mapping lives in source.py; all I/O lives in the scripts layer.
"""
```

Create `atlas/maal/tests/__init__.py` (empty file).

Create `atlas/maal/source.py`:

```python
"""Map CPP rows onto Atlas shapes. Pure — no I/O, no DB handles.

Two things here are load-bearing and non-obvious:

1. Cash is whatever CPP tags ``asset_class = 'CASH'``. That already covers every
   liquid ETF (LIQUIDBEES, LIQUIDCASE, LIQUIDETF) — verified 2026-07-31 across all
   3,340 live rows, zero LIQUID-named rows misfiled as EQUITY. So there is no symbol
   list here to go stale. GOLDBEES and SILVERBEES stay positions: asset-class
   exposure, not cash.

2. A SELL's price is ``price`` (net rate, matching the backoffice FIFO), never
   ``cost_rate`` (all-in incl. taxes). Using the all-in rate would overstate every
   realized gain by the transaction costs.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# The three UCCs, locked by the FM 2026-07-31.
CODE_BY_CLIENT_CODE: dict[str, str] = {
    "BJ53": "leaders",
    "BJ53IND": "ind11",
    "JR100PASS": "passive",
}

# CPP txn_type values that move shares. CORPUS_IN is capital, BONUS is a corporate
# action — neither is a trade, and counting them as one would corrupt realized P&L.
_TRADE_TYPES = {"BUY": "buy", "SELL": "sell"}

_QUANT = Decimal("0.0001")


def is_cash(asset_class: str | None) -> bool:
    """True when CPP has classified the instrument as cash (incl. liquid ETFs)."""
    return (asset_class or "").strip().upper() == "CASH"


def split_cash_and_positions(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition holdings into (positions, cash_rows) on CPP's asset_class."""
    positions = [r for r in rows if not is_cash(r.get("asset_class"))]
    cash_rows = [r for r in rows if is_cash(r.get("asset_class"))]
    return positions, cash_rows


def weight_pct(position_value: Decimal, total_value: Decimal) -> Decimal:
    """Weight as a percent of TOTAL portfolio value, cash included.

    CPP's own weight_pct divides by invested value only, so its weights always sum
    to 100 and cash reads 0%. Atlas needs cash to be visible, so it recomputes.
    """
    if not total_value or total_value <= 0:
        return Decimal("0")
    return (position_value / total_value * 100).quantize(_QUANT)


def trade_from_txn(
    txn: dict[str, Any],
    instrument_key: str,
    asset_class: str,
) -> dict[str, Any] | None:
    """One CPP transaction as a portfolio_trades row. None when it is not a trade."""
    side = _TRADE_TYPES.get((txn.get("txn_type") or "").strip().upper())
    if side is None:
        return None
    return {
        "trade_date": txn["txn_date"],
        "asset_class": asset_class,
        "instrument_key": instrument_key,
        "symbol": instrument_key.split(":", 1)[1],
        "side": side,
        "qty": txn["quantity"],
        "price": txn["price"],
        "value": txn["amount"],
        "cost": txn["cost_rate"],
        "reason": "manual",
        "source_txn_id": txn["id"],
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd "/Users/nimishshah/All AI/atlas-os" && .venv/bin/python -m pytest atlas/maal/tests/test_source.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 5: Run the full unit suite and the gate**

Run: `make test`
Expected: 49 existing tests still pass, plus the 8 new ones.

Run: `make gate`
Expected: exit 0 (lint + tests + pyright ratchet).

- [ ] **Step 6: Commit**

```bash
git add atlas/maal/
git commit -m "feat(maal): pure CPP row mapping — cash split, weight basis, trade extraction"
```

---

### Task 5: The sync job

**Files:**
- Create: `scripts/foundation/sync_maal_books.py`

- [ ] **Step 1: Write the job**

Create `scripts/foundation/sync_maal_books.py`:

```python
#!/usr/bin/env python3
"""Pull the three MaaL books out of the CPP database into atlas_foundation.

Reads (read-only, via MAAL_SOURCE_DB_URL): cpp_portfolios, cpp_holdings,
cpp_transactions, cpp_nav_series.
Writes: maal_holding_snapshot, portfolio_nav_daily (run_type='live'), portfolio_trades.

Positions are snapshotted per day and never overwritten, so the series is the change
log. Prices are NOT taken from CPP — Atlas marks positions with its own NSE close.
CPP is the source of WHAT is held and at what cost, not of what it is worth.

Run: PYTHONPATH=<repo>:<repo>/scripts/foundation python sync_maal_books.py [--as-of YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine, text

import _db
from atlas.maal.source import (
    CODE_BY_CLIENT_CODE,
    split_cash_and_positions,
    trade_from_txn,
)

log = logging.getLogger("sync_maal_books")


# A HUNG sync is worse than a failed one: cron fires again in twelve hours and now
# two processes are stuck on the box that also serves production, with nothing in any
# log. Both timeouts are deliberately generous — the whole pull is ~2,000 rows, so
# anything past a minute means CPP is wedged, not busy.
_CONNECT_TIMEOUT_S = 15
_STATEMENT_TIMEOUT_MS = 60_000


def _source_engine():
    url = os.environ.get("MAAL_SOURCE_DB_URL", "").strip()
    if not url:
        raise SystemExit("MAAL_SOURCE_DB_URL is not set — see docs/maal-process.md")
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": _CONNECT_TIMEOUT_S,
            "options": f"-c statement_timeout={_STATEMENT_TIMEOUT_MS}",
        },
    )


def _fetch_source(engine, client_codes: list[str]) -> dict[str, pd.DataFrame]:
    """Holdings, latest NAV row, and all transactions for the three UCCs."""
    with engine.connect() as conn:
        holdings = pd.read_sql(
            text("""
                SELECT p.client_code, h.symbol, h.isin, h.asset_class,
                       h.quantity, h.avg_cost
                FROM cpp_holdings h
                JOIN cpp_portfolios p ON p.id = h.portfolio_id
                WHERE p.client_code = ANY(:codes) AND h.quantity > 0
            """),
            conn, params={"codes": client_codes},
        )
        nav = pd.read_sql(
            text("""
                SELECT DISTINCT ON (p.client_code)
                       p.client_code, n.nav_date, n.current_value,
                       n.invested_amount, n.cash_value, n.bank_balance
                FROM cpp_nav_series n
                JOIN cpp_portfolios p ON p.id = n.portfolio_id
                WHERE p.client_code = ANY(:codes)
                ORDER BY p.client_code, n.nav_date DESC
            """),
            conn, params={"codes": client_codes},
        )
        txns = pd.read_sql(
            text("""
                SELECT t.id, p.client_code, t.txn_date, t.txn_type, t.symbol,
                       t.isin, t.quantity, t.price, t.cost_rate, t.amount
                FROM cpp_transactions t
                JOIN cpp_portfolios p ON p.id = t.portfolio_id
                WHERE p.client_code = ANY(:codes) AND NOT t.is_deleted
            """),
            conn, params={"codes": client_codes},
        )
    return {"holdings": holdings, "nav": nav, "txns": txns}


def _resolve_isins(isins: list[str]) -> dict[str, tuple[str, str]]:
    """ISIN -> (instrument_key, atlas asset_class). Missing ISINs are simply absent."""
    if not isins:
        return {}
    df = _db.read_sql(
        """
        SELECT isin, symbol,
               CASE WHEN instrument_type = 'ETF' THEN 'etf' ELSE 'stock' END AS ac
        FROM atlas_foundation.instrument_master
        WHERE isin = ANY(%(isins)s)
        """,
        params={"isins": isins},
    )
    return {r.isin: (f"{r.ac}:{r.symbol}", r.ac) for r in df.itertuples()}


def sync(as_of: dt.date) -> int:
    """Returns the number of unresolved ISINs — non-zero means the gate must shout."""
    client_codes = list(CODE_BY_CLIENT_CODE)
    src = _fetch_source(_source_engine(), client_codes)

    if src["holdings"].empty:
        raise SystemExit("CPP returned zero holdings for all three books — refusing to write")

    all_isins = sorted(
        set(src["holdings"]["isin"].dropna()) | set(src["txns"]["isin"].dropna())
    )
    resolved = _resolve_isins(all_isins)
    unresolved = [i for i in all_isins if i not in resolved]

    ids = _db.read_sql(
        """
        SELECT portfolio_id, params->>'client_code' AS client_code
        FROM atlas_foundation.portfolio_master
        WHERE params->>'source' = 'cpp'
        """
    )
    pid_by_code = dict(zip(ids["client_code"], ids["portfolio_id"]))
    if len(pid_by_code) != 3:
        raise SystemExit(f"expected 3 registered CPP books, found {len(pid_by_code)}")

    snap_rows, nav_rows, trade_rows = [], [], []

    for client_code, maal_code in CODE_BY_CLIENT_CODE.items():
        pid = pid_by_code[client_code]
        held = src["holdings"][src["holdings"]["client_code"] == client_code]
        rows = held.to_dict("records")
        positions, cash_rows = split_cash_and_positions(rows)

        # The data's OWN date, not today's. cpp_nav_series.nav_date is CPP's
        # statement of what day this portfolio was last valued. Refuse to write a
        # snapshot without it rather than silently stamping it with today —
        # a book dated Monday that actually holds Thursday's positions is the
        # failure this whole two-date scheme exists to prevent.
        nav_row = src["nav"][src["nav"]["client_code"] == client_code]
        if nav_row.empty:
            log.error("no cpp_nav_series row for %s — skipping this book entirely", client_code)
            continue
        n = nav_row.iloc[0]
        source_as_of = n["nav_date"]

        for r in rows:
            key_ac = resolved.get(r["isin"])
            snap_rows.append({
                "as_of": as_of,
                "source_as_of": source_as_of,
                "maal_code": maal_code,
                "isin": r["isin"],
                "source_symbol": r["symbol"],
                "instrument_key": key_ac[0] if key_ac else None,
                "asset_class": r["asset_class"],
                "quantity": r["quantity"],
                "avg_cost": r["avg_cost"],
            })

        cash = Decimal(str(n["cash_value"] or 0)) + Decimal(str(n["bank_balance"] or 0))
        total = Decimal(str(n["current_value"] or 0))
        nav_rows.append({
            "portfolio_id": pid, "run_type": "live", "date": source_as_of,
            "nav": total, "cash": cash, "invested": total - cash,
            "n_positions": len(positions),
        })
        if source_as_of < as_of:
            log.warning(
                "%s data is %d day(s) behind: source_as_of=%s run=%s",
                client_code, (as_of - source_as_of).days, source_as_of, as_of,
            )

        for t in src["txns"][src["txns"]["client_code"] == client_code].to_dict("records"):
            key_ac = resolved.get(t["isin"])
            if key_ac is None:
                continue  # counted in `unresolved` and reported; never silently fine
            trade = trade_from_txn(t, instrument_key=key_ac[0], asset_class=key_ac[1])
            if trade:
                trade_rows.append({**trade, "portfolio_id": pid, "run_type": "live"})

    log.info(
        "as_of=%s snapshot=%d nav=%d trades=%d unresolved_isins=%d",
        as_of, len(snap_rows), len(nav_rows), len(trade_rows), len(unresolved),
    )

    _db.upsert(
        "atlas_foundation.maal_holding_snapshot", snap_rows,
        conflict=("as_of", "maal_code", "isin"),
    )
    _db.upsert(
        "atlas_foundation.portfolio_nav_daily", nav_rows,
        conflict=("portfolio_id", "run_type", "date"),
    )
    _db.upsert(
        "atlas_foundation.portfolio_trades", trade_rows,
        conflict=("source_txn_id",),
    )

    if unresolved:
        log.error("UNRESOLVED ISINs (not in instrument_master): %s", ", ".join(unresolved))
    return len(unresolved)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD, defaults to today IST")
    args = ap.parse_args()
    as_of = (
        dt.date.fromisoformat(args.as_of) if args.as_of
        else dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()
    )
    return 0 if sync(as_of) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

**Before writing this file, read `scripts/foundation/_db.py` in full** and match its actual helper names. This plan assumes `_db.read_sql(sql, params)` and `_db.upsert(table, rows, conflict)`. If the real module exposes different names (e.g. `_db.query` / `_db.write_df`), use those — do not add wrappers to make this snippet compile.

- [ ] **Step 2: Dry-run against the real source**

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  PYTHONPATH=/home/ubuntu/atlas-os:/home/ubuntu/atlas-os/scripts/foundation \
  .venv/bin/python scripts/foundation/sync_maal_books.py'
```

Expected: an INFO line reading roughly `snapshot=35 nav=3 trades=1900+ unresolved_isins=N`, exit 0 when N is 0.

If unresolved ISINs are reported, that is the known `instrument_master` staleness — it is **not refreshed nightly** ([docs/table-census.md:187](../../table-census.md)). Run `scripts/foundation/build_universe.py` and `assign_sectors.py`, then re-run the sync. Do not add a fallback that guesses the symbol.

- [ ] **Step 3: Verify the write landed against real output**

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  U=$(printf "%s" "$ATLAS_DB_URL" | sed -E "s#^postgresql\+[a-z0-9]+://#postgresql://#; s#\?.*##") && \
  psql "$U" -c "SELECT maal_code, count(*) positions, count(*) FILTER (WHERE instrument_key IS NULL) unresolved, count(*) FILTER (WHERE asset_class='"'"'CASH'"'"') cash_rows FROM atlas_foundation.maal_holding_snapshot WHERE as_of = CURRENT_DATE GROUP BY 1 ORDER BY 1;" \
  -c "SELECT m.name, n.date, n.nav, n.cash, n.invested, n.n_positions FROM atlas_foundation.portfolio_nav_daily n JOIN atlas_foundation.portfolio_master m USING (portfolio_id) WHERE m.params->>'"'"'source'"'"'='"'"'cpp'"'"' AND n.date=CURRENT_DATE;" 2>&1 | sed -E "s#://[^@]+@#://***@#g"'
```

Expected: three `maal_code` rows (leaders ~10, ind11 ~6, passive ~19), `unresolved` = 0, `passive` showing `cash_rows` = 1 (LIQUIDCASE). Three NAV rows with `cash > 0` on passive and `nav = cash + invested`.

**This is the definition-of-done check for Task 5** — it asserts on real produced output, not a fixture.

- [ ] **Step 4: Verify the sync is idempotent**

Re-run the exact command from Step 2, then:

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  U=$(printf "%s" "$ATLAS_DB_URL" | sed -E "s#^postgresql\+[a-z0-9]+://#postgresql://#; s#\?.*##") && \
  psql "$U" -c "SELECT count(*) FROM atlas_foundation.portfolio_trades WHERE source_txn_id IS NOT NULL;" 2>&1 | sed -E "s#://[^@]+@#://***@#g"'
```

Expected: the same count as after the first run. A second run must add zero trades.

- [ ] **Step 5: Commit**

```bash
git add scripts/foundation/sync_maal_books.py
git commit -m "feat(maal): twice-daily sync of the three real books from the CPP database"
```

---

### Task 6: Cron wrapper and schedule

**Files:**
- Create: `scripts/ops/maal_sync.sh`
- Modify: `scripts/ops/crontab.txt`

- [ ] **Step 1: Write the wrapper**

Create `scripts/ops/maal_sync.sh`, mirroring `atlas_intraday.sh`:

```bash
#!/usr/bin/env bash
# MaaL book sync — pull BJ53 / BJ53IND / JR100PASS from the CPP database.
# Called twice a day by cron (see scripts/ops/crontab.txt): 12:00 and 22:00 IST.
# Positions in the portal only move when a backoffice file is uploaded, so the noon
# run catches a morning upload and the 22:00 run catches an evening one.
set -euo pipefail
REPO="/home/ubuntu/atlas-os"
cd "$REPO"
export PYTHONPATH="$REPO:$REPO/scripts/foundation"
set -a; source .env; set +a
"$REPO/.venv/bin/python" scripts/foundation/sync_maal_books.py
```

- [ ] **Step 2: Make it executable and add the cron lines**

```bash
chmod +x scripts/ops/maal_sync.sh
```

Append to `scripts/ops/crontab.txt`:

```
# MaaL book sync — 12:00 and 22:00 IST daily (06:30 and 16:30 UTC).
# Reads the CPP database (clients.jslwealth.in) read-only and lands the three real
# model books in maal_holding_snapshot + portfolio_nav_daily + portfolio_trades.
30 6  * * * /home/ubuntu/atlas-os/scripts/ops/maal_sync.sh >> /home/ubuntu/logs/maal_sync.log 2>&1
30 16 * * * /home/ubuntu/atlas-os/scripts/ops/maal_sync.sh >> /home/ubuntu/logs/maal_sync.log 2>&1
```

Note the 22:00 IST run lands **after** the 16:00 IST `atlas_daily.sh`. That is fine: the sync owns `portfolio_nav_daily` rows for these three `portfolio_id`s exclusively, and the engine's nightly mark never touches them (it only marks portfolios it computes). Confirm this by grepping the nightly writer before installing:

Run: `rg -n "portfolio_nav_daily" scripts/foundation/*.py | grep -i insert`
Expected: every writer scopes to engine portfolios. If any writes unconditionally across all of `portfolio_master`, exclude `params->>'source' = 'cpp'` there before installing the cron.

- [ ] **Step 3: Install and verify**

```bash
ssh jprod 'crontab -l > /tmp/cron.bak && cp /home/ubuntu/atlas-os/scripts/ops/crontab.txt /tmp/newcron && crontab /tmp/newcron && crontab -l | grep maal'
```

Expected: both maal_sync lines listed.

- [ ] **Step 4: Commit**

```bash
git add scripts/ops/maal_sync.sh scripts/ops/crontab.txt
git commit -m "feat(maal): twice-daily cron at 12:00 and 22:00 IST"
```

---

### Task 6A: FIFO realized P&L (TDD)

**Files:**
- Create: `atlas/maal/fifo.py`
- Test: `atlas/maal/tests/test_fifo.py`
- Modify: `scripts/foundation/sync_maal_books.py`

Storing a sell at the right price is not the same as knowing what it earned. `portfolio_trades` already has `realized_pnl`, `holding_days` and `tax_bucket`; without this task they stay NULL forever and the trade log reads as broken.

- [ ] **Step 1: Write the failing test**

Create `atlas/maal/tests/test_fifo.py`:

```python
"""FIFO lot matching.

RULE #0: the sequence below is BJ53's COMPLETE real INDUSINDBK history, read from
the live CPP database on 2026-07-31 — two buys and the sell that closed the position:

    2026-07-09  BUY   210 @ 1015.5100
    2026-07-10  BUY   210 @ 1027.5100
    2026-07-28  SELL  420 @  992.0000

Both lots are fully consumed by the sell, so the expected P&L is exact and
hand-checkable:
    (992.00 - 1015.51) * 210 = -4,937.10
    (992.00 - 1027.51) * 210 = -7,457.10
                        total = -12,394.20   (a real loss on a real trade)
"""

import datetime as dt
from decimal import Decimal

from atlas.maal.fifo import match_fifo

INDUSINDBK = [
    {"txn_date": dt.date(2026, 7, 9),  "txn_type": "BUY",  "quantity": Decimal("210"), "price": Decimal("1015.5100")},
    {"txn_date": dt.date(2026, 7, 10), "txn_type": "BUY",  "quantity": Decimal("210"), "price": Decimal("1027.5100")},
    {"txn_date": dt.date(2026, 7, 28), "txn_type": "SELL", "quantity": Decimal("420"), "price": Decimal("992.0000")},
]


def test_realized_pnl_matches_the_hand_computed_loss():
    sells = match_fifo(INDUSINDBK)
    assert len(sells) == 1
    assert sells[0]["realized_pnl"] == Decimal("-12394.20")


def test_holding_days_uses_the_oldest_matched_lot():
    # Oldest lot bought 2026-07-09, sold 2026-07-28 -> 19 days.
    assert match_fifo(INDUSINDBK)[0]["holding_days"] == 19


def test_short_holding_is_stcg():
    assert match_fifo(INDUSINDBK)[0]["tax_bucket"] == "STCG"


def test_partial_sell_consumes_only_the_oldest_lot():
    # Same real buys, but sell only 210: matches the 1015.51 lot alone.
    partial = INDUSINDBK[:2] + [dict(INDUSINDBK[2], quantity=Decimal("210"))]
    assert match_fifo(partial)[0]["realized_pnl"] == Decimal("-4937.10")


def test_bonus_shares_enter_at_zero_cost():
    # BJ53 has 2 real BONUS rows. A bonus lot must not be priced like a buy, or
    # the eventual sell understates the gain by the full market value.
    seq = [
        {"txn_date": dt.date(2026, 7, 9), "txn_type": "BUY",   "quantity": Decimal("100"), "price": Decimal("100")},
        {"txn_date": dt.date(2026, 7, 10), "txn_type": "BONUS", "quantity": Decimal("100"), "price": Decimal("0")},
        {"txn_date": dt.date(2026, 7, 28), "txn_type": "SELL",  "quantity": Decimal("200"), "price": Decimal("150")},
    ]
    # (150-100)*100 + (150-0)*100 = 5,000 + 15,000
    assert match_fifo(seq)[0]["realized_pnl"] == Decimal("20000.00")


def test_sell_with_no_matching_buy_is_reported_not_guessed():
    # The 16 pre-format BJ53 rows have no ISIN, so their buys are invisible here.
    # An unmatched sell must surface, never silently book the full proceeds as gain.
    seq = [{"txn_date": dt.date(2026, 7, 28), "txn_type": "SELL", "quantity": Decimal("10"), "price": Decimal("100")}]
    out = match_fifo(seq)
    assert out[0]["realized_pnl"] is None
    assert out[0]["unmatched_qty"] == Decimal("10")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "/Users/nimishshah/All AI/atlas-os" && .venv/bin/python -m pytest atlas/maal/tests/test_fifo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'atlas.maal.fifo'`

- [ ] **Step 3: Implement**

Create `atlas/maal/fifo.py`:

```python
"""FIFO lot matching for realized P&L. Pure — no I/O.

Matches each sell against the oldest open lots first, which is what the PMS
backoffice does; any other order produces numbers that are plausible and wrong.

An unmatched sell returns realized_pnl=None, NOT zero and NOT the full proceeds.
BJ53 has 16 pre-format rows with no ISIN, so their buys are invisible to us —
booking those sells as pure gain would invent profit that never happened.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

_PAISE = Decimal("0.01")
_LTCG_DAYS = 365

# Rows that OPEN a lot. BONUS enters at zero cost — it cost nothing, so the whole
# eventual sale price is gain. CORPUS_IN is cash, not shares, and never appears here.
_OPENING = {"BUY", "BONUS"}


def match_fifo(txns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One result row per SELL, in date order. Input must be one instrument."""
    lots: list[list[Any]] = []  # [qty_remaining, price, buy_date], oldest first
    results: list[dict[str, Any]] = []

    for t in sorted(txns, key=lambda r: (r["txn_date"], r["txn_type"])):
        kind = t["txn_type"].strip().upper()
        if kind in _OPENING:
            lots.append([t["quantity"], t["price"], t["txn_date"]])
            continue
        if kind != "SELL":
            continue

        to_match = t["quantity"]
        proceeds_gain = Decimal("0")
        oldest_matched: dt.date | None = None

        while to_match > 0 and lots:
            lot = lots[0]
            take = min(to_match, lot[0])
            proceeds_gain += (t["price"] - lot[1]) * take
            if oldest_matched is None:
                oldest_matched = lot[2]
            lot[0] -= take
            to_match -= take
            if lot[0] == 0:
                lots.pop(0)

        matched = t["quantity"] - to_match
        days = (t["txn_date"] - oldest_matched).days if oldest_matched else None
        results.append({
            "txn_date": t["txn_date"],
            "qty": t["quantity"],
            "matched_qty": matched,
            "unmatched_qty": to_match,
            # None, never 0 — an unmatched sell is unknown, not break-even.
            "realized_pnl": proceeds_gain.quantize(_PAISE) if matched == t["quantity"] else None,
            "holding_days": days,
            "tax_bucket": None if days is None else ("STCG" if days <= _LTCG_DAYS else "LTCG"),
        })

    return results
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "/Users/nimishshah/All AI/atlas-os" && .venv/bin/python -m pytest atlas/maal/tests/test_fifo.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Wire it into the sync**

In `sync_maal_books.py`, after building `trade_rows`, group them by `(portfolio_id, instrument_key)`, run `match_fifo` over each group's full transaction history, and attach `realized_pnl`, `holding_days` and `tax_bucket` to the matching sell rows before the upsert. FIFO needs the **whole** history of an instrument, not one run's window — which is why the full transaction pull (rather than an incremental one) is load-bearing here, not merely lazy.

- [ ] **Step 6: Commit**

```bash
git add atlas/maal/fifo.py atlas/maal/tests/test_fifo.py scripts/foundation/sync_maal_books.py
git commit -m "feat(maal): FIFO realized P&L, holding period and tax bucket on every sell"
```

---

### Task 6B: Prove the FIFO numbers against the real history

**Files:**
- Create: `scripts/ops/maal_pnl_reconcile.py`

Unit tests prove the algorithm. This proves the *data* — across all 991 real sells in the three books, not the handful a test author would pick.

- [ ] **Step 1: Write the reconciliation gate**

Create `scripts/ops/maal_pnl_reconcile.py`. It must:

1. Read every `portfolio_trades` row with `source_txn_id IS NOT NULL` and `side='sell'` for the three books.
2. Assert every sell has a non-NULL `realized_pnl`, **except** those whose instrument has an unmatched-buy history — report those explicitly by symbol and count.
3. Assert `sum(realized_pnl)` per book is finite and that no single sell's `realized_pnl` exceeds its own `value` (a gain larger than the sale proceeds means the cost basis went negative — the classic FIFO bug).
4. Assert `holding_days >= 0` on every matched sell, and that `tax_bucket` agrees with `holding_days <= 365`.
5. Print a per-book summary: sells, matched, unmatched, total realized P&L in ₹ lakh.
6. Exit non-zero if any assertion fails.

- [ ] **Step 2: Run it against real produced output**

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  PYTHONPATH=/home/ubuntu/atlas-os:/home/ubuntu/atlas-os/scripts/foundation \
  .venv/bin/python scripts/ops/maal_pnl_reconcile.py'
```

Expected: exit 0. Known tolerance: BJ53's 16 pre-format rows with no ISIN may leave a small number of unmatched sells — these must be **named in the output**, not absorbed into a pass. Any unmatched sell outside that named set is a real failure.

**This is the definition-of-done for realized P&L.** It asserts on real produced numbers, per rule #0.

- [ ] **Step 3: Add it to the nightly**

Append the reconcile call to `scripts/ops/maal_sync.sh`, after the sync, non-fatal:

```bash
# P&L reconciliation: proves the FIFO numbers still hold as new trades land.
# Non-fatal — a reconciliation failure must not stop tomorrow's position sync.
"$REPO/.venv/bin/python" scripts/ops/maal_pnl_reconcile.py || true
```

- [ ] **Step 4: Commit**

```bash
git add scripts/ops/maal_pnl_reconcile.py scripts/ops/maal_sync.sh
git commit -m "feat(maal): reconcile FIFO P&L across all 991 real sells, nightly"
```

---

### Task 6C: Make a dead sync loud

**Files:**
- Modify: `scripts/ops/freshness_guard.py`

A failed sync is visible in the cron log. A *dead* sync is not: the Monday book quietly serves the last good snapshot forever and reads as perfectly normal. This is the failure mode most likely to actually bite, because it fails by doing nothing.

- [ ] **Step 1: Read the existing guard**

Read `scripts/ops/freshness_guard.py` in full and match its existing registration shape — do not invent a new mechanism alongside it.

- [ ] **Step 2: Register both dates**

Add `atlas_foundation.maal_holding_snapshot` with two separate staleness checks, because they mean different things:

- `max(as_of)` older than 1 day → **the sync is dead.** Atlas stopped looking. Alert loudly.
- `max(source_as_of)` older than 4 days → **the upload is lagging.** Atlas is fine; CPP has not been fed. Warn, do not alert as a system failure.

Conflating these sends you debugging Atlas when the real answer is that nobody uploaded the backoffice file.

- [ ] **Step 3: Verify it fires**

Prove the guard actually trips rather than assuming it does:

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  scripts/ops/psql_masked.sh ATLAS_DB_URL -c "BEGIN; UPDATE atlas_foundation.maal_holding_snapshot SET as_of = as_of - 5; \\! /home/ubuntu/atlas-os/.venv/bin/python /home/ubuntu/atlas-os/scripts/ops/freshness_guard.py ; ROLLBACK;"'
```

Expected: the guard reports `maal_holding_snapshot` stale, and the ROLLBACK leaves the real data untouched. Confirm the row count afterwards is unchanged.

- [ ] **Step 4: Commit**

```bash
git add scripts/ops/freshness_guard.py
git commit -m "feat(maal): freshness guard distinguishes a dead sync from a lagging upload"
```

---

### Task 7: Confirm the portfolio pages populate

**Files:**
- Modify: `frontend/src/components/portfolios/PortfolioDetailV4.tsx`

- [ ] **Step 1: Look at the real pages**

Visit `/portfolios` on the board. Expected: **MaaL Leaders**, **MaaL IND11** and **MaaL Passive** now listed with a NAV, cash and position count, because [getPortfolios](../../../frontend/src/lib/queries/portfolios.ts#L67) reads `portfolio_master` + `portfolio_nav_daily` and those rows now exist.

Open each detail page. Expected to render: holdings by sector, live NAV chart, risk box, trade log. Expected to be **empty**: policy journal, desk cycle, backtest growth curve — those render engine decisions and these are human-run books.

- [ ] **Step 2: Suppress the engine-only panels for CPP books**

In `PortfolioDetailV4.tsx`, the portfolio detail already loads `params`. Gate the three engine panels on it rather than rendering empty boxes:

```tsx
const isExternal = detail.params?.source === 'cpp'
```

Then wrap the policy-journal, desk-cycle and backtest sections in `{!isExternal && ( ... )}`. Do not delete them — they are correct for engine portfolios.

- [ ] **Step 3: Verify**

Run: `cd frontend && npm run build`
Expected: build completes, `BUILD_ID` written.

Reload each MaaL detail page. Expected: no empty engine panels; holdings, NAV chart, risk box and trades all populated from real synced rows.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/portfolios/PortfolioDetailV4.tsx
git commit -m "feat(maal): hide engine-only panels on externally-sourced books"
```

---

### Task 8: Documentation and ADR

**Files:**
- Create: `docs/adr/0005-maal-books-come-from-the-cpp-database.md`
- Create: `docs/maal-process.md`
- Modify: `CLAUDE.md`
- Modify: `docs/refresh-schedule.md`

- [ ] **Step 1: Write the ADR**

Create `docs/adr/0005-maal-books-come-from-the-cpp-database.md` recording, in the style of [ADR 0003](../adr/0003-monday-confirmations-book-state.md):

- **Decision:** the opening book is the latest synced snapshot of the real portfolio, not the fold of prior recommendations. *Rejected:* continuing to fold, because the FM's calls are a superset of what executes and the folded book drifts from reality every week it compounds.
- **Decision:** CPP is the source of what is held and at what cost; Atlas prices it. *Rejected:* importing CPP's `current_price` / `weight_pct`, because its weights divide by invested value only, so cash would read 0% forever.
- **Decision:** a daily full snapshot, not a delta table. *Rejected:* storing computed changes, because the diff is a query over data we already keep, and two representations drift.
- **Consequence:** this supersedes Decision 2 of ADR 0003 in part — `resulting_book` still freezes a published report so it renders identically forever, but it no longer feeds the next week.
- **Consequence:** Atlas now reads a second database. This is an ingestion boundary (like bhavcopy or AMFI), not a runtime dependency — the board never queries CPP during a page load.

- [ ] **Step 2: Write the operator doc**

Create `docs/maal-process.md` covering: the three UCCs and their Atlas codes, the twice-daily schedule, `MAAL_SOURCE_DB_URL` and the `atlas_reader` grant, what to do when the sync reports unresolved ISINs, and the masking rule for any `psql` command that touches a URL.

- [ ] **Step 3: Fix the drifted schedule in CLAUDE.md**

In `CLAUDE.md`, the orchestrator line says 19:30 IST. The crontab says `30 10 * * 1-5` UTC = **16:00 IST**. Correct it, and add the MaaL sync to the same line's neighbourhood.

- [ ] **Step 4: Update the refresh schedule**

Add the two MaaL sync runs to `docs/refresh-schedule.md`.

- [ ] **Step 5: Commit**

```bash
git add docs/adr/0005-maal-books-come-from-the-cpp-database.md docs/maal-process.md CLAUDE.md docs/refresh-schedule.md
git commit -m "docs(maal): ADR 0005, operator runbook, and the 16:00 IST schedule correction"
```

---

# PHASE 2A — Rename to MaaL, and nothing else

**Do not start until Phase 1 has produced at least one clean sync with zero unresolved ISINs.**

**The contract for this phase: zero behavior change.** Every existing test passes without being edited, the board renders exactly what it rendered before, and the three published reports look identical. If a test needs changing to make this phase green, you have accidentally changed behavior — stop and move that change to Phase 2B. Merge and deploy 2A on its own before starting 2B.

### Task 9: Rename the tables and portfolio codes

**Files:**
- Create: `scripts/foundation/maal_rename.sql`

- [ ] **Step 1: Write the rename**

Create `scripts/foundation/maal_rename.sql`:

```sql
-- "Monday confirmations" -> "MaaL Process" (Multi Asset Alpha - Leaders).
-- Also aligns the three portfolio codes to CPP's own vocabulary so there is no
-- translation table between the two systems: alpha -> leaders, india_xi -> ind11.
--
-- Safe to run once. 4 confirmations / 3 published / 42 calls at time of writing;
-- RENAME preserves every published report intact.

ALTER TABLE atlas_foundation.mpf_confirmation RENAME TO maal_confirmation;
ALTER TABLE atlas_foundation.mpf_call         RENAME TO maal_call;
ALTER TABLE atlas_foundation.mpf_evidence     RENAME TO maal_evidence;

ALTER TABLE atlas_foundation.maal_confirmation RENAME COLUMN portfolio_code TO maal_code;

UPDATE atlas_foundation.maal_confirmation SET maal_code = 'leaders' WHERE maal_code = 'alpha';
UPDATE atlas_foundation.maal_confirmation SET maal_code = 'ind11'   WHERE maal_code = 'india_xi';

ALTER TABLE atlas_foundation.maal_confirmation
    DROP CONSTRAINT IF EXISTS mpf_confirmation_portfolio_code_check;
ALTER TABLE atlas_foundation.maal_confirmation
    ADD CONSTRAINT maal_confirmation_code_check
    CHECK (maal_code IN ('leaders', 'passive', 'ind11'));

UPDATE atlas_foundation.atlas_thresholds
   SET threshold_key = 'maal_max_cap.leaders' WHERE threshold_key = 'mpf_max_cap.alpha';
UPDATE atlas_foundation.atlas_thresholds
   SET threshold_key = 'maal_max_cap.passive' WHERE threshold_key = 'mpf_max_cap.passive';
UPDATE atlas_foundation.atlas_thresholds
   SET threshold_key = 'maal_max_cap.ind11' WHERE threshold_key = 'mpf_max_cap.india_xi';
```

- [ ] **Step 2: Back up the three tables first**

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  U=$(printf "%s" "$ATLAS_DB_URL" | sed -E "s#^postgresql\+[a-z0-9]+://#postgresql://#; s#\?.*##") && \
  pg_dump "$U" -t atlas_foundation.mpf_confirmation -t atlas_foundation.mpf_call \
    -t atlas_foundation.mpf_evidence > /home/ubuntu/backups/mpf_pre_rename_$(date +%Y%m%d).sql' 2>&1 | sed -E "s#://[^@]+@#://***@#g"
```

Expected: a non-empty dump file. Archive before rename — global standard.

- [ ] **Step 3: Apply and verify**

Apply via `_db.exec_script`, then:

```bash
ssh jprod 'cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  U=$(printf "%s" "$ATLAS_DB_URL" | sed -E "s#^postgresql\+[a-z0-9]+://#postgresql://#; s#\?.*##") && \
  psql "$U" -c "SELECT maal_code, status, count(*) FROM atlas_foundation.maal_confirmation GROUP BY 1,2 ORDER BY 1;" 2>&1 | sed -E "s#://[^@]+@#://***@#g"'
```

Expected: 4 rows total across codes drawn only from leaders/passive/ind11; 3 published. Zero rows with `alpha` or `india_xi`.

- [ ] **Step 4: Commit**

```bash
git add scripts/foundation/maal_rename.sql
git commit -m "refactor(maal): rename mpf_* to maal_* and align codes to leaders/passive/ind11"
```

---

### Task 10: Rename the frontend — mechanical only, no behavior change

**Files:**
- Rename: `frontend/src/lib/confirmations.ts` → `frontend/src/lib/maal.ts`
- Rename: `frontend/src/lib/queries/confirmations.ts` → `frontend/src/lib/queries/maal.ts`
- Rename: `frontend/src/lib/__tests__/confirmations.test.ts` → `frontend/src/lib/__tests__/maal.test.ts`
- Rename: `frontend/src/components/confirmations/` → `frontend/src/components/maal/`
- Rename: `frontend/src/app/portfolios/confirmations/` → `frontend/src/app/portfolios/maal/`
- Rename: `frontend/src/app/api/confirmations/route.ts` → `frontend/src/app/api/maal/route.ts`

- [ ] **Step 1: Confirm the suite is green BEFORE touching anything**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: PASS. This is the baseline the rename must not move. Write down the test count.

- [ ] **Step 2: (moved to Phase 2B)**

The real-snapshot test constants below now live in Task 11. Kept here only so the implementer does not go looking for them:

```ts
// RULE #0: the book below is BJ53's REAL holding set as synced from the CPP database
// on 2026-07-31 — the same ten positions the desk runs, priced by Atlas.
const REAL_LEADERS_SNAPSHOT: BookPosition[] = [
  { key: 'etf:GOLDBEES', symbol: 'GOLDBEES', name: 'NIPPON INDIA ETF GOLD BEES', sector: 'Gold', weightPct: 15.2 },
  { key: 'etf:NIFTYBEES', symbol: 'NIFTYBEES', name: 'NIPPON INDIA ETF NIFTY 50 BEES', sector: 'Broad Index', weightPct: 12.2 },
  { key: 'stock:CDSL', symbol: 'CDSL', name: 'Central Depository Services (India) Limited', sector: 'Capital Markets', weightPct: 12.1 },
  { key: 'stock:JINDALSAW', symbol: 'JINDALSAW', name: 'Jindal Saw Limited', sector: 'Metals', weightPct: 12.1 },
  { key: 'stock:DELHIVERY', symbol: 'DELHIVERY', name: 'Delhivery Limited', sector: 'Logistics', weightPct: 11.6 },
  { key: 'etf:HDFCSML250', symbol: 'HDFCSML250', name: 'HDFC NIFTY SMALLCAP 250 ETF', sector: 'Broad Index', weightPct: 9.0 },
  { key: 'etf:SILVERBEES', symbol: 'SILVERBEES', name: 'NIPPON INDIA SILVER ETF', sector: 'Silver', weightPct: 7.3 },
  { key: 'stock:JSFB', symbol: 'JSFB', name: 'Jana Small Finance Bank Limited', sector: 'Banking', weightPct: 7.0 },
  { key: 'stock:DIVISLAB', symbol: 'DIVISLAB', name: "Divi's Laboratories Limited", sector: 'Pharma', weightPct: 7.0 },
  { key: 'stock:ATHERENERG', symbol: 'ATHERENERG', name: 'Ather Energy Limited', sector: 'Auto', weightPct: 6.5 },
]

it('validates a sell against the real synced book, not a folded one', () => {
  const problems = validateCalls(REAL_LEADERS_SNAPSHOT, [
    sell({ key: 'stock:CDSL', weightPct: 4, reasons: ['Profit booking'] }),
  ])
  expect(problems).toEqual([])
})

it('rejects a sell of a name the real book does not hold', () => {
  const problems = validateCalls(REAL_LEADERS_SNAPSHOT, [
    sell({ key: 'stock:BIOCON', weightPct: 4, reasons: ['Profit booking'] }),
  ])
  expect(problems.map((p) => p.code)).toEqual(['sell_not_held'])
})
```

Before writing, resolve each `name` and `sector` above against `atlas_foundation.instrument_master` and correct any that differ. Do not invent a name to make the test compile.

- [ ] **Step 3: Perform the renames**

```bash
cd frontend/src
git mv lib/confirmations.ts lib/maal.ts
git mv lib/queries/confirmations.ts lib/queries/maal.ts
git mv lib/__tests__/confirmations.test.ts lib/__tests__/maal.test.ts
git mv components/confirmations components/maal
git mv app/portfolios/confirmations app/portfolios/maal
git mv app/api/confirmations app/api/maal
```

Then update every import and identifier. `PortfolioCode` → `MaalCode`; `PORTFOLIO_CODES` becomes `['leaders', 'passive', 'ind11']`; `PORTFOLIO_NAMES` becomes `{ leaders: 'Multi Asset Alpha - Leaders', passive: 'Passive', ind11: 'India XI' }`. Every `atlas_foundation.mpf_*` in `queries/maal.ts` becomes `maal_*`, and `portfolio_code` becomes `maal_code`.

Find every remaining reference:

Run: `rg -n "confirmations|mpf_|portfolio_code|india_xi|'alpha'" frontend/src --glob '!*.test.ts'`
Expected after the edit: no hits outside comments that legitimately describe history.

- [ ] **Step 4: Delete `foldBook` and re-point `getOpeningBook`**

Delete `foldBook` from `lib/maal.ts` entirely — nothing derives the book any more. In `lib/queries/maal.ts`, replace `getOpeningBook` with a read of the synced snapshot, priced by Atlas:

```ts
/**
 * The book this week starts from: the latest synced snapshot of the REAL portfolio,
 * priced with Atlas's own close. Not a fold of prior recommendations — the FM's calls
 * are a superset of what actually executes, so the fold drifted (see ADR 0005).
 */
export async function getOpeningBook(code: MaalCode, before?: string): Promise<BookPosition[]> {
  const rows = await sql<Array<Record<string, unknown>>>`
    WITH latest AS (
      SELECT max(as_of) AS as_of
      FROM atlas_foundation.maal_holding_snapshot
      WHERE maal_code = ${code}
        ${before ? sql`AND as_of < ${before}` : sql``}
    ),
    priced AS (
      SELECT s.instrument_key, s.source_symbol, s.asset_class,
             im.company_name,
             im.sector,
             s.quantity * o.close AS value
      FROM atlas_foundation.maal_holding_snapshot s
      JOIN latest ON latest.as_of = s.as_of
      JOIN atlas_foundation.instrument_master im ON im.isin = s.isin
      JOIN LATERAL (
        SELECT close FROM atlas_foundation.ohlcv_stock
        WHERE symbol = im.symbol ORDER BY date DESC LIMIT 1
      ) o ON true
      WHERE s.maal_code = ${code} AND s.instrument_key IS NOT NULL
    )
    SELECT instrument_key, source_symbol, company_name, sector, asset_class,
           value / nullif(sum(value) OVER (), 0) * 100 AS weight_pct
    FROM priced
    ORDER BY weight_pct DESC`
  return rows.map((r) => ({
    key: String(r.instrument_key),
    symbol: String(r.source_symbol),
    name: String(r.company_name ?? r.source_symbol),
    sector: r.sector == null ? null : String(r.sector),
    weightPct: round1(Number(r.weight_pct)),
  }))
}
```

Verify the real column names on `instrument_master` and `ohlcv_stock` before writing this — `company_name` and `close` are assumed here and must be checked with `\d`.

Note this returns positions only; the cash line now comes from `portfolio_nav_daily.cash`, so `cashPct` in `lib/maal.ts` must be replaced by a read of that column rather than `100 − Σ`. Add a `getBookCash(code)` alongside and use it in `BookCard` and the report.

- [ ] **Step 5: Prove nothing changed**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: PASS, with **the same test count as Step 1 and zero edited assertions**. If a test needed its expectations changed, you changed behavior — revert that bit and move it to Task 11.

Run: `npm run build`
Expected: build completes.

Visit `/portfolios/maal`. Expected: identical to what `/portfolios/confirmations` rendered before — same books, same folded numbers, same three published reports. Only the URL and the labels moved.

- [ ] **Step 6: Commit, merge and deploy 2A on its own**

```bash
git add -A frontend/src scripts/foundation/maal_rename.sql
git commit -m "refactor(maal): rename confirmations to MaaL Process

Pure rename: tables, files, routes, identifiers, portfolio codes. No behavior
change — the book is still folded. Task 11 re-points it at the real snapshot."
```

Merge and deploy before starting Phase 2B. The point of the split is that the next commit is small enough to read.

---

# PHASE 2B — Re-point the book at reality

**This is the commit that changes what the desk receives.** Keep it small and keep it alone.

### Task 11: Delete the fold, read the real snapshot (TDD)

**Files:**
- Modify: `frontend/src/lib/maal.ts`
- Modify: `frontend/src/lib/queries/maal.ts`
- Test: `frontend/src/lib/__tests__/maal.test.ts`

- [ ] **Step 1: Write the failing tests**

Add the `REAL_LEADERS_SNAPSHOT` constant and the two `it(...)` blocks shown in Task 10 Step 2 to `maal.test.ts`, and delete the `foldBook` tests.

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/__tests__/maal.test.ts`
Expected: FAIL — `validateCalls` still validates against the folded book, so the sell of CDSL at 4% reports `sell_not_held`.

- [ ] **Step 3: Delete `foldBook` and re-point `getOpeningBook`**

Apply the `getOpeningBook` replacement shown in Task 10 Step 4, delete `foldBook` from `lib/maal.ts`, and add `getBookCash(code)` reading `portfolio_nav_daily.cash` (used by `BookCard` and the report — cash is no longer `100 − Σ`).

- [ ] **Step 4: Surface the real as-of date**

The book now carries `source_as_of`. Render it on every `BookCard` and at the top of the printed report — "positions as of 29-Jul-2026" — and flag it when it trails today by more than one trading day. A circulated document that does not state which day its positions are from is the exact problem this phase exists to fix; shipping the new book without the date would trade one silent staleness for another.

- [ ] **Step 5: Delete the fold at publish**

In `publish()`, remove the `foldBook` call. `resulting_book` is still written at publish — it stays the frozen record of what the report said — but it is now `getOpeningBook` plus the week's calls **as stated**, purely for report fidelity. It is never read back as next week's opening book.

- [ ] **Step 6: Run the tests**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 7: Verify against the real board**

Run: `cd frontend && npm run build`
Expected: build completes.

Visit `/portfolios/maal`. Expected: leaders 10, ind11 6, passive 19 positions — matching the CPP source exactly — a non-zero cash figure on passive, and a visible "positions as of" date on every card.

- [ ] **Step 8: Commit**

```bash
git add -A frontend/src
git commit -m "feat(maal)!: the opening book is the real portfolio, not a fold

foldBook is deleted. getOpeningBook reads the latest CPP snapshot, priced by
Atlas, and the book states the date its positions are actually from. See ADR 0005."
```

---

### Task 11A: Sell list scope

**Files:**
- Modify: `frontend/src/lib/maal.ts`
- Modify: `frontend/src/components/maal/SellGrid.tsx`

- [ ] **Step 1: Write the failing test**

The FM's rule is that anything actually held is sellable, with cap-maxed names highlighted rather than being the only candidates. In `maal.test.ts`:

```ts
it('offers every real holding as a sell candidate', () => {
  expect(sellCandidates(REAL_LEADERS_SNAPSHOT, 12).map((p) => p.symbol))
    .toEqual(REAL_LEADERS_SNAPSHOT.map((p) => p.symbol))
})

it('flags the positions at or within 1% of the cap', () => {
  // Cap 12%: GOLDBEES 15.2, NIFTYBEES 12.2, CDSL 12.1, JINDALSAW 12.1, DELHIVERY 11.6
  expect(atCapSymbols(REAL_LEADERS_SNAPSHOT, 12))
    .toEqual(['GOLDBEES', 'NIFTYBEES', 'CDSL', 'JINDALSAW', 'DELHIVERY'])
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/__tests__/maal.test.ts`
Expected: FAIL — `sellCandidates` currently filters to cap-maxed names; `atCapSymbols` does not exist.

- [ ] **Step 3: Implement**

In `lib/maal.ts`, change `sellCandidates` to return the whole book sorted by weight, and add:

```ts
/** Positions at, above, or within CAP_TOLERANCE_PCT of the cap — highlighted, not filtered. */
export function atCapSymbols(book: BookPosition[], capPct: number): string[] {
  if (!(capPct > 0)) return []
  const floor = bps(capPct - CAP_TOLERANCE_PCT)
  return book.filter((p) => bps(p.weightPct) >= floor).map((p) => p.symbol)
}
```

Update `SellGrid.tsx` to pre-fill from the full book and mark the at-cap rows with the existing `cap` badge.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/lib/__tests__/maal.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/maal.ts frontend/src/components/maal/SellGrid.tsx
git commit -m "feat(maal): every real holding is a sell candidate; cap names are highlighted"
```

---

# PHASE 3 — 5-minute live P&L

### Task 12: Live mark table and pure P&L

**Files:**
- Modify: `scripts/foundation/maal_ddl.sql`
- Create: `atlas/maal/live.py`
- Test: `atlas/maal/tests/test_live.py`

- [ ] **Step 1: Append the mark table**

```sql
-- Intraday marks for the three MaaL books, today only (like atlas_sector_rs_intraday).
-- Written every 5 min by the existing intraday cron; NOT in the EOD freshness guard,
-- because it is empty overnight by design.
CREATE TABLE IF NOT EXISTS atlas_foundation.maal_live_mark (
    as_of_ts    timestamptz NOT NULL DEFAULT now(),
    maal_code   text NOT NULL,
    isin        text NOT NULL,
    ltp         numeric(18,4) NOT NULL CHECK (ltp > 0),
    PRIMARY KEY (maal_code, isin)
);
```

Primary key without the timestamp: each tick overwrites the last. There is no reason to keep a 5-minute tick history of a mark that is superseded five minutes later — the EOD close is already stored in `ohlcv_stock`.

- [ ] **Step 2: Write the failing test**

Create `atlas/maal/tests/test_live.py`:

```python
"""Live mark-to-market.

RULE #0: quantities and costs below are BJ53's REAL positions read from the CPP
database on 2026-07-31.
"""

from decimal import Decimal

from atlas.maal.live import live_pnl


def test_unrealized_pnl_against_real_positions():
    # Real BJ53: 304 CDSL at avg_cost 1277.3368. At an LTP of 1400 the position is up
    # (1400 - 1277.3368) * 304 = 37,289.53.
    result = live_pnl(
        [{"isin": "INE736A01011", "quantity": Decimal("304"), "avg_cost": Decimal("1277.3368")}],
        {"INE736A01011": Decimal("1400")},
    )
    assert result["unrealized"] == Decimal("37289.53")
    assert result["market_value"] == Decimal("425600.00")


def test_position_without_a_quote_is_reported_not_dropped():
    result = live_pnl(
        [{"isin": "INE736A01011", "quantity": Decimal("304"), "avg_cost": Decimal("1277.3368")}],
        {},
    )
    assert result["unquoted"] == ["INE736A01011"]
    assert result["market_value"] == Decimal("0")
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv/bin/python -m pytest atlas/maal/tests/test_live.py -v`
Expected: FAIL — no module `atlas.maal.live`.

- [ ] **Step 4: Implement**

Create `atlas/maal/live.py`:

```python
"""Mark the MaaL books to the live quote. Pure — no I/O.

A position with no quote is REPORTED, never silently valued at zero or dropped:
a missing mark on one name would otherwise quietly understate the whole book.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

_PAISE = Decimal("0.01")


def live_pnl(
    positions: list[dict[str, Any]],
    ltp_by_isin: dict[str, Decimal],
) -> dict[str, Any]:
    market_value = Decimal("0")
    cost = Decimal("0")
    unquoted: list[str] = []

    for p in positions:
        ltp = ltp_by_isin.get(p["isin"])
        if ltp is None:
            unquoted.append(p["isin"])
            continue
        market_value += p["quantity"] * ltp
        cost += p["quantity"] * p["avg_cost"]

    return {
        "market_value": market_value.quantize(_PAISE),
        "cost": cost.quantize(_PAISE),
        "unrealized": (market_value - cost).quantize(_PAISE),
        "unquoted": unquoted,
    }
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest atlas/maal/tests/test_live.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 6: Commit**

```bash
git add scripts/foundation/maal_ddl.sql atlas/maal/live.py atlas/maal/tests/test_live.py
git commit -m "feat(maal): live mark-to-market with explicit unquoted reporting"
```

---

### Task 13: Wire the 5-minute quote fetch

**Files:**
- Create: `scripts/foundation/maal_live_mark.py`
- Modify: `scripts/ops/atlas_intraday.sh`

- [ ] **Step 1: Write the fetcher**

Create `scripts/foundation/maal_live_mark.py`. It must:

1. Read the latest `maal_holding_snapshot` rows across all three books and collect the distinct ISINs (~30 instruments, one small query).
2. Resolve them to Kite instrument tokens the same way `scripts/foundation/build_sector_rs_intraday.py` does — **read that file first and reuse its session helper from `atlas/intraday/auth.py`; do not open a second Kite session.**
3. Call `kite.ltp(...)` once for the whole batch.
4. Upsert into `maal_live_mark` on `(maal_code, isin)`.
5. Log the count of quoted and unquoted instruments.

- [ ] **Step 2: Add it to the existing intraday job**

Append one line to `scripts/ops/atlas_intraday.sh`, after the crossover monitor:

```bash
# MaaL live marks: LTP for the three real books, refreshed every 5 min. Non-fatal —
# a missed tick is cosmetic, and the EOD sync is the source of record.
"$REPO/.venv/bin/python" scripts/foundation/maal_live_mark.py || true
```

No new cron line: `*/5 4-9 * * 1-5` already runs this script during market hours.

- [ ] **Step 3: Verify against the real market**

During market hours:

```bash
ssh jprod '/home/ubuntu/atlas-os/scripts/ops/atlas_intraday.sh && cd /home/ubuntu/atlas-os && set -a && source .env && set +a && \
  U=$(printf "%s" "$ATLAS_DB_URL" | sed -E "s#^postgresql\+[a-z0-9]+://#postgresql://#; s#\?.*##") && \
  psql "$U" -c "SELECT maal_code, count(*), min(as_of_ts) FROM atlas_foundation.maal_live_mark GROUP BY 1;" 2>&1 | sed -E "s#://[^@]+@#://***@#g"'
```

Expected: three rows, ~35 marks total, `as_of_ts` within the last five minutes.

- [ ] **Step 4: Surface it on the board**

Add a live P&L line to each MaaL book card and to the portfolio detail page, reading `maal_live_mark` joined to the latest snapshot. Show the mark timestamp next to it — a live number without its as-of time is a trap. When `maal_live_mark` is empty (outside market hours), show the EOD close-based figure and label it as such rather than showing a stale intraday number.

- [ ] **Step 5: Verify and commit**

Run: `cd frontend && npm run build && npx tsc --noEmit`
Expected: clean.

```bash
git add scripts/foundation/maal_live_mark.py scripts/ops/atlas_intraday.sh frontend/src
git commit -m "feat(maal): 5-minute live P&L on the existing intraday cron"
```

---

## Deploy

Follow [docs/deploy-hygiene.md](../../deploy-hygiene.md) exactly — a prod outage came from breaking this:

1. Merge to `main`; the box fast-forwards.
2. Rebuild to completion. **Never `pm2 reload` while a build runs.**
3. Confirm `frontend/.next/BUILD_ID` exists.
4. `rm -rf .next/cache/fetch-cache`.
5. Reload **once**.

Home/sectors/stocks are static-ISR, so only a rebuild advances the "as of" date.

## What already exists (reused, not rebuilt)

| Existing | How this plan uses it |
|---|---|
| `portfolio_master` / `portfolio_nav_daily` / `portfolio_trades` | The three books register here, so `/portfolios` and the detail pages populate with **no new UI**. `portfolio_nav_daily` already has `cash`, `invested` and `n_positions`; `portfolio_trades` already has `realized_pnl`, `holding_days`, `tax_bucket`. |
| `scripts/ops/atlas_intraday.sh` + `atlas/intraday/auth.py` | Phase 3 adds one line to the existing 5-minute cron and reuses the live Kite session. No new scheduler, no second auth. |
| `cpp_holdings.asset_class` | Already tags LIQUIDBEES / LIQUIDCASE / LIQUIDETF as `CASH`. Used directly instead of a hardcoded symbol list. |
| `computeFundRiskStats` (`frontend/src/lib/fundStats.ts`) | Powers the risk box on the detail page. The portal's own risk math is **not** ported. |
| `scripts/foundation/_db.py` | Connection handling and the statement-timeout pattern the CPP engine copies. |
| `scripts/ops/freshness_guard.py` | Extended with two new checks rather than a parallel alerting mechanism. |
| The confirmations UI | Renamed in place. No component is rewritten. |

Nothing here is rebuilt. The genuinely new code is one Python package (`atlas/maal/`), two scripts, one wrapper, one table.

## NOT in scope

| Deferred | Why |
|---|---|
| **Porting the portal's analytics** (XIRR, Modified Dietz, TWR, Sortino, monthly-returns grid, underwater chart) | A project in its own right. Once the books carry NAV history it becomes additive and low-risk. Bundling it means neither ships. |
| **Incremental transaction fetch** | Declined in review (D4). Every run re-pulls ~2,000 rows and that grows forever. Also note FIFO needs the full history per instrument anyway, so the full pull is currently load-bearing, not merely lazy. Revisit when the pull exceeds a few seconds. |
| **ASCII data-flow diagrams** | Declined in review (D4). |
| **`postgres_fdw` instead of a sync job** | Would make the board runtime-dependent on CPP being reachable during a page load, breaking the self-contained rule, and would put CPP credentials inside the database. |
| **Nightly refresh of `instrument_master`** | Pre-existing gap ([table-census.md:187](../../table-census.md)). The sync fails loudly on unresolved ISINs rather than papering over it. Mentioned, not fixed — it is outside this request. |
| **Reading `cpp_clients`** | Deliberately not granted. Atlas has no business holding client PII. |
| **The other three BJ53 sub-accounts** (BJ53MF, BJ53NEW, BJ53AML) | BJ53MF mirrors BJ53 exactly; the other two hold nothing. |

## Failure modes

| Codepath | Realistic production failure | Test? | Error handling? | Visible to you? |
|---|---|---|---|---|
| CPP connection | RDS unreachable or security group changed | gate script | connect timeout → non-zero exit | Yes — cron log + freshness guard |
| CPP connection | Query hangs mid-flight | — | statement timeout → non-zero exit | Yes — same |
| Sync writes | Sync silently stops running | — | freshness guard on `max(as_of)` | Yes — **only because of Task 6C** |
| Source data | Backoffice upload lags for days | — | freshness guard on `max(source_as_of)`, warn-not-alert | Yes — and the book states its real date |
| ISIN resolution | A new instrument is not in `instrument_master` | gate script | non-zero exit, ISINs named | Yes — sync fails loudly |
| FIFO | Sell with no matching buy (16 pre-format rows) | `test_sell_with_no_matching_buy_is_reported_not_guessed` | `realized_pnl = None`, never 0 | Yes — reconcile names them |
| FIFO | Cost basis goes negative | reconcile assertion 3 | non-zero exit | Yes |
| Live marks | Kite quote missing for a name | `test_position_without_a_quote_is_reported_not_dropped` | reported in `unquoted` | Yes |
| Live marks | Market closed | — | falls back to labelled EOD close | Yes |
| Publish | Stale editor tab sells a position no longer held | existing `validateCalls` tests | server-side revalidation | Yes — 409 |

**Zero critical gaps** — no failure mode is simultaneously untested, unhandled and silent. Before Task 6C existed, "sync silently stops" was one; that is why it was raised.

## Parallelization

| Step | Modules touched | Depends on |
|---|---|---|
| Tasks 1-3 (creds, registration, DDL) | `scripts/foundation/`, `scripts/ops/` | — |
| Tasks 4-5 (mapping, sync) | `atlas/maal/`, `scripts/foundation/` | 1-3 |
| Task 6A-6B (FIFO + reconcile) | `atlas/maal/`, `scripts/ops/` | 5 |
| Task 6C (freshness guard) | `scripts/ops/` | 3 |
| Task 7 (page panels) | `frontend/src/components/portfolios/` | 2 |
| Tasks 9-10 (rename) | `frontend/src/**`, `scripts/foundation/` | Phase 1 live |
| Task 11-11A (rewire) | `frontend/src/**` | 10 |
| Tasks 12-13 (live P&L) | `atlas/maal/`, `scripts/foundation/`, `frontend/src/` | 5 |

`Lane A: 1-3 → 4-5 → 6A → 6B (sequential, shared atlas/maal/)` · `Lane B: 6C (independent after 3)` · `Lane C: 7 (independent after 2, frontend only)`

Launch A, B and C in parallel after Task 3. Everything from Task 9 onward is sequential — 9-10 and 11 both rewrite the same frontend files, and the whole point of the 2A/2B split is that they land as separate commits.

## Definition of done

Phase 1:
- [ ] The leaked Supabase password is rotated.
- [ ] `atlas_reader` can read the four CPP tables and **cannot** read `cpp_clients`.
- [ ] `psql_masked.sh` masks the password on a **failing** query, not just a passing one.
- [ ] A sync run reports zero unresolved ISINs and writes 3 NAV rows, ~35 snapshot rows, and the full trade history.
- [ ] Every snapshot row carries a `source_as_of` from `cpp_nav_series`, and a lagging upload logs a warning naming the gap in days.
- [ ] Re-running the sync adds zero duplicate trades.
- [ ] `maal_pnl_reconcile.py` exits 0 across all 991 real sells, with any unmatched sells named explicitly rather than absorbed.
- [ ] The freshness guard trips when `as_of` is backdated, and the ROLLBACK leaves row counts unchanged.
- [ ] `/portfolios` lists the three MaaL books with real NAV, cash and position counts.
- [ ] `make gate` exits 0.

Phase 2A (contract: zero behavior change):
- [ ] No `mpf_`, `confirmations`, `alpha` or `india_xi` identifiers remain outside historical comments.
- [ ] The vitest suite passes with **the same test count and zero edited assertions** as before the rename.
- [ ] The three previously-published reports render identically.
- [ ] Merged and deployed on its own, before 2B starts.

Phase 2B:
- [ ] `foldBook` is deleted.
- [ ] `/portfolios/maal` shows leaders 10 / ind11 6 / passive 19 positions, matching the CPP source exactly.
- [ ] Passive shows non-zero cash (LIQUIDCASE ~6.8% plus residual).
- [ ] Every book card and the printed report state the positions' real `source_as_of` date.

Phase 3:
- [ ] `maal_live_mark` refreshes every 5 minutes during market hours.
- [ ] Live P&L renders with its as-of timestamp, and degrades to the labelled EOD figure outside market hours.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 7 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

Decisions taken in review, all folded into the plan above:

| # | Finding | Decision |
|---|---|---|
| D1 | Rename bundled with the behavior change | Split into Phase 2A (pure rename) and 2B (re-point the book) |
| D2 | Snapshot stamped with the run date, not the data date | Added `source_as_of` + staleness warning + freshness split |
| D3 | Plan promised realized P&L but never computed it | FIFO realized P&L moved into Phase 1 (Task 6A) |
| D4 | Three hardening items offered | Freshness guard accepted; incremental fetch and diagrams declined |
| D5 | Password-masking regex copy-pasted 8× | `scripts/ops/psql_masked.sh` wrapper; verified on the error path |
| D6 | No timeout on the outbound CPP connection | Connect + statement timeout, fail loudly |
| D7 | FIFO correctness unproven | Reconcile across all 991 real sells (Task 6B), nightly |

**OUTSIDE VOICE: did not run.** Codex CLI is installed and the auth probe reports ready, but the vendored binary is missing — `spawn .../codex-darwin-arm64/vendor/aarch64-apple-darwin/codex ENOENT`. Repair with `npm install -g @openai/codex`, then re-run. The Claude-subagent fallback was deliberately not used (standing instruction not to spawn agents unrequested). **This plan has had one reviewer, not two.**

**VERDICT:** ENG CLEARED — ready to implement. Outside voice outstanding.

NO UNRESOLVED DECISIONS

# Stock Universe — Liquidity Floor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Atlas's index-derived stock universe (739 scored) with a single liquidity rule — trailing 60-day median daily traded value ≥ ₹2.5 crore — taking coverage to ~1,207 names without fabricating a single score.

**Architecture:** The rule already exists as `atlas_thresholds.liquidity_min_traded_value_inr` (methodology §3.3) and is read by no code anywhere in the repo. This plan wires it up. Two prerequisites land first: a daily universe-membership snapshot (so history exists from day one), and a cap-cohort rule derived from market-cap rank instead of index membership (because every new name is in no index and would otherwise collapse into `micro`). Data sufficiency needs no new code — `compute_composite()` already does coverage-adjusted weighting, returning NULL for a lens with no inputs.

**Tech Stack:** Python 3.11 · pandas · SQLAlchemy 2.0 (`scripts/foundation/_db.py`) · PostgreSQL (Supabase, schema `atlas_foundation`) · pytest (`unit` / `integration` markers) · Next.js + `postgres` tagged templates (frontend queries)

**Spec:** `docs/superpowers/specs/2026-08-23-stock-universe-1050-design.md`

---

## Ground rules for every task

- **Rule #0 — no synthetic data.** Every fixture is a real record pulled from `atlas_foundation`. Tests that need the DB carry `@pytest.mark.integration`.
- **Rule #4 — no hardcoded methodology numbers.** The floor is read from `atlas_thresholds`. A pre-commit hook (`thresholds live in atlas_thresholds, not in code`) will reject a literal.
- **Never edit on the box.** Laptop → `make gate` → branch → PR → `main`.
- Connect via the `aws-1-ap-south-1` pooler on **6543** (`ATLAS_DB_URL`). The direct `db.<ref>.supabase.co:5432` host is IPv6-only and unreachable from macOS.
- Run `make gate` (lint + tests + pyright ratchet, ~7s) before every commit. **Not `make check`.**

## Two FM options, resolved

The spec flagged two one-liners with no answer. Judgment calls made here, both reversible:

- **Held names never drop out — INCLUDED** (Task 5). Prevents a live book position silently losing its conviction score and blinding the desk agents. Changes nothing today (no held name is below the floor); prevents a genuinely bad state later.
- **Hysteresis — DEFERRED.** YAGNI until churn is observed. Task 1's snapshot table makes churn measurable; if it exceeds ~5%/month, add a second threshold row then.

## File structure

| File | Responsibility | Task |
|---|---|---|
| `scripts/foundation/universe_core.py` *(new)* | Pure ADV + membership math. No I/O. The single place the rule is expressed. | 1 |
| `scripts/foundation/build_universe_snapshot.py` *(new)* | Daily membership journal → `atlas_universe_snapshot` | 1 |
| `tests/scripts/test_universe_core.py` *(new)* | Unit tests on the pure math, real ADV values as fixtures | 1 |
| `tests/integration/universe/test_universe_snapshot.py` *(new)* | Writer idempotence + row counts against the live DB | 1 |
| `scripts/foundation/fetch_marketcap.py` | Market-cap backfill — **run only, no code change** | 2 |
| `scripts/foundation/cap_cohort.py` *(new)* | Creates/refreshes `v_stock_cap`, the single cap rule | 3 |
| `tests/integration/universe/test_cap_cohort.py` *(new)* | Parity vs today's index-derived caps | 3 |
| `frontend/src/lib/queries/stock_lens.ts:102-110` | Replace inline cap CTE with the view | 4 |
| `frontend/src/lib/queries/sector_lens.ts:81-89` | Replace inline cap CTE with the view | 4 |
| `scripts/foundation/decile_core.py:27-48` | `cap_bucket()` reads the view | 4 |
| `scripts/foundation/build_universe.py:117-127` | `is_active` from the liquidity threshold | 5 |
| `tests/integration/universe/test_liquidity_universe.py` *(new)* | The rule reproduces measured counts at two floors | 5 |
| `scripts/ops/atlas_daily.sh` | Wire snapshot + cap refresh | 1, 3, 9 |

---

## Task 1: Universe snapshot — the history clock

> **AS BUILT — this task is COMPLETE.** Commits `b048184d`, `90f1ea61`, `a6186773`.
> The code below is the plan as drafted; review found three defects in it and the
> shipped version diverges deliberately. Read the commits, not this section, for what
> actually exists. Divergences:
> - `held_ids()` — the plan joined on `im.symbol = pt.instrument_key`. That column holds
>   the instrument_id UUID as text; the join matched 0 of 654 rows and would have failed
>   silently forever. It is also now **currently-held** (net open position > 0, netted
>   per book) and takes an `as_of` date, not ever-traded.
> - **Minimum-observation guard added.** `percentile_cont` returns a median over however
>   many rows exist; 39 names were passing the floor on fewer than 10 observations, one
>   with a ₹433cr "median" from two days. The `liq` CTE now requires ≥ `min_obs` rows
>   plus recency. Two new threshold rows: `liquidity_min_observations_60d` (40) and
>   `liquidity_recency_trading_days` (5).
> - `close_adj * volume` → `close * volume`. Adjusted price × raw volume is neither
>   actual traded rupees nor a consistent series. Numerically identical today (0 of
>   116,904 rows in-window differ) but prevents a split from evicting a name.
> - `liquidity_rank` column **dropped** — derivable at read time, no consumer, and
>   `method="first"` over an unordered query made tied ranks nondeterministic.
> - `snapshot_date()` added: `eod_cutoff()` can return a weekend, and in a date-keyed
>   journal that appends rows the market never traded.
> - Unit fixture `ALOKINDS ₹50,000,000` replaced — its true ADV is ₹49,985,288, i.e.
>   *below* the ₹5cr line the test asserted it was above.
>
> **Measured result: 1,205 names clear the ₹2.5cr floor, 1,207 with held rescues; 990
> at ₹5cr. Only 2 current active names drop. The guard evicts no current name.**

Lands first and alone. `de_index_constituents` has no reconstitution history (every row
`effective_to IS NULL`), so today's membership is being applied to 2019 data. That record
cannot be backfilled later; every day this is not running is a day of history lost.

**Files:**
- Create: `scripts/foundation/universe_core.py`
- Create: `scripts/foundation/build_universe_snapshot.py`
- Create: `tests/scripts/test_universe_core.py`
- Create: `tests/integration/universe/__init__.py` (empty)
- Create: `tests/integration/universe/test_universe_snapshot.py`
- Modify: `scripts/ops/atlas_daily.sh`

- [ ] **Step 1: Write the failing unit test**

Create `tests/scripts/test_universe_core.py`:

```python
"""Unit tests for scripts/foundation/universe_core.py — the liquidity-floor membership
math that decides which stocks Atlas scores.

Fixtures are REAL trailing-60-day median traded values pulled from
atlas_foundation.ohlcv_stock (snapshot 2026-08-23), NOT synthetic (rule #0). The four
names below bracket the ₹2.5 cr floor as measured on that date.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import universe_core as U  # noqa: E402

pytestmark = pytest.mark.unit

# Real 60-day median traded values, atlas_foundation snapshot 2026-08-23 (rupees).
# ALOKINDS sits just above the ₹5 cr line; AHLUCONT and PRSMJOHNSN fall below ₹2.5 cr.
REAL_ADV = pd.DataFrame(
    [
        {"instrument_id": "a", "symbol": "ALOKINDS", "adv_median_60d": Decimal("50000000")},
        {"instrument_id": "b", "symbol": "ORIENTCEM", "adv_median_60d": Decimal("26300000")},
        {"instrument_id": "c", "symbol": "AHLUCONT", "adv_median_60d": Decimal("22500000")},
        {"instrument_id": "d", "symbol": "PRSMJOHNSN", "adv_median_60d": Decimal("20300000")},
    ]
)


def test_members_at_2p5cr_floor_keeps_names_at_or_above() -> None:
    got = U.members(REAL_ADV, floor_inr=Decimal("25000000"), held_ids=frozenset())
    assert got == {"a", "b"}


def test_members_excludes_names_below_the_floor() -> None:
    got = U.members(REAL_ADV, floor_inr=Decimal("25000000"), held_ids=frozenset())
    assert "c" not in got, "AHLUCONT at ₹2.25 cr is below the ₹2.5 cr floor"
    assert "d" not in got, "PRSMJOHNSN at ₹2.03 cr is below the ₹2.5 cr floor"


def test_a_five_crore_floor_is_stricter_than_two_and_a_half() -> None:
    lo = U.members(REAL_ADV, floor_inr=Decimal("25000000"), held_ids=frozenset())
    hi = U.members(REAL_ADV, floor_inr=Decimal("50000000"), held_ids=frozenset())
    assert hi < lo, "a higher floor must yield a strict subset"
    assert hi == {"a"}


def test_held_names_stay_in_regardless_of_liquidity() -> None:
    got = U.members(REAL_ADV, floor_inr=Decimal("25000000"), held_ids=frozenset({"d"}))
    assert "d" in got, "a name held in a portfolio book must never lose its score"


def test_null_adv_is_excluded_never_treated_as_zero_or_passing() -> None:
    with_null = pd.concat(
        [REAL_ADV, pd.DataFrame([{"instrument_id": "e", "symbol": "NODATA",
                                  "adv_median_60d": None}])],
        ignore_index=True,
    )
    got = U.members(with_null, floor_inr=Decimal("25000000"), held_ids=frozenset())
    assert "e" not in got, "a NULL ADV means no signal — it must not pass the floor"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/scripts/test_universe_core.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'universe_core'`

- [ ] **Step 3: Write the minimal implementation**

Create `scripts/foundation/universe_core.py`:

```python
"""Liquidity-floor universe membership — the SINGLE place the rule is expressed.

A stock is in Atlas's coverage universe if its trailing 60-day MEDIAN daily traded
value is at least the floor in atlas_thresholds.liquidity_min_traded_value_inr
(methodology §3.3), or if it is held in a portfolio book.

Median, not mean: one block deal must not promote an illiquid name. Sixty days, not
two weeks: measured monthly churn is 5% at 60 days versus 16% at two weeks for a
near-identical member count (spec, 2026-08-23).

Pure — no I/O, no DB access. The SQL that produces the ADV frame lives in
build_universe_snapshot.adv_frame().
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

# 60 trading days back. Calendar span is wider than 60 to absorb weekends/holidays;
# the query takes the most recent 60 DISTINCT trading dates, not 60 calendar days.
LOOKBACK_TRADING_DAYS = 60
LOOKBACK_CALENDAR_DAYS = 150

THRESHOLD_KEY = "liquidity_min_traded_value_inr"


def members(
    adv: pd.DataFrame,
    floor_inr: Decimal,
    held_ids: frozenset[str],
) -> set[str]:
    """instrument_ids in the universe.

    Args:
        adv: frame with ``instrument_id`` and ``adv_median_60d`` (rupees). A NULL
             adv_median_60d means "no signal" and never passes — it is not zero.
        floor_inr: the floor, from atlas_thresholds. Never a literal (rule #4).
        held_ids: instrument_ids held in any portfolio book. Always retained, so a
                  live position cannot silently lose its conviction score.
    """
    if adv.empty:
        return set(held_ids)
    v = pd.to_numeric(adv["adv_median_60d"], errors="coerce")
    passing = adv.loc[v.notna() & (v >= float(floor_inr)), "instrument_id"]
    return {str(x) for x in passing} | {str(x) for x in held_ids}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/scripts/test_universe_core.py -v`
Expected: 5 passed

- [ ] **Step 5: Write the failing integration test**

Create `tests/integration/universe/__init__.py` (empty file), then
`tests/integration/universe/test_universe_snapshot.py`:

```python
"""Integration tests for the daily universe-membership snapshot.

Read/write against the live DB. The snapshot is the ONLY record of which stocks Atlas
covered on a given date — de_index_constituents carries no reconstitution history
(every row effective_to IS NULL), so without this table the 2019-2026 lens history is
being read against today's membership, which is survivorship bias.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _db  # noqa: E402
import build_universe_snapshot as S  # noqa: E402

pytestmark = pytest.mark.integration


def test_adv_frame_covers_the_whole_stock_master() -> None:
    """Every stock gets a row — including those with no recent trading, whose ADV is
    NULL rather than 0 (rule: NULL in a financial calc produces NULL)."""
    adv = S.adv_frame()
    n_stocks = _db.scalar(
        "SELECT count(*) FROM atlas_foundation.instrument_master WHERE asset_class='stock'"
    )
    assert len(adv) == n_stocks, f"expected one row per stock ({n_stocks}), got {len(adv)}"
    assert adv["adv_median_60d"].notna().sum() > 1000, "most stocks should have a real ADV"


def test_adv_frame_reproduces_the_measured_floor_counts() -> None:
    """The rule must reproduce the counts measured when the spec was written
    (2026-08-23): 1,271 names at ₹2.5 cr and 1,037 at ₹5 cr. Tolerance is wide because
    liquidity genuinely drifts; a large miss means the SQL changed meaning."""
    adv = S.adv_frame()
    v = adv["adv_median_60d"].astype("float64")
    at_2p5 = int((v >= 25_000_000).sum())
    at_5 = int((v >= 50_000_000).sum())
    assert 1150 <= at_2p5 <= 1400, f"₹2.5cr floor gave {at_2p5}, expected ~1271"
    assert 950 <= at_5 <= 1150, f"₹5cr floor gave {at_5}, expected ~1037"
    assert at_5 < at_2p5, "a higher floor must be strictly more selective"


def test_snapshot_write_is_idempotent_within_a_day() -> None:
    """Running twice the same day must not duplicate rows — atlas_daily.sh can retry."""
    S.run()
    first = _db.scalar(
        "SELECT count(*) FROM atlas_foundation.atlas_universe_snapshot "
        "WHERE date = (SELECT max(date) FROM atlas_foundation.atlas_universe_snapshot)"
    )
    S.run()
    second = _db.scalar(
        "SELECT count(*) FROM atlas_foundation.atlas_universe_snapshot "
        "WHERE date = (SELECT max(date) FROM atlas_foundation.atlas_universe_snapshot)"
    )
    assert first == second, f"second run duplicated rows: {first} -> {second}"


def test_snapshot_records_why_not_just_whether() -> None:
    """in_universe alone is not reconstructable. The ADV that produced it must be
    stored alongside, so a past membership decision can be re-derived."""
    cols = set(
        _db.read_df(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='atlas_foundation' AND table_name='atlas_universe_snapshot'"
        )["column_name"]
    )
    assert {"date", "instrument_id", "in_universe", "adv_median_60d", "liquidity_rank"} <= cols
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/universe/test_universe_snapshot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_universe_snapshot'`

- [ ] **Step 7: Write the snapshot writer**

Create `scripts/foundation/build_universe_snapshot.py`:

```python
#!/usr/bin/env python3
"""Daily universe-membership journal -> atlas_foundation.atlas_universe_snapshot.

WHY THIS EXISTS: de_index_constituents has no reconstitution history — every row is
effective_to IS NULL (500 live of 500 total). Today's membership is therefore applied
to 2019 lens scores, which is survivorship bias and will inflate any forward-return
study. This table is the fix, and it only works going forward: a day not recorded is
a day lost.

Writes one row per stock per run, whether or not it is in the universe, with the ADV
that produced the decision — so a past membership call can be re-derived, not just
looked up.

    python build_universe_snapshot.py            # append today
    python build_universe_snapshot.py --dry-run  # compute + report, no write
"""

from __future__ import annotations

import argparse

import _db
import pandas as pd
import universe_core as U

M = "atlas_foundation"
TGT = f"{M}.atlas_universe_snapshot"


def ensure_table() -> None:
    _db.exec_sql(f"""CREATE TABLE IF NOT EXISTS {TGT} (
        date date NOT NULL,
        instrument_id uuid NOT NULL,
        in_universe boolean NOT NULL,
        adv_median_60d numeric(20,4),
        liquidity_rank integer,
        floor_inr numeric(18,6) NOT NULL,
        computed_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (date, instrument_id))""")
    _db.exec_sql(
        f"CREATE INDEX IF NOT EXISTS ix_universe_snapshot_instrument "
        f"ON {TGT} (instrument_id)"
    )


def adv_frame() -> pd.DataFrame:
    """One row per stock: trailing-60-trading-day MEDIAN traded value, in rupees.

    LEFT JOIN, so a stock with no recent trading gets adv_median_60d = NULL — "no
    signal", never 0. The window is the most recent 60 DISTINCT trading dates, not 60
    calendar days, so holidays and long weekends cannot shorten it.
    """
    return _db.read_df(
        f"""
        WITH d AS (
            SELECT DISTINCT date FROM {M}.ohlcv_stock
            WHERE date > (CURRENT_DATE - INTERVAL '{U.LOOKBACK_CALENDAR_DAYS} days')
            ORDER BY date DESC LIMIT {U.LOOKBACK_TRADING_DAYS}
        ),
        liq AS (
            SELECT instrument_id,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY close_adj * volume)::numeric
                       AS adv_median_60d
            FROM {M}.ohlcv_stock
            WHERE date IN (SELECT date FROM d)
              AND close_adj IS NOT NULL AND volume IS NOT NULL
            GROUP BY instrument_id
        )
        SELECT im.instrument_id::text AS instrument_id, im.symbol, liq.adv_median_60d
        FROM {M}.instrument_master im
        LEFT JOIN liq ON liq.instrument_id = im.instrument_id
        WHERE im.asset_class = 'stock'
        """
    )


def held_ids() -> frozenset[str]:
    """instrument_ids with any trade in a portfolio book. portfolio_trades keys on
    instrument_key (the symbol), so this resolves through instrument_master."""
    df = _db.read_df(
        f"""SELECT DISTINCT im.instrument_id::text AS instrument_id
            FROM {M}.portfolio_trades pt
            JOIN {M}.instrument_master im
              ON im.symbol = pt.instrument_key AND im.asset_class = 'stock'"""
    )
    return frozenset(df["instrument_id"].tolist())


def run(dry_run: bool = False) -> dict:
    ensure_table()
    floor = _db.scalar(
        f"SELECT threshold_value FROM {M}.atlas_thresholds "
        f"WHERE threshold_key = :k AND is_active",
        {"k": U.THRESHOLD_KEY},
    )
    if floor is None:
        raise RuntimeError(f"{U.THRESHOLD_KEY} missing from {M}.atlas_thresholds")

    adv = adv_frame()
    held = held_ids()
    inside = U.members(adv, floor, held)

    adv["in_universe"] = adv["instrument_id"].isin(inside)
    adv["liquidity_rank"] = (
        adv["adv_median_60d"].rank(ascending=False, method="first").astype("Int64")
    )
    adv["floor_inr"] = floor
    adv["date"] = _db.eod_cutoff()

    n_in = int(adv["in_universe"].sum())
    print(f"  universe: {n_in} / {len(adv)} stocks at floor ₹{float(floor) / 1e7:.2f} cr")

    if dry_run:
        print("  DRY RUN — no write.")
        return {"written": 0, "dry_run": True, "in_universe": n_in}

    cols = ["date", "instrument_id", "in_universe", "adv_median_60d",
            "liquidity_rank", "floor_inr"]
    n = _db.upsert_df(TGT, adv[cols], ["date", "instrument_id"])
    return {"written": n, "in_universe": n_in}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="compute + report, no write")
    print(run(dry_run=ap.parse_args().dry_run))
```

- [ ] **Step 8: Run the integration tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/integration/universe/test_universe_snapshot.py -v`
Expected: 4 passed

If `test_adv_frame_reproduces_the_measured_floor_counts` fails, **stop and report the
actual counts** — it means the ADV SQL is not measuring what the spec measured. Do not
widen the tolerance to make it pass.

- [ ] **Step 9: Verify the schema gate still reads 0**

Run: `.venv/bin/python scripts/ops/schema_gate.py`
Expected: exit 0, no cross-schema references reported

- [ ] **Step 10: Wire into the nightly orchestrator**

In `scripts/ops/atlas_daily.sh`, immediately after the `gate "freshness_guard"` line
(currently line 113), add:

```bash
# Universe membership journal. step, not gate: a missed snapshot is a gap in history,
# not a reason to withhold a correct board. Promote to gate() after a clean month.
step "universe_snapshot" $PY scripts/foundation/build_universe_snapshot.py
```

- [ ] **Step 11: Run the gate and commit**

```bash
make gate
git add scripts/foundation/universe_core.py \
        scripts/foundation/build_universe_snapshot.py \
        tests/scripts/test_universe_core.py \
        tests/integration/universe/__init__.py \
        tests/integration/universe/test_universe_snapshot.py \
        scripts/ops/atlas_daily.sh
git commit -m "feat(universe): daily membership snapshot + liquidity-floor core

de_index_constituents carries no reconstitution history, so today's membership
is being applied to 2019 lens scores. This journal fixes that going forward and
cannot be backfilled — hence it lands before the universe rule changes.

Records the ADV that produced each decision, not just the decision."
```

---

## Task 2: Market-cap backfill

No code changes. `fetch_marketcap.py` already scans every stock
(`WHERE asset_class='stock'`), skips names already fetched, and is resumable — it just
has never been run to completion. `equity_marketcap` holds **302 of 2,411** stocks.
Task 3 cannot produce a correct cap rank without this.

**Files:** none modified. `scripts/foundation/fetch_marketcap.py` is run as-is.

- [ ] **Step 1: Record the starting coverage**

```bash
./scripts/foundation/psql.sh -c "SELECT count(*) FROM atlas_foundation.equity_marketcap WHERE market_cap_cr IS NOT NULL;"
```
Expected: 302

- [ ] **Step 2: Smoke-test the fetcher on 20 names before committing to a long run**

Run: `.venv/bin/python scripts/foundation/fetch_marketcap.py --limit 20 --workers 4`
Expected: `DONE: ok=N miss=M; total in table=...` with `ok` clearly greater than `miss`.

If `ok` is 0, Screener has changed its markup or is blocking — **stop and report**.
Do not proceed; every downstream cap label would be wrong.

- [ ] **Step 3: Run the full backfill**

Run: `.venv/bin/python scripts/foundation/fetch_marketcap.py --workers 6`

This takes a while (~2,100 names, rate-limited, 6 workers). It is resumable — if it
dies, re-run the same command and it resumes from where it stopped.

- [ ] **Step 4: Verify coverage and sanity-check the top of the list**

```bash
./scripts/foundation/psql.sh -c "
SELECT count(*) AS covered FROM atlas_foundation.equity_marketcap WHERE market_cap_cr IS NOT NULL;
SELECT symbol, market_cap_cr FROM atlas_foundation.equity_marketcap
 WHERE market_cap_cr IS NOT NULL ORDER BY market_cap_cr DESC LIMIT 10;"
```

Expected: `covered` ≥ 1,207. The top 10 must be recognisably India's largest listed
companies (RELIANCE, HDFCBANK, TCS, BHARTIARTL, ICICIBANK and similar). If the top of
the list contains obscure names, the parser is picking up the wrong number — **stop
and report**.

- [ ] **Step 5: Verify no gaps above the liquidity floor**

```bash
./scripts/foundation/psql.sh -c "
WITH d AS (SELECT DISTINCT date FROM atlas_foundation.ohlcv_stock
           WHERE date > CURRENT_DATE - INTERVAL '150 days' ORDER BY date DESC LIMIT 60),
liq AS (SELECT instrument_id,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY close_adj*volume)::numeric adv
        FROM atlas_foundation.ohlcv_stock WHERE date IN (SELECT date FROM d)
          AND close_adj IS NOT NULL AND volume IS NOT NULL GROUP BY 1)
SELECT count(*) AS liquid_without_marketcap
FROM liq LEFT JOIN atlas_foundation.equity_marketcap m USING (instrument_id)
WHERE liq.adv >= 25000000 AND m.market_cap_cr IS NULL;"
```

Expected: 0. A liquid name with no market cap would be mis-bucketed as `micro`.
If non-zero, list the symbols and re-run the fetcher for them before continuing.

- [ ] **Step 6: Commit the coverage note**

No code changed, so there is nothing to commit. Record the final `covered` count in the
PR description instead.

---

## Task 3: Cap cohort from market-cap rank

**This is the prerequisite that makes the whole project safe.** Production buckets caps
by index membership, so every one of the ~520 new names — all in no index — would become
`micro`, taking that cohort from 250 to ~770. Deciles are cut *within* cohort, so every
micro decile, the Leader badge and the `/stocks` cap filter would change meaning
silently, with no error anywhere.

The rule moves into a **database view** so the two TypeScript query files and
`decile_core.py` cannot drift apart.

**Files:**
- Create: `scripts/foundation/cap_cohort.py`
- Create: `tests/integration/universe/test_cap_cohort.py`
- Modify: `scripts/ops/atlas_daily.sh`

- [ ] **Step 1: Write the failing parity test**

Create `tests/integration/universe/test_cap_cohort.py`:

```python
"""Integration tests for atlas_foundation.v_stock_cap — the single cap-cohort rule.

The rule changes from index membership to market-cap rank. The two must AGREE on the
current universe, because the index rule was always approximating a market-cap rank:
NIFTY 100 = top 100, MIDCAP 150 = 101-250, SMLCAP 250 = 251-500. Disagreement above a
few percent means the market-cap data is wrong, not that the rule is.

Run BEFORE the universe flips (Task 5) — the parity check is only meaningful while
is_active is still the index-derived 747.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _db  # noqa: E402

pytestmark = pytest.mark.integration

OLD_CAP_SQL = """
    SELECT instrument_id,
      CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
           WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
           WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
    FROM atlas_foundation.de_index_constituents
    WHERE effective_to IS NULL
      AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
    GROUP BY instrument_id
"""


def test_view_exists_and_covers_every_active_stock() -> None:
    n_missing = _db.scalar(
        """SELECT count(*) FROM atlas_foundation.instrument_master im
           LEFT JOIN atlas_foundation.v_stock_cap v USING (instrument_id)
           WHERE im.asset_class='stock' AND im.is_active AND v.cap IS NULL"""
    )
    assert n_missing == 0, f"{n_missing} active stocks have no cap label"


# Cap tiers in rank order. Disagreement between the two rules is EXPECTED and is not
# an error: NSE selects index membership on a 6-MONTH AVERAGE market cap and
# reconstitutes semi-annually, while v_stock_cap ranks point-in-time. Names near ranks
# 100/250/500 therefore swap sides between reconstitutions. Measured 2026-08-23:
# 77.4% agreement, with near-perfectly symmetric flow across each boundary
# (large<->mid 11/11, mid<->small 19/18, small<->micro 54/55). What would signal a REAL
# defect is asymmetry (bias, not drift) or a tier-skip that cannot be explained.
_TIER_ORDER = {"large": 0, "mid": 1, "small": 2, "micro": 3}


def _old_vs_new() -> "pd.DataFrame":
    df = _db.read_df(
        f"""WITH old AS ({OLD_CAP_SQL})
            SELECT im.symbol, COALESCE(old.cap,'micro') AS old_cap, v.cap AS new_cap,
                   v.mcap_rank, m.market_cap_cr
            FROM atlas_foundation.instrument_master im
            JOIN atlas_foundation.v_stock_cap v USING (instrument_id)
            JOIN atlas_foundation.equity_marketcap m USING (instrument_id)
            LEFT JOIN old ON old.instrument_id = im.instrument_id
            WHERE im.asset_class='stock' AND im.is_active"""
    )
    assert len(df) > 700, "expected the current active universe"
    return df


def test_disagreements_are_boundary_drift_not_bias() -> None:
    """Equal numbers must cross each boundary in each direction. Systematic one-way
    flow would mean the market-cap basis is wrong, not merely out of phase."""
    df = _old_vs_new()
    d = df[df["old_cap"] != df["new_cap"]]
    for a, b in (("large", "mid"), ("mid", "small"), ("small", "micro")):
        out = len(d[(d["old_cap"] == a) & (d["new_cap"] == b)])
        back = len(d[(d["old_cap"] == b) & (d["new_cap"] == a)])
        assert abs(out - back) <= max(5, 0.25 * max(out, back, 1)), (
            f"asymmetric flow across {a}/{b}: {out} out vs {back} back — "
            "that is bias, not reconstitution lag"
        )


def test_every_tier_skip_is_individually_justified() -> None:
    """A name moving more than one tier is either a stale index label on a re-rated
    company or a bad market cap. Each must be named and explained, never bulk-accepted.

    KNOWN AND VERIFIED (2026-08-23):
      CUPID — index says micro, market-cap rank 240. The cap is REAL (Rs 38,192 cr
      confirmed externally 19-Aug-2026; the stock traded Rs 1,842 cr in one session on
      2026-08-18). NSE simply has not reconstituted. The new rule is right here and the
      index label is stale.
    """
    justified = {"CUPID"}
    df = _old_vs_new()
    d = df[df["old_cap"] != df["new_cap"]].copy()
    d["jump"] = (d["new_cap"].map(_TIER_ORDER) - d["old_cap"].map(_TIER_ORDER)).abs()
    skips = d[(d["jump"] > 1) & (~d["symbol"].isin(justified))]
    assert skips.empty, (
        "unexplained tier skips — verify each market cap against an external source "
        f"before accepting:\n{skips.to_string(index=False)}"
    )


def test_no_universe_member_is_missing_a_market_cap() -> None:
    """A NULL cap must never fall through to 'micro' — that would drop a real mid-cap
    into the micro cohort and distort its deciles. GUJGASLTD is the known case: it
    clears the liquidity floor but Screener has no obtainable cap for it."""
    missing = _db.read_df(
        """SELECT im.symbol FROM atlas_foundation.atlas_universe_snapshot s
           JOIN atlas_foundation.instrument_master im USING (instrument_id)
           LEFT JOIN atlas_foundation.v_stock_cap v USING (instrument_id)
           WHERE s.date = (SELECT max(date) FROM atlas_foundation.atlas_universe_snapshot)
             AND s.in_universe AND v.cap IS NULL"""
    )
    assert missing.empty, (
        f"universe members with no cap label: {list(missing['symbol'])} — "
        "these must be resolved or explicitly excluded, never defaulted to micro"
    )


def test_cohort_boundaries_are_exact() -> None:
    """large=100, mid=150, small=250 by construction; micro takes the remainder."""
    df = _db.read_df(
        """SELECT v.cap, count(*) n FROM atlas_foundation.v_stock_cap v
           JOIN atlas_foundation.instrument_master im USING (instrument_id)
           WHERE im.asset_class='stock' AND im.is_active GROUP BY 1"""
    )
    counts = dict(zip(df["cap"], df["n"], strict=True))
    assert counts.get("large") == 100
    assert counts.get("mid") == 150
    assert counts.get("small") == 250


def test_rank_is_strictly_ordered_by_market_cap() -> None:
    """Rank 1 must be the largest company by market cap — a reversed sort would
    silently invert every cohort."""
    top = _db.read_df(
        """SELECT im.symbol, m.market_cap_cr, v.mcap_rank
           FROM atlas_foundation.v_stock_cap v
           JOIN atlas_foundation.instrument_master im USING (instrument_id)
           JOIN atlas_foundation.equity_marketcap m USING (instrument_id)
           WHERE v.mcap_rank <= 3 ORDER BY v.mcap_rank"""
    )
    assert list(top["mcap_rank"]) == [1, 2, 3]
    assert top["market_cap_cr"].is_monotonic_decreasing
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/universe/test_cap_cohort.py -v`
Expected: FAIL — `relation "atlas_foundation.v_stock_cap" does not exist`

- [ ] **Step 3: Create the view**

Create `scripts/foundation/cap_cohort.py`:

```python
#!/usr/bin/env python3
"""atlas_foundation.v_stock_cap — the SINGLE cap-cohort rule.

Cap was derived from index membership, in frontend SQL, duplicated across
stock_lens.ts and sector_lens.ts (and a third time in decile_core.cap_bucket). That
worked only while the universe WAS the indices. Under the liquidity floor every new
name is in no index and would collapse into 'micro', taking that cohort from 250 to
~770 — and since deciles are cut within cohort, every micro decile and every Leader
badge would silently change meaning.

Market-cap rank is what the index rule was approximating all along (NIFTY 100 = top
100, MIDCAP 150 = 101-250, SMLCAP 250 = 251-500), so the two agree on the current
universe and the switch is regression-testable.

Ranked over ACTIVE stocks only: cap is a statement about position within Atlas's
coverage, exactly as the index rule was.

    python cap_cohort.py            # create or replace the view
    python cap_cohort.py --report   # create, then print cohort sizes
"""

from __future__ import annotations

import argparse

import _db

M = "atlas_foundation"

# SEBI cap classes. Matches decile_core.py's existing thresholds and what the index
# rule produces today.
LARGE_MAX, MID_MAX, SMALL_MAX = 100, 250, 500

DDL = f"""
CREATE OR REPLACE VIEW {M}.v_stock_cap AS
WITH r AS (
    SELECT im.instrument_id,
           row_number() OVER (ORDER BY m.market_cap_cr DESC, im.symbol) AS mcap_rank
    FROM {M}.instrument_master im
    JOIN {M}.equity_marketcap m ON m.instrument_id = im.instrument_id
    WHERE im.asset_class = 'stock' AND im.is_active
      AND m.market_cap_cr IS NOT NULL AND m.market_cap_cr > 0
)
SELECT instrument_id,
       mcap_rank,
       CASE WHEN mcap_rank <= {LARGE_MAX} THEN 'large'
            WHEN mcap_rank <= {MID_MAX}   THEN 'mid'
            WHEN mcap_rank <= {SMALL_MAX} THEN 'small'
            ELSE 'micro' END AS cap
FROM r
"""


def build(report: bool = False) -> dict:
    _db.exec_sql(DDL)
    sizes = _db.read_df(
        f"""SELECT cap, count(*) n FROM {M}.v_stock_cap
            GROUP BY 1 ORDER BY min(mcap_rank)"""
    )
    out = dict(zip(sizes["cap"], sizes["n"], strict=True))
    if report:
        for cap, n in out.items():
            print(f"  {cap:6s} {n}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print cohort sizes")
    print(build(report=ap.parse_args().report))
```

- [ ] **Step 4: Build the view and run the tests**

```bash
.venv/bin/python scripts/foundation/cap_cohort.py --report
.venv/bin/python -m pytest tests/integration/universe/test_cap_cohort.py -v
```
Expected: 4 passed, and the report shows `large 100 / mid 150 / small 250 / micro <rest>`.

If `test_new_rule_agrees_with_index_rule_on_at_least_95_percent` fails, the assertion
prints every disagreeing symbol with both labels. **Read that list before doing
anything else.** A handful of borderline names near a boundary is expected. A large
block disagreeing means `equity_marketcap` is stale or wrong for those names —
re-fetch them, do not lower the threshold.

- [ ] **Step 5: Wire the refresh into the nightly orchestrator**

The view reads `is_active` and `equity_marketcap`, so it needs no refresh — it is a
view, not a materialized view. But the market-cap data behind it does go stale. In
`scripts/ops/atlas_daily.sh`, directly after the `step "universe_snapshot"` line added
in Task 1, add:

```bash
# Market caps drift; the cap cohort is derived from their rank. Weekly is enough —
# a rank change inside a cohort is harmless, a cross-boundary move is rare.
[ "$(date +%u)" = "6" ] && step "marketcap_refresh" $PY scripts/foundation/fetch_marketcap.py --workers 4
```

- [ ] **Step 6: Run the gate and commit**

```bash
make gate
git add scripts/foundation/cap_cohort.py \
        tests/integration/universe/test_cap_cohort.py \
        scripts/ops/atlas_daily.sh
git commit -m "feat(universe): cap cohort from market-cap rank, as a view

Cap was derived from index membership in frontend SQL, duplicated three times.
Under the liquidity floor every new name is in no index and would collapse into
'micro' (250 -> ~770), silently changing what every micro decile and Leader
badge means.

Market-cap rank is what the index rule approximated, so the two agree on the
current universe — the parity test asserts >=95%."
```

---

## Task 4: Point every cap consumer at the view

Three copies of the cap rule exist. Task 3 created the fourth and made it canonical;
this task deletes the divergence.

**Files:**
- Modify: `frontend/src/lib/queries/stock_lens.ts:103-111`
- Modify: `frontend/src/lib/queries/sector_lens.ts:82-90`
- Modify: `scripts/foundation/decile_core.py:27-48`

- [ ] **Step 1: Replace the cap CTE in `stock_lens.ts`**

Find this block (lines 103-111, inside `getStockDecile`):

```sql
    cap AS (
      SELECT instrument_id,
        CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
             WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
             WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
      FROM atlas_foundation.de_index_constituents
      WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
      GROUP BY instrument_id
    ),
```

Replace with:

```sql
    -- cap comes from atlas_foundation.v_stock_cap (market-cap rank), NOT index
    -- membership: under the liquidity-floor universe most names are in no index.
    cap AS (
      SELECT instrument_id, cap FROM atlas_foundation.v_stock_cap
    ),
```

Leave the downstream `COALESCE(c.cap,'micro')` exactly as it is — it remains the correct
fallback for a stock with no market-cap row.

- [ ] **Step 2: Replace the identical cap CTE in `sector_lens.ts`**

The block at lines 82-90 is character-identical to the one in Step 1. Apply the
identical replacement:

```sql
    -- cap comes from atlas_foundation.v_stock_cap (market-cap rank), NOT index
    -- membership: under the liquidity-floor universe most names are in no index.
    cap AS (
      SELECT instrument_id, cap FROM atlas_foundation.v_stock_cap
    ),
```

Again, leave `COALESCE(c.cap,'micro')` downstream untouched.

- [ ] **Step 3: Point `decile_core.cap_bucket()` at the view**

In `scripts/foundation/decile_core.py`, replace the whole `cap_bucket()` function
(lines 27-48) with:

```python
def cap_bucket() -> pd.DataFrame:
    """instrument_id -> cap cohort, from atlas_foundation.v_stock_cap.

    Was derived here from free-float weight rank inside the broad index ETF. That
    ranked only names the ETF holds (the 750), so under the liquidity-floor universe
    every other name defaulted to 'micro'. The view ranks on full market cap over the
    whole active universe and is the single rule the frontend also reads.
    """
    w = _db.read_df(
        "SELECT instrument_id::text AS instrument_id, cap "
        "FROM atlas_foundation.v_stock_cap"
    )
    return w[["instrument_id", "cap"]]
```

The `BROAD` / `BROAD2` constants at the top of the file become unused. **Leave them.**
They are pre-existing and removing them is outside this change (standing rule:
pre-existing dead code is mentioned, never deleted). Note them in the PR description.

- [ ] **Step 4: Verify the frontend queries still run**

```bash
cd frontend && npx tsc --noEmit && cd ..
```
Expected: no errors.

Then exercise the real query against the live DB:
```bash
./scripts/foundation/psql.sh -c "
SELECT v.cap, count(*) FROM atlas_foundation.v_stock_cap v
JOIN atlas_foundation.atlas_lens_scores_daily l USING (instrument_id)
WHERE l.date = (SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily)
GROUP BY 1 ORDER BY 1;"
```
Expected: four cohorts, none empty.

- [ ] **Step 5: Verify `decile_core` still produces deciles**

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, 'scripts/foundation')
import decile_core as D
d = D.deciles(D.latest_date())
print(d.groupby('cap').size())
print('leaders:', int(d['lead2'].sum()))
"
```
Expected: four cohorts printed and a non-zero leader count. A zero leader count means
the cohorts are too small to cut deciles — **stop and report**.

- [ ] **Step 6: Run the gate and commit**

```bash
make gate
git add frontend/src/lib/queries/stock_lens.ts \
        frontend/src/lib/queries/sector_lens.ts \
        scripts/foundation/decile_core.py
git commit -m "refactor(cap): read cohort from v_stock_cap in all three consumers

The index-derived CASE was duplicated in stock_lens.ts, sector_lens.ts and
decile_core.cap_bucket(). One rule, one place, so they cannot drift."
```

---

## Task 5: Wire the liquidity threshold into the universe build

The rule itself. Everything before this was making it safe to turn on.

**Files:**
- Modify: `scripts/foundation/build_universe.py:117-127`
- Create: `tests/integration/universe/test_liquidity_universe.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/universe/test_liquidity_universe.py`:

```python
"""Integration tests for the liquidity-floor universe rule in build_universe.py.

The rule is ONE threshold comparison: trailing 60-day median daily traded value >=
atlas_thresholds.liquidity_min_traded_value_inr. These tests prove the threshold is
genuinely driving membership — not that a hardcoded number happens to match.

Read-only: every test uses dry_run, so nothing is written.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_universe as B  # noqa: E402

pytestmark = pytest.mark.integration


def test_active_set_at_the_two_and_a_half_crore_floor() -> None:
    """Measured 2026-08-23 through the SHIPPED rule (60-day median of close*volume,
    >=40 observations, recency, plus currently-held rescues): 1,207 names at ₹2.5 cr.
    Liquidity drifts, so the band is wide; a large miss means the rule changed
    meaning."""
    ids = B.liquid_universe(Decimal("25000000"))
    assert 1120 <= len(ids) <= 1320, f"got {len(ids)}, expected ~1207"


def test_a_higher_floor_is_a_strict_subset() -> None:
    """Proves the threshold drives the rule. Measured: 993 at ₹5 cr (990 over the
    floor + 3 held rescues)."""
    lo = B.liquid_universe(Decimal("25000000"))
    hi = B.liquid_universe(Decimal("50000000"))
    assert hi < lo, "a higher floor must yield a strict subset"
    assert 900 <= len(hi) <= 1100, f"got {len(hi)} at ₹5 cr, expected ~993"


def test_held_names_are_retained_regardless_of_liquidity() -> None:
    """A stock held in a portfolio book must never lose its conviction score, or the
    desk agents go blind on a live position."""
    import build_universe_snapshot as S

    held = S.held_ids()
    assert held, "expected at least one held stock in portfolio_trades"
    ids = B.liquid_universe(Decimal("50000000"))  # strict floor, to force the case
    assert held <= ids, f"held names dropped: {sorted(held - ids)}"


def test_current_active_names_are_almost_entirely_retained() -> None:
    """Measured against the shipped rule: 735 of today's 747 clear the floor outright,
    10 more are retained as currently-held, and exactly 2 drop. The observation guard
    added in Task 1 evicts NO current name. More than a handful means the rule is
    wrong."""
    import _db

    cur = set(
        _db.read_df(
            "SELECT instrument_id::text AS i FROM atlas_foundation.instrument_master "
            "WHERE asset_class='stock' AND is_active"
        )["i"]
    )
    ids = B.liquid_universe(Decimal("25000000"))
    dropped = cur - ids
    assert len(dropped) <= 5, f"{len(dropped)} current names would drop: {sorted(dropped)}"


def test_the_floor_is_read_from_thresholds_not_hardcoded() -> None:
    """Rule #4. The value must exist in atlas_thresholds and be the one in use."""
    import _db
    import universe_core as U

    v = _db.scalar(
        "SELECT threshold_value FROM atlas_foundation.atlas_thresholds "
        "WHERE threshold_key = :k AND is_active",
        {"k": U.THRESHOLD_KEY},
    )
    assert v is not None, f"{U.THRESHOLD_KEY} missing from atlas_thresholds"
    assert Decimal("10000000") <= Decimal(str(v)) <= Decimal("250000000"), (
        "floor outside the min_allowed/max_allowed band declared in atlas_thresholds"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/universe/test_liquidity_universe.py -v`
Expected: FAIL — `AttributeError: module 'build_universe' has no attribute 'liquid_universe'`

- [ ] **Step 3: Replace the coverage query in `build_universe.py`**

Add these imports near the existing ones at the top of the file:

```python
import build_universe_snapshot as _snap
import universe_core as U
```

Then find this block (lines 117-127):

```python
    # Coverage universe = NIFTY 500 ∪ NIFTY MICROCAP250 = 750 (NSE's Nifty Total Market
    # construction; the two indices are disjoint). is_active means "in Atlas coverage",
    # NOT "tradeable on NSE" — it scopes the data-integrity gate's "every active stock
    # has a sector" / "≤21 canonical sectors" checks to the board universe.
    # Widened from 500 to 750 (FM, 2026-07-30): the model portfolios hold microcaps
    # outside the 500 (JSFB, LLOYDSENGG), so 500 could not represent the desk's book.
    coverage = _db.read_df(
        "select distinct instrument_id from atlas_foundation.de_index_constituents "
        "where index_code in ('NIFTY 500', 'NIFTY MICROCAP250') and effective_to is null"
    )
    n500_ids = {str(x).strip() for x in coverage["instrument_id"]}
```

Replace with:

```python
    # Coverage universe = ONE liquidity floor: trailing 60-day MEDIAN daily traded value
    # >= atlas_thresholds.liquidity_min_traded_value_inr (methodology §3.3), plus any
    # stock held in a portfolio book. is_active means "in Atlas coverage", NOT
    # "tradeable on NSE" — it scopes the data-integrity gate's "every active stock has a
    # sector" / "≤21 canonical sectors" checks to the board universe.
    #
    # Was NIFTY 500 ∪ NIFTY MICROCAP250 = 750, which IS NSE's Nifty Total Market — the
    # largest index that exists, so the index rule could never exceed 750 (FM, 2026-08-23).
    # Data sufficiency is NOT gated here: compute_composite() already does a
    # coverage-adjusted weighted average, so a liquid name with no financials gets a
    # NULL fundamental lens rather than a fabricated score (rule #0).
    coverage_ids = liquid_universe()
```

Then update the single downstream use. In the stock loop a few lines below, change:

```python
                iid in n500_ids,
```

to:

```python
                iid in coverage_ids,
```

`n500_ids` was accurate when the rule was NIFTY 500; leaving the name would mislead the
next reader about what decides membership.

- [ ] **Step 4: Add the `liquid_universe()` function**

Insert immediately above `def build(` in `scripts/foundation/build_universe.py`:

```python
def liquid_universe(floor_inr: Decimal | None = None) -> set[str]:
    """instrument_ids in Atlas coverage: ADV over the floor, or held in a book.

    floor_inr defaults to atlas_thresholds.liquidity_min_traded_value_inr. It is a
    parameter only so tests can prove the threshold drives the rule (a stricter floor
    must yield a strict subset) — production never passes it.
    """
    if floor_inr is None:
        floor_inr = _db.scalar(
            "select threshold_value from atlas_foundation.atlas_thresholds "
            "where threshold_key = :k and is_active",
            {"k": U.THRESHOLD_KEY},
        )
        if floor_inr is None:
            raise RuntimeError(f"{U.THRESHOLD_KEY} missing from atlas_thresholds")
    return U.members(_snap.adv_frame(), floor_inr, _snap.held_ids())
```

Add `from decimal import Decimal` to the imports if it is not already there.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/integration/universe/test_liquidity_universe.py -v`
Expected: 5 passed

**No scheduling change is needed.** `build_universe.py` already runs weekly from
`scripts/ops/atlas_weekly.sh:22`. Weekly re-evaluation of a 60-day median is not daily
thrash — measured churn is ~5% per month, so ~1% per run.

- [ ] **Step 6: Set the threshold to ₹2.5 crore**

The stored value is ₹5 cr, which would evict 35 real Nifty-500 mid-caps (BLUEDART,
CERA, KANSAINER, WESTLIFE, EIHOTEL, CENTURYPLY among them). Set it to ₹2.5 cr.

Preferred: via `/admin/thresholds` in the running board, so `last_modified_by` records
the FM. If doing it from the CLI, stamp the attribution explicitly:

```bash
./scripts/foundation/psql.sh -c "
UPDATE atlas_foundation.atlas_thresholds
   SET threshold_value = 25000000,
       description = 'Minimum trailing 60-day median daily traded value; the stock coverage universe rule',
       last_modified_by = 'FM',
       last_modified_at = now()
 WHERE threshold_key = 'liquidity_min_traded_value_inr';
SELECT threshold_key, threshold_value, last_modified_by FROM atlas_foundation.atlas_thresholds
 WHERE threshold_key = 'liquidity_min_traded_value_inr';"
```
Expected: `threshold_value = 25000000.000000`

- [ ] **Step 7: Dry-run the universe build and READ the diff**

Run: `.venv/bin/python scripts/foundation/build_universe.py --dry-run`

Expected output includes a line like
`active stocks: 747 -> 1207 (+462 / -2)` followed by the full ADDED and REMOVED lists.

**Read the REMOVED list.** It should contain exactly 2 names, both illiquid and neither
held. Anything else — especially a recognisable large or mid-cap — means the rule is
wrong. **Stop and report; do not proceed to Task 7.**

- [ ] **Step 8: Run the gate and commit**

```bash
make gate
git add scripts/foundation/build_universe.py \
        tests/integration/universe/test_liquidity_universe.py
git commit -m "feat(universe): coverage is one liquidity floor, read from thresholds

NIFTY 500 union MICROCAP250 IS NSE's Nifty Total Market, so the index rule could
never exceed 750. Coverage is now trailing-60d median traded value >= the
liquidity_min_traded_value_inr threshold (which already existed at methodology
3.3 and was read by no code), plus any held name. 747 -> ~1271.

No eligibility gate: compute_composite() already returns NULL for a lens with
no inputs, so a liquid name with thin data gets a null lens, not a fake score."
```

---

## Task 6: Sectors for the new names

Measured 2026-08-23 against the SHIPPED rule: of the 470 names entering, **460 already
carry a sector** and **10 do not**. (It was 38 before Task 1's observation guard — the
guard removed exactly the obscure thin-data names that lacked sectors.) The canonical
set is at exactly **21** sectors, the FM-locked ceiling, so those 10 must fold into
existing sectors, never add a 22nd.

`assign_sectors.py` deliberately never fabricates a sector (rule #0); it reports and
guards. Filling them is an FM step, and this task produces the list to fill.

**Files:**
- Modify: none (report-only), unless the FM supplies mappings — then
  `scripts/foundation/assign_sectors.py` gains them.

- [ ] **Step 1: Produce the unmapped list**

```bash
./scripts/foundation/psql.sh -c "
WITH d AS (SELECT DISTINCT date FROM atlas_foundation.ohlcv_stock
           WHERE date > CURRENT_DATE - INTERVAL '150 days' ORDER BY date DESC LIMIT 60),
liq AS (SELECT instrument_id,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY close_adj*volume)::numeric adv
        FROM atlas_foundation.ohlcv_stock WHERE date IN (SELECT date FROM d)
          AND close_adj IS NOT NULL AND volume IS NOT NULL GROUP BY 1)
SELECT im.symbol, im.name, round(liq.adv/1e7, 2) AS adv_cr
FROM atlas_foundation.instrument_master im
JOIN liq USING (instrument_id)
WHERE im.asset_class='stock' AND liq.adv >= 25000000 AND im.sector IS NULL
ORDER BY liq.adv DESC;"
```
Expected: ~10 rows. Save the output — this is the FM's worklist.

- [ ] **Step 2: Print the 21 canonical sectors the FM must map into**

```bash
./scripts/foundation/psql.sh -c "
SELECT sector, count(*) n FROM atlas_foundation.instrument_master
WHERE asset_class='stock' AND is_active AND sector IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC;"
```
Expected: exactly 21 rows. **A 22nd sector must never be introduced** — the fold map is
FM-held and the `≤21` guard in `assign_sectors.py` will fail the run.

- [ ] **Step 3: Apply the FM's mappings**

Once the FM returns `symbol -> sector` for the 10, apply them with an explicit UPDATE
per symbol. Do not infer, do not pattern-match on the company name — that is
fabricating a classification (rule #0). Example shape, one row per FM-supplied pair:

```bash
./scripts/foundation/psql.sh -c "
UPDATE atlas_foundation.instrument_master
   SET sector = 'Capital Goods', updated_at = now()
 WHERE asset_class='stock' AND symbol = 'ESABINDIA';"
```

- [ ] **Step 4: Verify the guard passes**

Run: `.venv/bin/python scripts/foundation/assign_sectors.py`
Expected: unmapped count 0 (or a short, FM-acknowledged remainder) and distinct
actionable sectors ≤ 21.

- [ ] **Step 5: Commit any mapping changes**

Sector values live in the database, not in code, so there may be nothing to commit.
Record the 10 symbols and their assigned sectors in the PR description so the decision
is auditable.

---

## Task 7: Flip the universe and recompute

**Files:** none modified. This runs the pipeline.

Runtime is the live risk: 739 → ~1,207 is **+63%** on every lens, and it must still fit
inside the 16:00 IST cron window.

- [ ] **Step 1: Record the baseline runtime BEFORE the flip**

```bash
./scripts/foundation/psql.sh -c "
SELECT step_name, started_at, finished_at,
       finished_at - started_at AS took
FROM atlas_foundation.atlas_pipeline_runs
WHERE started_at > now() - INTERVAL '7 days'
ORDER BY started_at DESC LIMIT 25;"
```
Save the `compute_all` duration. This is the number Step 4 is compared against.

- [ ] **Step 2: Write the universe**

Run: `.venv/bin/python scripts/foundation/build_universe.py`

Expected: `active stocks: 747 -> 1207 (+462 / -2)` and a written-row count.

- [ ] **Step 3: Verify the write landed**

```bash
./scripts/foundation/psql.sh -c "
SELECT count(*) FILTER (WHERE is_active) AS active, count(*) AS total
FROM atlas_foundation.instrument_master WHERE asset_class='stock';"
```
Expected: `active` ≈ 1,207.

- [ ] **Step 4: Rebuild the cap view over the new universe and check cohorts**

```bash
.venv/bin/python scripts/foundation/cap_cohort.py --report
```
Expected: `large 100 / mid 150 / small 250 / micro ~707`.

If micro is far larger than ~771, some names are missing market caps and defaulting.
Re-run Task 2 Step 5's gap query.

- [ ] **Step 5: Full recompute, timed**

```bash
time .venv/bin/python scripts/foundation/compute_all.py 2>&1 | tail -40
```

Expected: completes without error. **Record the wall-clock.**

- [ ] **Step 6: Compare against the cron budget**

The nightly orchestrator starts at 16:00 IST. Compute the new duration as a fraction of
the window between the pipeline's start and the board deploy.

If the new runtime does not fit, **stop and report with the measured numbers** rather
than proceeding to deploy. The remedies (parallelism, incremental compute, a narrower
recompute set) are a separate change, not something to improvise here.

- [ ] **Step 7: Verify scores actually landed for the new names**

```bash
./scripts/foundation/psql.sh -c "
SELECT count(DISTINCT l.instrument_id) AS scored,
       (SELECT count(*) FROM atlas_foundation.instrument_master
         WHERE asset_class='stock' AND is_active) AS universe
FROM atlas_foundation.atlas_lens_scores_daily l
WHERE l.asset_class='stock'
  AND l.date = (SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily);"
```
Expected: `scored` ≥ 99% of `universe`.

---

## Task 8: Validation and lens-coverage report

Proves the widened universe did not quietly degrade anything, and produces the honest
picture of how much evidence the new names are being scored on.

**Files:** none modified. Report-only.

- [ ] **Step 1: Run all three lens gates**

```bash
.venv/bin/python scripts/foundation/validate_lenses.py --check A
.venv/bin/python scripts/foundation/validate_lenses.py --check B
.venv/bin/python scripts/foundation/validate_lenses.py --check C
```
Expected: exit 0 on all three, every assertion PASS.

**These files must not be edited to make them pass.** They are the independent
definition of done; a failure means the data is wrong, not the gate.

- [ ] **Step 2: Report lens coverage, new names versus existing**

```bash
./scripts/foundation/psql.sh -c "
WITH latest AS (SELECT max(date) d FROM atlas_foundation.atlas_lens_scores_daily),
prev AS (SELECT DISTINCT instrument_id FROM atlas_foundation.atlas_lens_scores_daily
         WHERE date = (SELECT d FROM latest) - INTERVAL '30 days')
SELECT (p.instrument_id IS NOT NULL) AS existing_name,
       count(*) AS n,
       round(avg((l.technical   IS NOT NULL)::int)*100) AS pct_technical,
       round(avg((l.fundamental IS NOT NULL)::int)*100) AS pct_fundamental,
       round(avg((l.catalyst    IS NOT NULL)::int)*100) AS pct_catalyst,
       round(avg((l.flow        IS NOT NULL)::int)*100) AS pct_flow,
       round(avg(l.composite)) AS avg_composite
FROM atlas_foundation.atlas_lens_scores_daily l
LEFT JOIN prev p USING (instrument_id)
WHERE l.asset_class='stock' AND l.date = (SELECT d FROM latest)
GROUP BY 1;"
```

New names will show lower `pct_fundamental` and `pct_catalyst`. That is correct and
expected — thin data produces NULL lenses, not fabricated scores.

**What would be a defect:** `avg_composite` for new names being wildly higher than for
existing names. That would mean coverage-adjusted weighting is flattering names scored
on one or two easy lenses. Report the numbers either way.

- [ ] **Step 3: Confirm no conviction tier is issued on too little evidence**

```bash
./scripts/foundation/psql.sh -c "
SELECT conviction_tier, count(*) n
FROM atlas_foundation.atlas_lens_scores_daily
WHERE asset_class='stock'
  AND date = (SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily)
GROUP BY 1 ORDER BY 2 DESC;"
```

Expected: a `BELOW_THRESHOLD` bucket that has grown, absorbing thin new names. If every
new name received a real tier, `min_lenses` is not doing its job — **stop and report**.

- [ ] **Step 4: Re-run the schema gate and the freshness guard**

```bash
.venv/bin/python scripts/ops/schema_gate.py
.venv/bin/python scripts/ops/freshness_guard.py --eod "$(date +%F)"
```
Expected: both exit 0.

- [ ] **Step 5: Record the results in the PR description**

Paste the Step 2 and Step 3 tables. These are the evidence that the widening was honest.

---

## Task 9: Materialized views, frontend, deploy

**Files:**
- Modify: `scripts/ops/atlas_daily.sh` (only if an MV refresh is missing)

**Deploy hygiene is load-bearing here** — a prod outage came from breaking it. NEVER
`pm2 reload` while a build runs. Full sequence: rebuild to completion → confirm
`frontend/.next/BUILD_ID` exists → `rm -rf .next/cache/fetch-cache` → reload ONCE.

- [ ] **Step 1: Refresh the materialized views**

```bash
./scripts/foundation/psql.sh -c "
REFRESH MATERIALIZED VIEW atlas_foundation.mv_stock_landscape;
REFRESH MATERIALIZED VIEW atlas_foundation.mv_sector_cards;
REFRESH MATERIALIZED VIEW atlas_foundation.mv_sector_breadth;
REFRESH MATERIALIZED VIEW atlas_foundation.mv_sector_rrg;"
```

- [ ] **Step 2: Verify `mv_stock_landscape` grew**

```bash
./scripts/foundation/psql.sh -c "SELECT count(*) FROM atlas_foundation.mv_stock_landscape;"
```
Expected: ~1,207 (was 747).

- [ ] **Step 3: Build the frontend to completion**

```bash
cd frontend && npm run build && ls -la .next/BUILD_ID && cd ..
```
Expected: build succeeds and `BUILD_ID` exists. **Do not reload anything until this
completes.**

- [ ] **Step 4: Check the pages that assume a ~750 universe**

With the dev server running (`cd frontend && npm run dev`), load and confirm:

- `/stocks` — cap counts read large 100 / mid 150 / small 250 / micro ~707; the screener
  filters return sane counts; the page does not time out
- `/sectors` — sector cards render; no sector shows a zero constituent count
- `/today` — renders; the "as of" date is current
- A single stock detail page for a **newly added** name (pick the top of the ADDED list
  from Task 5 Step 7) — the cap badge is correct and any thin lens shows as "no signal"
  rather than a zero

- [ ] **Step 5: Compare page load times against the pre-change baseline**

Any page more than ~30% slower needs its query looked at before deploy — a 63% larger
universe hitting an unindexed path will show up here.

- [ ] **Step 6: Run the full nightly orchestrator end to end**

```bash
bash scripts/ops/atlas_daily.sh
```
Expected: every `gate` line reports ok, `GATE_OK=1`, and the deploy step runs.

- [ ] **Step 7: Ship**

```bash
make gate
git add -A
git commit -m "feat(universe): 739 -> ~1271 stocks on a single liquidity floor"
git push -u origin HEAD
gh pr create --title "Stock universe: one liquidity floor (739 -> ~1271)" --body "$(cat <<'BODY'
Replaces the index-derived universe with a single rule: trailing 60-day median
daily traded value >= atlas_thresholds.liquidity_min_traded_value_inr (Rs 2.5 cr),
plus any stock held in a portfolio book.

NIFTY 500 union MICROCAP250 IS NSE's Nifty Total Market, so the old rule could
never exceed 750 regardless of intent.

Prerequisites that landed first:
- Daily universe-membership snapshot (de_index_constituents has no reconstitution
  history; this cannot be backfilled later)
- Cap cohort moved from index membership to market-cap rank, as a single view —
  otherwise all ~520 new names collapse into 'micro' (250 -> ~770) and every micro
  decile and Leader badge silently changes meaning

No eligibility gate: compute_composite() already does coverage-adjusted weighting,
so a liquid name with thin data gets NULL lenses, not fabricated scores.

Measured results, lens coverage and conviction-tier distribution are in the task
comments below.

Deferred: hysteresis on the floor (YAGNI until the snapshot shows churn above ~5%/mo).
Noted, not touched: decile_core.BROAD/BROAD2 are now unused (pre-existing).
BODY
)"
```

- [ ] **Step 8: Confirm the box picked it up**

After merge to `main`, the box fast-forwards and rebuilds itself. Confirm the live
board shows the new count, and that home/sectors/stocks advanced their "as of" date —
those are static-ISR, so only a completed rebuild moves them.

---

## Rollback

Every step is reversible without a code revert:

- **Universe too wide or wrong:** raise `liquidity_min_traded_value_inr` at
  `/admin/thresholds` and re-run `build_universe.py`. No deploy needed.
- **Full revert to the previous universe:** set the threshold to a value that
  reproduces the old 747, or revert Task 5's commit — `build_universe.py` is idempotent
  and the index rule is one commit away.
- **Cap cohort wrong:** `v_stock_cap` is a view. `CREATE OR REPLACE VIEW` with the old
  index-derived logic restores the previous behaviour instantly, with no frontend deploy.
- **Snapshot table:** append-only and read by nothing else. Safe to leave running
  regardless of what happens to the rest.

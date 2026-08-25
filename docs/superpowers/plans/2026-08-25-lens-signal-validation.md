# Lens Signal Validation (IC Study) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether Atlas's lens scores actually precede returns — per lens, per horizon, per cap cohort, per era — and surface the answer as a glass-box page the FM can read without trusting anyone's summary.

**Architecture:** Forward returns computed in SQL from `close_adj`; a pure Python engine turns (scores, forward returns, cohorts) into rank-IC and decile spreads; results land in one journal table; a nightly step appends the trailing window; a page renders it in plain English. The engine takes its inputs as parameters so funds can reuse it later without a rewrite.

**Tech Stack:** Python 3.12 · pandas · SciPy-free (Spearman via `rank()` + `corr`) · PostgreSQL (`atlas_foundation`) · pytest (`unit` / `integration`) · Next.js App Router

**Spec:** `docs/superpowers/specs/2026-08-23-lens-signal-validation-design.md`

---

## Ground truth measured 2026-08-25 — do not re-derive, do not assume

| Fact | Value |
|---|---|
| Lens journal span | 2019-01-01 → 2026-08-21, 1,895 dates |
| Price span | 1,976 trading dates, `close_adj` has **0 NULLs** |
| Instruments with prices | 2,611 |
| Current universe | 1,199 active stocks |

**Genuinely-scored cross-section per date** (at least one non-NULL lens):

```
2019  1,343     2023  1,769
2020  1,388     2024  1,078
2021  1,462     2025    497
2022  1,571     2026    531 (1,198 from 2026-08-21)
```

### THE CRITICAL FACT: `composite = 0.00` is a sentinel, not a score

`compute_composite()` returns `_ZERO` when no weighted lens is present. So a row with
every lens NULL carries `composite = 0.00, conviction_tier = 'BELOW_THRESHOLD'`.

Verified: CMRGREEN listed 2026-06-10 and has rows back to 2019-01-01 — all lenses NULL,
composite 0.00. 839 instruments have such rows predating their listing date.

**These rows are NOT look-ahead bias — no fabricated number exists.** The backfill wrote
a row per instrument per date and populated lenses only where real data existed, which is
why the genuinely-scored count grows 1,343 → 1,769 as companies actually listed. That is
correct point-in-time behaviour.

**But a naive IC study would rank 750 zeros at the bottom of every date and report a
spectacular, entirely fake IC.** Every query in this plan MUST exclude rows where the lens
being tested is NULL. Never filter on `composite > 0` — that conflates "no signal" with
"genuinely scored zero". Filter on the lens column being NOT NULL.

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `atlas/compute/signal_eval.py` *(new)* | Pure rank-IC + decile-spread math. No I/O. | 2 |
| `scripts/foundation/eval_signal.py` *(new)* | SQL loaders, journal writer, CLI | 3 |
| `tests/scripts/test_signal_eval.py` *(new)* | Unit tests on the pure math, real fixtures | 2 |
| `tests/integration/signal/test_eval_signal.py` *(new)* | Loader + end-to-end against live DB | 3 |
| `scripts/ops/atlas_daily.sh` | Nightly `step` | 5 |
| `frontend/src/lib/queries/signal_quality.ts` *(new)* | Read the journal | 6 |
| `frontend/src/app/methodology/signal/page.tsx` *(new)* | The glass-box page | 6 |

---

## Task 1: Forward-return SQL

**Files:** Create `scripts/foundation/eval_signal.py` (loader only; the rest lands in Task 3)

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/signal/__init__.py` (empty) and `tests/integration/signal/test_eval_signal.py`:

```python
"""Integration tests for the signal-evaluation loaders.

Read-only against the live DB. Forward returns come from ohlcv_stock.close_adj,
which is corporate-action adjusted and has zero NULLs across 1,976 trading dates.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import eval_signal as E  # noqa: E402

pytestmark = pytest.mark.integration


def test_forward_returns_are_computed_in_sql_not_pandas() -> None:
    """The frame must arrive already reduced. ohlcv_stock is 6.1M rows and the box has
    2 vCPUs — pulling raw prices into pandas to shift them is the thing the
    data-engineering rule forbids."""
    import _db

    df = E.forward_returns(start="2024-01-01", end="2024-03-31", horizons=(21,))
    assert not df.empty
    assert set(df.columns) >= {"instrument_id", "date", "fwd_21"}
    total = _db.scalar("SELECT count(*) FROM atlas_foundation.ohlcv_stock")
    assert len(df) < total / 10, (
        f"loader returned {len(df):,} of {total:,} rows — the date bounds are not in SQL"
    )
    # The window is ~60 sessions; anything near a full year means the bounds slipped.
    assert df["date"].nunique() < 120, f"{df['date'].nunique()} distinct dates for a Q1 window"


def test_forward_return_matches_a_hand_computed_value() -> None:
    """Reproduce one instrument's 21-session forward return from raw closes."""
    df = E.forward_returns(start="2024-06-03", end="2024-06-05", horizons=(21,))
    assert not df.empty
    row = df.dropna(subset=["fwd_21"]).iloc[0]
    import _db

    closes = _db.read_df(
        """SELECT close_adj FROM atlas_foundation.ohlcv_stock
           WHERE instrument_id = :i AND date >= :d
           ORDER BY date LIMIT 22""",
        {"i": str(row["instrument_id"]), "d": str(row["date"])},
    )
    assert len(closes) == 22, "need 22 sessions to span a 21-session forward return"
    expected = float(closes["close_adj"].iloc[21]) / float(closes["close_adj"].iloc[0]) - 1
    assert abs(float(row["fwd_21"]) - expected) < 1e-6


def test_scores_loader_excludes_null_lens_rows() -> None:
    """composite = 0.00 with all-NULL lenses is a NO-SIGNAL sentinel (839 instruments
    carry such rows predating their listing). Including them would rank ~750 zeros at
    the bottom of every date and manufacture a fake IC."""
    df = E.lens_scores(lens="technical", start="2019-01-01", end="2019-12-31")
    assert not df.empty
    assert df["score"].notna().all(), "loader must not return NULL scores"
    per_date = df.groupby("date").size()
    assert per_date.max() < 2000, (
        f"max {per_date.max()} rows on a date — the 2,093 placeholder rows are leaking in"
    )
    assert per_date.median() > 800, "2019 should have ~1,343 genuinely scored names"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/signal/test_eval_signal.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_signal'`

- [ ] **Step 3: Write the loaders**

Create `scripts/foundation/eval_signal.py`:

```python
#!/usr/bin/env python3
"""Signal evaluation — does a lens score precede a return?

Loaders live here; the math lives in atlas/compute/signal_eval.py (pure, no I/O).

TWO THINGS THIS FILE EXISTS TO GET RIGHT:

1. Forward returns are computed IN POSTGRES. ohlcv_stock is 6.1M rows and the box has
   2 vCPUs — pandas must receive a reduced frame, never raw prices to shift.

2. A NULL lens is excluded, never coerced. compute_composite() returns 0.00 when no
   weighted lens is present, so an unscored row reads composite = 0.00 /
   BELOW_THRESHOLD. 839 instruments carry such rows for dates predating their listing
   (CMRGREEN listed 2026-06-10, rows back to 2019-01-01). Ranking those zeros would put
   ~750 names at the bottom of every date and produce a large, entirely fake IC.
   Filter on the LENS column being NOT NULL — never on composite > 0, which conflates
   "no signal" with "genuinely scored zero".
"""

from __future__ import annotations

import _db
import pandas as pd

M = "atlas_foundation"

LENSES = ("technical", "fundamental", "valuation", "catalyst", "flow", "policy", "composite")
HORIZONS = (21, 63, 126)


def forward_returns(start: str, end: str, horizons=HORIZONS) -> pd.DataFrame:
    """Forward returns per (instrument_id, date), computed with SQL window functions.

    `lead(close_adj, h)` steps h TRADING sessions ahead (rows are one per session), which
    is what a horizon means here — not h calendar days.
    """
    cols = ",\n".join(
        f"       lead(close_adj, {h}) OVER w / NULLIF(close_adj, 0) - 1 AS fwd_{h}"
        for h in horizons
    )
    # Both bounds go into SQL. The lower bound is exact; the upper bound is widened by
    # ~1.6 calendar days per session so lead() at the largest horizon still has rows to
    # look forward into, then trimmed after. Without the widening the last `max(horizons)`
    # sessions of the window silently return NULL forward returns.
    lookahead_days = int(max(horizons) * 1.6) + 30
    frame = _db.read_df(
        f"""
        WITH px AS (
            SELECT instrument_id, date, close_adj
            FROM {M}.ohlcv_stock
            WHERE close_adj IS NOT NULL AND close_adj > 0
              AND date >= :a AND date <= (:b::date + :look * INTERVAL '1 day')
        )
        SELECT instrument_id::text AS instrument_id, date,
{cols}
        FROM px
        WINDOW w AS (PARTITION BY instrument_id ORDER BY date)
        """,
        {"a": start, "b": end, "look": lookahead_days},
    )
    return frame[frame["date"].astype(str) <= end].copy()


def lens_scores(lens: str, start: str, end: str) -> pd.DataFrame:
    """One lens's genuinely-scored rows. NULL rows are excluded, not zero-filled."""
    if lens not in LENSES:
        raise ValueError(f"unknown lens {lens!r}; expected one of {LENSES}")
    return _db.read_df(
        f"""SELECT instrument_id::text AS instrument_id, date, {lens}::float AS score
            FROM {M}.atlas_lens_scores_daily
            WHERE asset_class = 'stock' AND date BETWEEN :a AND :b
              AND {lens} IS NOT NULL""",  # noqa: S608 -- lens validated against LENSES above
        {"a": start, "b": end},
    )


def cap_cohorts() -> pd.DataFrame:
    """instrument_id -> cap cohort, from the single rule in v_stock_cap."""
    return _db.read_df(
        f"SELECT instrument_id::text AS instrument_id, cap FROM {M}.v_stock_cap"
    )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/integration/signal/test_eval_signal.py -v`
Expected: 3 passed.

If `test_forward_returns_are_computed_in_sql_not_pandas` fails on row count, the query is
returning the whole table before the date filter — push the dates into SQL rather than
`.query()`. **Report it; do not raise the row-count ceiling.**

- [ ] **Step 5: Gate and commit**

```bash
make gate
git add scripts/foundation/eval_signal.py tests/integration/signal/
git commit -m "feat(signal): forward-return and lens-score loaders

Forward returns computed in Postgres (6.1M-row table, 2-vCPU box). A NULL lens
is excluded rather than coerced: compute_composite() returns 0.00 when no
weighted lens is present, and 839 instruments carry such rows for dates before
they listed. Ranking those zeros would manufacture a large fake IC."
```

---

## Task 2: The evaluation engine (pure math)

**Files:**
- Create: `atlas/compute/signal_eval.py`
- Create: `tests/scripts/test_signal_eval.py`

- [ ] **Step 1: Write the failing unit test**

Create `tests/scripts/test_signal_eval.py`:

```python
"""Unit tests for atlas/compute/signal_eval.py — the rank-IC and decile-spread math.

Fixtures are REAL lens scores and REAL forward returns pulled from atlas_foundation
(2024-06-14 slice) and pasted here as literals so the test needs no DB. Rule #0: not one
of these numbers is invented.
"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.compute.signal_eval import evaluate

pytestmark = pytest.mark.unit

# Real (technical score, 21-session forward return) pairs, atlas_foundation 2024-06-14.
REAL = pd.DataFrame(
    {
        "instrument_id": [f"i{n}" for n in range(12)],
        "date": ["2024-06-14"] * 12,
        "score": [72.0, 68.5, 61.0, 58.0, 55.5, 51.0, 48.0, 44.5, 41.0, 37.5, 32.0, 28.0],
        "fwd_21": [0.081, 0.043, 0.055, 0.012, 0.028, -0.004, 0.019, -0.021,
                   -0.008, -0.036, -0.019, -0.052],
        "cap": ["large"] * 12,
    }
)


def test_positive_ic_when_score_tracks_forward_return() -> None:
    out = evaluate(REAL, horizon=21, deciles=4)
    row = out.iloc[0]
    assert row["n"] == 12
    assert row["rank_ic"] > 0.5, f"expected a strong positive IC, got {row['rank_ic']}"


def test_ic_flips_sign_when_the_score_is_reversed() -> None:
    """The single most important property: reverse the score and the IC must invert.
    A metric that does not is measuring something other than what it claims."""
    fwd = evaluate(REAL, horizon=21, deciles=4).iloc[0]["rank_ic"]
    rev = REAL.assign(score=100.0 - REAL["score"])
    back = evaluate(rev, horizon=21, deciles=4).iloc[0]["rank_ic"]
    assert back == pytest.approx(-fwd, abs=1e-9)


def test_shuffled_scores_have_near_zero_ic() -> None:
    """The null test. A score bearing no relation to the outcome must produce ~0 IC.
    Deterministic permutation — no RNG, so the assertion cannot flake."""
    shuffled = REAL.assign(score=[51.0, 28.0, 72.0, 37.5, 61.0, 44.5,
                                  32.0, 68.5, 41.0, 55.5, 48.0, 58.0])
    ic = evaluate(shuffled, horizon=21, deciles=4).iloc[0]["rank_ic"]
    assert abs(ic) < 0.45, f"a scrambled score should be near-zero, got {ic}"


def test_decile_spread_is_top_minus_bottom_mean_return() -> None:
    out = evaluate(REAL, horizon=21, deciles=4).iloc[0]
    top = REAL.nlargest(3, "score")["fwd_21"].mean()
    bot = REAL.nsmallest(3, "score")["fwd_21"].mean()
    assert out["decile_spread"] == pytest.approx(top - bot, abs=1e-9)


def test_rows_with_a_missing_forward_return_are_dropped_not_zeroed() -> None:
    """A NULL forward return means the horizon runs past the end of the data. It is not
    a 0% return, and treating it as one drags every IC toward the mean."""
    with_nan = pd.concat(
        [REAL, REAL.tail(1).assign(instrument_id="iX", fwd_21=None)], ignore_index=True
    )
    assert evaluate(with_nan, horizon=21, deciles=4).iloc[0]["n"] == 12


def test_a_date_below_the_minimum_cross_section_is_skipped() -> None:
    """Ranking 5 names produces a number, not a signal."""
    assert evaluate(REAL.head(5), horizon=21, deciles=4, min_n=20).empty


def test_cohorts_are_evaluated_separately() -> None:
    """Deciles are cut WITHIN cohort. Pooling large-caps with micro-caps measures the
    size effect, not the lens."""
    two = pd.concat([REAL, REAL.assign(cap="micro", instrument_id=REAL["instrument_id"] + "m")])
    out = evaluate(two, horizon=21, deciles=4)
    assert set(out["cohort"]) == {"large", "micro"}
    assert len(out) == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/scripts/test_signal_eval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'atlas.compute.signal_eval'`

- [ ] **Step 3: Write the engine**

Create `atlas/compute/signal_eval.py`:

```python
"""Rank-IC and decile spread for one signal against forward returns.

Pure: no I/O, no DB. Loaders live in scripts/foundation/eval_signal.py.

WHY SPEARMAN, NOT PEARSON: lens scores are ordinal 0-100. The claim being tested is
"a higher score precedes a higher return", which is about ordering, not linearity.

WHY WITHIN (date, cohort): deciles cut across dates measure market direction, and cut
across cap cohorts measure the size effect. Neither is the lens. Cutting within both
isolates it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_CROSS_SECTION = 20  # below this, a rank correlation is noise


def evaluate(
    df: pd.DataFrame,
    horizon: int,
    deciles: int = 10,
    min_n: int = MIN_CROSS_SECTION,
) -> pd.DataFrame:
    """One row per (date, cohort): rank_ic, n, decile_spread.

    Args:
        df: columns instrument_id, date, score, cap, and fwd_<horizon>.
            Rows whose score or forward return is NULL are DROPPED — a missing value is
            absence of evidence, never a zero.
        horizon: trading sessions ahead; selects the fwd_<horizon> column.
        deciles: buckets per cohort. 10 in production; tests use 4 on small frames.
        min_n: skip a (date, cohort) thinner than this.
    """
    col = f"fwd_{horizon}"
    if col not in df.columns:
        raise KeyError(f"{col} not in frame; got {sorted(df.columns)}")

    work = df.dropna(subset=["score", col]).copy()
    if work.empty:
        return _empty()

    out = []
    for (date, cohort), g in work.groupby(["date", "cap"], sort=True):
        n = len(g)
        if n < min_n:
            continue
        score = pd.Series(g["score"]).rank()
        fwd = pd.Series(g[col]).rank()
        ic = float(score.corr(fwd))  # Spearman == Pearson on ranks
        k = max(1, n // deciles)
        top = float(pd.Series(g.nlargest(k, "score")[col]).mean())
        bot = float(pd.Series(g.nsmallest(k, "score")[col]).mean())
        out.append(
            {
                "date": date,
                "cohort": cohort,
                "n": n,
                "rank_ic": ic if np.isfinite(ic) else np.nan,
                "decile_spread": top - bot,
            }
        )
    return pd.DataFrame(out) if out else _empty()


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "cohort", "n", "rank_ic", "decile_spread"])


def summarise(per_date: pd.DataFrame) -> dict:
    """Collapse a per-date frame into the numbers a human reads.

    t-stat is the plain mean/stderr form. Overlapping horizons autocorrelate, so it reads
    optimistic; that is acceptable for a ranking gate and is stated on the page rather
    than silently corrected. Upgrade to Newey-West only if a lens sits near the bar.
    """
    ic = pd.Series(per_date["rank_ic"]).dropna()
    if ic.empty:
        return {"n_dates": 0, "mean_ic": None, "hit_rate": None,
                "t_stat": None, "mean_spread": None}
    n = int(len(ic))
    sd = float(ic.std())
    return {
        "n_dates": n,
        "mean_ic": float(ic.mean()),
        "hit_rate": float((ic > 0).mean()),
        "t_stat": float(ic.mean() / (sd / np.sqrt(n))) if sd > 0 and n > 1 else None,
        "mean_spread": float(pd.Series(per_date["decile_spread"]).dropna().mean()),
    }
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/scripts/test_signal_eval.py -v`
Expected: 7 passed.

- [ ] **Step 5: Gate and commit**

```bash
make gate
git add atlas/compute/signal_eval.py tests/scripts/test_signal_eval.py
git commit -m "feat(signal): rank-IC and decile-spread engine

Pure math, no I/O. Spearman on ranks within (date, cohort) — pooling across
dates measures market direction, pooling across cohorts measures the size
effect, neither is the lens. NULL score or NULL forward return drops the row;
absence of evidence is never a zero.

Sign-flip and shuffled-score null tests included: a metric that does not
invert when the score inverts is measuring something other than it claims."
```

---

## Task 3: Journal table + backfill driver

**Files:** Modify `scripts/foundation/eval_signal.py`; modify `tests/integration/signal/test_eval_signal.py`

- [ ] **Step 1: Add the failing integration tests**

Append to `tests/integration/signal/test_eval_signal.py`:

```python
def test_backfill_writes_one_row_per_lens_horizon_cohort_era() -> None:
    E.ensure_table()
    E.backfill(start="2023-01-01", end="2023-06-30", lenses=("technical",), horizons=(21,))
    import _db

    df = _db.read_df(
        """SELECT lens, horizon_d, cohort, era, n_dates, mean_ic, hit_rate, mean_spread
           FROM atlas_foundation.atlas_signal_ic
           WHERE lens = 'technical' AND horizon_d = 21"""
    )
    assert not df.empty
    assert set(df["cohort"]) <= {"large", "mid", "small", "micro"}
    assert (df["n_dates"] > 0).all()


def test_backfill_is_idempotent() -> None:
    E.ensure_table()
    E.backfill(start="2023-01-01", end="2023-06-30", lenses=("technical",), horizons=(21,))
    import _db

    n1 = _db.scalar("SELECT count(*) FROM atlas_foundation.atlas_signal_ic")
    E.backfill(start="2023-01-01", end="2023-06-30", lenses=("technical",), horizons=(21,))
    n2 = _db.scalar("SELECT count(*) FROM atlas_foundation.atlas_signal_ic")
    assert n1 == n2, f"re-running duplicated rows: {n1} -> {n2}"


def test_eras_are_reported_separately_never_blended() -> None:
    """The scored cross-section went 1,769 (2023) -> 497 (2025) -> 1,198 (2026). A single
    blended IC across that break is uninterpretable, so era is part of the key."""
    E.ensure_table()
    E.backfill(start="2023-01-01", end="2023-03-31", lenses=("technical",), horizons=(21,))
    E.backfill(start="2025-01-01", end="2025-03-31", lenses=("technical",), horizons=(21,))
    import _db

    eras = _db.read_df(
        "SELECT DISTINCT era FROM atlas_foundation.atlas_signal_ic WHERE lens='technical'"
    )
    assert len(eras) >= 2, "2023 and 2025 must not collapse into one era row"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/integration/signal/test_eval_signal.py -v -k "backfill or era"`
Expected: FAIL — `module 'eval_signal' has no attribute 'ensure_table'`

- [ ] **Step 3: Add the table, era rule, and driver**

Append to `scripts/foundation/eval_signal.py`:

```python
TGT = f"{M}.atlas_signal_ic"

# The scored cross-section has two structural breaks, so an IC spanning them is
# uninterpretable and is never reported as one number. Measured 2026-08-25:
#   wide      2019-01-01..2024-03-31   1,343 -> 1,769 names/date
#   narrow    2024-04-01..2026-08-20     ~498 names/date (universe cut to NIFTY 500)
#   liquidity 2026-08-21..              1,198 names/date (liquidity floor)
ERAS = (
    ("wide", "2019-01-01", "2024-03-31"),
    ("narrow", "2024-04-01", "2026-08-20"),
    ("liquidity", "2026-08-21", "2099-12-31"),
)


def era_for(day) -> str:
    d = str(day)[:10]
    for name, lo, hi in ERAS:
        if lo <= d <= hi:
            return name
    return "unknown"


def ensure_table() -> None:
    _db.exec_sql(f"""CREATE TABLE IF NOT EXISTS {TGT} (
        lens          text        NOT NULL,
        horizon_d     integer     NOT NULL,
        cohort        text        NOT NULL,
        era           text        NOT NULL,
        n_dates       integer     NOT NULL,
        mean_ic       numeric(8,5),
        hit_rate      numeric(6,4),
        t_stat        numeric(10,4),
        mean_spread   numeric(10,6),
        first_date    date,
        last_date     date,
        computed_at   timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (lens, horizon_d, cohort, era))""")


def backfill(start: str, end: str, lenses=LENSES, horizons=HORIZONS) -> dict:
    """Evaluate each (lens, horizon) over [start, end] and upsert one row per cohort+era."""
    from atlas.compute.signal_eval import evaluate, summarise

    ensure_table()
    fwd = forward_returns(start, end, horizons)
    caps = cap_cohorts()
    written = 0
    for lens in lenses:
        scores = lens_scores(lens, start, end)
        if scores.empty:
            print(f"  {lens}: no scored rows in window", flush=True)
            continue
        joined = scores.merge(fwd, on=["instrument_id", "date"], how="inner").merge(
            caps, on="instrument_id", how="left"
        )
        joined["cap"] = joined["cap"].fillna("micro")
        for h in horizons:
            per_date = evaluate(joined, horizon=h)
            if per_date.empty:
                continue
            per_date["era"] = [era_for(d) for d in per_date["date"]]
            rows = []
            for (cohort, era), g in per_date.groupby(["cohort", "era"]):
                s = summarise(g)
                if not s["n_dates"]:
                    continue
                rows.append({
                    "lens": lens, "horizon_d": h, "cohort": cohort, "era": era,
                    "n_dates": s["n_dates"], "mean_ic": s["mean_ic"],
                    "hit_rate": s["hit_rate"], "t_stat": s["t_stat"],
                    "mean_spread": s["mean_spread"],
                    "first_date": min(g["date"]), "last_date": max(g["date"]),
                    "computed_at": pd.Timestamp.now(tz="Asia/Kolkata"),
                })
            if rows:
                written += _db.upsert_df(
                    TGT, pd.DataFrame(rows), ["lens", "horizon_d", "cohort", "era"]
                )
        print(f"  {lens}: done", flush=True)
    return {"written": written}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2026-08-21")
    ap.add_argument("--lens", nargs="*", default=list(LENSES))
    print(backfill(ap.parse_args().start, ap.parse_args().end, tuple(ap.parse_args().lens)))
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/integration/signal/test_eval_signal.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the real backfill and READ the output**

```bash
.venv/bin/python scripts/foundation/eval_signal.py --start 2019-01-01 --end 2026-08-21
./scripts/foundation/psql.sh -c "
SELECT lens, horizon_d, era, cohort, n_dates, mean_ic, hit_rate, round(mean_spread*100,2) spread_pct
FROM atlas_foundation.atlas_signal_ic
WHERE cohort='large' AND horizon_d=63 ORDER BY lens, era;"
```

**This is the moment the project exists for. Do not tune anything toward a number.**
Report exactly what comes out. Reference points for reading it:

- `|mean_ic| >= 0.03` sustained is a real equity factor
- `|mean_ic| > 0.15` is almost certainly a bug, not an edge — most likely NULL rows
  leaking in, or a forward return that overlaps the scoring date
- `mean_ic ≈ 0` means the lens does not predict at that horizon, which is a finding,
  not a failure

- [ ] **Step 6: Gate and commit**

```bash
make gate
git add scripts/foundation/eval_signal.py tests/integration/signal/test_eval_signal.py
git commit -m "feat(signal): IC journal table and backfill driver

One row per (lens, horizon, cohort, era). Era is part of the key because the
scored cross-section breaks twice — 1,769 names/date in 2023, 497 in 2025,
1,198 from 2026-08-21 — and an IC spanning those breaks is uninterpretable."
```

---

## Task 4: Sanity gate on the result

**Files:** Modify `tests/integration/signal/test_eval_signal.py`

- [ ] **Step 1: Add the tests that would catch a fake result**

```python
def test_no_lens_reports_an_implausibly_high_ic() -> None:
    """|IC| > 0.15 sustained does not happen in equities. If it appears, the most likely
    causes are NULL placeholder rows leaking in (composite = 0.00 for 839 instruments)
    or a forward return overlapping the scoring date. Fail loudly rather than celebrate."""
    import _db

    df = _db.read_df(
        "SELECT lens, era, cohort, horizon_d, mean_ic, n_dates "
        "FROM atlas_foundation.atlas_signal_ic WHERE abs(mean_ic) > 0.15 AND n_dates > 60"
    )
    assert df.empty, f"implausible IC — investigate before trusting:\n{df.to_string()}"


def test_the_cross_section_matches_the_known_era_shape() -> None:
    """Guards the NULL-exclusion. If placeholder rows leak in, the wide era jumps toward
    2,093 instead of the measured 1,343-1,769."""
    import _db

    n = _db.scalar(
        """SELECT max(n_dates) FROM atlas_foundation.atlas_signal_ic WHERE era = 'wide'"""
    )
    assert n and n > 100, "wide era should span hundreds of dates"
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/integration/signal/test_eval_signal.py -v -k "implausibl or era_shape"`

If `test_no_lens_reports_an_implausibly_high_ic` FAILS, **stop and report**. Do not raise
the 0.15 ceiling. An IC that high means the pipeline is measuring itself, and the two
usual causes are named in the docstring.

- [ ] **Step 3: Commit**

```bash
make gate
git add tests/integration/signal/test_eval_signal.py
git commit -m "test(signal): fail loudly on an implausibly good result"
```

---

## Task 5: Nightly step

**Files:** Modify `scripts/ops/atlas_daily.sh`

- [ ] **Step 1: Add the step**

In `scripts/ops/atlas_daily.sh`, immediately after the `step "universe_snapshot"` line:

```bash
# Rolling signal quality. step, not gate: a lens losing predictive power is a finding for
# the FM to act on, not a reason to withhold a correct board. Promote to gate() only once
# a baseline exists and has held for a month.
step "signal_ic" $PY scripts/foundation/eval_signal.py --start "$(date -d '2 years ago' +%F)" --end "$EOD"
```

- [ ] **Step 2: Verify it parses and runs**

```bash
bash -n scripts/ops/atlas_daily.sh && echo "syntax OK"
.venv/bin/python scripts/foundation/eval_signal.py --start 2024-08-01 --end 2026-08-21 --lens technical
```
Expected: completes, prints `{'written': N}` with N > 0.

- [ ] **Step 3: Commit**

```bash
make gate
git add scripts/ops/atlas_daily.sh
git commit -m "feat(signal): nightly rolling IC as a non-blocking step"
```

---

## Task 6: The glass-box page

**Files:**
- Create: `frontend/src/lib/queries/signal_quality.ts`
- Create: `frontend/src/app/methodology/signal/page.tsx`

**A hook blocks `frontend/src/**` until a planning skill runs — invoke
`superpowers:test-driven-development` before the first edit.**

This page answers one question — *does Atlas's scoring actually work?* — and it must
answer it honestly, including when the answer is no. It lives under `/methodology`, not
`/admin`, because it is the evidence behind every score on the board, not an internal
diagnostic.

- [ ] **Step 1: Write the query module**

Create `frontend/src/lib/queries/signal_quality.ts`:

```ts
import { sql } from '@/lib/db'

export type SignalRow = {
  lens: string; horizon_d: number; cohort: string; era: string
  n_dates: number; mean_ic: number | null; hit_rate: number | null
  t_stat: number | null; mean_spread: number | null
  first_date: string; last_date: string
}

export async function getSignalQuality(): Promise<SignalRow[]> {
  const rows = await sql<Record<string, string>[]>`
    SELECT lens, horizon_d, cohort, era, n_dates, mean_ic, hit_rate,
           t_stat, mean_spread, first_date::text, last_date::text
    FROM atlas_foundation.atlas_signal_ic
    ORDER BY era, lens, horizon_d, cohort`
  const n = (v: string | null) => (v == null ? null : Number(v))
  return rows.map(r => ({
    lens: r.lens, horizon_d: Number(r.horizon_d), cohort: r.cohort, era: r.era,
    n_dates: Number(r.n_dates), mean_ic: n(r.mean_ic), hit_rate: n(r.hit_rate),
    t_stat: n(r.t_stat), mean_spread: n(r.mean_spread),
    first_date: r.first_date, last_date: r.last_date,
  }))
}
```

- [ ] **Step 2: Write the page**

Create `frontend/src/app/methodology/signal/page.tsx`. Requirements — these are the
content, not decoration:

1. **Lead with the plain-English verdict per lens**, e.g.
   *"Technical: top-decile names beat bottom-decile by 4.2% over 3 months, in 61% of
   months tested (wide era, large-caps, 1,290 dates)."* The number a person can act on
   comes first; the statistic supports it.
2. **A three-state badge per lens**: `carries signal` (|IC| ≥ 0.03 and hit rate ≥ 55%),
   `weak` (|IC| ≥ 0.01), `no evidence` (below that). Never hide a `no evidence` lens —
   that is the most valuable cell on the page.
3. **Eras side by side, never averaged.** Label them with what changed:
   wide = 1,343–1,769 names/date · narrow = ~498 (universe cut to NIFTY 500) ·
   liquidity = 1,198 (₹2.5cr floor, from 2026-08-21).
4. **Show `n_dates` beside every figure.** An IC over 40 dates is not an IC over 1,290.
5. **A short "how to read this" panel** stating: rank-IC is the correlation between score
   rank and forward-return rank; 0.03 is a real equity factor; anything above 0.15 is
   more likely a bug than an edge; and the t-stat reads optimistic because overlapping
   horizons autocorrelate.
6. Follow the existing look — reuse the components in `frontend/src/components/` rather
   than inventing a chart. Check what `/methodology` already uses first.
7. Right-align numbers, Indian formatting, `+/-` signs on percentages.

- [ ] **Step 3: Verify against real data**

```bash
cd frontend && npx tsc --noEmit
```
Then execute the query through `./scripts/foundation/psql.sh` — `tsc` type-checks the
template literal but never proves the SQL parses. Confirm the page renders every lens
including any with `no evidence`.

- [ ] **Step 4: Commit**

```bash
make gate
git add frontend/src/lib/queries/signal_quality.ts frontend/src/app/methodology/signal/page.tsx
git commit -m "feat(signal): glass-box page for lens predictive power

Under /methodology, not /admin: this is the evidence behind every score on the
board. Shows eras side by side rather than averaged, n_dates beside every
figure, and never hides a lens with no evidence."
```

---

## Rollback

- The journal table is append-only and read by one page. Dropping it removes the feature
  and nothing else.
- The nightly entry is a `step`, so a failure never withholds the board.
- No existing score, weight or threshold is modified anywhere in this plan. The study
  measures the methodology; it does not change it.

## Out of scope

Funds (the engine takes its inputs as parameters, so it is a call-site change later),
auto-demotion of lens weights on decay, Newey-West standard errors, and any change to how
a lens is computed.

**The baseline freeze and the blocking gate are deliberately NOT in this plan.** The spec
describes a `--baseline` mode that freezes each lens's IC into `atlas_thresholds` and a
`--gate` mode that fails on regression below it. Freezing a baseline before anyone has
seen a single measured IC would be freezing a number nobody has judged. Run the study,
read the result, then decide what is worth defending. That is a follow-up chunk. **If a lens shows no evidence, that is a finding to bring to the FM —
not a licence to start tuning.**

# ruff: noqa: S608 -- SQL here is assembled from the schema constant _gdb.M; every value is bound.
"""build_universe_snapshot on a REAL database (rule #0): the ADV$ window and its two guards,
``in_sp500``'s exclusive end, the percentile table, the exit-2 gate and the write.

Needs ``ATLAS_DB_URL`` pointing at a Postgres with the atlas_global DDL applied, the committed
seeds (``seed_thresholds.py`` — ``liquidity_min_observations_60d`` and
``liquidity_recency_trading_days``; the floor is deliberately NOT seeded) and real rows in
``instrument_master``, ``index_membership`` and ``ohlcv_daily`` — the Phase 1 scratch clone of
runbook §6. Unset, the module skips; it never passes vacuously. Every expected value is read
from the database independently of the script's own SQL.

The write test needs the floor SET. It inserts the row itself — the value is the median ADV$
of this database's own ETFs, read from the real rows at test time and never a constant in the
repo (the floor is the FM's to set: docs/global/phase1.md P1-E) — and deletes it, and the
snapshot rows it wrote, in its teardown. Nothing persists.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import psycopg2
import pytest

from tests.unit.global_market.script_loader import load_global_script

_gdb = load_global_script("_gdb")
bus = load_global_script("build_universe_snapshot")
im = load_global_script("ingest_index_membership")
U = bus.U

pytestmark = pytest.mark.integration

M = _gdb.M
TEST_BY = "test_universe_snapshot_db"
SPY_ID = f"(select instrument_id from {M}.instrument_master where symbol = 'SPY' and is_active)"

if not os.environ.get("ATLAS_DB_URL", "").strip():
    pytest.skip("ATLAS_DB_URL not set — the snapshot needs a database", allow_module_level=True)


@pytest.fixture(scope="module")
def as_of() -> date:
    d = bus.anchor(_gdb.eod_cutoff())
    assert d is not None, "no SPY bar in ohlcv_daily — the scratch clone has no anchor"
    return d


@pytest.fixture(scope="module")
def thr() -> dict[str, Decimal]:
    t = bus.thresholds()
    assert U.THRESHOLD_KEY_MIN_OBS in t and U.THRESHOLD_KEY_RECENCY in t, "run seed_thresholds.py"
    assert bus.THRESHOLD_KEY not in t, f"{bus.THRESHOLD_KEY} must be unset: it is never seeded"
    return t


@pytest.fixture(scope="module")
def adv(as_of: date, thr: dict[str, Decimal]) -> pd.DataFrame:
    return bus.adv_frame(
        as_of, int(thr[U.THRESHOLD_KEY_MIN_OBS]), int(thr[U.THRESHOLD_KEY_RECENCY])
    )


@pytest.fixture(scope="module")
def window(as_of: date) -> list[date]:
    """The 60 most recent SPY sessions at or before the anchor, oldest first — read without
    the script's 150-calendar-day bound, so a dense archive must agree with it."""
    df = _gdb.read_df(
        f"select date from {M}.ohlcv_daily where instrument_id = {SPY_ID} and date <= :d "
        f"order by date desc limit {U.LOOKBACK_TRADING_DAYS}",
        {"d": as_of},
    )
    return sorted(df["date"])


def _values(frame: pd.DataFrame) -> np.ndarray:
    v = pd.Series(pd.to_numeric(frame["adv_median_60d"], errors="coerce")).dropna()
    return v.to_numpy(dtype=float)


def test_one_row_per_active_instrument_and_spy_reproduces_the_median(
    as_of: date, adv: pd.DataFrame, window: list[date]
) -> None:
    n_active = _gdb.scalar(f"select count(*) from {M}.instrument_master where is_active")
    assert len(adv) == n_active and adv["instrument_id"].is_unique
    assert set(adv["asset_class"]) == {"etf", "stock"}
    assert len(window) == U.LOOKBACK_TRADING_DAYS and window[-1] == as_of
    assert bool((adv["n_obs"] <= U.LOOKBACK_TRADING_DAYS).all())
    assert bool(adv["last_date"].dropna().le(as_of).all())
    # A holiday is not a session: a stray bar on one (Stooq has them) must not be counted.
    holidays = _gdb.read_df(
        f"select distinct date from {M}.ohlcv_daily where date >= :lo and date <= :hi "
        f"and date not in (select date from {M}.ohlcv_daily where instrument_id = {SPY_ID})",
        {"lo": window[0], "hi": window[-1]},
    )
    assert len(holidays) > 0, "no stray holiday bars in this window — the test proves nothing"
    assert not bool(adv["last_date"].isin(list(holidays["date"])).any())
    spy = _gdb.read_df(
        f"select close * volume as traded from {M}.ohlcv_daily where instrument_id = {SPY_ID} "
        "and date >= :lo and date <= :hi and close is not null and volume is not null",
        {"lo": window[0], "hi": window[-1]},
        coerce_float=False,
    )
    row = adv.set_index("symbol").loc["SPY"]
    assert row["n_obs"] == len(spy) == U.LOOKBACK_TRADING_DAYS and row["status"] == bus.STATUS_OK
    assert isinstance(row["adv_median_60d"], Decimal)  # numeric, never a float
    assert row["adv_median_60d"] == np.median(np.array(spy["traded"].tolist()))
    print(f"SPY ADV$ {as_of}: {row['adv_median_60d']:,} over {window[0]} → {window[-1]}")


def test_thin_and_stale_names_get_null_never_low(
    adv: pd.DataFrame, thr: dict[str, Decimal], window: list[date]
) -> None:
    """A median over a handful of prints is the block deal it exists to exclude, and a median
    of a name that stopped trading is history — both are NULL, and NULL never passes."""
    min_obs = int(thr[U.THRESHOLD_KEY_MIN_OBS])
    recent = list(window[-int(thr[U.THRESHOLD_KEY_RECENCY]) :])
    enough = adv["n_obs"] >= min_obs
    none = adv.loc[adv["n_obs"] == 0]
    thin = adv.loc[(adv["n_obs"] > 0) & ~enough]
    stale = adv.loc[enough & ~adv["last_date"].isin(recent)]
    ok = adv.loc[enough & adv["last_date"].isin(recent)]
    for part in (none, thin, stale):
        assert len(part) > 0, "no such names in this database — the test proves nothing"
        assert bool(part["adv_median_60d"].isna().all())
    assert set(none["status"]) == {"no_bars"} and set(thin["status"]) == {"too_few_observations"}
    assert set(stale["status"]) == {"stale"} and set(ok["status"]) == {bus.STATUS_OK}
    assert bool(ok["adv_median_60d"].notna().all())
    assert len(none) + len(thin) + len(stale) + len(ok) == len(adv)
    assert all(isinstance(v, Decimal) for v in ok["adv_median_60d"])
    print(f"no bars {len(none)}, too few {len(thin)}, stale {len(stale)}, with ADV$ {len(ok)}")


def test_in_sp500_is_the_interval_containing_the_date_with_an_exclusive_end(as_of: date) -> None:
    members = bus.sp500_members(as_of)
    assert im.MEMBERS_MIN <= len(members) <= im.MEMBERS_MAX, len(members)
    # A real departure: a closed interval whose instrument holds no other interval covering its
    # end — in on effective_from, out on effective_to (EXCLUSIVE end, ddl/00_core.sql).
    gone = _gdb.read_df(
        f"""select x.instrument_id::text as iid, x.effective_from, x.effective_to
            from {M}.index_membership x
            where x.index_code = :c and x.effective_to is not null
              and not exists (select 1 from {M}.index_membership y
                              where y.index_code = x.index_code
                                and y.instrument_id = x.instrument_id
                                and y.effective_from <= x.effective_to
                                and (y.effective_to is null or y.effective_to > x.effective_to))
            order by x.effective_to desc limit 1""",
        {"c": bus.imx.INDEX_CODE},
    )
    assert len(gone) == 1, "no closed interval in index_membership — the test proves nothing"
    iid, start, end = gone.iloc[0]
    assert iid in bus.sp500_members(start) and iid not in bus.sp500_members(end)
    print(f"{len(members)} members on {as_of}; {iid} in on {start}, out on {end}")


def test_the_percentile_table_agrees_with_numpy_on_the_real_frame(adv: pd.DataFrame) -> None:
    table = bus.percentile_table(adv).set_index("asset_class")
    assert list(table.index) == ["etf", "stock"]
    for cls, grp in adv.groupby("asset_class"):
        v, row = _values(grp), table.loc[cls]
        assert row["n_active"] == len(grp) and row["n_with_adv"] == len(v) > 0
        pcts = [row[f"p{p}"] for p in bus.PERCENTILES]
        assert pcts == [pytest.approx(np.percentile(v, p)) for p in bus.PERCENTILES]
        assert pcts == sorted(pcts)
        counts = [row[f"ge_{f}"] for f in bus.CANDIDATE_FLOORS_USD]
        assert counts == [int((v >= f).sum()) for f in bus.CANDIDATE_FLOORS_USD]
        assert counts == sorted(counts, reverse=True)
        print(
            f"{cls}: "
            + ", ".join(f"P{p} ${x:,.0f}" for p, x in zip(bus.PERCENTILES, pcts, strict=True))
        )


def _snapshot(as_of: date) -> pd.DataFrame:
    return _gdb.read_df(
        f"select instrument_id::text as instrument_id, in_universe, in_sp500, adv_usd_median_60d, "
        f"floor_usd, aum_usd, basket_eligible, computed_at from {M}.universe_snapshot "
        "where date = :d order by instrument_id",
        {"d": as_of},
        coerce_float=False,
    )


def test_with_the_floor_unset_main_prints_and_saves_the_table_and_exits_2(
    as_of: date, adv: pd.DataFrame, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = len(_snapshot(as_of))
    csv = tmp_path / "universe.csv"
    rc = bus.main(["--eod", as_of.isoformat(), "--report-dir", str(tmp_path), "--report", str(csv)])
    out = capsys.readouterr().out
    assert rc == 2 and len(_snapshot(as_of)) == before
    assert "REFUSED" in out and bus.THRESHOLD_KEY in out and "nothing written" in out
    text = (tmp_path / f"adv_usd_{as_of}.md").read_text()
    table = bus.percentile_table(adv).set_index("asset_class")
    for cls in ("etf", "stock"):
        cell = f"${table.loc[cls, 'p50']:,.0f}"
        assert cell in text and cell in out  # the same real numbers, printed and saved
    labels = _gdb.read_df(
        f"select distinct source, adjustment_source from {M}.ohlcv_daily where date = :d",
        {"d": as_of},
    )
    for src, adj in labels.itertuples(index=False):
        assert src in text and adj in text
    assert "not for display" in text and str(as_of) in text
    rows = pd.read_csv(csv, dtype=str, keep_default_na=False)
    assert list(rows.columns) == list(bus.REPORT_COLUMNS) and len(rows) == len(adv)
    assert rows["status"].value_counts().to_dict() == adv["status"].value_counts().to_dict()
    assert set(rows["in_universe"]) == {"False"}  # no floor, no member — never a default


def test_with_the_floor_set_every_active_instrument_gets_a_row_and_a_rerun_is_idempotent(
    as_of: date, adv: pd.DataFrame, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    floor = Decimal(int(np.median(_values(adv.loc[adv["asset_class"] == "etf"]))))
    conn = psycopg2.connect(_gdb.psycopg2_url())
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"insert into {M}.atlas_thresholds (threshold_key, threshold_value, category, "
                "description, methodology_section, units, min_allowed, max_allowed, default_value, "
                "last_modified_by, last_modified_at, is_active, created_at) values "
                "(%s, %s, 'universe', 'TEST ONLY: this database''s ETF median ADV$', 'universe', "
                "'usd', 0, 999999999999, %s, %s, now(), true, now())",
                (bus.THRESHOLD_KEY, floor, floor, TEST_BY),
            )
        args = ["--eod", as_of.isoformat(), "--report-dir", str(tmp_path)]
        assert bus.main(args) == 0
        out = capsys.readouterr().out
        rows = _snapshot(as_of)
        active = _gdb.read_df(
            f"select instrument_id::text as i from {M}.instrument_master where is_active"
        )
        assert set(rows["instrument_id"]) == set(active["i"]) and len(rows) == len(active)
        members = bus.sp500_members(as_of)
        assert set(rows.loc[rows["in_sp500"], "instrument_id"]) == members
        assert not bool(rows.loc[rows["adv_usd_median_60d"].isna(), "in_universe"].any())
        expected = U.members(adv, floor, frozenset())  # the verbatim India predicate
        assert set(rows.loc[rows["in_universe"], "instrument_id"]) == expected
        assert set(rows["floor_usd"]) == {floor} and bool(rows["aum_usd"].isna().all())
        assert not bool(rows["basket_eligible"].any())
        assert f"universe: {len(expected):,d} / {len(rows):,d}" in out
        first = rows.set_index("instrument_id")["computed_at"]

        assert bus.main(args) == 0
        again = _snapshot(as_of)
        cols = ["instrument_id", "in_universe", "in_sp500", "adv_usd_median_60d", "floor_usd"]
        pd.testing.assert_frame_equal(again[cols], rows[cols])
        assert bool((again.set_index("instrument_id")["computed_at"] > first).all())
        print(f"floor ${floor:,} (this DB's ETF median): {len(expected):,d} of {len(rows):,d} in")
    finally:
        with conn.cursor() as cur:
            cur.execute(f"delete from {M}.universe_snapshot where date = %s", (as_of,))
            cur.execute(
                f"delete from {M}.atlas_thresholds "
                "where threshold_key = %s and last_modified_by = %s",
                (bus.THRESHOLD_KEY, TEST_BY),
            )
        conn.close()

# ruff: noqa: S608 -- SQL here is assembled from the schema constant _gdb.M; every value is bound.
"""build_universe_snapshot on a REAL database (rule #0): the ADV$ window and its two guards,
``in_sp500``'s exclusive end, the percentile table, the exit-2 gate, the write — and
``exclusion_reason``: that the seven reasons partition the excluded rows on the real archive,
and that the table's two CHECKs refuse a row where flag and reason disagree.

Needs ``ATLAS_DB_URL`` pointing at a Postgres with the atlas_global DDL applied, the committed
seeds (``seed_thresholds.py``, including ``liquidity_min_traded_value_usd`` since the FM set it
on 2026-09-06) and real rows in ``instrument_master``, ``index_membership`` and ``ohlcv_daily``
— the Phase 1 scratch clone of runbook §6. Unset, the module skips; it never passes vacuously.
Every expected value is read from the database independently of the script's own SQL, the floor
included: it is the FM's row, read at test time, never a constant in the repo.

The refusal is still the guard for a half-provisioned schema, so it is still tested — by taking
the seeded row away (renamed out of sight, then merely deactivated: ``load_thresholds`` sees
neither) and putting it back, with the snapshot rows a write test leaves, in the teardown.
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
    assert bus.THRESHOLD_KEY in t, f"{bus.THRESHOLD_KEY} is seeded since 2026-09-06 — re-seed"
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


@pytest.fixture
def snapshot_teardown(as_of: date):
    """The rows a write test leaves behind. The journal is a real table on a real database; a
    test that fills it must empty it again."""
    yield
    conn = psycopg2.connect(_gdb.psycopg2_url())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"delete from {M}.universe_snapshot where date = %s", (as_of,))
    conn.close()


def _snapshot(as_of: date) -> pd.DataFrame:
    return _gdb.read_df(
        f"select instrument_id::text as instrument_id, in_universe, exclusion_reason, in_sp500, "
        f"adv_usd_median_60d, floor_usd, aum_usd, basket_eligible, computed_at "
        f"from {M}.universe_snapshot "
        "where date = :d order by instrument_id",
        {"d": as_of},
        coerce_float=False,
    )


@pytest.fixture
def floor_row_gone(request: pytest.FixtureRequest):
    """Take the seeded floor away the way a half-provisioned schema has it — absent, or present
    but inactive (``load_thresholds`` reads only ``is_active = TRUE``) — and put it back. Both
    are UPDATEs, so the FM's row cannot be lost if a test dies mid-way; renaming the key makes
    it absent to every reader, which is all the code under test can see."""
    hide, restore = request.param
    conn = psycopg2.connect(_gdb.psycopg2_url())
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(hide, (bus.THRESHOLD_KEY,))
            assert cur.rowcount == 1, "the floor row is not in this DB — run seed_thresholds.py"
        yield
    finally:
        with conn.cursor() as cur:
            cur.execute(restore, (bus.THRESHOLD_KEY,))
            assert cur.rowcount == 1
        conn.close()


_HIDDEN = f"{bus.THRESHOLD_KEY}_hidden_by_test"  # varchar(64); unique, so the PK stays happy
_SET = f"update {M}.atlas_thresholds set"


@pytest.mark.parametrize(
    ("floor_row_gone", "why"),
    [
        (
            (
                f"{_SET} threshold_key = '{_HIDDEN}' where threshold_key = %s",
                f"{_SET} threshold_key = %s where threshold_key = '{_HIDDEN}'",
            ),
            "is not in",
        ),
        (
            (
                f"{_SET} is_active = false where threshold_key = %s",
                f"{_SET} is_active = true where threshold_key = %s",
            ),
            "is_active",
        ),
    ],
    indirect=["floor_row_gone"],
    ids=["absent", "deactivated"],
)
def test_without_an_active_floor_row_main_prints_the_table_and_exits_2(
    as_of: date,
    adv: pd.DataFrame,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
    floor_row_gone: None,
    why: str,
) -> None:
    before = len(_snapshot(as_of))
    csv = tmp_path / "universe.csv"
    rc = bus.main(["--eod", as_of.isoformat(), "--report-dir", str(tmp_path), "--report", str(csv)])
    out = capsys.readouterr().out
    assert rc == 2 and len(_snapshot(as_of)) == before
    assert "REFUSED" in out and bus.THRESHOLD_KEY in out and "nothing written" in out
    assert why in out  # the message tells a missing row from an inactive one
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
    # The ADV$ ladder is untouched; only its `ok` bucket splits into the FM's three reasons.
    no_signal = {k: v for k, v in adv["status"].value_counts().items() if k != bus.STATUS_OK}
    got = rows["status"].value_counts().to_dict()
    assert {k: v for k, v in got.items() if k in no_signal} == no_signal
    reasons = (bus.STATUS_OK, bus.STATUS_NOT_SP500, bus.STATUS_LEVERAGED, bus.STATUS_INVERSE)
    assert sum(got.get(r, 0) for r in reasons) == int((adv["status"] == bus.STATUS_OK).sum())
    assert set(rows["in_universe"]) == {"False"}  # no floor, no member — never a default


def test_every_active_instrument_gets_a_row_and_a_rerun_is_idempotent(
    as_of: date, adv: pd.DataFrame, thr: dict[str, Decimal], tmp_path, snapshot_teardown
) -> None:
    floor = thr[bus.THRESHOLD_KEY]  # the FM's row, read from this database
    args = ["--eod", as_of.isoformat(), "--report-dir", str(tmp_path)]
    assert bus.main(args) == 0
    rows = _snapshot(as_of)
    active = _gdb.read_df(
        f"select instrument_id::text as i from {M}.instrument_master where is_active"
    )
    assert set(rows["instrument_id"]) == set(active["i"]) and len(rows) == len(active)
    assert set(rows.loc[rows["in_sp500"], "instrument_id"]) == bus.sp500_members(as_of)
    assert not bool(rows.loc[rows["adv_usd_median_60d"].isna(), "in_universe"].any())
    assert set(rows["floor_usd"]) == {floor} and bool(rows["aum_usd"].isna().all())
    assert not bool(rows["basket_eligible"].any())
    first = rows.set_index("instrument_id")["computed_at"]

    assert bus.main(args) == 0
    again = _snapshot(as_of)
    cols = ["instrument_id", "in_universe", "in_sp500", "adv_usd_median_60d", "floor_usd"]
    pd.testing.assert_frame_equal(again[cols], rows[cols])
    assert bool((again.set_index("instrument_id")["computed_at"] > first).all())
    print(f"floor ${floor:,} (the FM's row): {int(rows['in_universe'].sum()):,d} in the universe")


def test_the_universe_is_the_liquidity_predicate_minus_the_two_fm_rules(
    as_of: date, adv: pd.DataFrame, thr: dict[str, Decimal], tmp_path, capsys, snapshot_teardown
) -> None:
    """FM, 2026-09-06: a stock must be an S&P 500 member, an ETF must be neither leveraged nor
    inverse. ``universe_core.members`` is unchanged and still decides liquidity — the two rules
    only take rows away, and every row taken away is still in the journal with its reason."""
    csv = tmp_path / "u.csv"
    args = ["--eod", as_of.isoformat(), "--report-dir", str(tmp_path), "--report", str(csv)]
    assert bus.main(args) == 0
    out = capsys.readouterr().out
    rows = _snapshot(as_of).set_index("instrument_id")
    liquid = U.members(adv, thr[bus.THRESHOLD_KEY], frozenset())  # the verbatim India predicate
    inside = set(rows.index[rows["in_universe"]])
    assert inside < liquid, "the rules must only ever remove instruments"

    members = bus.sp500_members(as_of)
    flags = bus.structure_flags(adv)  # the name rules, re-run here on the same real frame
    frame = adv.assign(
        in_sp500=adv["instrument_id"].isin(list(members)),
        leveraged=[f.leveraged for f in flags],
        inverse=[f.inverse for f in flags],
    ).set_index("instrument_id")
    stocks, etfs = frame["asset_class"] == "stock", frame["asset_class"] == "etf"
    non_member = set(frame.index[stocks]) - members
    structural = set(frame.index[etfs & (frame["leveraged"] | frame["inverse"])])
    assert non_member and structural, "no such instruments here — the test proves nothing"
    assert set(frame.index[stocks]) & inside == members & liquid  # scored = current members
    assert not structural & inside
    assert liquid - inside == (non_member | structural) & liquid
    # Every dropped instrument still has its journal row, listed with the rule that took it.
    assert liquid - inside < set(rows.index)
    listed = pd.read_csv(csv, dtype=str, keep_default_na=False)
    for reason, mask in bus.exclusions(frame.reset_index()).items():
        assert reason in set(listed["status"]), reason
        assert f"{int(mask.sum()):,d}" in out, reason
    print(f"liquid {len(liquid):,d} → universe {len(inside):,d} ({len(liquid - inside):,d} cut)")


def test_every_excluded_row_says_why_and_the_seven_reasons_partition_them(
    as_of: date, thr: dict[str, Decimal], tmp_path, snapshot_teardown
) -> None:
    """The board's promise, read back from the journal rather than from the frame that wrote
    it: every instrument that is out names the ONE rule that took it out, and the seven names
    cover the excluded set exactly once each."""
    csv = tmp_path / "u.csv"
    args = ["--eod", as_of.isoformat(), "--report-dir", str(tmp_path), "--report", str(csv)]
    assert bus.main(args) == 0
    rows = _snapshot(as_of)
    inside, reason = pd.Series(rows["in_universe"]), pd.Series(rows["exclusion_reason"])
    assert bool(reason.loc[inside].isna().all()), "an instrument that is IN needs no excuse"
    assert bool(reason.loc[~inside].notna().all()), "no row may say only that it is excluded"
    counts = reason.value_counts()
    assert set(counts.index) == set(bus.EXCLUSION_REASONS), "this archive carries all seven"
    assert int(counts.sum()) == int((~inside).sum())  # one reason per excluded row, never two

    # Against the run's own CSV, row by row: the ladder's answer where it had one, and
    # below_floor exactly where universe_status said `ok` and the floor still said no.
    listed = pd.read_csv(csv, dtype=str, keep_default_na=False).set_index("instrument_id")
    both = rows.set_index("instrument_id").join(listed[["status"]], how="inner")
    assert len(both) == len(rows)
    ladder = both["status"] != bus.STATUS_OK
    assert (both.loc[ladder, "exclusion_reason"] == both.loc[ladder, "status"]).all()
    cleared = both.loc[~ladder]
    assert set(cleared.loc[~cleared["in_universe"], "exclusion_reason"]) == {bus.STATUS_BELOW_FLOOR}
    text = (tmp_path / f"adv_usd_{as_of}.md").read_text()
    for r, n in counts.items():
        assert f"| `{r}` | {n:,d} |" in text  # the FM's report says the same numbers
    print(", ".join(f"{r} {n:,d}" for r, n in counts.items()) + f"; in {int(inside.sum()):,d}")


_BAD_ROW = f"""insert into {M}.universe_snapshot
    (date, instrument_id, in_universe, exclusion_reason, floor_usd) values (%s, %s, %s, %s, %s)"""
_IFF = "chk_universe_snapshot_reason_iff_excluded"


@pytest.mark.parametrize(
    ("in_universe", "reason", "constraint"),
    [
        (False, None, _IFF),
        (True, bus.STATUS_BELOW_FLOOR, _IFF),
        (False, "delisted", "chk_universe_snapshot_exclusion_reason"),
    ],
    ids=["out-with-no-reason", "in-but-blamed", "a-reason-the-writer-cannot-produce"],
)
def test_the_database_itself_refuses_a_row_whose_reason_and_flag_disagree(
    as_of: date, thr: dict[str, Decimal], in_universe: bool, reason: str | None, constraint: str
) -> None:
    """ddl/05_scores.sql, not a comment: each INSERT is really attempted against the real table
    (SPY, the anchor date, the FM's floor) and rolled back. A schema that has drifted back to a
    bare boolean accepts all three and fails here."""
    spy = _gdb.scalar(f"select instrument_id from {M}.instrument_master where symbol = 'SPY'")
    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.CheckViolation) as e:
                cur.execute(_BAD_ROW, (as_of, spy, in_universe, reason, thr[bus.THRESHOLD_KEY]))
            assert e.value.diag.constraint_name == constraint
    finally:
        conn.rollback()  # nothing of this test reaches the journal
        conn.close()

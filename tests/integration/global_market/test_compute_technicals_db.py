# ruff: noqa: S608 -- SQL here is assembled from the schema constant _gdb.M; every value is bound.
"""compute_technicals.py against the REAL archive (rule #0): recompute-and-diff, and the
cross-checks that would catch a bug the recompute cannot.

Needs ``ATLAS_DB_URL`` pointing at a Postgres carrying the atlas_global DDL, the committed
seeds and real ``ohlcv_daily`` rows that ``compute_technicals.py`` has already been run over
— the Phase 1 scratch clone of runbook §6. Unset or empty, the module skips; it never passes
vacuously. Nothing here writes: every assertion reads rows the nightly job produced.

Why these checks
----------------
Recompute-and-diff (``test_every_metric_reproduces_*``) proves the journal is deterministic
and that nothing was lost between the frame and ``numeric(p, s)`` — it is the axis India's
harness runs. On its own it is half a test: it calls the same functions the writer called, so
a wrong formula reproduces perfectly. The rest of the module is therefore checks whose
expected value does NOT come from this repo's compute path:

* **SPY's 12-month return, by hand** — raw closes, an ``asof`` anchor found in SQL, one
  division. Catches a wrong price column, a wrong basis, a row-offset anchor.
* **SPY against itself** — beta and correlation must be exactly 1, relative strength exactly
  0, at every window. Any misalignment between an instrument's sessions and the benchmark's
  moves these off their fixed point, and nothing else in the suite would notice.
* **empyrical** — the library the methodology names, called directly on the same window, vs
  the vectorised rolling forms the writer uses. This is the check that keeps the fast path
  honest.
* **build_universe_snapshot's ADV\\$** — the number the FM set the liquidity floor from. Two
  scripts compute it because the dependency is circular (the universe needs ADV\\$; this
  journal's scope needs the universe), so it is read from the OTHER script and must agree
  here to within the rounding this table's ``numeric(20,4)`` column applies, and no more.
* **Cross-column ties** — ``above_ema_N`` against the stored EMA and the raw close, ``ibs``
  and ``atr_14_pct`` against raw bars. Sixty columns go into one INSERT; these catch the
  off-by-one column list that a value-level diff never would.
"""

from __future__ import annotations

import os
from decimal import Decimal

import empyrical
import numpy as np
import pandas as pd
import pytest

from atlas.global_market import price_basis as PB
from tests.unit.global_market.script_loader import load_global_script

pytestmark = pytest.mark.integration

if not os.environ.get("ATLAS_DB_URL", "").strip():
    pytest.skip(
        "ATLAS_DB_URL not set — the technicals journal needs a database",
        allow_module_level=True,
    )

_gdb = load_global_script("_gdb")
ct = load_global_script("compute_technicals")
bus = load_global_script("build_universe_snapshot")
G = ct.G
M = _gdb.M

SAMPLE_INSTRUMENTS = 50  # the floor the definition of done sets
TOLERANCE = 1e-6


# ── fixtures: the journal as the nightly run left it ──


@pytest.fixture(scope="module")
def anchor():
    """The latest date technical_daily holds — the session the journal is anchored on."""
    day = _gdb.scalar(f"select max(date) from {M}.technical_daily")
    if day is None:
        pytest.skip("technical_daily is empty — run compute_technicals.py against this database")
    return day


@pytest.fixture(scope="module")
def calendar(anchor):
    return ct.sessions(anchor)


@pytest.fixture(scope="module")
def benchmark(anchor, calendar):
    return ct.benchmark_close(anchor, calendar)[0]


@pytest.fixture(scope="module")
def risk_free(calendar):
    return ct.risk_free_daily(calendar)


@pytest.fixture(scope="module")
def scales() -> dict[str, int]:
    """Each numeric column's stored scale, read from the database, so a recomputed value is
    compared at the precision the column actually keeps rather than at float precision."""
    frame = _gdb.read_df(
        "select column_name, numeric_scale from information_schema.columns "
        "where table_schema = :s and table_name = 'technical_daily' and numeric_scale is not null",
        {"s": _gdb.SCHEMA},
    )
    return dict(zip(frame["column_name"], frame["numeric_scale"].astype(int), strict=True))


@pytest.fixture(scope="module")
def sample(anchor) -> pd.DataFrame:
    """Instruments with the DEEPEST stored history first, then a spread of the rest.

    Depth is what exercises the long windows (a 252-session beta, a 756-session drawdown);
    taking only the alphabetical head would diff nothing but the short-window columns.
    """
    frame = _gdb.read_df(
        f"""
        select t.instrument_id::text as instrument_id, im.symbol, im.asset_class,
               count(*) as rows, min(t.date) as first_date, max(t.date) as last_date
        from {M}.technical_daily t join {M}.instrument_master im using (instrument_id)
        group by 1, 2, 3 order by count(*) desc, im.symbol
        """
    )
    if len(frame) < SAMPLE_INSTRUMENTS:
        pytest.skip(f"only {len(frame)} instruments in technical_daily; need {SAMPLE_INSTRUMENTS}")
    deep = frame.head(10)
    spread = frame.iloc[10:].iloc[:: max(1, (len(frame) - 10) // (SAMPLE_INSTRUMENTS - 10))]
    picked = pd.concat([deep, spread]).head(SAMPLE_INSTRUMENTS)
    assert len(picked) >= SAMPLE_INSTRUMENTS
    return picked


def _stored(instrument_id: str) -> pd.DataFrame:
    frame = _gdb.read_df(
        f"select * from {M}.technical_daily where instrument_id = cast(:i as uuid) order by date",
        {"i": instrument_id},
        coerce_float=False,
    )
    return frame.set_index("date")


def _plan(instrument_id: str) -> PB.BasisPlan:
    """The basis plan this instrument's bars carry, resolved the way the producer resolves it.

    Read from ``adjustment_source`` on the bars, NOT from the stored ``price_basis``: the
    stamp is one of the things under test, so deriving the recompute from it would let a
    wrong stamp agree with itself.
    """
    sources = _gdb.read_df(
        f"select distinct adjustment_source from {M}.ohlcv_daily "
        "where instrument_id = cast(:i as uuid)",
        {"i": instrument_id},
    )
    plan = ct.uniform_plan(list(sources["adjustment_source"]))
    assert plan is not None, f"{instrument_id}: bars carry no single basis plan"
    return plan


def _raw_bars(instrument_id: str, series: str = PB.TOTAL_RETURN) -> pd.DataFrame:
    """Bars straight from ohlcv_daily — never through compute_technicals' own reader.

    ``series`` picks the whole OHLC family, not just the close: a split-only ATR or IBS is a
    statement about the split-only high and low, and checking it against the raw ones would
    only agree on instruments that never split.
    """
    _, high, low, close = PB.price_columns(series)
    return _gdb.read_df(
        f"select date, {high} as high, {low} as low, {close} as close from {M}.ohlcv_daily "
        "where instrument_id = cast(:i as uuid) order by date",
        {"i": instrument_id},
    ).set_index("date")


def _floats(frame: pd.DataFrame, column: str) -> pd.Series:
    """One column of a frame as a float64 Series.

    Indexing a DataFrame widens to every scalar type a cell could hold, so a bare
    ``pd.to_numeric(frame[col]).astype(...)`` reads as one type error per union member.
    ``G.as_series`` is the writer's own narrowing helper, reused here so the test and the
    code under test agree on what a column is.
    """
    return G.as_series(pd.to_numeric(frame[column], errors="coerce")).astype("float64")


def _diff(stored: pd.Series, expected: pd.Series, scale: int) -> float:
    """Largest absolute difference BEYOND the column's own storage rounding.

    The stored value has been through ``numeric(_, scale)`` and the recomputed one has not,
    so half a unit in the last kept place (:func:`_storable`) is not drift — it is the column.
    Rounding the expected side instead does NOT remove that difference, it hides one and
    invents another: ``numpy.round`` rounds halves to EVEN and Postgres rounds them AWAY FROM
    ZERO, so a value landing exactly on a half disagrees by a WHOLE unit for that reason
    alone. Measured on this archive: ``pos_52w`` for ACGL on 2026-08-17 recomputes to exactly
    60.15625 both times — Postgres stored 60.1563, ``np.round`` says 60.1562, and the
    identical computation read as 1e-4 of drift. So the comparison is against the bound, as
    :func:`_within_storage` already does for the liquidity block.
    """
    lhs = G.as_series(pd.to_numeric(stored, errors="coerce")).to_numpy(dtype="float64")
    rhs = np.asarray(expected, dtype="float64")
    both = ~np.isnan(lhs) & ~np.isnan(rhs)  # positional: both come from the same date list
    if not both.any():
        return 0.0
    storable = 0.5 * 10.0**-scale
    return float(max(np.abs(lhs[both] - rhs[both]).max() - storable, 0.0))


def _storable(scale: int) -> Decimal:
    """The largest error storing a value in a ``numeric(_, scale)`` column can introduce.

    Half a unit in the last kept place. A value READ BACK from the journal has been through
    that rounding; a value recomputed in flight has not, so the two legitimately differ by up
    to this much and by nothing else. Comparing against it — rather than re-rounding one side
    — keeps the check independent of whose rounding mode is whose (Postgres rounds halves
    away from zero, Python's Decimal defaults to half-even, and a value landing exactly on a
    half would disagree by one unit in the last place for that reason alone).
    """
    return Decimal(1).scaleb(-scale) / 2


def _missing(value: object) -> bool:
    """SQL NULL, however pandas hands it back — None from a read, NaN from an outer join."""
    return value is None or (isinstance(value, float) and np.isnan(value))


def _within_storage(mine: object, theirs: object, scale: int) -> bool:
    """Are two Decimals the same number, allowing only the column's own rounding?

    A NULL on ONE side is a real disagreement: it means a guard fired for one producer and
    not the other, which is exactly the drift this comparison exists to find.
    """
    if _missing(mine) and _missing(theirs):
        return True
    if _missing(mine) or _missing(theirs):
        return False
    return abs(Decimal(str(mine)) - Decimal(str(theirs))) <= _storable(scale)


# ── recompute and diff ──


def test_every_metric_reproduces_on_the_real_sample(
    sample, anchor, calendar, benchmark, risk_free, scales
):
    """Rerun the compute on unchanged input; every stored value must come back."""
    worst: dict[str, float] = {}
    checked = 0
    for row in sample.itertuples(index=False):
        stored = _stored(row.instrument_id)
        if stored.empty:
            continue
        bars = ct.bar_frame(row.instrument_id, _plan(row.instrument_id), anchor, calendar)
        metrics = G.metric_frame(bars, G.series(bars, "close_ret"), benchmark, risk_free)
        metrics.index = [stamp.date() for stamp in metrics.index]
        common = [d for d in stored.index if d in set(metrics.index)]
        assert len(common) == len(stored), f"{row.symbol}: stored dates absent from a rerun"
        for column in G.METRIC_COLUMNS:
            if column.startswith("above_ema_"):
                continue  # booleans: compared exactly below
            delta = _diff(stored.loc[common, column], metrics.loc[common, column], scales[column])
            worst[column] = max(worst.get(column, 0.0), delta)
        for column in [f"above_ema_{p}" for p in G.T.EMA_PERIODS]:
            lhs = stored.loc[common, column]
            rhs = metrics.loc[common, column]
            same = [
                (a is None and pd.isna(b))
                or (a is not None and not pd.isna(b) and bool(a) == bool(b))
                for a, b in zip(lhs, rhs, strict=True)
            ]
            assert all(same), f"{row.symbol}.{column} did not reproduce"
        checked += 1
    assert checked >= SAMPLE_INSTRUMENTS
    ranked = sorted(worst.items(), key=lambda kv: kv[1], reverse=True)
    print(
        f"\nrecompute-and-diff: {checked} real instruments, {len(G.METRIC_COLUMNS)} columns; "
        f"largest |stored - recomputed| = {ranked[0][1]:.3e} ({ranked[0][0]}); "
        + ", ".join(f"{c}={d:.1e}" for c, d in ranked[1:4])
    )
    over = {c: d for c, d in worst.items() if d >= TOLERANCE}
    assert not over, f"recompute drifted beyond {TOLERANCE}: {over}"


def test_the_liquidity_block_reproduces_to_the_stored_precision(sample, anchor, calendar, scales):
    """ADV\\$ is money — Decimal end to end, never a float — so a rerun must reproduce it to
    the last digit the column KEEPS, not to a hand-picked tolerance.

    The stored side has been through ``numeric(20,4)``; the recomputed side is the unbounded
    ``::numeric`` the query returns. They may therefore differ by up to half a hundredth of a
    cent and by NOTHING else — :func:`_storable` is that bound, and a real drift in the
    window, the guard or the aggregate would be orders of magnitude larger.
    """
    thresholds = ct.load_thresholds(_gdb.SCHEMA, engine=_gdb.engine())
    ids = [str(i) for i in sample["instrument_id"]]
    fresh = ct.liquidity_frame(ids, anchor, calendar, int(thresholds[ct.MIN_OBSERVATIONS_KEY]))
    stored = _gdb.read_df(
        f"select instrument_id::text as instrument_id, date, "
        f"{', '.join(G.LIQUIDITY_COLUMNS)} from {M}.technical_daily "
        "where instrument_id = any(cast(:ids as uuid[]))",
        {"ids": ids},
        coerce_float=False,
    ).set_index(["instrument_id", "date"])
    joined = stored.join(fresh, how="inner", rsuffix="_fresh")
    assert len(joined) > 0
    for column in G.LIQUIDITY_COLUMNS:
        scale = scales[column]
        bad = [
            (key, mine, theirs)
            for key, mine, theirs in zip(
                joined.index, joined[column], joined[f"{column}_fresh"], strict=True
            )
            if not _within_storage(mine, theirs, scale)
        ]
        assert not bad, f"{column} changed on rerun beyond numeric(_,{scale}): {bad[:3]}"


def test_the_bounded_incremental_window_gives_the_unbounded_liquidity_answer(
    sample, anchor, calendar
):
    """A normal night reads only the sessions the ADV\\$ window needs, not the whole archive.

    That bound — 59 sessions of run-up before the first row that will be written — is one
    off-by-one away from a silently SHORTER 60-session window, and a short window moves the
    median that the $1,000,000 universe floor is set from. So it is checked against the same
    computation over the FULL calendar, on real bars: every row the incremental run would
    actually WRITE (dates past the floor) must be identical. Rows at or before the floor are
    the run-up and are discarded by ``rows_for``, so they are deliberately not compared.
    """
    thresholds = ct.load_thresholds(_gdb.SCHEMA, engine=_gdb.engine())
    min_obs = int(thresholds[ct.MIN_OBSERVATIONS_KEY])
    ids = [str(i) for i in sample["instrument_id"].head(20)]
    floor_day = G.as_dates(calendar)[-5]  # as if the last four sessions were unwritten
    window = ct.liquidity_window(calendar, ids, dict.fromkeys(ids, floor_day), incremental=True)
    assert 0 < len(window) < len(calendar), "the incremental bound did not bind"
    bounded = ct.liquidity_frame(ids, anchor, window, min_obs).sort_index()
    whole = ct.liquidity_frame(ids, anchor, calendar, min_obs).sort_index()
    tail = whole.loc[whole.index.get_level_values("date") > floor_day]
    assert len(tail) >= len(ids), f"only {len(tail)} rows past the floor — nothing was compared"
    mine = bounded.reindex(tail.index)
    # The median and the zero-volume count are order-independent: BIT-identical or the window
    # moved. The 20-session mean is a rolling SUM, so pandas accumulates it from wherever the
    # frame starts and the two runs differ in the last bits of a float — measured 6e-08 USD
    # on a $2e+08 mean, 1e-16 relative and nine orders inside numeric(20,4).
    for column in ("adv_usd_60d_median", "zero_volume_days_60d"):
        pd.testing.assert_series_equal(mine[column], tail[column], check_exact=True)
    pd.testing.assert_series_equal(mine["adv_usd_20d_mean"], tail["adv_usd_20d_mean"], rtol=1e-12)


# ── cross-check 1: SPY's own 12-month return, computed by hand from raw closes ──


def test_spy_twelve_month_return_matches_hand_arithmetic(anchor):
    """One division over two raw closes, with the anchor found in SQL. No repo code."""
    spy = _gdb.scalar(
        f"select instrument_id::text from {M}.instrument_master where symbol = 'SPY' and is_active"
    )
    stored = _gdb.read_df(
        f"select ret_12m, ret_24m from {M}.technical_daily "
        "where instrument_id = cast(:i as uuid) and date = :d",
        {"i": spy, "d": anchor},
    )
    if stored.empty or pd.isna(stored["ret_12m"].iloc[0]):
        pytest.skip("SPY has no 12-month window in this archive")
    last = _gdb.scalar(
        f"select close_tr from {M}.ohlcv_daily "
        "where instrument_id = cast(:i as uuid) and date = :d",
        {"i": spy, "d": anchor},
    )
    for months, column in ((12, "ret_12m"), (24, "ret_24m")):
        base = _gdb.scalar(
            f"select close_tr from {M}.ohlcv_daily where instrument_id = cast(:i as uuid) "
            "and date <= (cast(:d as date) - make_interval(months => :m)) "
            "order by date desc limit 1",
            {"i": spy, "d": anchor, "m": months},
        )
        if base is None or pd.isna(stored[column].iloc[0]):
            continue
        by_hand = float(Decimal(last) / Decimal(base) - 1)
        assert abs(float(stored[column].iloc[0]) - by_hand) < TOLERANCE, column


# ── cross-check 2: SPY against itself sits on fixed points ──


def test_spy_is_its_own_benchmark_and_lands_on_the_fixed_points(anchor):
    """beta = 1, correlation = 1, relative strength = 0. A benchmark series misaligned by one
    session, or reindexed onto the wrong calendar, breaks all three and nothing else
    would say so."""
    row = _gdb.read_df(
        f"""
        select t.* from {M}.technical_daily t join {M}.instrument_master im using (instrument_id)
        where im.symbol = 'SPY' and t.date = :d
        """,
        {"d": anchor},
    )
    assert len(row) == 1, "SPY has no technicals row at the anchor"
    for window in G.RS_WINDOWS:
        value = row[f"rs_{window}_spy"].iloc[0]
        if pd.isna(value):
            continue
        assert abs(float(value)) < TOLERANCE, f"rs_{window}_spy of SPY is {value}, not 0"
    for column in ("beta_spy_252", "corr_spy_252"):
        value = row[column].iloc[0]
        if pd.isna(value):
            continue
        assert abs(float(value) - 1.0) < TOLERANCE, f"{column} of SPY is {value}, not 1"


# ── cross-check 3: the risk block against empyrical itself ──


def test_the_risk_block_equals_empyrical_on_the_deepest_instrument(anchor, calendar, benchmark):
    """The vectorised rolling forms vs the library the methodology names, same window, same bars.

    Only an instrument with the full lookback can be checked; on a thin archive that is SPY.
    """
    deepest = _gdb.read_df(
        f"""
        select t.instrument_id::text as instrument_id, im.symbol, count(*) as rows
        from {M}.technical_daily t join {M}.instrument_master im using (instrument_id)
        group by 1, 2 order by count(*) desc limit 1
        """
    )
    instrument_id = str(deepest["instrument_id"].iloc[0])
    stored = _stored(instrument_id)
    bars = ct.bar_frame(instrument_id, _plan(instrument_id), anchor, calendar)
    # The RETURN series, which is what every risk metric is computed on — `close` is the
    # trend series, and on a feed carrying both they are different columns.
    returns = bars["close_ret"].pct_change()
    # SPY's returns on THIS instrument's sessions — reindexed before differencing, exactly as
    # risk_frame does it. Passing `returns` here (as this test once did) asks empyrical for
    # the beta of a series against ITSELF, which is 1 by construction and checks nothing; it
    # only looked right while the deepest instrument in the archive happened to be SPY.
    market_returns = G.as_series(benchmark.reindex(bars.index)).pct_change()

    def window(n: int) -> pd.Series:
        return returns.iloc[-n:]

    checks: list[tuple[str, float]] = []
    if len(returns.dropna()) >= G.VOL_SESSIONS["252d"]:
        checks.append(("vol_252d_ann", float(empyrical.annual_volatility(window(252)))))
        checks.append(("mdd_12m", float(empyrical.max_drawdown(window(252)))))
        checks.append(
            (
                "beta_spy_252",
                float(empyrical.beta(window(252), market_returns.iloc[-252:])),
            )
        )
    if len(returns.dropna()) >= G.DOWNSIDE_SESSIONS:
        checks.append(("downside_dev_63d", float(empyrical.downside_risk(window(63)))))
    if len(returns.dropna()) >= G.CALMAR_SESSIONS:
        checks.append(("mdd_36m", float(empyrical.max_drawdown(window(756)))))
        checks.append(("calmar_36m", float(empyrical.calmar_ratio(window(756)))))
    assert checks, f"{deepest['symbol'].iloc[0]} is too short to check any risk window"
    last = stored.loc[anchor]
    for column, expected in checks:
        got = last[column]
        assert got is not None and not pd.isna(got), f"{column} is NULL but empyrical computes it"
        assert abs(float(got) - expected) < TOLERANCE, (
            f"{column}: stored {float(got)!r} vs empyrical {expected!r}"
        )


def test_annual_volatility_is_the_annualised_standard_deviation(anchor, calendar):
    """The 20-session volatility against numpy alone — a second, library-free reading."""
    deepest = _gdb.scalar(
        f"select instrument_id::text from {M}.technical_daily "
        "group by instrument_id order by count(*) desc limit 1"
    )
    stored = _stored(deepest)
    bars = ct.bar_frame(deepest, _plan(deepest), anchor, calendar)
    returns = bars["close_ret"].pct_change().to_numpy()[-20:]
    by_hand = float(np.std(returns, ddof=1) * np.sqrt(252))
    assert abs(float(stored.loc[anchor, "vol_20d_ann"]) - by_hand) < TOLERANCE


# ── cross-check 4: the ADV$ the universe gate used ──


def test_adv_matches_build_universe_snapshot(anchor, scales):
    """``adv_usd_60d_median`` is the same quantity ``build_universe_snapshot`` sets the
    liquidity floor from, and TWO scripts legitimately compute it.

    They have to: the universe needs ADV\\$ to decide membership, and this journal needs the
    universe to decide its scope, so the dependency is circular and the number cannot simply
    be read from one by the other. That makes drift a real risk — a changed window, a changed
    minimum-observations guard, a different median — and this is the check that catches it.
    So it is read from the OTHER script here, not recomputed locally.

    The two sides differ only by storage: this journal's value has been through
    ``numeric(20,4)``, ``bus.adv_frame`` returns the unbounded ``::numeric``. Half a hundredth
    of a cent is allowed (:func:`_storable`); anything more is the drift being hunted. Do not
    "restore" exact equality here — it never held, and the failure it produces is noise.

    Only instruments whose last bar IS the anchor are comparable: the snapshot writes a row
    for every active instrument and NULLs a stale one, while the journal only has rows on an
    instrument's own sessions.
    """
    thresholds = bus.thresholds()
    snapshot = bus.adv_frame(
        anchor,
        int(thresholds[bus.U.THRESHOLD_KEY_MIN_OBS]),
        int(thresholds[bus.U.THRESHOLD_KEY_RECENCY]),
    )
    snapshot = snapshot[snapshot["last_date"] == anchor].set_index("instrument_id")
    journal = _gdb.read_df(
        f"select instrument_id::text as instrument_id, adv_usd_60d_median "
        f"from {M}.technical_daily where date = :d",
        {"d": anchor},
        coerce_float=False,
    ).set_index("instrument_id")
    shared = journal.index.intersection(snapshot.index)
    assert len(shared) > 100, f"only {len(shared)} instruments in both — nothing was compared"
    scale = scales["adv_usd_60d_median"]
    mismatches = [
        (instrument_id, mine, theirs)
        for instrument_id in shared
        for mine, theirs in [
            (
                journal.loc[instrument_id, "adv_usd_60d_median"],
                snapshot.loc[instrument_id, "adv_median_60d"],
            )
        ]
        if not _within_storage(mine, theirs, scale)
    ]
    assert not mismatches, (
        f"{len(mismatches)} of {len(shared)} ADV$ values differ by more than the "
        f"numeric(_,{scale}) rounding — the two producers have drifted: {mismatches[:3]}"
    )


# ── cross-check 5: columns tied to each other and to the raw bars ──


def test_above_flags_agree_with_the_stored_emas_and_the_raw_close(sample):
    """Sixty columns go into one INSERT. If the list ever slips by one, a value diff still
    passes (every column reproduces — into the wrong column); this does not."""
    for row in sample.head(15).itertuples(index=False):
        stored = _stored(row.instrument_id)
        bars = _raw_bars(row.instrument_id, _plan(row.instrument_id).trend)
        close = _floats(bars, "close")
        for period in G.T.EMA_PERIODS:
            ema = _floats(stored, f"ema_{period}")
            flag = stored[f"above_ema_{period}"]
            both = ema.notna()
            if not both.any():
                continue
            aligned = G.as_series(close.reindex(ema.index))
            expected = G.as_series(aligned[both] > ema[both])
            got = pd.Series([bool(v) for v in flag[both]], index=ema.index[both])
            assert (expected.to_numpy() == got.to_numpy()).all(), (
                f"{row.symbol}: above_ema_{period} disagrees with ema_{period} and the raw close"
            )


def test_ibs_and_atr_percent_agree_with_the_raw_bars(sample):
    """IBS and ATR-percent are ties between columns and the bar they came from."""
    for row in sample.head(15).itertuples(index=False):
        stored = _stored(row.instrument_id)
        bars = _raw_bars(row.instrument_id, _plan(row.instrument_id).trend).reindex(stored.index)
        high = _floats(bars, "high")
        low = _floats(bars, "low")
        close = _floats(bars, "close")
        ibs = _floats(stored, "ibs")
        span = (high - low).where(high > low)
        expected = ((close - low) / span).round(6)
        both = ibs.notna() & expected.notna()
        assert (ibs[both] - expected[both]).abs().max() < TOLERANCE, f"{row.symbol}: ibs"
        atr = _floats(stored, "atr_14")
        pct = _floats(stored, "atr_14_pct")
        expected_pct = (atr / close).round(8)
        both = pct.notna() & expected_pct.notna()
        assert (pct[both] - expected_pct[both]).abs().max() < TOLERANCE, f"{row.symbol}: atr_pct"


# ── the honesty columns ──


def test_every_row_declares_the_basis_its_bars_actually_carry(anchor):
    """price_basis is not decoration: it must be what adjustment_source says, for every row."""
    frame = _gdb.read_df(
        f"""
        select distinct t.price_basis, o.adjustment_source
        from {M}.technical_daily t
        join {M}.ohlcv_daily o on o.instrument_id = t.instrument_id and o.date = t.date
        """
    )
    assert not frame.empty
    for basis, source in zip(frame["price_basis"], frame["adjustment_source"], strict=True):
        plan = PB.plan_for(source)
        assert plan is not None, f"{source!r} resolves to no basis, yet rows were written"
        assert plan.stamp == basis, f"{source!r} stored as price_basis={basis!r}"


def test_bounded_metrics_stay_inside_their_bounds_on_every_real_row():
    """RSI is a 0-100 oscillator, the 52-week position is a 0-100 percentage, a drawdown is
    never positive and a correlation never leaves [-1, 1]. Cheap, and over the WHOLE table."""
    breaches = _gdb.read_df(
        f"""
        select count(*) filter (where rsi_2 < 0 or rsi_2 > 100) as rsi_2,
               count(*) filter (where rsi_14 < 0 or rsi_14 > 100) as rsi_14,
               count(*) filter (where pos_52w < 0 or pos_52w > 100) as pos_52w,
               count(*) filter (where ibs < 0 or ibs > 1) as ibs,
               count(*) filter (where mdd_12m > 0 or mdd_36m > 0) as drawdown,
               count(*) filter (where corr_spy_252 < -1 or corr_spy_252 > 1) as corr,
               count(*) filter (where vol_20d_ann < 0 or vol_63d_ann < 0) as volatility,
               count(*) filter (where zero_volume_days_60d < 0) as zero_volume
        from {M}.technical_daily
        """
    )
    offending = {c: int(breaches[c].iloc[0]) for c in breaches.columns if breaches[c].iloc[0]}
    assert not offending, f"metrics outside their definitional bounds: {offending}"


def test_the_journal_only_has_rows_on_sessions_the_benchmark_traded(anchor):
    """Stooq carries stray bars on exchange holidays; a holiday is not a session, and
    build_universe_snapshot already treats SPY's bars as the calendar."""
    stray = _gdb.scalar(
        f"""
        select count(*) from {M}.technical_daily t
        where not exists (
            select 1 from {M}.ohlcv_daily o
            where o.instrument_id = (select instrument_id from {M}.instrument_master
                                     where symbol = 'SPY' and is_active)
              and o.date = t.date)
        """
    )
    assert stray == 0, f"{stray} technical_daily rows fall on dates SPY did not trade"


def test_peer_relative_strength_is_null_until_the_classification_engine_lands():
    """There is no peer group in Phase 1. The columns exist; a NUMBER in them would be a
    fabricated benchmark wearing a real column's name."""
    filled = _gdb.scalar(
        f"select count(*) from {M}.technical_daily where "
        + " or ".join(f"rs_{w}_peer is not null" for w in G.PEER_WINDOWS)
    )
    assert filled == 0, f"{filled} rows carry a peer RS with no peer groups defined"

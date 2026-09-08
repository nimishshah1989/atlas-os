# ruff: noqa: S608 -- SQL here is assembled from the schema constant _gdb.M and the gate's own
# BASIS_SYMBOL; every value is bound as a :param. Not an injection vector.
"""``--check BASIS`` against a REAL database and the REAL FRED feed (rule #0).

Needs ``ATLAS_DB_URL`` pointing at a Postgres carrying the ``atlas_global`` schema with SPY
bars in ``ohlcv_daily`` — the Stooq archive as ``import_stooq`` leaves it. Nothing is
fabricated and nothing is written: the gate reads, FRED is fetched keylessly, and the row
counts are compared before and after to prove the "writes nothing" contract.

A database without SPY bars SKIPS (there is nothing to measure); a database WITH them must
produce the verdict, so the module can never pass vacuously. The measured figures are
printed beside the reference run of 2026-09-07 rather than pinned to it: the archive grows
by a session a day, so the numbers move — the thresholds, not the readings, are the contract.
"""

from __future__ import annotations

import os

import pytest

from tests.unit.global_market.script_loader import load_global_script

_gdb = load_global_script("_gdb")
vg = load_global_script("validate_global")

pytestmark = pytest.mark.integration

if not os.environ.get("ATLAS_DB_URL", "").strip():
    pytest.skip("ATLAS_DB_URL not set — the BASIS gate needs a database", allow_module_level=True)

M = _gdb.M
GUARDED = ("ohlcv_daily", "macro_daily", "instrument_master")


def _counts() -> dict[str, int]:
    return {t: _gdb.scalar(f"select count(*) from {M}.{t}") for t in GUARDED}


@pytest.fixture(scope="module")
def spy_bars() -> int:
    n = _gdb.scalar(
        f"select count(*) from {M}.ohlcv_daily where instrument_id = "
        f"(select instrument_id from {M}.instrument_master where symbol = :sym and is_active)",
        {"sym": vg.BASIS_SYMBOL},
    )
    if not n:
        pytest.skip(f"no {vg.BASIS_SYMBOL} bars in {M}.ohlcv_daily — nothing to measure")
    return int(n)


@pytest.fixture(scope="module")
def gate(spy_bars: int) -> tuple[object, dict[str, int], dict[str, int]]:
    """The real gate, run once. Returns the Gate plus the row counts either side of it."""
    before = _counts()
    g = vg.Gate()
    vg.check_BASIS(g)
    return g, before, _counts()


def test_the_gate_passes_on_the_real_archive(gate: tuple, spy_bars: int) -> None:
    g, _, _ = gate
    print(f"{vg.BASIS_SYMBOL}: {spy_bars:,d} bars in {M}.ohlcv_daily")
    assert g.fails == 0, f"{g.fails} BASIS check(s) failed — see the printed detail above"


def test_the_gate_writes_nothing(gate: tuple) -> None:
    _, before, after = gate
    assert before == after, f"the gate changed row counts: {before} → {after}"


def test_the_measured_basis_is_total_return(spy_bars: int) -> None:
    """The verdict the next chunk keys off, re-derived here from the same real inputs the
    gate uses — so a change in either feed shows up as a changed verdict, not a silent one."""
    import numpy as np
    import pandas as pd

    from atlas.global_market.providers.fred import fred_series

    bars = _gdb.read_df(
        f"select date, close from {M}.ohlcv_daily where instrument_id = "
        f"(select instrument_id from {M}.instrument_master where symbol = :sym and is_active) "
        "and close is not null order by date",
        {"sym": vg.BASIS_SYMBOL},
    )
    index = fred_series(
        vg.BASIS_INDEX_SERIES, bars["date"].iloc[0], None, end=bars["date"].iloc[-1]
    )
    m = bars.merge(index, on="date", how="inner").sort_values("date", ignore_index=True)
    assert len(m) >= vg.BASIS_MIN_SESSIONS

    px, ix = m["close"].astype(float), m["value"].astype(float)
    years = (m["date"].iloc[-1] - m["date"].iloc[0]).days / vg.BASIS_DAYS_PER_YEAR
    r = pd.DataFrame({"a": px.pct_change(), "b": ix.pct_change()}).dropna()
    corr = float(np.corrcoef(r["a"], r["b"])[0, 1])
    trend = vg._rank_trend(px / ix)
    excess = vg._cagr(float(px.iloc[0]), float(px.iloc[-1]), years) - vg._cagr(
        float(ix.iloc[0]), float(ix.iloc[-1]), years
    )
    print(
        f"measured over {len(m):,d} sessions / {years:.2f} years: r={corr:.6f} rho={trend:.5f} "
        f"excess={excess:+.4%}/yr (2026-09-07 reference: 0.998352 / 0.99712 / +1.6339%)"
    )
    assert vg.basis_verdict(excess, trend) == "total_return"
    assert corr >= vg.BASIS_MIN_RETURN_CORR
    assert abs(float((px / ix).iloc[-1]) / vg.BASIS_SPOT_RATIO - 1) <= vg.BASIS_SPOT_RATIO_TOL

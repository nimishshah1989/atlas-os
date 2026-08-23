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

import _db  # noqa: E402  # pyright: ignore[reportMissingImports]
import build_universe_snapshot as S  # noqa: E402  # pyright: ignore[reportMissingImports]
import universe_core as U  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.integration


def _frame():
    as_of = S.snapshot_date()
    return as_of, S.adv_frame(as_of, int(S.threshold(U.THRESHOLD_KEY_MIN_OBS)))


def test_adv_frame_covers_the_whole_stock_master() -> None:
    """Every stock gets a row — including those with no recent trading, whose ADV is
    NULL rather than 0 (rule: NULL in a financial calc produces NULL)."""
    _, adv = _frame()
    n_stocks = _db.scalar(
        "SELECT count(*) FROM atlas_foundation.instrument_master WHERE asset_class='stock'"
    )
    assert len(adv) == n_stocks, f"expected one row per stock ({n_stocks}), got {len(adv)}"
    assert adv["adv_median_60d"].notna().sum() > 1000, "most stocks should have a real ADV"


def test_adv_frame_reproduces_the_measured_floor_counts() -> None:
    """Counts measured 2026-08-23 AFTER the minimum-observation and recency guards:
    1,205 names at ₹2.5 cr and 990 at ₹5 cr (pre-guard these were 1,282 and 1,043 —
    the guard removes ~77 names whose "median" came from too few prints to have a
    middle). Tolerance is wide because liquidity genuinely drifts; a large miss means
    the SQL changed meaning."""
    _, adv = _frame()
    v = adv["adv_median_60d"].astype("float64")
    at_2p5 = int((v >= 25_000_000).sum())
    at_5 = int((v >= 50_000_000).sum())
    assert 1100 <= at_2p5 <= 1300, f"₹2.5cr floor gave {at_2p5}, expected ~1205 post-guard"
    assert 900 <= at_5 <= 1100, f"₹5cr floor gave {at_5}, expected ~990 post-guard"
    assert at_5 < at_2p5, "a higher floor must be strictly more selective"


def test_thin_traders_get_a_null_adv_not_a_small_one() -> None:
    """The guard's whole point: a median over 2 prints IS the block deal it exists to
    exclude. Names below the session minimum must come back NULL — not low, not 0 —
    so members() drops them via the NULL path with no second code path."""
    as_of, adv = _frame()
    min_obs = int(S.threshold(U.THRESHOLD_KEY_MIN_OBS))
    thin = _db.read_df(
        """WITH d AS (SELECT DISTINCT date FROM atlas_foundation.ohlcv_stock
                      WHERE date <= :c AND date > (CAST(:c AS date) - INTERVAL '150 days')
                      ORDER BY date DESC LIMIT 60)
           SELECT instrument_id::text AS instrument_id, count(*) n
           FROM atlas_foundation.ohlcv_stock WHERE date IN (SELECT date FROM d)
             AND close IS NOT NULL AND volume IS NOT NULL
           GROUP BY 1 HAVING count(*) < :m""",
        {"c": as_of, "m": min_obs},
    )
    assert len(thin) > 0, "no thin traders in the window — this test proves nothing"
    got = adv[adv["instrument_id"].isin(thin["instrument_id"].tolist())]
    assert got["adv_median_60d"].notna().sum() == 0, (
        f"{got['adv_median_60d'].notna().sum()} names under {min_obs} sessions kept an ADV"
    )


def test_snapshot_is_dated_a_real_trading_day() -> None:
    """The journal is keyed on the date it describes, so that date must be one the
    market actually traded — eod_cutoff() alone returns weekends, and a Sunday row
    can never be joined to OHLCV or lens history."""
    d = S.snapshot_date()
    assert d is not None, "no trading date at or before the EOD cutoff"
    assert d <= _db.eod_cutoff(), "snapshot must never be dated past the EOD cutoff"
    traded = _db.scalar(
        "SELECT count(*) FROM atlas_foundation.ohlcv_stock WHERE date = :d", {"d": d}
    )
    assert traded > 0, f"{d} has no OHLCV rows — not a trading day"


def test_held_ids_are_resolvable_and_actually_currently_held() -> None:
    """Regression: instrument_key holds the instrument_id UUID, not the symbol, so the
    obvious join (im.symbol = pt.instrument_key) matches nothing and the retention
    guarantee silently evaporates — an empty result means every held name is one
    liquidity dip away from losing its score with no error raised anywhere.

    Also pins the currently-held semantics: the set must be a STRICT subset of
    ever-traded, or the net-open-position filter is not filtering."""
    held = S.held_ids()
    assert len(held) > 0, "no held names resolved — the UUID-vs-symbol join is back"
    ever = set(
        _db.read_df(
            """SELECT DISTINCT im.instrument_id::text AS instrument_id
               FROM atlas_foundation.portfolio_trades pt
               JOIN atlas_foundation.instrument_master im
                 ON im.instrument_id::text = pt.instrument_key AND im.asset_class='stock'"""
        )["instrument_id"]
    )
    assert held < ever, "currently-held must be a strict subset of ever-traded"
    # spot-check: every retained id is a real stock in the master
    n = _db.scalar(
        "SELECT count(*) FROM atlas_foundation.instrument_master "
        "WHERE instrument_id::text = ANY(:ids) AND asset_class='stock'",
        {"ids": list(held)},
    )
    assert n == len(held), f"{len(held) - n} held ids are not stocks in instrument_master"


def _latest_day_stats() -> tuple:
    """(row count, newest computed_at) for the most recent snapshot date."""
    row = _db.read_df(
        "SELECT count(*) AS n, max(computed_at) AS stamp "
        "FROM atlas_foundation.atlas_universe_snapshot "
        "WHERE date = (SELECT max(date) FROM atlas_foundation.atlas_universe_snapshot)"
    ).iloc[0]
    return int(row["n"]), row["stamp"]


def test_snapshot_write_is_idempotent_and_refreshes_values() -> None:
    """Running twice the same day must not duplicate rows — atlas_daily.sh can retry.
    Row parity alone would also hold if the upsert silently did nothing, so assert the
    DO UPDATE actually fires by watching computed_at advance."""
    S.run()
    first, stamp1 = _latest_day_stats()
    S.run()
    second, stamp2 = _latest_day_stats()
    assert first == second, f"second run duplicated rows: {first} -> {second}"
    assert stamp2 > stamp1, "computed_at did not advance — the upsert refreshed nothing"


def test_snapshot_records_why_not_just_whether() -> None:
    """in_universe alone is not reconstructable. The ADV that produced it and the floor
    it was compared against must be stored alongside, so a past membership decision can
    be re-derived."""
    cols = set(
        _db.read_df(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='atlas_foundation' AND table_name='atlas_universe_snapshot'"
        )["column_name"]
    )
    assert {"date", "instrument_id", "in_universe", "adv_median_60d", "floor_inr"} <= cols

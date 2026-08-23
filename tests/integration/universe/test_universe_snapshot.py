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


def test_held_ids_actually_resolve_against_the_books() -> None:
    """Regression: instrument_key holds the instrument_id UUID, not the symbol, so the
    obvious join (im.symbol = pt.instrument_key) matches nothing and the retention
    guarantee silently evaporates. An empty result here means every held name is one
    liquidity dip away from losing its score with no error raised anywhere."""
    held = S.held_ids()
    traded = _db.scalar(
        "SELECT count(DISTINCT instrument_key) FROM atlas_foundation.portfolio_trades "
        "WHERE asset_class = 'stock'"
    )
    assert traded > 0, "no stock trades in the books — this test proves nothing"
    assert len(held) == traded, f"{traded} traded stocks but only {len(held)} resolved"


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

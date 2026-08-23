"""Integration tests for the liquidity-floor universe rule in build_universe.py.

The rule is ONE threshold comparison: trailing 60-day median daily traded value >=
atlas_thresholds.liquidity_min_traded_value_inr. These tests prove the threshold is
genuinely driving membership — not that a hardcoded number happens to match.

Read-only: nothing here writes.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _db  # noqa: E402  # pyright: ignore[reportMissingImports]
import build_universe as B  # noqa: E402  # pyright: ignore[reportMissingImports]
import build_universe_snapshot as S  # noqa: E402  # pyright: ignore[reportMissingImports]
import universe_core as U  # noqa: E402  # pyright: ignore[reportMissingImports]

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
    held = S.held_ids(S.snapshot_date())
    assert held, "expected at least one held stock in portfolio_trades"
    ids = B.liquid_universe(Decimal("50000000"))  # strict floor, to force the case
    assert held <= ids, f"held names dropped: {sorted(held - ids)}"


def test_current_active_names_are_almost_entirely_retained() -> None:
    """Measured 2026-08-23: of today's 747 active names, 735 clear the ₹2.5 cr floor
    outright, 2 more are retained as currently-held, and 10 drop. Those 10 split into
    two arms that mean completely different things, so they are asserted separately —
    a single combined bound would let a widening data gap hide behind the liquidity
    arm:

      * 2 genuinely below the floor (PRSMJOHNSN ₹2.03 cr, AHLUCONT ₹2.25 cr) — both
        micro-cap, both just under. This is the rule working.
      * 8 with a NULL ADV — no signal, so they never pass. NOT an illiquidity finding:
        atlas_foundation.ohlcv_stock has no current prices for them. All four active
        series-BE names have stale OHLCV (STLTECH stops 2026-06-30, MTARTECH
        2026-06-30, LOTUSDEV 2026-08-10) while 742 of 743 active EQ names are current
        to the latest trading day; the other five joined NIFTY MICROCAP250 on
        2026-05-04 and have 2-14 rows ever ingested. Pre-existing ingestion gap,
        reported not fixed — but bounded here so it cannot widen unnoticed.
    """
    cur = set(
        _db.read_df(
            "SELECT instrument_id::text AS i FROM atlas_foundation.instrument_master "
            "WHERE asset_class='stock' AND is_active"
        )["i"]
    )
    dropped = cur - B.liquid_universe(Decimal("25000000"))
    as_of = S.snapshot_date()
    adv = S.adv_frame(
        as_of,
        int(S.threshold(U.THRESHOLD_KEY_MIN_OBS)),
        int(S.threshold(U.THRESHOLD_KEY_RECENCY)),
    ).set_index("instrument_id")
    no_signal = {i for i in dropped if pd.isna(adv.loc[i, "adv_median_60d"])}
    below = dropped - no_signal

    assert len(below) <= 5, (
        f"{len(below)} current names fall below the floor, expected ~2: "
        + ", ".join(sorted(str(adv.loc[i, "symbol"]) for i in below))
    )
    assert len(no_signal) <= 10, (
        f"{len(no_signal)} current names have NO ADV signal (missing OHLCV), expected 8 "
        "— the ingestion gap has widened: "
        + ", ".join(sorted(str(adv.loc[i, "symbol"]) for i in no_signal))
    )


def test_the_floor_is_read_from_thresholds_not_hardcoded() -> None:
    """Rule #4. The value must exist in atlas_thresholds and sit inside the band that
    row itself declares — the band is read from the row, not restated here."""
    row = _db.read_df(
        "SELECT threshold_value, min_allowed, max_allowed "
        "FROM atlas_foundation.atlas_thresholds WHERE threshold_key = :k AND is_active",
        {"k": U.THRESHOLD_KEY},
    )
    assert len(row) == 1, f"{U.THRESHOLD_KEY} missing from atlas_thresholds"
    v, lo, hi = (Decimal(str(row.iloc[0][c])) for c in row.columns)
    assert lo <= v <= hi, f"floor {v} outside the declared band {lo}..{hi}"


def test_no_two_active_stocks_share_an_isin() -> None:
    """instrument_master carries four duplicate-ISIN pairs from NSE renames
    (GUJGASLTD/GUJENERGY, AMIRCHAND/AEROPLANE, ASHIKA/ASHIKAG, LYPSAGEMS/AURUS). Both
    rows of a pair are the SAME security, so if both ever went active v_stock_cap
    would rank one company twice — consuming two slots in the top-100/250/500 and
    displacing a real name across every cut. Today only one row of each pair carries
    OHLCV, so the liquidity floor excludes the twin, but that is an accident of the
    data and not a guarantee. This must fail loudly if it ever stops holding."""
    dupes = _db.read_df(
        """SELECT isin, string_agg(symbol, '/' ORDER BY symbol) AS symbols
           FROM atlas_foundation.instrument_master
           WHERE asset_class = 'stock' AND is_active AND isin IS NOT NULL AND isin <> ''
           GROUP BY isin HAVING count(*) > 1"""
    )
    assert dupes.empty, (
        "active stocks sharing an ISIN (same security counted twice in v_stock_cap): "
        + "; ".join(f"{r.isin} {r.symbols}" for r in dupes.itertuples())
    )

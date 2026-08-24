"""Unit tests for scripts/foundation/universe_core.py — the liquidity-floor membership
math that decides which stocks Atlas scores.

Fixtures are REAL trailing-60-day median traded values pulled from
atlas_foundation.ohlcv_stock (snapshot 2026-08-23, window 2026-05-25..2026-08-18),
NOT synthetic (rule #0). Values are exact to the paisa as measured — deliberately not
rounded, because rounding a fixture across the very threshold the test asserts on would
make the test prove something the data does not.

The four names bracket both floors as measured on that date:
  BIRLACORPN  ₹5.23 cr  — above ₹5 cr, so in at either floor
  ORIENTCEM   ₹2.63 cr  — between the two floors
  AHLUCONT    ₹2.25 cr  — below ₹2.5 cr
  PRSMJOHNSN  ₹2.03 cr  — below ₹2.5 cr
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

import universe_core as U  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.unit

# Real 60-day median traded values, atlas_foundation snapshot 2026-08-23 (rupees).
REAL_ADV = pd.DataFrame(
    [
        {"instrument_id": "a", "symbol": "BIRLACORPN", "adv_median_60d": Decimal("52254238.40")},
        {"instrument_id": "b", "symbol": "ORIENTCEM", "adv_median_60d": Decimal("26252683.66")},
        {"instrument_id": "c", "symbol": "AHLUCONT", "adv_median_60d": Decimal("22515894.50")},
        {"instrument_id": "d", "symbol": "PRSMJOHNSN", "adv_median_60d": Decimal("20259065.12")},
    ]
)

FLOOR_2P5CR = Decimal("25000000")
FLOOR_5CR = Decimal("50000000")


def test_members_at_2p5cr_floor_keeps_names_at_or_above() -> None:
    got = U.members(REAL_ADV, floor_inr=FLOOR_2P5CR, held_ids=frozenset())
    assert got == {"a", "b"}


def test_members_excludes_names_below_the_floor() -> None:
    got = U.members(REAL_ADV, floor_inr=FLOOR_2P5CR, held_ids=frozenset())
    assert "c" not in got, "AHLUCONT at ₹2.25 cr is below the ₹2.5 cr floor"
    assert "d" not in got, "PRSMJOHNSN at ₹2.03 cr is below the ₹2.5 cr floor"


def test_a_five_crore_floor_is_stricter_than_two_and_a_half() -> None:
    lo = U.members(REAL_ADV, floor_inr=FLOOR_2P5CR, held_ids=frozenset())
    hi = U.members(REAL_ADV, floor_inr=FLOOR_5CR, held_ids=frozenset())
    assert hi < lo, "a higher floor must yield a strict subset"
    assert hi == {"a"}


def test_held_names_stay_in_regardless_of_liquidity() -> None:
    got = U.members(REAL_ADV, floor_inr=FLOOR_2P5CR, held_ids=frozenset({"d"}))
    assert "d" in got, "a name currently held in a portfolio book must never lose its score"


def test_a_value_exactly_at_the_floor_passes() -> None:
    """The rule is >=, not >. ORIENTCEM's real ADV used as its own floor must pass —
    a name is excluded for being BELOW the floor, never for merely reaching it."""
    exactly = Decimal("26252683.66")  # ORIENTCEM's measured ADV, to the paisa
    got = U.members(REAL_ADV, floor_inr=exactly, held_ids=frozenset())
    assert "b" in got, "a name sitting exactly on the floor must be in the universe"
    assert got == {"a", "b"}


def test_empty_frame_yields_only_the_held_names() -> None:
    """No ADV rows at all (a fresh window, an ingestion outage) must not raise and must
    not invent members — the held names, and nothing else."""
    empty = REAL_ADV.iloc[0:0]
    assert U.members(empty, floor_inr=FLOOR_2P5CR, held_ids=frozenset()) == set()
    assert U.members(empty, floor_inr=FLOOR_2P5CR, held_ids=frozenset({"d"})) == {"d"}


def test_null_adv_is_excluded_never_treated_as_zero_or_passing() -> None:
    with_null = pd.concat(
        [
            REAL_ADV,
            pd.DataFrame([{"instrument_id": "e", "symbol": "NODATA", "adv_median_60d": None}]),
        ],
        ignore_index=True,
    )
    got = U.members(with_null, floor_inr=FLOOR_2P5CR, held_ids=frozenset())
    assert "e" not in got, "a NULL ADV means no signal — it must not pass the floor"


def test_a_thin_name_is_null_not_low_so_it_cannot_be_rescued_by_a_lower_floor() -> None:
    """Below the minimum session count the SQL emits NULL, not a small number. That
    distinction is the whole guard: a 2-print median can be enormous, so if it were
    stored as a value rather than NULL it would sail over any floor."""
    thin = pd.DataFrame([{"instrument_id": "f", "symbol": "THIN", "adv_median_60d": None}])
    assert U.members(thin, floor_inr=Decimal("1"), held_ids=frozenset()) == set()

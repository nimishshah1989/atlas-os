"""verify_fund_rank._close — a missing breadth never agrees with a real 0%.

The whole point of the roll-up's COALESCE fix is that 0.0 (fund holds scored names, none
lead) and NULL (no signal at all) are different answers. The gate that compares stored
breadth against production breadth must not collapse them, or it would report agreement
exactly where the defect lives.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from verify_fund_rank import _close  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.unit

NAN = float("nan")


def test_missing_does_not_agree_with_a_real_zero() -> None:
    assert not _close(None, 0.0)
    assert not _close(0.0, None)
    assert not _close(NAN, 0.0)  # pandas reads SQL NULL as NaN


def test_missing_agrees_with_missing() -> None:
    assert _close(None, None)
    assert _close(NAN, None)


def test_equal_and_near_equal_values_agree() -> None:
    assert _close(0.0, 0.0)
    assert _close(0.095760, 0.0957601)


def test_different_values_disagree() -> None:
    assert not _close(0.0957, 0.0559)

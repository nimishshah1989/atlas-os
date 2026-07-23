"""Telegram cross-alert message formatting for the EMA-cross portfolios.

Anchored on the REAL MRPL 13/34 live trade (rule #0): BUY 476 @ ₹174.49 on
2026-07-20, confirmed by the EMA13>EMA34 golden cross at the 2026-07-17 close
(ema_13 157.52, ema_34 156.46 from atlas_foundation.technical_daily).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import portfolio_alerts as A  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.unit


def test_buy_alert_reads_as_a_golden_cross() -> None:
    msg = A.format_cross_alert(
        fast=13,
        slow=34,
        symbol="MRPL",
        side="buy",
        qty=476,
        price=174.49,
        reason="signal",
        trade_date=date(2026, 7, 20),
        ema_fast=157.52,
        ema_slow=156.46,
    )
    assert "EMA 13/34" in msg
    assert "BUY" in msg
    assert "MRPL" in msg
    assert "above" in msg  # EMA13 crossed above EMA34
    assert "174.49" in msg and "476" in msg
    assert "157.52" in msg and "156.46" in msg


def test_sell_signal_reads_as_a_death_cross() -> None:
    msg = A.format_cross_alert(
        fast=13,
        slow=34,
        symbol="MRPL",
        side="sell",
        qty=476,
        price=150.53,
        reason="signal",
        trade_date=date(2026, 5, 8),
        ema_fast=150.10,
        ema_slow=151.30,
    )
    assert "SELL" in msg
    assert "below" in msg  # EMA13 crossed below EMA34
    assert "death" in msg.lower()


def test_sell_stop_names_the_stop_not_a_cross() -> None:
    msg = A.format_cross_alert(
        fast=50,
        slow=200,
        symbol="GRAVITA",
        side="sell",
        qty=100,
        price=1500.0,
        reason="stop",
        trade_date=date(2026, 6, 1),
        ema_fast=None,
        ema_slow=None,
    )
    assert "SELL" in msg
    assert "stop" in msg.lower()
    # EMA line is omitted gracefully when the values aren't available.
    assert "None" not in msg

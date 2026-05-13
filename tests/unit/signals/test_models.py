from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from atlas.signals.models import SignalReportResponse, TVSignalPayload


def test_tv_signal_payload_parses_valid():
    payload = TVSignalPayload(
        tier=1,
        code="breakout_52w_volume",
        chart="vs_nifty",
        ticker="HDFCBANK",
        exchange="NSE",
        close="1820.50",
        volume="4500000",
        time="2026-05-13T09:20:00Z",
        secret="test_secret_32_chars_long_exactly",
    )
    assert payload.tier == 1
    assert payload.close == Decimal("1820.50")
    assert payload.volume == 4500000


def test_tv_signal_payload_rejects_float_close():
    with pytest.raises(ValidationError):
        TVSignalPayload(
            tier=1,
            code="x",
            chart="vs_nifty",
            ticker="X",
            exchange="NSE",
            close=1820.5,  # float not allowed
            volume="100",
            time="2026-05-13T09:20:00Z",
            secret="x",
        )


def test_tv_signal_payload_rejects_invalid_chart():
    with pytest.raises(ValidationError):
        TVSignalPayload(
            tier=1,
            code="x",
            chart="vs_invalid",
            ticker="X",
            exchange="NSE",
            close="100",
            volume="100",
            time="2026-05-13T09:20:00Z",
            secret="x",
        )


def test_signal_report_response_has_required_fields():
    r = SignalReportResponse(
        id="00000000-0000-0000-0000-000000000001",
        ticker="HDFCBANK",
        condition_label="52-week high breakout with 1.5x volume",
        condition_tier=1,
        confirmation_level="dual",
        triggered_at=datetime.now(UTC),
        verdict="bullish",
    )
    assert r.ticker == "HDFCBANK"


def test_signal_report_response_optional_fields_default_none():
    r = SignalReportResponse(
        id="00000000-0000-0000-0000-000000000001",
        ticker="RELIANCE",
        condition_label="Label",
        condition_tier=1,
        confirmation_level="tv_only",
        triggered_at=datetime.now(UTC),
        verdict="watch",
    )
    assert r.conviction_score is None
    assert r.narrative is None

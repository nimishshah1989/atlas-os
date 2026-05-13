"""Tests for atlas.intraday.persistence (pure unit tests, no DB required)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from atlas.intraday.persistence import BarRecord, NiftyBarRecord

_IST = timezone(timedelta(hours=5, minutes=30))


class TestBarRecord:
    def test_bar_record_creation_with_all_fields(self) -> None:
        bar_time = datetime(2026, 5, 12, 9, 30, tzinfo=_IST)
        inst_id = uuid.uuid4()
        bar = BarRecord(
            instrument_id=inst_id,
            bar_time=bar_time,
            open=Decimal("100.00"),
            high=Decimal("102.50"),
            low=Decimal("99.50"),
            close=Decimal("101.75"),
            volume=50000,
            tick_count=120,
            ema_20=Decimal("100.50"),
            ema_50=Decimal("99.80"),
            rs_vs_nifty=Decimal("1.23"),
            gap_filled=False,
        )
        assert bar.instrument_id == inst_id
        assert bar.close == Decimal("101.75")
        assert bar.gap_filled is False

    def test_bar_record_gap_filled_defaults_to_false(self) -> None:
        bar = BarRecord(
            instrument_id=uuid.uuid4(),
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=None,
            high=None,
            low=None,
            close=Decimal("100"),
            volume=None,
            tick_count=None,
            ema_20=None,
            ema_50=None,
            rs_vs_nifty=None,
        )
        assert bar.gap_filled is False

    def test_bar_record_optional_fields_accept_none(self) -> None:
        bar = BarRecord(
            instrument_id=uuid.uuid4(),
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=None,
            high=None,
            low=None,
            close=Decimal("150.00"),
            volume=None,
            tick_count=None,
            ema_20=None,
            ema_50=None,
            rs_vs_nifty=None,
        )
        assert bar.open is None
        assert bar.ema_20 is None
        assert bar.rs_vs_nifty is None

    def test_bar_record_close_is_decimal_not_float(self) -> None:
        bar = BarRecord(
            instrument_id=uuid.uuid4(),
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=None,
            high=None,
            low=None,
            close=Decimal("200.00"),
            volume=None,
            tick_count=None,
            ema_20=None,
            ema_50=None,
            rs_vs_nifty=None,
        )
        assert isinstance(bar.close, Decimal)

    def test_bar_record_gap_filled_can_be_true(self) -> None:
        bar = BarRecord(
            instrument_id=uuid.uuid4(),
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=None,
            high=None,
            low=None,
            close=Decimal("100"),
            volume=None,
            tick_count=None,
            ema_20=None,
            ema_50=None,
            rs_vs_nifty=None,
            gap_filled=True,
        )
        assert bar.gap_filled is True

    def test_bar_record_return_since_open_defaults_none(self) -> None:
        """return_since_open defaults to None when not specified."""
        bar = BarRecord(
            instrument_id=uuid.uuid4(),
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=None,
            high=None,
            low=None,
            close=Decimal("100"),
            volume=None,
            tick_count=None,
            ema_20=None,
            ema_50=None,
            rs_vs_nifty=None,
        )
        assert bar.return_since_open is None

    def test_bar_record_return_since_open_accepted_as_decimal(self) -> None:
        """return_since_open is stored as Decimal when provided."""
        bar = BarRecord(
            instrument_id=uuid.uuid4(),
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=None,
            high=None,
            low=None,
            close=Decimal("150"),
            volume=None,
            tick_count=None,
            ema_20=None,
            ema_50=None,
            rs_vs_nifty=None,
            return_since_open=Decimal("0.012345"),
        )
        assert isinstance(bar.return_since_open, Decimal)
        assert bar.return_since_open == Decimal("0.012345")


# ---------------------------------------------------------------------------
# NiftyBarRecord
# ---------------------------------------------------------------------------


class TestNiftyBarRecord:
    def test_nifty_bar_record_creation_with_all_fields(self) -> None:
        """NiftyBarRecord can be created with all OHLC + return_since_open fields."""
        bar = NiftyBarRecord(
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=Decimal("24500.00"),
            high=Decimal("24550.00"),
            low=Decimal("24480.00"),
            close=Decimal("24530.00"),
            return_since_open=Decimal("0.001224"),
        )
        assert bar.close == Decimal("24530.00")
        assert bar.return_since_open == Decimal("0.001224")

    def test_nifty_bar_record_return_since_open_defaults_none(self) -> None:
        """return_since_open defaults to None when not provided."""
        bar = NiftyBarRecord(
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=Decimal("24500.00"),
            high=Decimal("24550.00"),
            low=Decimal("24480.00"),
            close=Decimal("24530.00"),
        )
        assert bar.return_since_open is None

    def test_nifty_bar_record_all_prices_are_decimal(self) -> None:
        """open, high, low, close are Decimal — not float."""
        bar = NiftyBarRecord(
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=Decimal("24500.00"),
            high=Decimal("24550.00"),
            low=Decimal("24480.00"),
            close=Decimal("24530.00"),
            return_since_open=Decimal("0.001"),
        )
        for field_name, val in [
            ("open", bar.open),
            ("high", bar.high),
            ("low", bar.low),
            ("close", bar.close),
        ]:
            assert isinstance(val, Decimal), f"{field_name} should be Decimal not {type(val)}"

    def test_nifty_bar_record_return_since_open_is_decimal_or_none(self) -> None:
        """return_since_open is Decimal when set."""
        bar = NiftyBarRecord(
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=Decimal("24500.00"),
            high=Decimal("24550.00"),
            low=Decimal("24480.00"),
            close=Decimal("24530.00"),
            return_since_open=Decimal("0.005"),
        )
        assert isinstance(bar.return_since_open, Decimal)

    def test_nifty_bar_record_bar_time_is_tz_aware(self) -> None:
        """bar_time must carry timezone info."""
        bar = NiftyBarRecord(
            bar_time=datetime(2026, 5, 12, 9, 30, tzinfo=_IST),
            open=Decimal("24500.00"),
            high=Decimal("24550.00"),
            low=Decimal("24480.00"),
            close=Decimal("24530.00"),
        )
        assert bar.bar_time.tzinfo is not None

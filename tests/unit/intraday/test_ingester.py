"""Tests for atlas.intraday.ingester (unit tests, no DB or KiteConnect required)."""

from __future__ import annotations

from decimal import Decimal

from atlas.intraday.ingester import _BAR_MINUTES, IntradayIngester


class TestSecondsToBoundary:
    """Tests for _seconds_to_next_boundary via ingester instance."""

    def _make_ingester(self) -> IntradayIngester:
        return IntradayIngester(conn_str="postgresql://fake/fake")

    def test_returns_float(self) -> None:
        ingester = self._make_ingester()
        result = ingester._seconds_to_next_boundary()
        assert isinstance(result, float)

    def test_returns_non_negative(self) -> None:
        ingester = self._make_ingester()
        result = ingester._seconds_to_next_boundary()
        assert result >= 0.0

    def test_returns_at_most_15_minutes(self) -> None:
        ingester = self._make_ingester()
        result = ingester._seconds_to_next_boundary()
        assert result <= 900.0  # 15 * 60 seconds

    def test_bar_minutes_contains_correct_values(self) -> None:
        assert _BAR_MINUTES == {0, 15, 30, 45}


class TestMergeTick:
    """Tests for _merge_tick OHLCV accumulation logic."""

    def _make_ingester(self, token_map: dict) -> IntradayIngester:
        ingester = IntradayIngester(conn_str="postgresql://fake/fake")
        ingester._token_map = token_map
        return ingester

    def test_first_tick_initialises_bar(self) -> None:
        token = 12345
        inst_id = "aaa-bbb-ccc"
        ingester = self._make_ingester({token: inst_id})

        tick = {
            "instrument_token": token,
            "last_price": 100.0,
            "ohlc": {"open": 99.0},
            "volume": 1000,
        }
        ingester._merge_tick(tick)

        assert token in ingester._current_bar
        bar = ingester._current_bar[token]
        assert bar["close"] == Decimal("100.0")
        assert bar["open"] == Decimal("99.0")
        assert bar["tick_count"] == 1

    def test_second_tick_updates_close_and_increments_tick_count(self) -> None:
        token = 12345
        ingester = self._make_ingester({token: "abc"})

        tick1 = {
            "instrument_token": token,
            "last_price": 100.0,
            "ohlc": {"open": 99.0},
            "volume": 1000,
        }
        tick2 = {
            "instrument_token": token,
            "last_price": 102.0,
            "ohlc": {"open": 99.0},
            "volume": 2000,
        }
        ingester._merge_tick(tick1)
        ingester._merge_tick(tick2)

        bar = ingester._current_bar[token]
        assert bar["close"] == Decimal("102.0")
        assert bar["tick_count"] == 2

    def test_high_tracks_maximum_price(self) -> None:
        token = 12345
        ingester = self._make_ingester({token: "abc"})

        for price in [100.0, 105.0, 103.0, 108.0, 106.0]:
            ingester._merge_tick(
                {
                    "instrument_token": token,
                    "last_price": price,
                    "ohlc": {"open": 100.0},
                    "volume": 1000,
                }
            )

        assert ingester._current_bar[token]["high"] == Decimal("108.0")

    def test_low_tracks_minimum_price(self) -> None:
        token = 12345
        ingester = self._make_ingester({token: "abc"})

        for price in [100.0, 98.0, 95.0, 97.0, 99.0]:
            ingester._merge_tick(
                {
                    "instrument_token": token,
                    "last_price": price,
                    "ohlc": {"open": 100.0},
                    "volume": 1000,
                }
            )

        assert ingester._current_bar[token]["low"] == Decimal("95.0")

    def test_unknown_token_tick_is_ignored(self) -> None:
        ingester = self._make_ingester({99999: "abc"})
        ingester._merge_tick(
            {
                "instrument_token": 11111,  # not in token_map
                "last_price": 100.0,
                "ohlc": {},
                "volume": 500,
            }
        )
        assert 11111 not in ingester._current_bar

    def test_tick_missing_instrument_token_is_ignored(self) -> None:
        ingester = self._make_ingester({})
        ingester._merge_tick({"last_price": 100.0, "volume": 500})
        assert len(ingester._current_bar) == 0

    def test_tick_missing_last_price_is_ignored(self) -> None:
        token = 12345
        ingester = self._make_ingester({token: "abc"})
        ingester._merge_tick({"instrument_token": token, "volume": 500})
        assert token not in ingester._current_bar


class TestStripDialect:
    def test_strip_psycopg2_dialect(self) -> None:
        from atlas.intraday.ingester import _strip_dialect

        result = _strip_dialect("postgresql+psycopg2://user:pass@host/db")
        assert result == "postgresql://user:pass@host/db"

    def test_plain_postgresql_unchanged(self) -> None:
        from atlas.intraday.ingester import _strip_dialect

        result = _strip_dialect("postgresql://user:pass@host/db")
        assert result == "postgresql://user:pass@host/db"

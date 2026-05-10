import io
import sys
import zipfile
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, ".")
from scripts.etf_sector_backfill import (
    TARGET_ETFS,
    TICKER_BHAV_ALIASES,
    build_bhav_url,
    build_master_upsert_params,
    build_new_bhav_url,
    build_ohlcv_insert_params,
    download_bhav_zip,
    parse_bhav_csv,
    parse_bhav_date,
    parse_bhav_zip,
    safe_decimal,
    safe_int_volume,
    trading_dates,
    verify_tickers,
)


class TestSafeDecimal:
    def test_normal_value(self):
        assert safe_decimal("246.80") == Decimal("246.80")

    def test_empty_string_returns_none(self):
        assert safe_decimal("") is None

    def test_zero_string_returns_zero(self):
        assert safe_decimal("0.00") == Decimal("0.00")

    def test_strips_whitespace(self):
        assert safe_decimal("  123.45  ") == Decimal("123.45")

    def test_invalid_string_returns_none(self):
        assert safe_decimal("N/A") is None

    def test_dash_returns_none(self):
        assert safe_decimal("-") is None


class TestSafeIntVolume:
    def test_integer_string(self):
        assert safe_int_volume("50000") == 50000

    def test_float_format_truncates(self):
        # NSE sometimes emits "12345.00"
        assert safe_int_volume("12345.00") == 12345

    def test_empty_string_returns_zero(self):
        assert safe_int_volume("") == 0

    def test_invalid_returns_zero(self):
        assert safe_int_volume("N/A") == 0


class TestParseBhavDate:
    def test_short_month(self):
        assert parse_bhav_date("07-APR-2016") == date(2016, 4, 7)

    def test_full_month_name_fallback(self):
        assert parse_bhav_date("07-APRIL-2016") == date(2016, 4, 7)

    def test_strips_whitespace(self):
        assert parse_bhav_date("  07-APR-2016  ") == date(2016, 4, 7)

    def test_invalid_returns_none(self):
        assert parse_bhav_date("not-a-date") is None


class TestParseBhavZip:
    def _make_zip(self, csv_content: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("bhav.csv", csv_content)
        return buf.getvalue()

    def test_extracts_target_tickers(self):
        csv_content = (
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,"
            "TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN\n"
            "PHARMABEES,EQ,100.00,102.00,99.00,101.50,101.50,100.20,"
            "50000,5075000.00,07-APR-2016,500,INE001\n"
            "NIFTYBEES,EQ,245.00,247.50,244.00,246.80,246.80,244.75,"
            "1000000,247000000.00,07-APR-2016,4321,INE002\n"
        )
        zip_bytes = self._make_zip(csv_content)
        targets = {"PHARMABEES", "AUTOBEES"}
        rows = parse_bhav_zip(zip_bytes, targets)
        assert len(rows) == 1
        row = rows[0]
        assert row["ticker"] == "PHARMABEES"
        assert row["date"] == date(2016, 4, 7)
        assert row["open"] == Decimal("100.00")
        assert row["close"] == Decimal("101.50")
        assert row["volume"] == 50000

    def test_skips_non_eq_series(self):
        csv_content = (
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,"
            "TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN\n"
            "PHARMABEES,BE,100.00,102.00,99.00,101.50,101.50,100.20,"
            "50000,5075000.00,07-APR-2016,500,INE001\n"
        )
        zip_bytes = self._make_zip(csv_content)
        rows = parse_bhav_zip(zip_bytes, {"PHARMABEES"})
        assert rows == []

    def test_returns_empty_for_no_matches(self):
        csv_content = (
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,"
            "TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN\n"
        )
        zip_bytes = self._make_zip(csv_content)
        rows = parse_bhav_zip(zip_bytes, {"PHARMABEES"})
        assert rows == []

    def test_handles_bad_zip(self):
        rows = parse_bhav_zip(b"not a zip", {"PHARMABEES"})
        assert rows == []


class TestBuildBhavUrl:
    def test_known_date_primary(self):
        d = date(2023, 1, 2)
        url = build_bhav_url(d)
        assert url == (
            "https://archives.nseindia.com/content/historical/"
            "EQUITIES/2023/JAN/cm02JAN2023bhav.csv.zip"
        )

    def test_december(self):
        d = date(2022, 12, 30)
        url = build_bhav_url(d)
        assert "DEC" in url
        assert "2022" in url
        assert "30DEC2022" in url

    def test_fallback_uses_different_subdomain(self):
        d = date(2023, 1, 2)
        primary = build_bhav_url(d, fallback=False)
        fallback = build_bhav_url(d, fallback=True)
        assert "archives.nseindia.com" in primary
        assert "nsearchives.nseindia.com" in fallback
        # Path component should be identical
        assert primary.split(".com")[1] == fallback.split(".com")[1]

    def test_single_digit_day_is_zero_padded(self):
        d = date(2023, 4, 5)
        url = build_bhav_url(d)
        assert "05APR2023" in url


class TestTradingDates:
    def test_excludes_saturday(self):
        # 2023-01-07 is a Saturday
        dates = trading_dates(date(2023, 1, 6), date(2023, 1, 9))
        weekdays = {d.weekday() for d in dates}
        assert 5 not in weekdays  # no Saturday
        assert 6 not in weekdays  # no Sunday

    def test_includes_all_weekdays_in_range(self):
        # Mon 2023-01-02 to Fri 2023-01-06 = 5 days
        dates = trading_dates(date(2023, 1, 2), date(2023, 1, 6))
        assert len(dates) == 5

    def test_single_day_range(self):
        d = date(2023, 1, 3)  # Tuesday
        dates = trading_dates(d, d)
        assert dates == [d]

    def test_ascending_order(self):
        dates = trading_dates(date(2023, 1, 2), date(2023, 1, 6))
        assert dates == sorted(dates)


class TestDownloadBhavZip:
    def test_returns_bytes_on_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"PK\x03\x04fake_zip"
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        result = download_bhav_zip(mock_session, date(2023, 1, 3))
        assert result == b"PK\x03\x04fake_zip"

    def test_returns_none_on_404(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        result = download_bhav_zip(mock_session, date(2023, 1, 1), retry=0)
        assert result is None

    def test_returns_none_when_all_retries_fail(self):
        import requests as req

        mock_session = MagicMock()
        mock_session.get.side_effect = req.ConnectionError("timeout")

        result = download_bhav_zip(mock_session, date(2023, 1, 3), retry=0)
        assert result is None


class TestVerifyTickers:
    def _make_zip_bytes(self, symbols: list[str]) -> bytes:
        lines = [
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,"
            "TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN"
        ]
        for sym in symbols:
            lines.append(
                f"{sym},EQ,100.00,102.00,99.00,101.50,101.50,100.20,"
                f"50000,5075000.00,09-MAY-2026,500,INE001"
            )
        csv_content = "\n".join(lines)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("bhav.csv", csv_content)
        return buf.getvalue()

    def test_found_and_missing_split(self):
        zip_bytes = self._make_zip_bytes(["PHARMABEES", "AUTOBEES"])
        found, missing = verify_tickers(zip_bytes, {"PHARMABEES", "AUTOBEES", "METALIETF"})
        assert "PHARMABEES" in found
        assert "AUTOBEES" in found
        assert "METALIETF" in missing

    def test_all_present(self):
        zip_bytes = self._make_zip_bytes(["PHARMABEES", "AUTOBEES"])
        found, missing = verify_tickers(zip_bytes, {"PHARMABEES", "AUTOBEES"})
        assert missing == set()
        assert found == {"PHARMABEES", "AUTOBEES"}

    def test_all_missing(self):
        zip_bytes = self._make_zip_bytes([])
        found, missing = verify_tickers(zip_bytes, {"PHARMABEES"})
        assert found == set()
        assert "PHARMABEES" in missing

    def test_returns_disjoint_sets(self):
        zip_bytes = self._make_zip_bytes(["PHARMABEES"])
        found, missing = verify_tickers(zip_bytes, {"PHARMABEES", "METALIETF"})
        assert found & missing == set()  # disjoint
        assert found | missing == {"PHARMABEES", "METALIETF"}  # complete


class TestBuildMasterUpsertParams:
    def test_required_fields_present(self):
        etf = {
            "ticker": "PHARMABEES",
            "name": "Nippon India ETF Nifty Pharma",
            "sector": "Pharma",
            "benchmark": "NIFTY PHARMA",
        }
        params = build_master_upsert_params(etf)
        assert params["ticker"] == "PHARMABEES"
        assert params["exchange"] == "NSE"
        assert params["country"] == "IN"
        assert params["currency"] == "INR"
        assert params["is_active"] is True
        assert params["source"] == "nse_bhav"

    def test_sector_and_benchmark_forwarded(self):
        etf = {
            "ticker": "MOENERGY",
            "name": "Motilal Oswal Nifty Energy ETF",
            "sector": "Energy",
            "benchmark": "NIFTY ENERGY",
        }
        params = build_master_upsert_params(etf)
        assert params["sector"] == "Energy"
        assert params["benchmark"] == "NIFTY ENERGY"

    def test_missing_optional_fields_return_none(self):
        etf = {"ticker": "TEST", "name": "Test ETF"}
        params = build_master_upsert_params(etf)
        assert params["sector"] is None
        assert params["benchmark"] is None


class TestBuildOhlcvInsertParams:
    def test_maps_fields_correctly(self):
        from datetime import date as date_type
        from decimal import Decimal

        row = {
            "ticker": "PHARMABEES",
            "date": date_type(2023, 1, 3),
            "open": Decimal("101.00"),
            "high": Decimal("103.00"),
            "low": Decimal("100.00"),
            "close": Decimal("102.50"),
            "volume": 50000,
        }
        params = build_ohlcv_insert_params(row)
        assert params["ticker"] == "PHARMABEES"
        assert params["date"] == date_type(2023, 1, 3)
        assert params["close"] == Decimal("102.50")
        assert params["volume"] == 50000

    def test_preserves_decimal_type(self):
        from decimal import Decimal

        row = {
            "ticker": "X",
            "date": date(2023, 1, 3),
            "open": Decimal("1.00"),
            "high": Decimal("2.00"),
            "low": Decimal("0.50"),
            "close": Decimal("1.50"),
            "volume": 100,
        }
        params = build_ohlcv_insert_params(row)
        assert isinstance(params["close"], Decimal)
        assert isinstance(params["open"], Decimal)

    def test_none_prices_preserved(self):
        # open/high/low can be None for some ETFs
        row = {
            "ticker": "X",
            "date": date(2023, 1, 3),
            "open": None,
            "high": None,
            "low": None,
            "close": Decimal("1.50"),
            "volume": 0,
        }
        params = build_ohlcv_insert_params(row)
        assert params["open"] is None
        assert params["high"] is None


class TestBuildNewBhavUrl:
    def test_ddmmyyyy_format(self):
        d = date(2026, 5, 8)
        url = build_new_bhav_url(d)
        assert url.endswith("sec_bhavdata_full_08052026.csv")
        assert "nsearchives.nseindia.com" in url

    def test_zero_padded_day_and_month(self):
        d = date(2025, 1, 2)
        url = build_new_bhav_url(d)
        assert "02012025" in url


class TestParseBhavCsv:
    """Tests for the new NSE BHAV CSV format (sec_bhavdata_full_DDMMYYYY.csv)."""

    CSV_HEADER = (
        "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, "
        "LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, "
        "NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"
    )

    def _make_csv(self, rows: list[str]) -> bytes:
        return (self.CSV_HEADER + "\n".join(rows)).encode("utf-8")

    @staticmethod
    def _row(
        sym, series="EQ", dt="08-May-2026", o="1.00", h="1.00", lo="1.00", c="1.00", vol="100"
    ) -> str:
        """Build a minimal new-format BHAV CSV row (15 columns)."""
        return (
            f"{sym}, {series}, {dt}, 0.00, {o}, {h}, {lo}, "
            f"{c}, {c}, {c}, {vol}, 1.00, 1, 50, 50.00"
        )

    def test_extracts_target_tickers(self):
        csv_bytes = self._make_csv(
            [
                self._row("PHARMABEES", o="24.81", h="24.96", lo="24.60", c="24.78", vol="7292625"),
                self._row(
                    "NIFTYBEES", o="246.00", h="248.00", lo="244.00", c="247.00", vol="1000000"
                ),
            ]
        )
        rows = parse_bhav_csv(csv_bytes, {"PHARMABEES"})
        assert len(rows) == 1
        row = rows[0]
        assert row["ticker"] == "PHARMABEES"
        assert row["date"] == date(2026, 5, 8)
        assert row["close"] == Decimal("24.78")
        assert row["open"] == Decimal("24.81")
        assert row["volume"] == 7292625

    def test_skips_non_eq_series(self):
        csv_bytes = self._make_csv(
            [
                self._row("PHARMABEES", series="GS"),
            ]
        )
        rows = parse_bhav_csv(csv_bytes, {"PHARMABEES"})
        assert rows == []

    def test_returns_empty_for_no_matches(self):
        csv_bytes = self._make_csv(
            [
                self._row("NIFTYBEES"),
            ]
        )
        rows = parse_bhav_csv(csv_bytes, {"PHARMABEES"})
        assert rows == []

    def test_volume_float_format(self):
        # NSE sometimes emits volume as a float in the new format
        csv_bytes = self._make_csv(
            [
                self._row("MOENERGY", vol="198905.00"),
            ]
        )
        rows = parse_bhav_csv(csv_bytes, {"MOENERGY"})
        assert rows[0]["volume"] == 198905


class TestTargetEtfs:
    """Sanity checks on TARGET_ETFS and TICKER_BHAV_ALIASES."""

    def test_ten_etfs_defined(self):
        assert len(TARGET_ETFS) == 10

    def test_no_invalid_tickers(self):
        # These symbols never existed on NSE; any of them in TARGET_ETFS is a bug.
        invalid = {"NETFIT", "NETFMETAL", "NETFMID150"}
        tickers = {e["ticker"] for e in TARGET_ETFS}
        assert tickers & invalid == set(), f"Invalid tickers found: {tickers & invalid}"

    def test_correct_current_tickers_present(self):
        tickers = {e["ticker"] for e in TARGET_ETFS}
        assert "ITBEES" in tickers
        assert "MID150BEES" in tickers
        assert "METALIETF" in tickers

    def test_alias_keys_are_current_tickers(self):
        current_tickers = {e["ticker"] for e in TARGET_ETFS}
        for _canonical in TICKER_BHAV_ALIASES:
            assert _canonical in current_tickers, f"Alias key '{_canonical}' is not in TARGET_ETFS"

    def test_alias_values_are_old_symbols_not_in_target(self):
        current_tickers = {e["ticker"] for e in TARGET_ETFS}
        for _canonical, aliases in TICKER_BHAV_ALIASES.items():
            for alias in aliases:
                assert (
                    alias not in current_tickers
                ), f"Alias '{alias}' should be an old symbol, not a current ticker"

    def test_itbees_alias_includes_netfit(self):
        assert "NETFIT" in TICKER_BHAV_ALIASES.get("ITBEES", [])

    def test_mid150bees_alias_includes_netfmid150(self):
        assert "NETFMID150" in TICKER_BHAV_ALIASES.get("MID150BEES", [])

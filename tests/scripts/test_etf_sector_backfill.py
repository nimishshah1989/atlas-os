import io
import sys
import zipfile
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, ".")
from scripts.etf_sector_backfill import (
    build_bhav_url,
    download_bhav_zip,
    parse_bhav_date,
    parse_bhav_zip,
    safe_decimal,
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


class TestParseBhavDate:
    def test_short_month(self):
        assert parse_bhav_date("07-APR-2016") == date(2016, 4, 7)

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
        found, missing = verify_tickers(
            zip_bytes, {"PHARMABEES", "AUTOBEES", "NETFMETAL"}
        )
        assert "PHARMABEES" in found
        assert "AUTOBEES" in found
        assert "NETFMETAL" in missing

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
        found, missing = verify_tickers(zip_bytes, {"PHARMABEES", "NETFMETAL"})
        assert found & missing == set()  # disjoint
        assert found | missing == {"PHARMABEES", "NETFMETAL"}  # complete

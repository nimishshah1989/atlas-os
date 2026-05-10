import io
import sys
import zipfile
from datetime import date
from decimal import Decimal

sys.path.insert(0, ".")
from scripts.etf_sector_backfill import parse_bhav_date, parse_bhav_zip, safe_decimal


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

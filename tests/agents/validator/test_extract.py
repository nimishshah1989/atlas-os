"""Unit tests for route_crawler.extract.parse_dom_value.

No DB or browser required — pure parse logic.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas.agents.validator.route_crawler.extract import ExtractError, parse_dom_value


class TestPercentage:
    def test_positive_pct(self) -> None:
        assert parse_dom_value("+12.5%") == Decimal("0.125")

    def test_negative_pct(self) -> None:
        assert parse_dom_value("-3.2%") == Decimal("-0.032")

    def test_bare_pct(self) -> None:
        assert parse_dom_value("85%") == Decimal("0.85")

    def test_pct_with_spaces(self) -> None:
        assert parse_dom_value("  50%  ") == Decimal("0.50")

    def test_pct_with_commas(self) -> None:
        # Edge case: large percentage like "1,000%" is unusual but should parse
        assert parse_dom_value("1,000%") == Decimal("10.00")


class TestCurrency:
    def test_indian_lakh(self) -> None:
        assert parse_dom_value("₹1,23,456.78") == Decimal("123456.78")

    def test_simple_currency(self) -> None:
        assert parse_dom_value("₹1000") == Decimal("1000")

    def test_currency_with_spaces(self) -> None:
        assert parse_dom_value("₹ 500.00") == Decimal("500.00")


class TestNumeric:
    def test_bare_fraction(self) -> None:
        assert parse_dom_value("0.85") == Decimal("0.85")

    def test_integer(self) -> None:
        assert parse_dom_value("85") == Decimal("85")

    def test_with_commas(self) -> None:
        assert parse_dom_value("1,234.56") == Decimal("1234.56")

    def test_positive_sign(self) -> None:
        assert parse_dom_value("+5.0") == Decimal("5.0")

    def test_negative(self) -> None:
        assert parse_dom_value("-3.14") == Decimal("-3.14")


class TestCategorical:
    def test_state_string(self) -> None:
        assert parse_dom_value("Overweight") == "Overweight"

    def test_yes_no(self) -> None:
        assert parse_dom_value("Yes") == "Yes"
        assert parse_dom_value("No") == "No"

    def test_state_with_spaces(self) -> None:
        assert parse_dom_value("  Leader  ") == "Leader"


class TestAbsent:
    def test_em_dash(self) -> None:
        assert parse_dom_value("—") is None

    def test_en_dash(self) -> None:
        assert parse_dom_value("–") is None

    def test_bare_dash(self) -> None:
        assert parse_dom_value("-") is None

    def test_empty_string(self) -> None:
        assert parse_dom_value("") is None

    def test_na(self) -> None:
        assert parse_dom_value("N/A") is None
        assert parse_dom_value("n/a") is None


class TestExtractError:
    def test_loading_dots(self) -> None:
        with pytest.raises(ExtractError) as exc_info:
            parse_dom_value("Loading...")
        assert exc_info.value.raw == "Loading..."

    def test_loading_word(self) -> None:
        with pytest.raises(ExtractError):
            parse_dom_value("LOADING")

    def test_fetching(self) -> None:
        with pytest.raises(ExtractError):
            parse_dom_value("Fetching data...")

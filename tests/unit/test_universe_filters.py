"""Unit tests for universe-builder pure-logic helpers.

These tests run without a database — they exercise the classification
and filtering logic that lives in pure Python (no SQL).

Tier classification (``stocks._classify_tier``), ETF theme classification
(``etfs._classify_theme``), and fund category-to-benchmark mapping
(``funds._category_to_benchmark_code``) are all testable in isolation
and form Tier 3's ground-truth reference.
"""

from __future__ import annotations

import pytest

from atlas.universe.etfs import _classify_theme
from atlas.universe.funds import _category_to_benchmark_code
from atlas.universe.stocks import _classify_tier

# ---------------------------------------------------------------------------
# Stock tier classification
# ---------------------------------------------------------------------------


def _make_tier_args(
    *,
    instrument_id: str = "00000000-0000-0000-0000-000000000001",
    in_nifty_100: bool = False,
    in_nifty_500: bool = False,
    midcap_ids: set[str] | None = None,
    smallcap_ids: set[str] | None = None,
) -> dict[str, object]:
    return {
        "instrument_id": instrument_id,
        "in_nifty_100": in_nifty_100,
        "in_nifty_500": in_nifty_500,
        "midcap_ids": midcap_ids or set(),
        "smallcap_ids": smallcap_ids or set(),
    }


class TestClassifyTier:
    def test_nifty_100_is_large(self) -> None:
        args = _make_tier_args(in_nifty_100=True, in_nifty_500=True)
        assert _classify_tier(**args) == "Large"  # type: ignore[arg-type]

    def test_midcap_constituent_is_mid(self) -> None:
        iid = "test-mid-id"
        args = _make_tier_args(
            instrument_id=iid,
            in_nifty_500=True,
            midcap_ids={iid},
        )
        assert _classify_tier(**args) == "Mid"  # type: ignore[arg-type]

    def test_smallcap_constituent_is_small(self) -> None:
        iid = "test-small-id"
        args = _make_tier_args(
            instrument_id=iid,
            in_nifty_500=True,
            smallcap_ids={iid},
        )
        assert _classify_tier(**args) == "Small"  # type: ignore[arg-type]

    def test_outside_nifty_500_is_micro(self) -> None:
        args = _make_tier_args(in_nifty_500=False)
        assert _classify_tier(**args) == "Micro"  # type: ignore[arg-type]

    def test_nifty_100_wins_over_midcap_membership(self) -> None:
        """If a stock is both Nifty 100 AND in midcap_ids, Nifty 100 wins.

        Methodology 3.2: tier is hierarchical; Large beats Mid.
        """
        iid = "ambiguous"
        args = _make_tier_args(
            instrument_id=iid,
            in_nifty_100=True,
            in_nifty_500=True,
            midcap_ids={iid},
        )
        assert _classify_tier(**args) == "Large"  # type: ignore[arg-type]

    def test_nifty_500_member_with_no_subindex_falls_back_to_small(self) -> None:
        """A NIFTY 500 stock not in NIFTY 100 / Midcap 150 / Smallcap 250
        defaults to Small (the larger of the two non-Mid options)."""
        args = _make_tier_args(in_nifty_500=True)
        assert _classify_tier(**args) == "Small"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ETF theme classification
# ---------------------------------------------------------------------------


class TestClassifyTheme:
    @pytest.mark.parametrize(
        "name",
        [
            "NIFTYBEES",
            "Nippon India ETF Nifty 50",
            "ICICI Prudential Nifty 100 ETF",
            "Mirae Asset Nifty Next 50 ETF",
            "Nippon India ETF Nifty 500",
            "SBI ETF Sensex",
        ],
    )
    def test_broad_indices_classified_broad(self, name: str) -> None:
        theme, linked = _classify_theme(name, None)
        assert theme == "Broad"
        assert linked is None

    @pytest.mark.parametrize(
        "name,expected_sector",
        [
            ("Nippon India ETF Nifty Bank BeES", "Bank"),
            ("ICICI Prudential IT ETF", "IT"),
            ("Nippon India ETF Pharma", "Pharma"),
            ("HDFC Auto ETF", "Auto"),
            ("Nippon India FMCG ETF", "FMCG"),
            ("ICICI Pru Healthcare ETF", "Healthcare"),
            ("Kotak PSU Bank ETF", "PSU Bank"),
            ("ICICI Pru Private Bank ETF", "Private Bank"),
        ],
    )
    def test_sectoral_classified_with_link(self, name: str, expected_sector: str) -> None:
        theme, linked = _classify_theme(name, None)
        assert theme == "Sectoral", f"got {theme} for {name}"
        assert linked == expected_sector

    @pytest.mark.parametrize(
        "name",
        [
            "Mirae Asset NYSE FANG+ ETF",
            "Motilal Oswal Nasdaq 100 ETF",
            "Nippon India Gold BeES",
            "ICICI Pru Quality 30 ETF",
            "Nippon Consumption ETF",
        ],
    )
    def test_thematic_default(self, name: str) -> None:
        theme, linked = _classify_theme(name, None)
        assert theme == "Thematic"
        assert linked is None

    def test_pharma_before_fmcg_specificity(self) -> None:
        """Both 'PHARMA' and 'FMCG' have similar lengths; ordering matters."""
        _, linked = _classify_theme("Nippon Pharma Plus ETF", None)
        assert linked == "Pharma"

    def test_psu_bank_before_bank_specificity(self) -> None:
        """'PSU BANK' must be checked before 'BANK' to avoid mis-tagging."""
        _, linked = _classify_theme("Kotak Nifty PSU Bank ETF", None)
        assert linked == "PSU Bank", f"got {linked}, expected 'PSU Bank'"

    def test_empty_name_safe(self) -> None:
        theme, linked = _classify_theme("", "")
        assert theme == "Thematic"
        assert linked is None

    def test_none_name_safe(self) -> None:
        theme, linked = _classify_theme(None, None)
        assert theme == "Thematic"
        assert linked is None


# ---------------------------------------------------------------------------
# Fund category → benchmark mapping
# ---------------------------------------------------------------------------


class TestCategoryToBenchmarkCode:
    @pytest.mark.parametrize(
        "category,expected",
        [
            ("Large Cap Fund", "NIFTY100"),
            ("Large Cap", "NIFTY100"),
            ("Large & Mid Cap Fund", "NIFTY200"),
            ("Large & Midcap", "NIFTY200"),
            ("Mid Cap Fund", "MIDCAP150"),
            ("Mid Cap", "MIDCAP150"),
            ("Small Cap Fund", "SMALLCAP250"),
            ("Multi Cap Fund", "NIFTY500"),
            ("Flexi Cap Fund", "NIFTY500"),
            ("ELSS", "NIFTY500"),
            ("Sectoral / Thematic Fund", "NIFTY500"),
            ("Sectoral / Thematic", "NIFTY500"),
        ],
    )
    def test_known_categories(self, category: str, expected: str) -> None:
        assert _category_to_benchmark_code(category) == expected

    def test_unknown_category_falls_back_to_nifty500(self) -> None:
        assert _category_to_benchmark_code("Some Unknown Category") == "NIFTY500"

    def test_large_and_mid_takes_precedence_over_large(self) -> None:
        """'Large & Mid Cap Fund' must NOT match the 'Large Cap' prefix.

        Order in ``_CATEGORY_BENCHMARK_PREFIXES`` puts 'Large & Mid' first.
        """
        assert _category_to_benchmark_code("Large & Mid Cap Fund") == "NIFTY200"

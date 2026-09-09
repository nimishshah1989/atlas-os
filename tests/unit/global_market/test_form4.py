"""The Form 4 parser, on seven real ownership documents.

Every file is a verbatim SEC download (provenance and sha256s in
``tests/fixtures/global/form4/SOURCE.md``). Each was kept because it is the only honest witness
to one thing this parser can get wrong — and three of the four traps below are the silent kind:
no exception, no missing row, just a fact quietly lost.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from atlas.global_market.providers.form4 import (
    OPEN_MARKET,
    document_url,
    parse_form4,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "form4"


@cache
def filing(stem: str):
    return parse_form4((FIXTURES / f"{stem}.xml").read_bytes())


SALE_10B51 = "AAPL_0001140361-26-035636_sale_10b51"
AWARD = "AAPL_0001140361-26-035362_award"
EXERCISE = "AAPL_0001140361-26-025622_exercise_withholding"
JPM_SALE = "JPM_0001225208-26-007064_sale_10b51"
GIFT = "JPM_0001225208-26-006750_gift"
EMPTY = "JPM_0001225208-26-006542_no_transactions"
VZ_SALE = "VZ_0001760581-26-000050_sale"


# ── the field that decides whether a sale means anything ────────────────────


def test_a_10b5_1_plan_sale_is_flagged_as_one() -> None:
    """Apple's SVP sold 1,439 shares at $317.01 on 2026-09-01. The filing's own footnote names a
    Rule 10b5-1 plan adopted on 5 May: she chose to sell in MAY and the calendar chose September.
    Reading it as a bearish decision that week is exactly wrong, and this flag is the only
    machine-readable way to know."""
    f = filing(SALE_10B51)
    assert f.under_10b5_1 is True
    assert f.issuer_symbol == "AAPL"
    assert f.owner_name == "Newstead Jennifer"
    assert f.is_officer is True
    assert f.officer_title == "SVP, GC and Government Affairs"
    (txn,) = f.transactions
    assert txn.code == "S"
    assert txn.shares == Decimal("1439")
    assert txn.price_per_share == Decimal("317.01")
    assert txn.acquired_disposed == "D"
    assert txn.value_usd == Decimal("1439") * Decimal("317.01")


def test_every_sale_in_this_real_sample_is_a_plan_sale() -> None:
    """The finding, and the reason the flag is carried rather than collapsed away: all three
    sales here — Apple's, JPMorgan's and Verizon's — were scheduled months earlier.

    JPMorgan's spells the flag ``<aff10b5One>1</aff10b5One>``, which is why an earlier census
    of these files (written with ``grep 'aff10b5One>true'``) reported four of six plan sales
    instead of six of six. The parser is the only thing that counts them correctly.
    """
    for stem in (SALE_10B51, JPM_SALE, VZ_SALE):
        f = filing(stem)
        assert any(t.code == "S" for t in f.transactions), stem
        assert f.under_10b5_1 is True, stem


# ── the silent trap: two encodings of one boolean ───────────────────────────


def test_both_spellings_of_a_boolean_are_read() -> None:
    """Apple writes ``<isOfficer>true</isOfficer>``. JPMorgan writes ``<isOfficer>1</isOfficer>``.
    Both are valid, and a parser accepting only "true" reads every JPMorgan officer as not an
    officer: no error, no missing row, just a relationship gone."""
    assert "<isOfficer>true</isOfficer>" in (FIXTURES / f"{SALE_10B51}.xml").read_text()
    assert "<isOfficer>1</isOfficer>" in (FIXTURES / f"{EMPTY}.xml").read_text()
    assert filing(SALE_10B51).is_officer is True
    assert filing(EMPTY).is_officer is True
    assert filing(EMPTY).owner_name == "Lake Marianne"
    assert filing(EMPTY).officer_title == "CEO CCB"


def test_the_plan_flag_reads_both_spellings_too() -> None:
    """JPMorgan writes ``<aff10b5One>0</aff10b5One>`` where Apple writes ``true``/``false``. A
    "0" read as truthy would mark every JPMorgan sale as a scheduled one and mute a real signal."""
    assert "<aff10b5One>0</aff10b5One>" in (FIXTURES / f"{EMPTY}.xml").read_text()
    assert filing(EMPTY).under_10b5_1 is False


# ── which codes are a decision ──────────────────────────────────────────────


def test_only_open_market_purchases_and_sales_count_as_decisions() -> None:
    assert OPEN_MARKET == {"P", "S"}
    assert all(t.is_open_market for t in filing(SALE_10B51).transactions)
    # A gift moves stock and expresses nothing about its value.
    assert not any(t.is_open_market for t in filing(GIFT).transactions)
    assert "G" in {t.code for t in filing(GIFT).transactions}


def test_an_rsu_GRANT_is_a_derivative_line_and_this_parser_does_not_read_it() -> None:
    """Apple's 2026-09-01 award to John Ternus has ZERO non-derivative transactions: the RSU
    grant is a derivative security, filed in the derivative table. Skipping that table is
    deliberate — a grant is the company paying someone, not a view on the price — so the filing
    correctly parses to no transactions at all. What a grant eventually DELIVERS shows up later
    as a non-derivative ``M``, which is read and then excluded by ``OPEN_MARKET``."""
    f = filing(AWARD)
    assert f.transactions == ()
    assert f.owner_name == "Ternus John"
    assert "<derivativeTransaction>" in (FIXTURES / f"{AWARD}.xml").read_text()


def test_an_option_exercise_and_its_tax_withholding_are_not_buying_and_selling() -> None:
    """Apple's 2026-06-17 filing is M (exercise) and F (shares withheld for the tax on the vest).
    Counting M as a purchase would make every vesting date look like insider conviction, and F as
    a sale would make every one look like an exit."""
    codes = {t.code for t in filing(EXERCISE).transactions}
    assert {"M", "F"} <= codes
    assert not any(t.is_open_market for t in filing(EXERCISE).transactions)


def test_a_transaction_with_no_price_is_worth_None_rather_than_zero() -> None:
    """A gift reports shares and no price. A zero there would book a real transfer of stock as
    worth nothing, and it would then be summed into a net-buying figure as though the insider had
    paid nothing for it."""
    gift = [t for t in filing(GIFT).transactions if t.code == "G"]
    assert gift
    assert all(t.price_per_share in (None, Decimal(0)) for t in gift)
    assert all(t.value_usd is None or t.value_usd == Decimal(0) for t in gift)
    # A real sale has both, so the None above is about the document and not about the parser.
    (sale,) = [t for t in filing(SALE_10B51).transactions if t.code == "S"]
    assert sale.value_usd is not None and sale.value_usd > Decimal(0)


# ── the shapes that must not raise ──────────────────────────────────────────


def test_a_filing_with_no_transactions_parses_to_none_rather_than_raising() -> None:
    """JPMorgan's 2026-07-08 document has both tables empty. It is a filing that happened and
    moves nothing — a real state, not a malformed document."""
    f = filing(EMPTY)
    assert f.transactions == ()
    assert f.issuer_symbol == "JPM"
    assert f.period_of_report == dt.date(2026, 6, 25)


def test_every_fixture_parses_and_names_its_issuer_and_owner() -> None:
    for stem in (SALE_10B51, AWARD, EXERCISE, JPM_SALE, GIFT, EMPTY, VZ_SALE):
        f = filing(stem)
        assert f.issuer_cik and f.issuer_symbol, stem
        assert f.owner_name and f.owner_cik, stem
        assert f.period_of_report is not None, stem


# ── the URL that is not the one the index gives you ─────────────────────────


def test_the_xsl_prefix_is_stripped_because_that_path_serves_HTML() -> None:
    """``primaryDocument`` is ``xslF345X06/form4.xml``, which EDGAR renders as HTML — 15,625
    bytes for this filing against 3,153 for the raw XML at the same name without the prefix.
    Both return 200, so fetching the wrong one fails as a parse error far from its cause."""
    url = document_url("320193", "0001140361-26-035636", "xslF345X06/form4.xml")
    assert url == ("https://www.sec.gov/Archives/edgar/data/320193/000114036126035636/form4.xml")
    assert "xsl" not in url
    # A document already unprefixed is left alone, and the CIK is not zero-padded in an
    # Archives path the way it is in the submissions one.
    assert document_url(19617, "0001225208-26-007064", "doc4.xml").endswith(
        "/data/19617/000122520826007064/doc4.xml"
    )


def test_the_committed_fixture_is_the_raw_xml_and_not_the_rendering() -> None:
    """If a refresh ever grabbed the XSL path these files would silently become HTML and every
    assertion above would fail in a confusing way. This one fails clearly."""
    for stem in (SALE_10B51, EMPTY):
        head = (FIXTURES / f"{stem}.xml").read_bytes()[:64]
        assert head.startswith(b"<?xml"), stem
        assert b"<html" not in head.lower(), stem


# ── the census the lens design rests on ─────────────────────────────────────


def test_not_one_of_these_real_filings_is_an_open_market_PURCHASE() -> None:
    """The finding that shaped the flow lens, pinned so it cannot quietly stop being true.

    Across the eighteen most recent Form 4s from Apple, JPMorgan and Verizon there is not a
    single code ``P``. Insiders at healthy megacaps are paid in stock and sell it; they almost
    never buy it on the open market. A ``P`` is therefore a STRONG signal — nobody buys their own
    stock by accident — and also a RARE one, so a flow lens built on it is silent far more often
    than it speaks. That is a property to plan around, not a defect to discover later.
    """
    codes = {
        t.code
        for stem in (SALE_10B51, AWARD, EXERCISE, JPM_SALE, GIFT, EMPTY, VZ_SALE)
        for t in filing(stem).transactions
    }
    assert "P" not in codes
    assert codes == {"S", "M", "F", "G"}
    # And the other half of the finding: not one of the sales was discretionary either.
    assert all(filing(stem).under_10b5_1 for stem in (SALE_10B51, JPM_SALE, VZ_SALE)), (
        "every sale in this sample was scheduled months earlier by a 10b5-1 plan"
    )

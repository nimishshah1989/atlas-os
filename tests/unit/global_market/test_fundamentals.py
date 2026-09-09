"""``atlas.global_market.fundamentals`` against REAL SEC company-facts payloads.

Every number asserted below is read out of ``tests/fixtures/global/edgar/`` — verbatim SEC
company facts for Apple, JPMorgan and Verizon, trimmed to the mapped tags and otherwise
untouched (provenance in that directory's ``SOURCE.md``). Nothing here is invented, no
``Mock`` stands in for a filing, and the expected values are Apple's and JPMorgan's own
filed figures, written out with the arithmetic so a reader can check them by hand (rule #0).

No network, no database: the payloads are files.

WHY APPLE'S FY2020 IS THE WORKED EXAMPLE. It is the last fiscal year in which the company
tagged a discrete fourth quarter — the SEC dropped the selected-quarterly-data requirement in
2021 — so it is the one window where four REPORTED quarters can be summed and checked against
the REPORTED annual figure, and where ``implied_q4`` can be checked against a Q4 that actually
exists rather than against itself.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from atlas.global_market.fundamentals import ratios, xbrl_map

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "edgar"
PAYLOADS = {
    "AAPL": "companyfacts_AAPL_CIK0000320193.json",
    "JPM": "companyfacts_JPM_CIK0000019617.json",
    "VZ": "companyfacts_VZ_CIK0000732712.json",
}
QUARTER_DAYS = (80, 100)
ANNUAL_DAYS = (350, 380)

# Apple's FY2020 (ended 2020-09-26) as filed, in USD. Kept as dates only: every value below is
# read from the payload, so a wrong fixture fails the test instead of matching a copied number.
FY2020_QUARTER_ENDS = ("2019-12-28", "2020-03-28", "2020-06-27", "2020-09-26")
FY2020_END = "2020-09-26"
FY2019_END = "2019-09-28"
REVENUE_TAG = "RevenueFromContractWithCustomerExcludingAssessedTax"


@cache
def payload(symbol: str) -> dict[str, Any]:
    return json.loads((FIXTURES / PAYLOADS[symbol]).read_text())


def facts(symbol: str, tag: str) -> list[dict[str, Any]]:
    units = payload(symbol)["facts"]["us-gaap"].get(tag, {}).get("units", {})
    return [f for unit_facts in units.values() for f in unit_facts]


def reported(symbol: str, tag: str, end: str, months: int) -> Decimal:
    """The one value ``symbol`` filed for ``tag`` over the period ending ``end``.

    ``months`` is 0 for a balance (an instant), 3 for a quarter, 12 for a year. The same
    figure is re-filed as a comparative under later ``filed`` dates; the test asserts they
    agree, so a value that was actually RESTATED cannot slip through as if it were one number
    (Apple's FY2019 diluted share count is exactly such a case — see the buyback test).
    """
    found = set()
    for fact in facts(symbol, tag):
        if fact["end"] != end:
            continue
        start = fact.get("start")
        if months == 0:
            if start is not None:
                continue
        else:
            if start is None:
                continue
            days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
            lo, hi = QUARTER_DAYS if months == 3 else ANNUAL_DAYS
            if not lo <= days <= hi:
                continue
        found.add(Decimal(str(fact["val"])))
    assert len(found) == 1, f"{symbol} {tag} {end} ({months}m): {sorted(found)} in the fixture"
    return found.pop()


def tag_values(symbol: str, end: str, months: int) -> dict[str, Decimal]:
    """``{tag: value}`` for one period — the shape :func:`xbrl_map.pick` consumes."""
    out: dict[str, Decimal] = {}
    for tag in xbrl_map.TAG_CONCEPTS:
        try:
            out[tag] = reported(symbol, tag, end, months)
        except AssertionError:
            continue  # the filer did not report this element for this period
    return out


# ── the tag picker, on real payloads ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("symbol", "end", "months", "concept", "expected_tag"),
    [
        # Apple after ASC 606: the contract-with-customer element.
        ("AAPL", FY2020_END, 12, "revenue", REVENUE_TAG),
        ("AAPL", FY2020_END, 12, "cost_of_revenue", "CostOfGoodsAndServicesSold"),
        ("AAPL", FY2020_END, 0, "equity", "StockholdersEquity"),
        (
            "AAPL",
            FY2020_END,
            12,
            "depreciation_amortization",
            "DepreciationDepletionAndAmortization",
        ),
        ("AAPL", FY2020_END, 0, "debt_short", "LongTermDebtCurrent"),
        ("AAPL", FY2020_END, 12, "dividends_paid", "PaymentsOfDividends"),
        # A bank's top line is net of interest expense, and it is the ONLY revenue element
        # JPMorgan files quarterly — the correction that keeps every bank from scoring null.
        ("JPM", "2026-06-30", 3, "revenue", "RevenuesNetOfInterestExpense"),
        ("JPM", "2026-06-30", 0, "debt_short", "ShortTermBorrowings"),
        # JPMorgan retired the plain cash element in 2019; the restricted-inclusive one is
        # what it files now, and recording the tag is what makes that visible on the row.
        (
            "JPM",
            "2026-06-30",
            0,
            "cash",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        # Verizon: plain Revenues, the including-NCI equity element (it files no other),
        # DepreciationAndAmortization, and the post-2024 interest element.
        ("VZ", "2026-06-30", 3, "revenue", "Revenues"),
        (
            "VZ",
            "2026-06-30",
            0,
            "equity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
        ("VZ", "2026-06-30", 3, "depreciation_amortization", "DepreciationAndAmortization"),
        ("VZ", "2026-06-30", 3, "interest_expense", "InterestExpenseNonoperating"),
        ("VZ", "2026-06-30", 0, "debt_long", "LongTermDebtAndCapitalLeaseObligations"),
    ],
)
def test_pick_chooses_the_documented_tag(
    symbol: str, end: str, months: int, concept: str, expected_tag: str
) -> None:
    value, tag = xbrl_map.pick(concept, tag_values(symbol, end, months))
    assert tag == expected_tag
    assert value == reported(symbol, expected_tag, end, months)


def test_pick_returns_none_not_zero_for_a_concept_the_filer_never_tags() -> None:
    """A bank files no ``OperatingIncomeLoss``, no gross profit and no capital expenditure.

    Those are the inputs to EBIT, EBITDA, ROCE, operating margin, interest cover and free cash
    flow; a zero here would price JPMorgan as a company that earns nothing from operations.
    """
    for concept in ("operating_income", "gross_profit", "capex", "assets_current"):
        value, tag = xbrl_map.pick(concept, tag_values("JPM", "2026-06-30", 3))
        assert (value, tag) == (None, None), concept
        assert value is not Decimal(0)
    # and the ratios built on them stay None rather than collapsing to zero
    assert ratios.ebitda(None, Decimal("1")) is None
    assert ratios.operating_margin(None, Decimal("57347000000")) is None
    assert ratios.fcf(Decimal("1"), None) is None


def test_net_income_prefers_the_parent_attributable_element_when_both_are_filed() -> None:
    """Verizon files both, and they differ: 3,835 (parent) against 3,949 (consolidated, June
    2026 quarter). ``NetIncomeLoss`` must win, because it is the numerator that pairs with the
    parent equity ROE divides by. ``ProfitLoss`` is a fallback for filers that publish nothing
    else — Caterpillar tags no ``NetIncomeLoss`` at all on its quarterly durations, so without
    it an S&P 500 industrial would carry no net income.
    """
    values = tag_values("VZ", "2026-06-30", 3)
    assert values["NetIncomeLoss"] == Decimal("3835000000")
    assert values["ProfitLoss"] == Decimal("3949000000")
    value, tag = xbrl_map.pick("net_income", values)
    assert (value, tag) == (Decimal("3835000000"), "NetIncomeLoss")
    # …and the fallback fires when the parent element is the one that is absent
    del values["NetIncomeLoss"]
    assert xbrl_map.pick("net_income", values) == (Decimal("3949000000"), "ProfitLoss")


def test_pick_refuses_an_unknown_concept() -> None:
    with pytest.raises(KeyError, match="unknown concept"):
        xbrl_map.pick("ebitda", {})


def test_every_mapped_tag_is_reachable_and_uniquely_owned() -> None:
    """The map's own consistency: no concept lists a tag twice, and every concept has a unit."""
    for concept, tags in xbrl_map.CONCEPTS.items():
        assert len(set(tags)) == len(tags), concept
        assert concept in xbrl_map.UNITS
    assert xbrl_map.UNITS["eps_diluted"] == "USD/shares"
    assert xbrl_map.UNITS["shares_diluted"] == "shares"
    assert xbrl_map.INSTANT_CONCEPTS <= set(xbrl_map.CONCEPTS)


# ── TTM assembly ──────────────────────────────────────────────────────────────────────────


def test_ttm_revenue_equals_the_four_reported_quarters_and_the_reported_year() -> None:
    """Apple FY2020: 91,819 + 58,313 + 59,685 + 64,698 = 274,515 (USD millions), which is the
    twelve-month figure Apple filed in the same 10-K. Four real quarters, one real year."""
    quarters = [reported("AAPL", REVENUE_TAG, end, 3) for end in FY2020_QUARTER_ENDS]
    assert quarters == [
        Decimal("91819000000"),
        Decimal("58313000000"),
        Decimal("59685000000"),
        Decimal("64698000000"),
    ]
    assert ratios.ttm(quarters) == Decimal("274515000000")
    assert ratios.ttm(quarters) == reported("AAPL", REVENUE_TAG, FY2020_END, 12)


def test_implied_q4_reproduces_the_last_fourth_quarter_apple_actually_tagged() -> None:
    """FY − Q1 − Q2 − Q3 is not a guess: on FY2020, where the real Q4 exists in the payload,
    the identity returns it to the dollar. That is the licence to use it on every year since,
    where no filer tags a discrete Q4 at all."""
    q1, q2, q3, q4 = (reported("AAPL", REVENUE_TAG, end, 3) for end in FY2020_QUARTER_ENDS)
    annual = reported("AAPL", REVENUE_TAG, FY2020_END, 12)
    assert ratios.implied_q4(annual, q1, q2, q3) == q4 == Decimal("64698000000")


def test_ttm_is_none_when_a_quarter_is_missing() -> None:
    quarters = [reported("AAPL", REVENUE_TAG, end, 3) for end in FY2020_QUARTER_ENDS]
    assert ratios.ttm([*quarters[:3], None]) is None
    assert ratios.implied_q4(None, *quarters[:3]) is None


def test_ttm_refuses_a_window_that_is_not_four_quarters() -> None:
    quarters = [reported("AAPL", REVENUE_TAG, end, 3) for end in FY2020_QUARTER_ENDS]
    with pytest.raises(ValueError, match="exactly 4 quarters"):
        ratios.ttm(quarters[:3])


def test_mean_of_needs_every_value() -> None:
    equity = [reported("AAPL", "StockholdersEquity", end, 0) for end in FY2020_QUARTER_ENDS]
    assert ratios.mean_of(equity) == Decimal("76394250000")
    assert ratios.mean_of([*equity[:3], None]) is None
    assert ratios.mean_of([]) is None


# ── the ratios, on Apple's filed FY2020 ───────────────────────────────────────────────────


def test_roe_matches_the_hand_calculation() -> None:
    """ROE = TTM net income ÷ average equity over the four quarters.

    By hand, from Apple's FY2020 10-K and the three 10-Qs of that year (USD millions):
        net income          57,411
        equity              89,531 (Q1) · 78,425 (Q2) · 72,282 (Q3) · 65,339 (Q4)
        average equity      (89,531 + 78,425 + 72,282 + 65,339) / 4 = 76,394.25
        ROE                 57,411 / 76,394.25 = 0.751509…  (75.15%)
    """
    net_income = reported("AAPL", "NetIncomeLoss", FY2020_END, 12)
    equity = [reported("AAPL", "StockholdersEquity", end, 0) for end in FY2020_QUARTER_ENDS]
    average = ratios.mean_of(equity)
    assert net_income == Decimal("57411000000")
    assert equity == [
        Decimal("89531000000"),
        Decimal("78425000000"),
        Decimal("72282000000"),
        Decimal("65339000000"),
    ]
    assert average == Decimal("76394250000")
    result = ratios.roe(net_income, average)
    assert result is not None
    assert result.quantize(Decimal("0.000001")) == Decimal("0.751509")


def test_the_rest_of_apples_fy2020_ratios() -> None:
    """Each expected value is the quotient of two figures in Apple's FY2020 10-K."""
    revenue = reported("AAPL", REVENUE_TAG, FY2020_END, 12)
    ebit = reported("AAPL", "OperatingIncomeLoss", FY2020_END, 12)
    debt = reported("AAPL", "LongTermDebtNoncurrent", FY2020_END, 0) + reported(
        "AAPL", "LongTermDebtCurrent", FY2020_END, 0
    )
    equity = reported("AAPL", "StockholdersEquity", FY2020_END, 0)
    free_cash = ratios.fcf(
        reported("AAPL", "NetCashProvidedByUsedInOperatingActivities", FY2020_END, 12),
        reported("AAPL", "PaymentsToAcquirePropertyPlantAndEquipment", FY2020_END, 12),
    )
    assert (revenue, ebit, debt, equity) == (
        Decimal("274515000000"),
        Decimal("66288000000"),
        Decimal("107440000000"),
        Decimal("65339000000"),
    )
    assert free_cash == Decimal("73365000000")  # 80,674 operating − 7,309 capex

    got = {
        # 104,956 / 274,515
        "gross_margin": ratios.gross_margin(
            reported("AAPL", "GrossProfit", FY2020_END, 12), revenue
        ),
        "operating_margin": ratios.operating_margin(ebit, revenue),  # 66,288 / 274,515
        "net_margin": ratios.net_margin(
            reported("AAPL", "NetIncomeLoss", FY2020_END, 12), revenue
        ),  # 57,411 / 274,515
        "fcf_margin": ratios.fcf_margin(free_cash, revenue),  # 73,365 / 274,515
        "roce": ratios.roce(ebit, equity, debt),  # 66,288 / (65,339 + 107,440)
        "debt_to_equity": ratios.debt_to_equity(debt, equity, is_financial=False),
        "current_ratio": ratios.current_ratio(  # 143,713 / 105,392
            reported("AAPL", "AssetsCurrent", FY2020_END, 0),
            reported("AAPL", "LiabilitiesCurrent", FY2020_END, 0),
            is_financial=False,
        ),
        "interest_cover": ratios.interest_cover(  # 66,288 / 2,873
            ebit, reported("AAPL", "InterestExpense", FY2020_END, 12)
        ),
    }
    expected = {
        "gross_margin": Decimal("0.382332"),
        "operating_margin": Decimal("0.241473"),
        "net_margin": Decimal("0.209136"),
        "fcf_margin": Decimal("0.267253"),
        "roce": Decimal("0.383658"),
        "debt_to_equity": Decimal("1.644347"),
        "current_ratio": Decimal("1.363604"),
        "interest_cover": Decimal("23.072746"),
    }
    for name, value in got.items():
        assert value is not None, name
        assert isinstance(value, Decimal), name
        assert value.quantize(Decimal("0.000001")) == expected[name], name


def test_growth_and_operating_leverage_across_apples_fy2019_and_fy2020() -> None:
    """Revenue 260,174 → 274,515 (+5.5121%); EBIT 63,930 → 66,288 (+3.6884%). Operating
    leverage is the second over the first: 0.669… — Apple grew profit slower than sales that
    year, which is what a sub-1 reading means."""
    revenue = ratios.growth(
        reported("AAPL", REVENUE_TAG, FY2020_END, 12),
        reported("AAPL", REVENUE_TAG, FY2019_END, 12),
    )
    ebit = ratios.growth(
        reported("AAPL", "OperatingIncomeLoss", FY2020_END, 12),
        reported("AAPL", "OperatingIncomeLoss", FY2019_END, 12),
    )
    assert revenue is not None and ebit is not None
    assert revenue.quantize(Decimal("0.000001")) == Decimal("0.055121")
    assert ebit.quantize(Decimal("0.000001")) == Decimal("0.036884")
    leverage = ratios.operating_leverage(ebit, revenue)
    assert leverage is not None
    assert leverage.quantize(Decimal("0.0001")) == (ebit / revenue).quantize(Decimal("0.0001"))
    assert leverage < Decimal(1)


def test_buyback_yield_reads_the_share_count_as_restated_for_the_split() -> None:
    """Apple's FY2019 diluted share count was filed as 4,648,913 thousand in the FY2019 10-K
    and re-filed as 18,595,651 thousand in the FY2020 one, after the August 2020 four-for-one
    split. Buyback yield compares FY2020's 17,528,214 with the RESTATED comparative — the
    pre-split number would read as a 277% issuance. This is why the table keys on ``filed``.
    """
    fy2020 = reported("AAPL", "WeightedAverageNumberOfDilutedSharesOutstanding", FY2020_END, 12)
    as_filed_2019, restated_2019 = sorted(
        {
            Decimal(str(f["val"]))
            for f in facts("AAPL", "WeightedAverageNumberOfDilutedSharesOutstanding")
            if f["end"] == FY2019_END and f.get("start") == "2018-09-30"
        }
    )
    assert (as_filed_2019, restated_2019) == (Decimal("4648913000"), Decimal("18595651000"))
    # Four-for-one, to the rounding Apple itself carried into the restated weighted average
    assert (restated_2019 / as_filed_2019).quantize(Decimal("0.000001")) == Decimal("4.000000")

    yield_ = ratios.buyback_yield(fy2020, restated_2019)
    assert yield_ is not None
    assert yield_.quantize(Decimal("0.000001")) == Decimal("0.057403")
    stale = ratios.buyback_yield(fy2020, as_filed_2019)
    assert stale is not None and stale < Decimal("-2")  # what ignoring `filed` would produce


# ── the financial-company flag ────────────────────────────────────────────────────────────


def test_the_financial_flag_suppresses_exactly_the_balance_sheet_ratios() -> None:
    """The flag must suppress D/E and the current ratio and NOTHING else.

    Apple's real inputs are used on both sides, so the difference is the flag alone rather
    than a bank's missing elements — which would prove nothing.
    """
    debt = reported("AAPL", "LongTermDebtNoncurrent", FY2020_END, 0) + reported(
        "AAPL", "LongTermDebtCurrent", FY2020_END, 0
    )
    equity = reported("AAPL", "StockholdersEquity", FY2020_END, 0)
    current_assets = reported("AAPL", "AssetsCurrent", FY2020_END, 0)
    current_liabilities = reported("AAPL", "LiabilitiesCurrent", FY2020_END, 0)

    assert ratios.debt_to_equity(debt, equity, is_financial=True) is None
    assert ratios.current_ratio(current_assets, current_liabilities, is_financial=True) is None
    assert ratios.debt_to_equity(debt, equity, is_financial=False) is not None
    assert ratios.current_ratio(current_assets, current_liabilities, is_financial=False) is not None

    # Everything else is unaffected: a bank's profitability is still scored, and on JPMorgan's
    # own filed figures. Net margin = 21,155 / 57,347 = 0.368895 for the June 2026 quarter.
    revenue = reported("JPM", "RevenuesNetOfInterestExpense", "2026-06-30", 3)
    net_income = reported("JPM", "NetIncomeLoss", "2026-06-30", 3)
    margin = ratios.net_margin(net_income, revenue)
    assert margin is not None
    assert margin.quantize(Decimal("0.000001")) == Decimal("0.368895")
    jpm_equity = reported("JPM", "StockholdersEquity", "2026-06-30", 0)
    assert ratios.roe(net_income, jpm_equity) is not None


# ── the contract: never a default ─────────────────────────────────────────────────────────


def test_every_ratio_is_none_when_an_input_is_missing() -> None:
    one = Decimal("1")
    assert ratios.roe(None, one) is None and ratios.roe(one, None) is None
    assert ratios.roce(one, None, one) is None and ratios.roce(one, one, None) is None
    assert ratios.gross_margin(None, one) is None
    assert ratios.operating_margin(one, None) is None
    assert ratios.net_margin(None, None) is None
    assert ratios.fcf_margin(one, None) is None
    assert ratios.fcf(None, one) is None
    assert ratios.ebitda(one, None) is None
    assert ratios.growth(one, None) is None
    assert ratios.interest_cover(one, None) is None
    assert ratios.operating_leverage(None, one) is None
    assert ratios.buyback_yield(one, None) is None
    assert ratios.debt_to_equity(None, one, is_financial=False) is None
    assert ratios.current_ratio(one, None, is_financial=False) is None


def test_a_denominator_that_would_invert_the_meaning_is_none() -> None:
    """Zero and negative bases return None, not a very large or sign-flipped number: return on
    negative equity reads as a profit for a loss-making company, and growth off a loss has no
    direction. Real case: a company with negative book value would otherwise rank top decile."""
    positive, negative, zero = Decimal("100"), Decimal("-50"), Decimal(0)
    assert ratios.roe(positive, negative) is None
    assert ratios.roe(positive, zero) is None
    assert ratios.roce(positive, negative, Decimal("10")) is None  # equity + debt = -40
    assert ratios.growth(positive, negative) is None
    assert ratios.growth(positive, zero) is None
    assert ratios.interest_cover(positive, zero) is None
    assert ratios.operating_leverage(positive, negative) is None
    assert ratios.debt_to_equity(positive, negative, is_financial=False) is None
    # …but a loss over positive equity is a real, negative ROE and IS returned
    assert ratios.roe(negative, positive) == Decimal("-0.5")

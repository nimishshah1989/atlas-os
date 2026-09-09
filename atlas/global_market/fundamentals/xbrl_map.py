"""us-gaap tag → concept, in priority order. Pure: a dict and one lookup.

WHY A TUPLE PER CONCEPT. There is no single tag for "revenue". A filer picks one from the
taxonomy, and the choice changes with the taxonomy and with the filer's own business: Apple
tagged ``SalesRevenueNet`` until FY2018 and ``RevenueFromContractWithCustomerExcludingAssessedTax``
after (ASC 606 retired the old element); Coca-Cola and Verizon use plain ``Revenues``;
JPMorgan, whose top line is net of interest expense, uses ``RevenuesNetOfInterestExpense``
quarterly and ``Revenues`` only at year end. Reading one tag per concept scores half the
index zero, which is the failure rule #0 exists to prevent. So each concept is an ORDERED
tuple, first present wins per period, and :func:`pick` returns the tag it used so the stored
row can be audited back to the element the filer actually reported.

EVERY TAG BELOW WAS VERIFIED against real ``data.sec.gov`` company-facts payloads on
2026-09-09 — AAPL, JPM, VZ (the three committed under ``tests/fixtures/global/edgar/``) plus
KO and PG — and, for the tags absent from all five, against the SEC ``frames`` API for
CY2025Q1 (filer counts in the comments). Corrections made to the starting list:

* ``CostOfRevenue`` appears in NONE of the five (1,126 filers use it index-wide); the tag the
  big filers use is ``CostOfGoodsAndServicesSold``, with ``CostOfGoodsSold`` / ``CostOfServices``
  on pre-2018 filings. All four are kept, in that order.
* ``RevenuesNetOfInterestExpense`` was missing from the list and is the ONLY quarterly revenue
  tag JPMorgan files — without it every bank's revenue is null after 2019.
* ``DepreciationAndAmortization`` was missing and is Verizon's only D&A tag.
* ``DebtCurrent`` ("short-term debt and current maturities of long-term debt") was missing and
  is the complete current-debt element; ``LongTermDebtCurrent`` alone understates PG and VZ,
  so ``DebtCurrent`` leads and the narrower elements follow. ``CommercialPaper`` is the last
  resort (Apple files no other short-term borrowing element).
* ``LongTermDebtAndCapitalLeaseObligations`` was missing; Verizon has filed no plain
  ``LongTermDebtNoncurrent`` since 2013.
* ``PaymentsOfDividends`` was missing; ``PaymentsOfDividendsCommonStock`` (the listed tag) stops
  in 2017 for Apple and never appears for JPM/KO/PG/VZ.
* ``interest_expense`` was absent from the list altogether although ``stock_financials_pit`` has
  the column and §B needs interest cover. ``InterestExpense`` was superseded by
  ``InterestExpenseNonoperating`` around 2024, so both are needed.
* ``StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`` stays SECOND, as
  listed: ``NetIncomeLoss`` is parent-attributable, so ROE must divide by parent equity where
  it exists. VZ and PG file only the including-NCI element, and then it is the honest input.
* ``ProfitLoss`` was missing from the ``net_income`` list. Caterpillar files no ``NetIncomeLoss``
  on any quarterly duration (checked live on 2026-09-09: its 2025-06 → 2026-06 quarters are
  ``ProfitLoss`` only), so without the fallback an S&P 500 industrial carries no net income at
  all — the exact shape of the failure rule #0 exists to prevent.

``cost_of_revenue`` has no column in ``stock_financials_pit`` today; it is mapped here because
gross margin is otherwise unavailable for the many filers (JPM, VZ, PG) that report no
``GrossProfit``. The one-line DDL addition is named in the chunk's hand-over notes.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

# concept → us-gaap tags, most preferred first. Verified 2026-09-09 (see the module docstring).
CONCEPTS: dict[str, tuple[str, ...]] = {
    # ── income statement (duration facts) ──
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",  # 537 filers CY2025Q1
        "RevenuesNetOfInterestExpense",  # banks and brokers; JPM's only quarterly top line
        "Revenues",
        "SalesRevenueNet",  # retired by ASC 606; the only revenue tag before 2018
    ),
    "cost_of_revenue": (
        "CostOfRevenue",  # 1,126 filers CY2025Q1; none of the five sampled
        "CostOfGoodsAndServicesSold",  # 1,502 filers CY2025Q1
        "CostOfGoodsSold",
        "CostOfServices",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    # ``ProfitLoss`` (consolidated, including any non-controlling interest) is the fallback,
    # and it is not optional: Caterpillar tags NO ``NetIncomeLoss`` at all on its quarterly
    # durations — verified on the live payload 2026-09-09 — so without it CAT carries no net
    # income, no margin and no ROE. Parent-attributable stays FIRST so it pairs with the
    # parent equity ``StockholdersEquity`` gives; the chosen tag says which basis a row is on.
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "eps_diluted": ("EarningsPerShareDiluted",),
    "shares_diluted": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
    "interest_expense": ("InterestExpense", "InterestExpenseNonoperating"),
    # ── balance sheet (instant facts) ──
    "equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "assets": ("Assets",),
    "assets_current": ("AssetsCurrent",),
    "liabilities_current": ("LiabilitiesCurrent",),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        # Banks retired the plain element: JPM has filed only this one since 2019. It folds in
        # restricted cash, which the recorded tag makes visible on the row.
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "debt_long": (
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
    ),
    "debt_short": (
        "DebtCurrent",
        "LongTermDebtCurrent",
        "ShortTermBorrowings",
        "CommercialPaper",
    ),
    # ── cash flow (duration facts) ──
    "depreciation_amortization": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
    ),
    "operating_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
    "dividends_paid": ("PaymentsOfDividendsCommonStock", "PaymentsOfDividends"),
}

# Concepts measured AT a date (a balance) rather than OVER one (a flow). Company facts marks
# the difference by the presence of ``start``, and the two cannot be mixed: a balance carried
# by a 10-Q belongs to the quarter that ENDS on it, never to the quarter's duration.
INSTANT_CONCEPTS: frozenset[str] = frozenset(
    {"equity", "assets", "assets_current", "liabilities_current", "cash", "debt_long", "debt_short"}
)

# The company-facts ``units`` key each concept is published under. Anything else under the same
# tag (a foreign-currency unit on a dual-reporting filer) is not this concept's value.
UNITS: dict[str, str] = {
    concept: (
        "USD/shares"
        if concept == "eps_diluted"
        else "shares"
        if concept == "shares_diluted"
        else "USD"
    )
    for concept in CONCEPTS
}

# Every tag we know about, for the extraction pass that walks the payload once.
TAG_CONCEPTS: dict[str, list[str]] = {}
for _concept, _tags in CONCEPTS.items():
    for _tag in _tags:
        TAG_CONCEPTS.setdefault(_tag, []).append(_concept)


def pick(concept: str, facts: Mapping[str, Decimal]) -> tuple[Decimal | None, str | None]:
    """The value of ``concept`` from one period's ``{tag: value}``, and the tag it came from.

    First present tag wins, in :data:`CONCEPTS` order. ``(None, None)`` when the filer
    reported none of them for that period — which is a real outcome (a bank files no
    ``OperatingIncomeLoss``), not a zero and not a default.
    """
    if concept not in CONCEPTS:
        raise KeyError(f"unknown concept {concept!r}; known: {sorted(CONCEPTS)}")
    for tag in CONCEPTS[concept]:
        if tag in facts:
            return facts[tag], tag
    return None, None

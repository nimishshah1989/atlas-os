"""One filer's fundamental metric set AS OF a date. Pure, Decimal, no I/O, no clock.

The gap between ``stock_financials_pit`` and the fundamental lens. The table holds one row per
``(instrument, period_end, form, filed)`` exactly as the filings arrived; the lens wants nine
ratios. Everything in between is here, and every step of it is a way to be wrong.

POINT IN TIME IS A FILTER, NOT A SORT. The table exists so a question asked about 2023-05-12
gets the numbers that were on file that day, not today's corrected ones. So the window is
``filed <= as_of``, and where a period was restated the row with the LATEST ``filed`` inside
that window wins — the restatement is visible from the day it was filed and not before.

A QUARTERLY SERIES IS ASSEMBLED, NOT READ. Three quarters in four, the trailing twelve months
does not exist in any filing: no US filer tags a discrete fourth quarter after 2020 (the SEC
dropped the selected-quarterly-data requirement), so a fiscal year's Q4 is the accounting
identity FY − Q1 − Q2 − Q3 over four figures the filer did report — :func:`ratios.implied_q4`,
tested against the last real Q4 Apple tagged. Without it a TTM exists only at year ends.

CASH FLOW IS FILED YEAR TO DATE, so a discrete quarter of it usually does not exist. A 10-Q's
cash-flow statement covers three, six or nine months from the year start, and ``facts`` keeps
only the filing's own period class — so ``operating_cash_flow`` and ``capex`` appear in 13 of
Apple's 71 assembled quarters and 18 and 10 of Verizon's 72, against 56 and 72 for revenue.
Free cash flow is therefore ``None`` for most filers most of the time. It is not a lens
sub-score, so nothing is lost from a score; it is a metric the card cannot always show, and
saying so is better than differencing year-to-date figures nobody filed.

FLOWS SUM, STOCKS DO NOT. Revenue, income and cash flow are durations: a trailing twelve months
is their sum over four quarters. Equity, debt and share count are balances at an instant: the
latest one is the current figure, and the one a return is measured against is the MEAN over the
window, because a company that doubled its equity mid-year did not earn its profit on either
end point. Getting this backwards inflates every return in a growing company.

GROWTH NEEDS EIGHT QUARTERS, WHICH IS WHY THE FLOOR IS EIGHT. Year-on-year growth compares this
trailing twelve months with the one ending four quarters earlier; ``fund_min_quarters`` = 8 is
that requirement and not a taste.

NOTHING IS FILLED IN. Every field is ``Decimal | None`` and ``None`` means the inputs were not
there — never zero, never a neutral value (rule #0). A lens that renormalises over the
sub-scores it has is honest about coverage; one fed a silent zero prices a company as if it
earned nothing.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from atlas.global_market.fundamentals import ratios
from atlas.global_market.fundamentals.facts import ANNUAL, QUARTER, PeriodRow

# A trailing twelve months is four quarters, and a year-on-year comparison is two of those
# windows end to end. Definitions of the windows, not tunable bands.
TTM_QUARTERS = ratios.TTM_QUARTERS
YOY_QUARTERS = TTM_QUARTERS * 2

# Flows are summed over a window; balances are read at an instant. Which is which is a fact
# about the concept, so it lives here rather than at each call site.
FLOW_CONCEPTS = frozenset(
    {
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "eps_diluted",
        "depreciation_amortization",
        "interest_expense",
        "operating_cash_flow",
        "capex",
        "dividends_paid",
        "cost_of_revenue",
    }
)
BALANCE_CONCEPTS = frozenset(
    {
        "equity",
        "assets",
        "cash",
        "assets_current",
        "liabilities_current",
        "debt_long",
        "debt_short",
        "shares_diluted",
    }
)


@dataclass(frozen=True)
class Quarter:
    """One fiscal quarter's flows and the balances at its end.

    ``implied`` marks a fourth quarter reached by ``FY − Q1 − Q2 − Q3`` rather than one the
    filer tagged. It is an accounting identity over four reported figures, not an estimate,
    but the lens's evidence says which so a reader can tell.
    """

    period_end: dt.date
    filed: dt.date
    flows: dict[str, Decimal]
    balances: dict[str, Decimal]
    implied: bool = False


@dataclass(frozen=True)
class Metrics:
    """What the fundamental lens is scored on, and what it took to get there."""

    as_of: dt.date
    period_end: dt.date
    filed: dt.date
    quarters: int  # how many quarters the assembled series holds, for the coverage floor
    implied_quarters: int

    roe: Decimal | None = None
    roce: Decimal | None = None
    gross_margin: Decimal | None = None
    operating_margin: Decimal | None = None
    net_margin: Decimal | None = None
    fcf_margin: Decimal | None = None
    revenue_growth: Decimal | None = None
    eps_growth: Decimal | None = None
    debt_to_equity: Decimal | None = None
    current_ratio: Decimal | None = None
    interest_cover: Decimal | None = None
    operating_leverage: Decimal | None = None
    buyback_yield: Decimal | None = None

    revenue_ttm: Decimal | None = None
    operating_income_ttm: Decimal | None = None
    net_income_ttm: Decimal | None = None
    eps_diluted_ttm: Decimal | None = None
    free_cash_flow_ttm: Decimal | None = None
    ebitda_ttm: Decimal | None = None


def _visible(rows: Sequence[PeriodRow], as_of: dt.date) -> list[PeriodRow]:
    """The rows a reader on ``as_of`` could have seen, one per period: the latest filed.

    Ties on ``filed`` (an amendment filed the same day) break on the accession, so the choice
    is deterministic rather than dependent on the query's row order.
    """
    latest: dict[tuple[dt.date, str], PeriodRow] = {}
    for row in rows:
        if row.filed > as_of:
            continue
        key = (row.period_end, row.period_class)
        seen = latest.get(key)
        if seen is None or (row.filed, row.accession_no or "") > (
            seen.filed,
            seen.accession_no or "",
        ):
            latest[key] = row
    return sorted(latest.values(), key=lambda r: r.period_end)


def _split(row: PeriodRow) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    flows = {k: v for k, v in row.values.items() if k in FLOW_CONCEPTS}
    balances = {k: v for k, v in row.values.items() if k in BALANCE_CONCEPTS}
    return flows, balances


def quarters_as_of(rows: Sequence[PeriodRow], as_of: dt.date) -> list[Quarter]:
    """The filer's quarterly series, oldest first, as visible on ``as_of``.

    Reported quarters pass through. For each annual row whose three quarters are all present,
    a fourth is derived by the identity — per CONCEPT, so a company that reports revenue
    quarterly but not depreciation gets an implied Q4 revenue and no implied Q4 depreciation,
    rather than a whole quarter dropped or a whole quarter invented.
    """
    visible = _visible(rows, as_of)
    by_end: dict[dt.date, Quarter] = {}
    for row in visible:
        if row.period_class != QUARTER:
            continue
        flows, balances = _split(row)
        by_end[row.period_end] = Quarter(row.period_end, row.filed, flows, balances)

    for row in visible:
        if row.period_class != ANNUAL or row.period_end in by_end:
            continue
        # The three quarters that share this fiscal year, newest first: the ones ending in the
        # 275 days before the year end. A quarter's end is ~91, ~183 and ~275 days back.
        earlier = sorted(
            (q for q in by_end.values() if 0 < (row.period_end - q.period_end).days <= 275),
            key=lambda q: q.period_end,
            reverse=True,
        )[:3]
        if len(earlier) != 3:
            continue
        annual_flows, balances = _split(row)
        implied: dict[str, Decimal] = {}
        for concept, annual in annual_flows.items():
            three = [q.flows.get(concept) for q in earlier]
            value = ratios.implied_q4(annual, *three)
            if value is not None:
                implied[concept] = value
        if implied:
            by_end[row.period_end] = Quarter(row.period_end, row.filed, implied, balances, True)
    return sorted(by_end.values(), key=lambda q: q.period_end)


def _flow_ttm(window: Sequence[Quarter], concept: str) -> Decimal | None:
    return ratios.ttm([q.flows.get(concept) for q in window])


def _balance_mean(window: Sequence[Quarter], concept: str) -> Decimal | None:
    """The mean of the balances the filer actually reported inside the window.

    NOT ``ratios.mean_of`` over four slots, which refuses on any gap. A balance sheet is not
    filed every quarter by every registrant: measured on the committed fixtures, equity
    appears in 43 of Apple's 71 assembled quarters and 43 of Verizon's 72. Demanding four
    would make return on equity — the single heaviest input the profitability sub-score has —
    absent for most of the index most of the time, on filers who reported the number twice.
    The mean of two real balances is an average of what was filed; a refusal over two missing
    slots is a refusal over nothing.
    """
    present = [b for q in window if (b := q.balances.get(concept)) is not None]
    return sum(present, Decimal(0)) / Decimal(len(present)) if present else None


def _balance_latest(window: Sequence[Quarter], concept: str) -> Decimal | None:
    """The most recent balance in the window that was actually filed.

    Not simply the last quarter's: a filer that reports a balance annually leaves it absent in
    two quarters out of three, and the newest one it DID file is the current figure.
    """
    for quarter in reversed(window):
        value = quarter.balances.get(concept)
        if value is not None:
            return value
    return None


def _total_debt(window: Sequence[Quarter]) -> Decimal | None:
    """Long- plus short-term debt as most recently filed. A company with debt filed under only
    one of the two elements has that much debt, not none — the same rule
    ``ingest_financials.db_rows`` applies to the stored column."""
    parts = [_balance_latest(window, c) for c in ("debt_long", "debt_short")]
    present = [p for p in parts if p is not None]
    return sum(present, Decimal(0)) if present else None


def metrics_as_of(
    rows: Sequence[PeriodRow], as_of: dt.date, *, is_financial: bool
) -> Metrics | None:
    """The metric set a reader on ``as_of`` could compute, or ``None`` with no full TTM window.

    ``is_financial`` suppresses the balance-sheet ratios at the source — a bank's leverage is
    its business model, and one ladder cannot score a lender and a manufacturer. It is the
    same decision India's scorer makes by passing those inputs as ``None``.
    """
    series = quarters_as_of(rows, as_of)
    if len(series) < TTM_QUARTERS:
        return None
    window = series[-TTM_QUARTERS:]
    prior = series[-YOY_QUARTERS:-TTM_QUARTERS] if len(series) >= YOY_QUARTERS else []
    newest = window[-1]

    revenue = _flow_ttm(window, "revenue")
    operating_income = _flow_ttm(window, "operating_income")
    net_income = _flow_ttm(window, "net_income")
    eps = _flow_ttm(window, "eps_diluted")
    equity_now = _balance_latest(window, "equity")
    debt = _total_debt(window)

    revenue_prior = _flow_ttm(prior, "revenue") if prior else None
    operating_prior = _flow_ttm(prior, "operating_income") if prior else None
    revenue_growth = ratios.growth(revenue, revenue_prior)
    free_cash_flow = ratios.fcf(
        _flow_ttm(window, "operating_cash_flow"), _flow_ttm(window, "capex")
    )

    return Metrics(
        as_of=as_of,
        period_end=newest.period_end,
        filed=newest.filed,
        quarters=len(series),
        implied_quarters=sum(1 for q in series if q.implied),
        # A return is earned over the window, so its denominator is the window's MEAN equity.
        roe=ratios.roe(net_income, _balance_mean(window, "equity")),
        roce=ratios.roce(operating_income, equity_now, debt),
        gross_margin=ratios.gross_margin(_flow_ttm(window, "gross_profit"), revenue),
        operating_margin=ratios.operating_margin(operating_income, revenue),
        net_margin=ratios.net_margin(net_income, revenue),
        fcf_margin=ratios.fcf_margin(free_cash_flow, revenue),
        revenue_growth=revenue_growth,
        eps_growth=ratios.growth(eps, _flow_ttm(prior, "eps_diluted") if prior else None),
        debt_to_equity=ratios.debt_to_equity(debt, equity_now, is_financial=is_financial),
        current_ratio=ratios.current_ratio(
            _balance_latest(window, "assets_current"),
            _balance_latest(window, "liabilities_current"),
            is_financial=is_financial,
        ),
        interest_cover=ratios.interest_cover(
            operating_income, _flow_ttm(window, "interest_expense")
        ),
        operating_leverage=ratios.operating_leverage(
            ratios.growth(operating_income, operating_prior), revenue_growth
        ),
        buyback_yield=ratios.buyback_yield(
            _balance_latest(window, "shares_diluted"),
            _balance_latest(prior, "shares_diluted") if prior else None,
        ),
        revenue_ttm=revenue,
        operating_income_ttm=operating_income,
        net_income_ttm=net_income,
        eps_diluted_ttm=eps,
        free_cash_flow_ttm=free_cash_flow,
        ebitda_ttm=ratios.ebitda(operating_income, _flow_ttm(window, "depreciation_amortization")),
    )

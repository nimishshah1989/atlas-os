"""TTM assembly and the stock ratios of ``docs/global/plan.md`` §B. Pure, Decimal, no I/O.

THE CONTRACT, and it is the whole point of this module: every function takes explicit inputs
and returns ``Decimal | None``. ``None`` means an input was missing or the ratio is undefined
on the inputs given — never zero, never a default, never a neutral score (rule #0). A lens
that renormalises over the sub-scores it actually has is honest about coverage; a lens fed a
silent zero prices a company as if it earned nothing.

WHY ``implied_q4`` EXISTS, and why it is not derived data in the rule #0 sense. No US filer
tags a discrete fourth quarter after 2020: the SEC dropped the selected-quarterly-data
requirement, so a 10-K carries only the twelve-month duration. Measured on the three
committed fixtures, Apple, JPMorgan and Verizon each file Q1/Q2/Q3 as three-month durations
and Q4 not at all (Apple's last reported Q4 duration is FY2020, Verizon's FY2019). The fourth
quarter is therefore the accounting identity FY − Q1 − Q2 − Q3 over four values the filer
reported, and :func:`implied_q4` is tested against the real Q4 Apple DID tag in FY2020, where
the identity reproduces it exactly. Without it, no trailing-twelve-month figure exists for
any quarter that is not a fiscal year end — which is three quarters in four.

SIGN CONVENTIONS, taken from the filings and not adjusted here: ``capex`` and
``dividends_paid`` are cash OUTFLOWS reported positive, so free cash flow subtracts capex;
``interest_expense`` is a cost reported positive. Values arrive exactly as filed.

DENOMINATORS THAT INVERT THE MEANING return ``None``. Return on equity with negative equity is
arithmetically a positive number for a loss-making company, and a growth rate off a negative
base reads backwards; those are not results to store and colour green. The rule is applied
once, in :func:`_ratio`, so no caller can forget it.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

# A trailing twelve months is four quarters — the definition of the window, not a tunable band.
TTM_QUARTERS = 4

ZERO = Decimal(0)


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    """``numerator / denominator``, or ``None`` when either is missing or the denominator is
    not strictly positive (a zero or negative base makes the ratio meaningless, not small)."""
    if numerator is None or denominator is None or denominator <= ZERO:
        return None
    return numerator / denominator


def _all_present(values: Sequence[Decimal | None]) -> list[Decimal] | None:
    """The values as a list, or ``None`` if any is missing. One gap and the aggregate is not
    a smaller aggregate — it is a different, unknown number."""
    if not values or any(v is None for v in values):
        return None
    return [v for v in values if v is not None]


# ── period assembly ──


def ttm(quarters: Sequence[Decimal | None]) -> Decimal | None:
    """Trailing twelve months = the sum of exactly four quarterly values.

    Fewer or more than four is a caller error and raises; a missing value among the four is a
    coverage gap and returns ``None``.
    """
    if len(quarters) != TTM_QUARTERS:
        raise ValueError(f"ttm() takes exactly {TTM_QUARTERS} quarters, got {len(quarters)}")
    present = _all_present(quarters)
    return None if present is None else sum(present, ZERO)


def implied_q4(
    annual: Decimal | None,
    q1: Decimal | None,
    q2: Decimal | None,
    q3: Decimal | None,
) -> Decimal | None:
    """The fourth fiscal quarter as ``FY − Q1 − Q2 − Q3`` — the only way to obtain it after
    2020 (see the module docstring). ``None`` unless all four inputs are present."""
    present = _all_present([annual, q1, q2, q3])
    if present is None:
        return None
    full_year, *first_three = present
    return full_year - sum(first_three, ZERO)


def mean_of(values: Sequence[Decimal | None]) -> Decimal | None:
    """The arithmetic mean, or ``None`` if any value is missing — the average equity a
    return-on-equity divides by is an average of the four balances, not of those that
    happened to be filed."""
    present = _all_present(values)
    if present is None:
        return None
    return sum(present, ZERO) / Decimal(len(present))


# ── derived period figures ──


def ebitda(operating_income: Decimal | None, dep_amort: Decimal | None) -> Decimal | None:
    """EBIT + D&A. ``None`` if either is missing — a bank files no ``OperatingIncomeLoss``, so
    EBITDA does not exist for it, and 0 + D&A would be a fabrication."""
    present = _all_present([operating_income, dep_amort])
    return None if present is None else sum(present, ZERO)


def fcf(operating_cash_flow: Decimal | None, capex: Decimal | None) -> Decimal | None:
    """Free cash flow = operating cash flow − capital expenditure (an outflow filed positive)."""
    if operating_cash_flow is None or capex is None:
        return None
    return operating_cash_flow - capex


def growth(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    """Year-on-year growth as a fraction. ``None`` off a zero or negative base: EPS growth
    measured from a loss has no sign anyone can read."""
    if current is None or prior is None:
        return None
    return _ratio(current - prior, prior)


# ── profitability ──


def roe(ttm_net_income: Decimal | None, average_equity: Decimal | None) -> Decimal | None:
    """Return on equity = TTM net income ÷ average shareholders' equity over the four quarters
    (pair with :func:`mean_of`). ``None`` on non-positive equity."""
    return _ratio(ttm_net_income, average_equity)


def roce(
    ttm_operating_income: Decimal | None,
    equity: Decimal | None,
    total_debt: Decimal | None,
) -> Decimal | None:
    """Return on capital employed = TTM EBIT ÷ (equity + total debt).

    Capital employed needs BOTH components: a company with debt it did not file is not a
    debt-free company. ``None`` if either is missing or the sum is not positive.
    """
    employed = _all_present([equity, total_debt])
    return None if employed is None else _ratio(ttm_operating_income, sum(employed, ZERO))


def gross_margin(gross_profit: Decimal | None, revenue: Decimal | None) -> Decimal | None:
    return _ratio(gross_profit, revenue)


def operating_margin(operating_income: Decimal | None, revenue: Decimal | None) -> Decimal | None:
    return _ratio(operating_income, revenue)


def net_margin(net_income: Decimal | None, revenue: Decimal | None) -> Decimal | None:
    return _ratio(net_income, revenue)


def fcf_margin(free_cash_flow: Decimal | None, revenue: Decimal | None) -> Decimal | None:
    return _ratio(free_cash_flow, revenue)


# ── balance sheet (suppressed for financial companies) ──


def debt_to_equity(
    total_debt: Decimal | None, equity: Decimal | None, *, is_financial: bool
) -> Decimal | None:
    """Debt ÷ equity, or ``None`` for a financial company.

    A bank's leverage is its business model and its regulator's concern, not a quality
    signal: ten times equity is normal for a lender and alarming for a manufacturer, so one
    ladder cannot score both. India's scorer suppresses the same sub-score by passing the
    balance-sheet inputs as ``None``; this flag is that decision made explicit at the source.
    """
    if is_financial:
        return None
    return _ratio(total_debt, equity)


def current_ratio(
    current_assets: Decimal | None, current_liabilities: Decimal | None, *, is_financial: bool
) -> Decimal | None:
    """Current assets ÷ current liabilities, or ``None`` for a financial company — which does
    not classify its balance sheet as current and non-current at all. Measured on the
    committed JPMorgan payload: no ``AssetsCurrent`` and no ``LiabilitiesCurrent`` fact
    exists, in any period, so the inputs are absent as well as meaningless."""
    if is_financial:
        return None
    return _ratio(current_assets, current_liabilities)


# ── coverage, leverage, shareholder return ──


def interest_cover(
    ttm_operating_income: Decimal | None, ttm_interest_expense: Decimal | None
) -> Decimal | None:
    """EBIT ÷ interest expense. ``None`` when interest expense is zero or absent: a company
    that pays no interest has infinite cover, which is not a number to rank on."""
    return _ratio(ttm_operating_income, ttm_interest_expense)


def operating_leverage(
    operating_income_growth: Decimal | None, revenue_growth: Decimal | None
) -> Decimal | None:
    """ΔEBIT% ÷ Δrevenue% — how much of a sales move reaches the operating line.

    ``None`` when revenue growth is zero (division by nothing) or negative: on shrinking sales
    the ratio's sign no longer distinguishes operating leverage from operating collapse.
    """
    return _ratio(operating_income_growth, revenue_growth)


def buyback_yield(
    shares_diluted_now: Decimal | None, shares_diluted_year_ago: Decimal | None
) -> Decimal | None:
    """Minus the year-on-year change in diluted share count: positive when the count fell.

    Not a cash figure — it is the shareholder's change in claim, which is what a buyback and a
    dilutive issuance both move. Dividend yield is deliberately NOT here: it needs a price,
    and this module never reaches outside its arguments.
    """
    shrinkage = growth(shares_diluted_now, shares_diluted_year_ago)
    return None if shrinkage is None else -shrinkage

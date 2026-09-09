"""The PIT metric assembly, on the three real company-facts payloads.

``metrics_as_of`` is the step between ``stock_financials_pit`` and the fundamental lens, and
every part of it is a way to be wrong: the point-in-time filter, the implied fourth quarter,
summing flows but not balances, and the year-on-year window. The assertions below are Apple's,
JPMorgan's and Verizon's own filed figures — provenance in
``tests/fixtures/global/edgar/SOURCE.md``.

Two properties are asserted rather than a value, because they hold whatever the fixtures move
to on a refresh: a margin must reproduce the numerator it was divided from, and a metric set
read as of an earlier date must not know a later filing.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from atlas.global_market.fundamentals.facts import extract_rows
from atlas.global_market.fundamentals.metrics import (
    TTM_QUARTERS,
    YOY_QUARTERS,
    metrics_as_of,
    quarters_as_of,
)
from atlas.global_market.fundamentals.metrics import rows_from_records as metrics_from_records

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "edgar"
PAYLOADS = {
    "AAPL": ("companyfacts_AAPL_CIK0000320193.json", False),
    "JPM": ("companyfacts_JPM_CIK0000019617.json", True),
    "VZ": ("companyfacts_VZ_CIK0000732712.json", False),
}
TODAY = dt.date(2026, 9, 8)  # a fixed anchor: these are dated fixtures, not a live feed
IID = "6f9619ff-8b86-d011-b42d-00c04fc964ff"  # a valid uuid; nothing here reads it


@cache
def rows(symbol: str) -> tuple[Any, ...]:
    name, _ = PAYLOADS[symbol]
    return tuple(extract_rows(json.loads((FIXTURES / name).read_text())))


@cache
def metrics(symbol: str, as_of: dt.date = TODAY):
    _, is_financial = PAYLOADS[symbol]
    return metrics_as_of(rows(symbol), as_of, is_financial=is_financial)


# ── the series ──


@pytest.mark.parametrize("symbol", sorted(PAYLOADS))
def test_every_filer_assembles_more_than_the_coverage_floor(symbol: str) -> None:
    """``fund_min_quarters`` is 8 — two trailing-twelve-month windows end to end, which is what
    a year-on-year growth rate needs. All three fixtures clear it by decades."""
    series = quarters_as_of(rows(symbol), TODAY)
    assert len(series) >= YOY_QUARTERS
    assert [q.period_end for q in series] == sorted(q.period_end for q in series)
    assert len({q.period_end for q in series}) == len(series)


@pytest.mark.parametrize("symbol", sorted(PAYLOADS))
def test_a_fourth_quarter_is_implied_where_no_filer_tags_one(symbol: str) -> None:
    """Post-2020 no US filer tags a discrete Q4, so the identity has to supply it — and the
    row says so rather than passing as reported."""
    series = quarters_as_of(rows(symbol), TODAY)
    implied = [q for q in series if q.implied]
    assert implied, "no fourth quarter was implied: a TTM would exist only at year ends"
    assert all(q.flows for q in implied)  # an implied quarter with nothing in it is not one


# ── flows sum, balances do not ──


def test_a_margin_reproduces_the_figure_it_was_divided_from() -> None:
    """The property that catches a numerator and denominator drawn from different windows."""
    m = metrics("AAPL")
    assert m is not None
    assert m.revenue_ttm and m.net_income_ttm and m.operating_income_ttm
    assert m.net_margin is not None and m.operating_margin is not None
    assert abs(m.net_margin * m.revenue_ttm - m.net_income_ttm) < Decimal("1e-6")
    assert abs(m.operating_margin * m.revenue_ttm - m.operating_income_ttm) < Decimal("1e-6")


def test_the_trailing_twelve_months_is_the_sum_of_its_four_quarters() -> None:
    m = metrics("VZ")
    series = quarters_as_of(rows("VZ"), TODAY)
    window = series[-TTM_QUARTERS:]
    assert m is not None
    assert m.revenue_ttm == sum((q.flows["revenue"] for q in window), Decimal(0))


def test_return_on_equity_averages_the_balances_the_filer_reported() -> None:
    """Equity is a BALANCE: a return earned over a year is measured against the average of the
    equity that earned it, not against either end point. And the average is over what was
    filed — equity appears in fewer than two thirds of the assembled quarters, so demanding
    four would make ROE absent for most of the index."""
    m = metrics("VZ")
    series = quarters_as_of(rows("VZ"), TODAY)
    window = series[-TTM_QUARTERS:]
    filed = [b for q in window if (b := q.balances.get("equity")) is not None]
    assert 0 < len(filed) <= TTM_QUARTERS
    average = sum(filed, Decimal(0)) / Decimal(len(filed))
    assert m is not None and m.net_income_ttm is not None
    assert m.roe is not None
    assert abs(m.roe - m.net_income_ttm / average) < Decimal("1e-9")


# ── point in time ──


def test_a_metric_set_does_not_know_a_filing_it_could_not_have_seen() -> None:
    """The whole reason ``stock_financials_pit`` is keyed by ``filed``. Read as of the start of
    2021, Apple's newest period is its FY2020 year end and the window is decades shorter."""
    now = metrics("AAPL")
    then = metrics("AAPL", dt.date(2021, 1, 1))
    assert now is not None and then is not None
    assert then.period_end < now.period_end
    assert then.filed <= dt.date(2021, 1, 1)
    assert then.quarters < now.quarters
    assert all(
        row.filed <= dt.date(2021, 1, 1)
        for row in quarters_as_of(rows("AAPL"), dt.date(2021, 1, 1))
    )


def test_before_any_filing_there_is_no_metric_set_rather_than_an_empty_one() -> None:
    assert metrics_as_of(rows("AAPL"), dt.date(1999, 1, 1), is_financial=False) is None


# ── coverage is honest ──


def test_a_bank_gets_no_balance_sheet_ratios_and_no_operating_margin() -> None:
    """JPMorgan files no ``OperatingIncomeLoss``, no ``AssetsCurrent`` and no
    ``LiabilitiesCurrent`` in any period; ``is_financial`` suppresses the leverage read on top.
    Every one of those is ``None`` — not zero, which would score a bank badly for being one."""
    m = metrics("JPM")
    assert m is not None
    assert m.operating_margin is None
    assert m.roce is None  # needs EBIT
    assert m.debt_to_equity is None
    assert m.current_ratio is None
    assert m.roe is not None and m.net_margin is not None  # what it DOES file still scores


def test_free_cash_flow_is_absent_because_cash_flow_is_filed_year_to_date() -> None:
    """A 10-Q's cash-flow statement covers three, six or nine months from the year start, so a
    discrete quarter of it mostly does not exist. Apple reports it in 13 of 71 assembled
    quarters. FCF is not a lens sub-score, so no score is lost — but the card cannot always
    show it, and that is the honest answer rather than a differenced figure nobody filed."""
    series = quarters_as_of(rows("AAPL"), TODAY)
    with_ocf = sum(1 for q in series if q.flows.get("operating_cash_flow") is not None)
    assert 0 < with_ocf < len(series) // 2
    m = metrics("AAPL")
    assert m is not None and m.free_cash_flow_ttm is None


def test_total_debt_takes_whichever_component_the_filer_reported() -> None:
    """A company with debt filed under only the long-term element has that much debt, not
    none — the same rule the stored ``total_debt`` column follows."""
    m = metrics("VZ")
    assert m is not None
    assert m.debt_to_equity is not None and m.debt_to_equity > 0


# ── the round trip through the table ──


def test_the_table_round_trips_to_the_same_metric_set() -> None:
    """``ingest_financials`` writes a PeriodRow into columns and ``rows_from_records`` reads it
    back. If the two column maps ever disagree, a concept stops being scored — silently, since
    an absent input is a legitimate answer everywhere else in this module.

    So the metric set is built twice on Verizon's real payload: once from the parsed filings,
    once from the records the writer would have stored, and the two must agree field for field.
    """
    from tests.unit.global_market.script_loader import load_global_script

    fin = load_global_script("ingest_financials")
    parsed = list(rows("VZ"))
    records = fin.db_rows(parsed, IID, is_financial=False)
    replayed = metrics_from_records(records)

    direct = metrics_as_of(parsed, TODAY, is_financial=False)
    through_table = metrics_as_of(replayed, TODAY, is_financial=False)
    assert direct is not None and through_table is not None
    assert direct == through_table


def test_a_null_column_is_an_absent_concept_and_not_a_none_value() -> None:
    """``.get`` must not be able to tell them apart, so the reader leaves NULLs out."""
    [row] = metrics_from_records(
        [
            {
                "period_end": dt.date(2026, 3, 31),
                "form": "10-Q",
                "filed": dt.date(2026, 4, 30),
                "revenue": Decimal("100"),
                "operating_income": None,
            }
        ]
    )
    assert row.values == {"revenue": Decimal("100")}
    assert row.period_class == "quarter"

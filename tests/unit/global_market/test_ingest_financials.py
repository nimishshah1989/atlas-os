"""``ingest_financials``'s pure half, on the REAL company-facts payloads it will meet in prod.

The three files under ``tests/fixtures/global/edgar/`` are verbatim SEC downloads for Apple,
JPMorgan and Verizon (trimmed to the mapped tags; provenance in that directory's
``SOURCE.md``). Nothing is stubbed and no filing is invented: the assertions below are Apple's
own restated share count, JPMorgan's absent operating income, and the forms and durations SEC
actually publishes. No network, no database — the extraction is a pure function of a payload
and the CLI is exercised through its parser.

The row-building rules under test are the two that can be silently wrong:

* only the filing's OWN period class survives, so a nine-month year-to-date never lands in a
  column read as a quarter, and
* ``filed`` is part of the key, so a restatement is a second row and the earlier one is still
  there to be read as of its own date.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from atlas.global_market.fundamentals import facts
from tests.unit.global_market.script_loader import load_global_script

fin = load_global_script("ingest_financials")

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "global" / "edgar"
DDL = REPO / "scripts" / "global_market" / "ddl" / "04_fundamentals_events.sql"
PAYLOADS = {
    "AAPL": "companyfacts_AAPL_CIK0000320193.json",
    "JPM": "companyfacts_JPM_CIK0000019617.json",
    "VZ": "companyfacts_VZ_CIK0000732712.json",
}
IID = "6f9619ff-8b86-d011-b42d-00c04fc964ff"  # a syntactically valid uuid; nothing reads it here


@cache
def payload(symbol: str) -> dict[str, Any]:
    return json.loads((FIXTURES / PAYLOADS[symbol]).read_text())


@cache
def rows(symbol: str) -> tuple[Any, ...]:
    return tuple(facts.extract_rows(payload(symbol)))


def raw_facts(symbol: str, tag: str) -> list[dict[str, Any]]:
    units = payload(symbol)["facts"]["us-gaap"].get(tag, {}).get("units", {})
    return [f for unit_facts in units.values() for f in unit_facts]


# ── the table's contract, read off the DDL ────────────────────────────────────────────────


def test_allowed_forms_are_exactly_the_ddl_check() -> None:
    """The form filter and ``chk_stock_financials_pit_form`` cannot drift apart: a form the
    script admits and the CHECK refuses is a whole nightly that dies on the insert."""
    pattern = r"chk_stock_financials_pit_form\s+CHECK \(form IN \(([^)]*)\)\)"
    check = re.search(pattern, DDL.read_text())
    assert check is not None
    assert facts.ALLOWED_FORMS == set(re.findall(r"'([^']+)'", check.group(1)))
    assert facts.ANNUAL_FORMS < facts.ALLOWED_FORMS


def test_every_written_column_exists_on_the_table() -> None:
    body = DDL.read_text().split("CREATE TABLE IF NOT EXISTS atlas_global.stock_financials_pit")[1]
    body = body.split("CONSTRAINT stock_financials_pit_pkey")[0]
    declared = set(re.findall(r"^\s{4}(\w+)\s+\w", body, flags=re.MULTILINE))
    assert set(fin.DB_COLUMNS) <= declared, set(fin.DB_COLUMNS) - declared
    assert fin.CONFLICT_COLUMNS == ["instrument_id", "period_end", "form", "filed"]
    # cost_of_revenue is mapped but deliberately unwritten: the table has no column for it.
    assert "cost_of_revenue" not in declared
    assert "cost_of_revenue" not in fin.CONCEPT_COLUMNS


# ── period classification ─────────────────────────────────────────────────────────────────


def test_period_class_separates_balances_quarters_years_and_year_to_date() -> None:
    """The four shapes company facts serves, using Apple's own FY2020 Q3 10-Q dates: a balance
    (no start), the three-month quarter, the nine-month year-to-date, and the fiscal year."""
    assert facts.period_class(None, "2020-06-27") == facts.INSTANT
    assert facts.period_class("2020-03-29", "2020-06-27") == facts.QUARTER
    assert facts.period_class("2019-09-29", "2020-06-27") is None  # nine-month YTD: no column
    assert facts.period_class("2019-09-29", "2020-09-26") == facts.ANNUAL
    assert facts.period_class("2019-12-29", "2020-06-27") is None  # six-month YTD


def test_the_payloads_really_do_carry_the_shapes_this_filters() -> None:
    """Guards the test above from becoming vacuous: the fixtures contain year-to-date
    durations and non-periodic forms, so the filters are exercised, not merely present."""
    classes = {
        facts.period_class(f.get("start"), f["end"])
        for f in raw_facts("AAPL", "RevenueFromContractWithCustomerExcludingAssessedTax")
    }
    assert None in classes and facts.QUARTER in classes and facts.ANNUAL in classes
    forms = {f["form"] for f in raw_facts("VZ", "Revenues")}
    assert "8-K" in forms  # Verizon tags its earnings releases; the table admits no 8-K


# ── extraction ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("symbol", sorted(PAYLOADS))
def test_every_row_is_a_periodic_filing_of_its_own_period(symbol: str) -> None:
    extracted = rows(symbol)
    assert extracted, symbol
    for row in extracted:
        assert row.form in facts.ALLOWED_FORMS
        annual = row.form in facts.ANNUAL_FORMS
        assert row.period_class == (facts.ANNUAL if annual else facts.QUARTER)
        assert row.filed >= row.period_end  # a filing cannot predate the period it reports
        assert row.period_start is not None
        assert facts.period_class(row.period_start.isoformat(), row.period_end.isoformat()) == (
            row.period_class
        )
        assert row.values, "a row with no value is not a row"
        assert set(row.tags) == set(row.values)


def test_apple_extracts_its_whole_filed_history() -> None:
    extracted = rows("AAPL")
    quarterly = [r for r in extracted if not r.is_annual]
    assert extracted[0].period_end == dt.date(2007, 9, 29)
    assert extracted[-1].period_end == dt.date(2026, 6, 27)
    assert facts.quarter_count(extracted) == len({r.period_end for r in quarterly})
    assert facts.quarter_count(extracted) >= 40  # ten years of quarters, and then some
    newest = max(extracted, key=lambda r: (r.period_end, r.filed))
    assert (newest.form, newest.fiscal_year, newest.fiscal_period) == ("10-Q", 2026, "Q3")
    assert newest.values["revenue"] == Decimal("109417000000")
    assert newest.tags["revenue"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert newest.accession_no == "0000320193-26-000020"


def test_no_filer_in_the_fixtures_tags_a_discrete_fourth_quarter_after_2020() -> None:
    """The fact that forces ``ratios.implied_q4`` to exist, asserted rather than asserted-to.

    A fiscal Q4 would be a quarterly row whose period_end is also a fiscal-year end. Apple's
    last is FY2020; nothing after it, for any of the three filers.
    """
    for symbol in PAYLOADS:
        year_ends = {r.period_end for r in rows(symbol) if r.is_annual}
        q4s = {r.period_end for r in rows(symbol) if not r.is_annual and r.period_end in year_ends}
        assert not [d for d in q4s if d.year > 2021], (symbol, sorted(q4s))


# ── the point-in-time key ─────────────────────────────────────────────────────────────────


def test_a_restatement_is_a_second_row_never_an_overwrite() -> None:
    """Apple's FY2019 diluted share count, as the record actually moved.

    The FY2019 10-K (filed 2019-10-31) reported 4,648,913 thousand diluted shares. The FY2020
    10-K (filed 2020-10-30) re-presented the same fiscal year at 18,595,651 thousand, restated
    for the August 2020 four-for-one split. Same instrument, same period_end, same form —
    only ``filed`` differs, so both rows exist and a reader as of 2020-01-01 still sees the
    number that was on file that day. Keying on (instrument, period_end) would have destroyed
    the first one, and every pre-split backtest with it.
    """
    fy2019 = [r for r in rows("AAPL") if r.period_end == dt.date(2019, 9, 28) and r.form == "10-K"]
    by_filed = {r.filed: r.values["shares_diluted"] for r in fy2019}
    assert by_filed[dt.date(2019, 10, 31)] == Decimal("4648913000")
    assert by_filed[dt.date(2020, 10, 30)] == Decimal("18595651000")

    # Three 10-Ks re-present FY2019 (2019, 2020 and 2021); the 2021 one repeats the restated
    # figure, so two distinct values across three point-in-time rows is the correct record.
    assert len(fy2019) == 3
    assert set(by_filed.values()) == {Decimal("4648913000"), Decimal("18595651000")}

    records = fin.db_rows(fy2019, IID, is_financial=False)
    keys = [tuple(r[c] for c in fin.CONFLICT_COLUMNS) for r in records]
    assert len(set(keys)) == len(keys), "two filings of one period must not collide on the key"
    assert len({k[:3] for k in keys}) == 1  # identical but for `filed`


def test_no_two_rows_share_the_primary_key() -> None:
    """Every fixture, every row: the upsert would silently merge two real filings otherwise."""
    for symbol in PAYLOADS:
        keys = [
            tuple(r[c] for c in fin.CONFLICT_COLUMNS)
            for r in fin.db_rows(rows(symbol), IID, is_financial=False)
        ]
        assert len(set(keys)) == len(keys), symbol


def test_fiscal_labels_are_taken_only_for_the_filings_own_period() -> None:
    """Company facts stamps every fact with the FILING's fiscal year, so a comparative would
    be mislabelled by a year if the stamp were copied. Apple's 2026 Q3 10-Q carries its own
    quarter as (2026, Q3) and the prior-year comparatives with no year at all."""
    own = [r for r in rows("AAPL") if r.filed == dt.date(2026, 7, 31) and r.form == "10-Q"]
    assert len(own) > 1, "the filing carries comparatives as well as its own quarter"
    newest = max(own, key=lambda r: r.period_end)
    assert (newest.fiscal_year, newest.fiscal_period) == (2026, "Q3")
    for row in own:
        if row is newest:
            continue
        assert row.fiscal_year is None and row.fiscal_period is None
    # an annual row keeps FY, which its twelve-month duration proves, with or without a year
    annuals = [r for r in rows("AAPL") if r.is_annual]
    assert {r.fiscal_period for r in annuals} == {"FY"}


# ── the database records ──────────────────────────────────────────────────────────────────


def test_db_rows_map_concepts_onto_the_tables_columns() -> None:
    newest = max(rows("AAPL"), key=lambda r: (r.period_end, r.filed))
    (record,) = fin.db_rows([newest], IID, is_financial=False)
    assert set(record) == set(fin.DB_COLUMNS)
    assert record["instrument_id"] == IID
    assert record["is_financial_co"] is False
    assert record["revenue"] == newest.values["revenue"]
    assert record["dep_amort"] == newest.values.get("depreciation_amortization")
    assert record["total_assets"] == newest.values["assets"]
    # total_debt is the sum of the two components the filer reported, both real
    assert record["total_debt"] == newest.values["debt_long"] + newest.values["debt_short"]
    assert record["total_debt"] == Decimal("82347000000")


def test_a_bank_carries_nulls_where_it_files_nothing_and_never_a_zero() -> None:
    """JPMorgan files no operating income, gross profit, capital expenditure or current
    assets — the table stores NULL for each, which is what makes the fundamental lens
    renormalise instead of scoring the bank as unprofitable."""
    newest = max(rows("JPM"), key=lambda r: (r.period_end, r.filed))
    (record,) = fin.db_rows([newest], IID, is_financial=True)
    absent = ("operating_income", "gross_profit", "capex", "current_assets", "current_liabilities")
    for column in absent:
        assert record[column] is None, column
    assert record["is_financial_co"] is True
    assert record["revenue"] == Decimal("57347000000")
    assert record["net_income"] == Decimal("21155000000")


def test_verizons_row_uses_the_fallback_tags_and_says_which() -> None:
    newest = max(rows("VZ"), key=lambda r: (r.period_end, r.filed))
    assert newest.tags["equity"] == (
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    )
    assert newest.tags["debt_long"] == "LongTermDebtAndCapitalLeaseObligations"
    assert newest.tags["interest_expense"] == "InterestExpenseNonoperating"
    summary = facts.tag_summary(rows("VZ"))
    assert "revenue=Revenues" in summary
    assert "depreciation_amortization=DepreciationAndAmortization" in summary


def test_cash_flow_lands_on_the_periods_that_report_it() -> None:
    """A 10-Q's cash-flow statement is cumulative, so only the FIRST fiscal quarter's is a
    three-month duration; Q2 and Q3 publish six- and nine-month figures, which this refuses to
    store in a quarterly column. Annual rows carry the full year. Apple, FY2026 Q1 vs Q3."""
    q1 = next(r for r in rows("AAPL") if r.period_end == dt.date(2025, 12, 27))
    q3 = max(
        (r for r in rows("AAPL") if r.period_end == dt.date(2026, 6, 27)), key=lambda r: r.filed
    )
    assert q1.values["operating_cash_flow"] == Decimal("53925000000")
    assert q1.values["capex"] == Decimal("2373000000")
    assert "operating_cash_flow" not in q3.values
    fy2025 = next(r for r in rows("AAPL") if r.period_end == dt.date(2025, 9, 27) and r.is_annual)
    assert "operating_cash_flow" in fy2025.values and "capex" in fy2025.values


def test_the_upsert_updates_every_column_except_the_key() -> None:
    """A re-run must be idempotent, and a key column must never appear in the SET list — an
    ``ON CONFLICT`` that rewrote ``filed`` would turn the point-in-time journal into a
    last-write-wins table, which is the one thing this table exists not to be."""
    sql = fin.UPSERT_SQL
    head, _, update = sql.partition("do update set")
    for column in fin.CONFLICT_COLUMNS:
        assert f"{column} = excluded.{column}" not in update, column
    for column in fin.DB_COLUMNS:
        if column not in fin.CONFLICT_COLUMNS:
            assert f"{column} = excluded.{column}" in update, column
    assert "ingested_at = now()" in update  # a re-run is visible to the freshness guard
    assert f"on conflict ({', '.join(fin.CONFLICT_COLUMNS)})" in head
    assert f"'{fin.SOURCE_LABEL}'" not in sql  # the label rides on the VALUES template
    assert fin.SOURCE_LABEL == "edgar_xbrl"  # ddl/04_fundamentals_events.sql's own default


# ── plumbing ──────────────────────────────────────────────────────────────────────────────


def test_rate_limit_spaces_request_starts_under_the_sec_ceiling() -> None:
    """Ten a second is the SEC's stated ceiling; the limiter waits only for the shortfall, so
    a slow parse between calls costs no extra delay."""
    slept: list[float] = []
    clock = iter([0.0, 0.0, 0.005, 0.005, 10.0, 10.0])  # read before the gap and after the wait
    fin._last_call[0] = -1000.0  # a cold process: the first request never waits
    fin._rate_limit(clock=lambda: next(clock), sleep=slept.append)  # no wait
    fin._rate_limit(clock=lambda: next(clock), sleep=slept.append)  # 5 ms later: wait the rest
    fin._rate_limit(clock=lambda: next(clock), sleep=slept.append)  # 10 s later: no wait
    assert slept == [pytest.approx(fin.SEC_MIN_INTERVAL_S - 0.005)]
    assert fin.SEC_MIN_INTERVAL_S >= 0.1  # >= 0.1 s between starts is <= 10 requests a second


def test_the_cli_parses_the_documented_flags() -> None:
    args = fin.parser().parse_args(
        ["--eod", "2026-09-07", "--limit", "5", "--symbols", "AAPL,MSFT", "--report", "/tmp/f.csv"]
    )
    assert args.eod == dt.date(2026, 9, 7)
    assert (args.limit, args.symbols) == (5, "AAPL,MSFT")
    assert isinstance(args.report, Path)  # Report opens what it is handed; a str fails late
    assert args.dry_run is False and args.full is False
    defaults = fin.parser().parse_args([])
    assert defaults.eod is None and defaults.report is None
    assert fin.parser().parse_args(["--dry-run", "--full"]).full is True


def test_the_report_carries_the_status_column_report_counts_by() -> None:
    assert "status" in fin.REPORT_COLUMNS
    assert set(fin.FAILURE_STATUSES) <= set(fin.REPORT_COLUMNS) | {
        fin.STATUS_NO_CIK,
        fin.STATUS_NO_FACTS,
        fin.STATUS_NO_ROWS,
        fin.STATUS_FETCH_FAILED,
    }
    assert fin.STATUS_WRITTEN not in fin.FAILURE_STATUSES

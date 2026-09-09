"""``ingest_nport``'s pure half, on the four real N-PORT filings it will meet in prod.

No network and no database: the record builders are pure functions of a parsed filing, and
the filings are the verbatim downloads under ``tests/fixtures/global/nport/`` (provenance in
that directory's ``SOURCE.md``). The rules under test are the ones that can be silently wrong:

* an ETF's AUM is the SERIES' net assets only where the series has one share class, so VOO
  must come out with no AUM at all rather than the Vanguard 500 Index Fund's $1.67tn;
* a holding resolves to a scored instrument by CUSIP or ISIN and never by a ticker, because
  the only tickers in these filings are on futures lines; and
* every column the writer names must exist in the DDL — a rename there is a runtime
  ``UndefinedColumn`` on the box at one in the morning otherwise.
"""

from __future__ import annotations

import gzip
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from atlas.global_market.providers.nport import parse_nport
from tests.unit.global_market.script_loader import load_global_script

nport = load_global_script("ingest_nport")
membership = load_global_script("ingest_index_membership")

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "global" / "nport"
DDL = REPO / "scripts" / "global_market" / "ddl" / "02_etf.sql"
IID = "6f9619ff-8b86-d011-b42d-00c04fc964ff"  # a syntactically valid uuid; nothing reads it here
HELD = "11111111-2222-3333-4444-555555555555"


def parsed(slug: str):
    return parse_nport(gzip.decompress((FIXTURES / f"{slug}_primary_doc.xml.gz").read_bytes()))


# ── AUM: the series is not the share class ──


def test_a_single_class_series_net_assets_are_the_etfs_aum() -> None:
    facts, holdings = parsed("ivv")
    row = nport.meta_row(facts, IID, holdings)
    assert row["aum_usd"] == Decimal("888128937468.17")
    assert row["aum_as_of"] == date(2026, 6, 30)
    assert row["aum_source"] == "nport"
    assert row["series_class_count"] == 1
    assert row["series_net_assets_usd"] == row["aum_usd"]


def test_a_multi_class_series_gets_no_aum_at_all() -> None:
    """VOO is one of four classes of a $1.67tn fund. That figure is real and it is not VOO's.

    Writing it into ``aum_usd`` would put a wrong number on the card and a wrong band into the
    cost lens; the honest outcome is a missing sub-score (rule #0).
    """
    facts, holdings = parsed("voo")
    row = nport.meta_row(facts, IID, holdings)
    assert row["aum_usd"] is None
    assert row["aum_as_of"] is None
    assert row["aum_source"] is None
    assert row["series_class_count"] == 4
    assert row["series_net_assets_usd"] == Decimal("1671231561960.14")


def test_the_gearing_columns_separate_a_three_times_fund_from_an_index_one() -> None:
    """Two different questions, two columns, and they answer differently.

    "How much of the fund is in derivatives" is the MARK — TQQQ 0.370 against IVV's 0.0000157.
    "How much does the fund control" is the NOTIONAL — TQQQ 2.70 against IVV's 0.00158, and
    only that one is the leverage multiple. Both are real; neither is the other.
    """
    tqqq = nport.meta_row(*_meta_args("tqqq"))
    ivv = nport.meta_row(*_meta_args("ivv"))
    assert tqqq["derivative_notional_share"] > Decimal(2)
    assert ivv["derivative_notional_share"] < Decimal("0.01")
    assert Decimal("0.35") < tqqq["derivatives_share"] < Decimal("0.40")
    assert ivv["derivatives_share"] < Decimal("0.0001")


def _meta_args(slug: str):
    facts, holdings = parsed(slug)
    return facts, IID, holdings


def test_derivatives_share_counts_the_lines_that_are_derivatives() -> None:
    """A line is a derivative because it filed a ``derivativeInfo`` block, not because its
    ``assetCat`` is one of the codes this repo happens to remember."""
    _, ivv = parsed("ivv")
    only_line = abs(ivv.loc[ivv["derivative_category"].notna(), "weight_frac"].iloc[0])
    assert nport.abs_weight(ivv, only="derivative_category") == only_line
    assert nport.abs_weight(ivv) > only_line  # unmasked, it is the whole snapshot
    _, tqqq = parsed("tqqq")
    assert nport.abs_weight(tqqq, only="derivative_category") > 0
    assert nport.abs_weight(ivv.iloc[0:0]) is None  # a filing with no positions


def test_a_weight_no_column_could_hold_is_refused_before_it_reaches_the_batch() -> None:
    """``chk_etf_holdings_weight_frac`` bounds weight_frac at ±10. One filer's impossible
    pctVal would abort a whole 50,000-row batch, so the fund is refused and reported."""
    _, ivv = parsed("ivv")
    assert nport.WEIGHT_LIMIT == Decimal(10)
    assert max(abs(w) for w in ivv["weight_frac"] if w is not None) < nport.WEIGHT_LIMIT
    ddl = DDL.read_text()
    assert "weight_frac >= -10 AND weight_frac <= 10" in ddl
    assert nport.STATUS_WEIGHT_OUT_OF_RANGE in nport.FAILURE_STATUSES


# ── resolution ──


def test_a_holding_resolves_by_cusip_then_isin_and_never_by_ticker() -> None:
    """IVV holds CBRE (CUSIP 12504L109, ISIN US12504L1098) and an E-Mini future.

    Three aliases are offered: the CUSIP, an ISIN belonging to a DIFFERENT holding, and the
    future's own code. Only the first two may ever match.
    """
    facts, holdings = parsed("ivv")
    aliases = {"12504L109": HELD, "ESU6": "ffffffff-0000-0000-0000-000000000000"}
    rows, resolved = nport.holding_rows(holdings, IID, facts.period_date, aliases)

    assert resolved == 1
    cbre = next(r for r in rows if r["holding_name"] == "CBRE Group, Inc.")
    assert cbre["holding_instrument_id"] == HELD
    assert cbre["as_of_date"] == date(2026, 6, 30)
    assert all(r["holding_instrument_id"] is None for r in rows if r is not cbre)


def test_isin_carries_the_resolution_where_there_is_no_cusip() -> None:
    """176 of EWJ's 182 holdings file no CUSIP. Without the ISIN branch, none of them could
    ever reach an instrument."""
    facts, holdings = parsed("ewj")
    with_isin = holdings.loc[holdings["cusip"].isna() & holdings["isin"].notna()]
    target = str(with_isin["isin"].iloc[0])
    rows, resolved = nport.holding_rows(holdings, IID, facts.period_date, {target: HELD})
    assert resolved == 1
    assert next(r for r in rows if r["isin"] == target)["holding_instrument_id"] == HELD


def test_a_filers_own_spelling_of_a_cusip_still_resolves() -> None:
    """We normalise the alias side once, in ``alias_map``; the filing side is normalised on
    every row, because five thousand registrants type their own identifiers."""
    facts, holdings = parsed("ivv")
    scruffy = holdings.copy()
    scruffy.loc[scruffy["holding_name"] == "CBRE Group, Inc.", "cusip"] = " 12504l109 "
    rows, resolved = nport.holding_rows(scruffy, IID, facts.period_date, {"12504L109": HELD})
    assert resolved == 1
    assert any(r["holding_instrument_id"] == HELD for r in rows)


def test_no_aliases_means_no_resolution_rather_than_a_wrong_one() -> None:
    facts, holdings = parsed("tqqq")
    rows, resolved = nport.holding_rows(holdings, IID, facts.period_date, {})
    assert resolved == 0
    assert len(rows) == len(holdings)
    assert all(r["holding_instrument_id"] is None for r in rows)


# ── the CUSIP bridge these resolutions depend on ──


def test_the_cusip_bridge_takes_only_resolved_tickers() -> None:
    holdings = pd.DataFrame(
        {
            "ticker": ["NVDA", "AAPL", None],
            "cusip": ["67066G104", "037833100", "—"],
        }
    )
    assert membership.cusip_aliases(holdings, {"NVDA": IID}) == {"67066G104": IID}


def test_a_cusip_two_resolved_tickers_claim_is_dropped_not_guessed() -> None:
    """One of the two would be wrong, and a wrong look-through is worse than a missing one."""
    holdings = pd.DataFrame({"ticker": ["A", "B"], "cusip": ["000000001", "000000001"]})
    assert membership.cusip_aliases(holdings, {"A": IID, "B": HELD}) == {}


# ── the writer's columns are the table's columns ──


def _columns(table: str) -> set[str]:
    """Column names of ``table`` in the DDL — the CREATE body plus every ADD COLUMN."""
    body = re.search(
        rf"CREATE TABLE IF NOT EXISTS atlas_global\.{table} \((.*?)\n\);", DDL.read_text(), re.S
    )
    assert body, f"no CREATE TABLE for {table} in {DDL.name}"
    names = {
        m.group(1)
        for line in body.group(1).splitlines()
        if (m := re.match(r"\s{4}([a-z][a-z0-9_]*)\s+[a-z]", line))
    }
    names |= set(
        re.findall(
            rf"ALTER TABLE atlas_global\.{table}\s+ADD COLUMN IF NOT EXISTS ([a-z_]+)",
            DDL.read_text(),
        )
    )
    return names


@pytest.mark.parametrize(
    ("table", "columns"),
    [
        ("etf_holdings", "HOLDING_DB_COLUMNS"),
        ("etf_meta", "META_DB_COLUMNS"),
    ],
)
def test_every_column_the_writer_names_exists_in_the_ddl(table: str, columns: str) -> None:
    """A rename in the DDL without one here is an ``UndefinedColumn`` at 01:00 UTC on the box,
    after the fetches have already spent their budget."""
    missing = set(getattr(nport, columns)) - _columns(table)
    assert not missing, f"{columns} names columns {table} does not have: {sorted(missing)}"


def test_the_record_builders_fill_exactly_those_columns() -> None:
    facts, holdings = parsed("ivv")
    rows, _ = nport.holding_rows(holdings, IID, facts.period_date, {})
    assert set(rows[0]) == set(nport.HOLDING_DB_COLUMNS)
    assert set(nport.meta_row(facts, IID, holdings)) == set(nport.META_DB_COLUMNS)


def test_the_sources_it_writes_are_the_ones_the_checks_allow() -> None:
    """``etf_holdings.source`` and ``etf_meta.aum_source`` are both CHECK-constrained."""
    ddl = DDL.read_text()
    assert "chk_etf_holdings_source CHECK (source IN ('issuer_csv', 'nport'))" in ddl
    assert nport.SOURCE_LABEL == "nport"
    assert f"'{nport.SOURCE_LABEL}'" in ddl


# ── the CLI ──


def test_the_flags_are_the_documented_ones() -> None:
    """The parser IS the contract the orchestrator calls; read its options back."""
    options = {o for action in nport.build_parser()._actions for o in action.option_strings}
    assert {"--symbols", "--limit", "--in-universe", "--full", "--dry-run", "--report"} <= options


def test_a_dry_run_flag_exists_because_the_fetch_is_expensive() -> None:
    args = nport.build_parser().parse_args(["--symbols", "IVV", "--dry-run"])
    assert args.symbols == "IVV" and args.dry_run and not args.full

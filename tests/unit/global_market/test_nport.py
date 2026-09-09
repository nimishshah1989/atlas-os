"""Form N-PORT-P parsing, on four real filings and nothing else.

Every assertion below names a value some registrant actually filed
(``tests/fixtures/global/nport/SOURCE.md`` carries the accession and the hash of each
download). There is no constructed XML here and no ``Mock()``: three of the four traps this
parser exists for — the percent, the multi-class series, the "N/A" — were found by reading
real payloads, and a fabricated fixture would have agreed with whatever the parser did.

The numbers are dated. Re-fetching moves these funds to a LATER period; the assertions that
name one move with it, which is why SOURCE.md records what each file was when it was fetched.
"""

from __future__ import annotations

import gzip
import hashlib
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from atlas.global_market.providers.nport import (
    FORM,
    parse_filings_index,
    parse_nport,
    primary_doc_url_of,
)

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "nport"

# The uncompressed sha256 of each fixture, as SOURCE.md records it.
SERVED = {
    "ivv": "9924e5b86bf304d0c2d24679e15642b681de6605ed38ca8b1bb1db7aa5b3b7e9",
    "tqqq": "36ebaf3960bff364864f4efddaf9de06504a9d362eaef53155227ba2e11d121a",
    "voo": "e5b36312ae54cd8e4d614b24a54310e0d1c7a948bc849ab3cb95fb239d8cca0f",
    "ewj": "77474976fd55df002052ebd4774a443077f3e777043438d2322d37f25027db6b",
}


def payload(slug: str) -> bytes:
    return gzip.decompress((FIXTURES / f"{slug}_primary_doc.xml.gz").read_bytes())


def parsed(slug: str):
    return parse_nport(payload(slug))


def sum_abs(frame) -> Decimal:
    return sum((abs(w) for w in frame["weight_frac"] if w is not None), Decimal(0))


# ── the fixtures are the filings ──


@pytest.mark.unit
@pytest.mark.parametrize("slug", sorted(SERVED))
def test_the_fixtures_are_the_filings_as_served(slug: str) -> None:
    """Gzip is packaging, not editing: the payload must hash to what SEC served."""
    assert hashlib.sha256(payload(slug)).hexdigest() == SERVED[slug]


# ── the percent ──


@pytest.mark.unit
def test_pct_val_is_a_percent_so_weight_frac_is_a_hundredth_of_it() -> None:
    """IVV's CBRE line: ``pctVal`` 0.061079735228, ``valUSD/netAssets`` 0.00061079….

    The whole unit question in one row. A parser that took ``pctVal`` for a fraction would
    put every S&P 500 constituent at a hundred times its weight and the fund at 100× NAV.
    """
    facts, holdings = parsed("ivv")
    cbre = holdings.loc[holdings["holding_name"] == "CBRE Group, Inc."].iloc[0]
    assert facts.net_assets is not None
    implied = cbre["market_value_usd"] / facts.net_assets
    assert abs(cbre["weight_frac"] - implied) < Decimal("1e-9")
    assert cbre["weight_frac"] < Decimal("0.001")  # 0.061% of the fund, not 6.1%


@pytest.mark.unit
@pytest.mark.parametrize(("slug", "count"), [("ivv", 508), ("voo", 520), ("ewj", 182)])
def test_an_index_funds_weights_sum_to_about_one(slug: str, count: int) -> None:
    """The plan's Σ|weight_frac| ∈ [0.9, 1.1] gate, on the funds it is written for."""
    _, holdings = parsed(slug)
    assert len(holdings) == count
    assert Decimal("0.9") <= sum_abs(holdings) <= Decimal("1.1")


# ── leverage ──


@pytest.mark.unit
def test_leverage_is_invisible_in_the_weights_and_visible_in_the_notional() -> None:
    """TQQQ is a three-times fund whose weights sum to 1.0126 — barely above IVV's 1.0012.

    A swap is marked at its unrealised value, not its notional, so nothing in the weights
    separates a geared fund from a plain one. ``derivative_notional_share`` does: 2.70
    against 0.0016.
    """
    tqqq_facts, tqqq = parsed("tqqq")
    ivv_facts, ivv = parsed("ivv")

    assert Decimal("0.9") <= sum_abs(tqqq) <= Decimal("1.1")
    assert abs(sum_abs(tqqq) - sum_abs(ivv)) < Decimal("0.02")  # the weights cannot tell them apart

    assert tqqq_facts.derivative_notional_share is not None
    assert tqqq_facts.derivative_notional_share > Decimal(2)
    assert ivv_facts.derivative_notional_share is not None
    assert ivv_facts.derivative_notional_share < Decimal("0.01")


@pytest.mark.unit
def test_every_derivative_line_is_marked_as_one() -> None:
    """TQQQ's ten swaps and one future carry a ``derivative_category``; its equities do not.

    Look-through reads this column: a swap's mark is not an equity position.
    """
    _, tqqq = parsed("tqqq")
    kinds = tqqq["derivative_category"].value_counts(dropna=True).to_dict()
    assert kinds == {"SWP": 10, "FUT": 1}
    assert tqqq.loc[tqqq["derivative_category"].notna(), "notional_usd"].notna().all()
    assert tqqq.loc[tqqq["asset_category"] == "EC", "derivative_category"].isna().all()


# ── the series is not the share class ──


@pytest.mark.unit
def test_a_multi_class_series_says_how_many_classes_share_its_assets() -> None:
    """VOO is one of FOUR classes of the Vanguard 500 Index Fund; IVV is its series alone.

    The filed ``netAssets`` is the series', and N-PORT carries no class-level assets — which
    is why ``ingest_nport.meta_row`` refuses to call the first figure an ETF's AUM.
    """
    voo, _ = parsed("voo")
    ivv, _ = parsed("ivv")
    assert voo.class_count == 4
    assert voo.series_name == "VANGUARD 500 INDEX FUND"
    assert voo.net_assets is not None and voo.net_assets > Decimal("1e12")
    assert ivv.class_count == 1
    assert ivv.series_id == "S000004310"


@pytest.mark.unit
def test_the_period_is_the_filers_fiscal_quarter_not_the_calendars() -> None:
    """ProShares reports 31 May and iShares 30 June, and neither date is ``repPdEnd``.

    ``repPdEnd`` is the filer's fiscal YEAR end — 2027-03-31 for a filing whose holdings are
    as of 2026-06-30 — so anything that read it as the snapshot date would be nine months out.
    """
    ivv, _ = parsed("ivv")
    tqqq, _ = parsed("tqqq")
    assert ivv.period_date == date(2026, 6, 30)
    assert ivv.fiscal_year_end == date(2027, 3, 31)
    assert tqqq.period_date == date(2026, 5, 31)
    assert not ivv.is_final_filing


# ── "N/A" is a value the filers write ──


@pytest.mark.unit
def test_na_is_not_a_country() -> None:
    """VOO files ``invCountry`` as the literal ``N/A`` on its twelve futures lines.

    ``country_iso2`` is ``char(2)``: unhandled, that string is stored as ``N/``.
    """
    _, voo = parsed("voo")
    missing = voo["country_iso2"].isna()
    assert missing.sum() == 12
    assert voo.loc[missing, "derivative_category"].notna().all()
    assert not (voo["country_iso2"].dropna() == "N/").any()
    assert set(voo["country_iso2"].dropna()) == {"US"}


@pytest.mark.unit
def test_a_japanese_fund_is_identified_by_isin_because_it_has_no_cusip() -> None:
    """176 of EWJ's 182 lines file no CUSIP, and two file the ISIN itself as ``N/A``.

    ISIN is therefore not a nicety: without it those holdings have no identity at all.
    """
    _, ewj = parsed("ewj")
    assert ewj["cusip"].isna().sum() == 176
    assert ewj["isin"].isna().sum() == 2
    assert bool(ewj["holding_key"].notna().all())
    assert ewj["holding_key"].is_unique


@pytest.mark.unit
def test_a_foreign_line_keeps_its_currency_and_still_values_in_dollars() -> None:
    """180 of EWJ's rows carry ``currencyConditional curCd="JPY"`` in place of ``curCd``;
    ``valUSD`` is US dollars either way."""
    _, ewj = parsed("ewj")
    assert ewj["currency"].value_counts().to_dict() == {"JPY": 180, "USD": 2}
    assert bool(ewj["market_value_usd"].notna().all())


# ── the categories that live in an attribute ──


@pytest.mark.unit
def test_the_other_categories_are_not_lost_to_an_attribute() -> None:
    """A category outside the enum has no element — it is an attribute on a *Conditional*.

    IVV holds a Hologic CVR (``assetConditional assetCat="OTHER" desc="Right"``) and an
    E-Mini future whose issuer is ``issuerConditional issuerCat="OTHER" desc="Future"``.
    Reading only the elements loses both.
    """
    _, ivv = parsed("ivv")
    assert (ivv["asset_category"] == "OTHER/Right").sum() == 1
    assert (ivv["issuer_category"] == "OTHER/Future").sum() == 1
    assert ivv["asset_category"].isna().sum() == 0
    _, tqqq = parsed("tqqq")
    assert (tqqq["asset_category"] == "OTHER/Exchange traded fund").sum() == 1


# ── the key ──


@pytest.mark.unit
@pytest.mark.parametrize("slug", sorted(SERVED))
def test_holding_keys_are_unique_within_a_snapshot(slug: str) -> None:
    """``etf_holdings`` is keyed ``(instrument_id, as_of_date, holding_key)``: a repeat would
    make one line of the filing overwrite another."""
    _, holdings = parsed(slug)
    assert holdings["holding_key"].is_unique


@pytest.mark.unit
def test_one_cusip_on_two_lines_keeps_both() -> None:
    """IVV holds CUSIP 066922519 twice. Neither line may be dropped, and neither may win."""
    _, ivv = parsed("ivv")
    repeated = ivv.loc[ivv["cusip"] == "066922519"]
    assert len(repeated) == 2
    assert sorted(repeated["holding_key"]) == ["066922519", "066922519#2"]


@pytest.mark.unit
def test_a_ticker_labelled_future_ticker_is_not_a_ticker() -> None:
    """IVV files its E-Mini's code under ``otherDesc="Future Ticker"``; that is not a symbol.

    Vanguard and iShares DO put futures under the real ``ticker`` element (``ESU6``), which is
    why the writer resolves holdings by CUSIP and ISIN and never by this column.
    """
    _, ivv = parsed("ivv")
    assert bool(ivv["holding_ticker"].isna().all())
    _, voo = parsed("voo")
    tickers = voo.loc[voo["holding_ticker"].notna()]
    assert set(tickers["holding_ticker"]) == {"ESU6"}
    assert tickers["derivative_category"].notna().all()


# ── refusals ──


@pytest.mark.unit
def test_a_document_that_is_not_an_nport_is_refused() -> None:
    other = b'<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/nport">'
    other += b"<headerData><submissionType>NPORT-EX</submissionType></headerData></edgarSubmission>"
    with pytest.raises(ValueError, match="not an NPORT-P filing"):
        parse_nport(other)


@pytest.mark.unit
def test_a_filing_without_a_period_is_refused() -> None:
    """Holdings with no date are not a snapshot: ``as_of_date`` is part of their key."""
    stripped = re.sub(rb"<repPdDate>[^<]*</repPdDate>", b"", payload("tqqq"))
    with pytest.raises(ValueError, match="no repPdDate"):
        parse_nport(stripped)


# ── the filing index ──


@pytest.mark.unit
def test_the_filing_index_is_newest_first_and_keeps_the_amendment() -> None:
    """The real atom for series S000004310: ten filings, one of them an NPORT-P/A.

    Sorted newest-filed first, because the writer takes ``refs[0]``. An amendment restates its
    own period, so it must not be filtered out — and it must not jump the queue either.
    """
    refs = parse_filings_index((FIXTURES / "ivv_filing_index.atom").read_bytes(), "S000004310")
    assert len(refs) == 10
    assert [r.filed for r in refs] == sorted((r.filed for r in refs), reverse=True)
    assert refs[0].accession == "0002071691-26-019760"
    assert refs[0].filed == date(2026, 8, 25)
    assert not refs[0].is_amendment
    assert sum(r.is_amendment for r in refs) == 1
    assert {r.cik for r in refs} == {"0001100663"}
    assert all(r.form.startswith(FORM) for r in refs)


@pytest.mark.unit
def test_the_archive_path_drops_the_ciks_padding_and_the_accessions_dashes() -> None:
    """EDGAR prints ``0001100663`` and ``0002071691-26-019760``; the Archives path wants
    ``1100663`` and ``000207169126019760``. Getting either wrong is a 404 for every fund."""
    refs = parse_filings_index((FIXTURES / "ivv_filing_index.atom").read_bytes(), "S000004310")
    assert refs[0].primary_doc_url == (
        "https://www.sec.gov/Archives/edgar/data/1100663/000207169126019760/primary_doc.xml"
    )
    assert primary_doc_url_of("0000036405", "0000036405-26-000473").endswith(
        "/data/36405/000003640526000473/primary_doc.xml"
    )


@pytest.mark.unit
def test_a_series_with_no_filings_is_an_empty_list_not_a_failure() -> None:
    """A young fund, or a unit investment trust — SPY files no N-PORT at all."""
    empty = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
    empty += b"<company-info><cik>0000884394</cik></company-info></feed>"
    assert parse_filings_index(empty, "S000000000") == []

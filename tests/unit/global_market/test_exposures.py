"""L1 exposures, on the four real N-PORT filings.

Every number below is what a registrant filed (``tests/fixtures/global/nport/SOURCE.md``).
The three things this module can get wrong, and does not:

* renormalising a vector, so a fund 97 per cent in one country reads 100 per cent in it;
* folding an asset code it has never seen into ``equity``, which moves weight between asset
  classes invisibly;
* claiming a sector or a look-through it does not have.

And one thing the filings themselves disagree about, which is why the country test is here.
"""

from __future__ import annotations

import gzip
from decimal import Decimal
from functools import cache
from pathlib import Path

import pandas as pd
import pytest

from atlas.global_market.classify.exposures import (
    ASSET_CLASS,
    CASH,
    DERIVATIVE,
    EQUITY,
    FIXED_INCOME,
    TOP_N,
    exposures,
)
from atlas.global_market.providers.nport import parse_nport

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "nport"


@cache
def holdings(slug: str) -> pd.DataFrame:
    payload = gzip.decompress((FIXTURES / f"{slug}_primary_doc.xml.gz").read_bytes())
    return parse_nport(payload)[1]


@cache
def exposure(slug: str):
    return exposures(holdings(slug))


# ── the weights are shares of the whole fund ──


@pytest.mark.parametrize("slug", ["ivv", "tqqq", "voo", "ewj"])
def test_no_vector_claims_more_than_the_fund(slug: str) -> None:
    """Nothing is renormalised, so every vector sums to at most the fund's total weight."""
    e = exposure(slug)
    for vector in (e.country_vec, e.asset_vec, e.sector_vec):
        assert sum(vector.values(), Decimal(0)) <= e.sum_abs_weight + Decimal("1e-9")
    assert e.top10_w is not None and e.top10_w <= e.sum_abs_weight
    assert e.n_holdings == len(holdings(slug))


def test_cash_is_not_the_country_the_rest_of_the_fund_is_in() -> None:
    """EWJ is 0.9936 Japan and 0.9946 in total, and the difference is a US money-market line.

    Renormalising would read 1.0000 Japan and make a country-purity threshold meaningless.
    """
    e = exposure("ewj")
    assert e.top_country == "JP"
    assert e.top_country_w is not None
    assert Decimal("0.99") < e.top_country_w < e.sum_abs_weight
    assert e.country_vec["US"] > 0


# ── the asset map ──


def test_a_code_the_map_has_never_seen_keeps_its_own_name() -> None:
    """TQQQ holds 0.1835 of itself in another fund, filed as ``OTHER/Exchange traded fund``.

    That weight is NOT equity and must not be folded into it. It appears under its own code and
    is counted in ``unmapped_w`` so a gate can see how much of the universe the map misses.
    """
    e = exposure("tqqq")
    assert "OTHER/Exchange traded fund" in e.asset_vec
    assert e.unmapped_w == e.asset_vec["OTHER/Exchange traded fund"]
    assert e.equity_w is not None
    assert e.asset_vec[EQUITY] == e.equity_w < e.unmapped_w + e.asset_vec[EQUITY]


def test_a_geared_fund_holds_more_derivative_than_equity() -> None:
    """The exposure view of what the weights alone could not show: TQQQ's derivative bucket
    (0.3704) is larger than its equity one (0.3035)."""
    e = exposure("tqqq")
    assert e.asset_vec[DERIVATIVE] > e.asset_vec[EQUITY]
    assert e.asset_vec[CASH] > 0


@pytest.mark.parametrize("slug", ["ivv", "voo", "ewj"])
def test_a_plain_index_fund_is_almost_all_equity(slug: str) -> None:
    e = exposure(slug)
    assert e.equity_w is not None
    assert e.equity_w > Decimal("0.98")
    assert e.unmapped_w < Decimal("0.01")


def test_the_map_only_carries_codes_a_filing_showed() -> None:
    """Guessing a code moves weight between asset classes invisibly. The map's keys are the
    ones the module docstring names a fund for; the buckets are the classification
    vocabulary's plus the two it has no word for."""
    assert set(ASSET_CLASS) == {"EC", "DBT", "ABS-MBS", "ABS-O", "STIV", "RA", "DE"}
    assert set(ASSET_CLASS.values()) == {EQUITY, FIXED_INCOME, CASH, DERIVATIVE}


# ── concentration ──


def test_top_ten_and_herfindahl_separate_a_broad_fund_from_a_narrow_one() -> None:
    """IVV's ten largest are 0.3636 of it against TQQQ's 0.5196, and the Herfindahl says the
    same thing over the whole book."""
    broad, narrow = exposure("ivv"), exposure("tqqq")
    assert broad.top10_w is not None and narrow.top10_w is not None
    assert broad.top10_w < narrow.top10_w
    assert broad.hhi is not None and narrow.hhi is not None
    assert broad.hhi < narrow.hhi


def test_the_top_ten_really_is_the_ten_largest() -> None:
    weights = sorted(
        (abs(w) for w in holdings("ivv")["weight_frac"] if w is not None), reverse=True
    )
    assert exposure("ivv").top10_w == sum(weights[:TOP_N], Decimal(0))


# ── the look-through, and what it honestly cannot reach ──


def test_an_unresolved_snapshot_has_no_look_through_and_says_so() -> None:
    """The parser's frame carries no ``holding_instrument_id`` — resolution happens in the
    ingest. That is a real input, not an error: no sector vector and a zero scored weight."""
    e = exposure("ivv")
    assert e.lookthrough_scored_w == Decimal(0)
    assert e.sector_vec == {}


def test_a_resolved_holding_carries_its_own_sector_and_nothing_else_does() -> None:
    """Sector is the HOLDING's, read through ``holding_instrument_id``. A fund whose holdings
    do not resolve has no sector vector — which is what an international fund has, and is not
    a reason to guess one from the fund's name."""
    frame = holdings("ivv").copy()
    frame["holding_instrument_id"] = [
        "iid-a" if i == 0 else ("iid-b" if i == 1 else None) for i in range(len(frame))
    ]
    e = exposures(frame, {"iid-a": "information_technology"})
    first = abs(frame["weight_frac"].iloc[0])
    second = abs(frame["weight_frac"].iloc[1])
    assert e.sector_vec == {"information_technology": first}
    assert e.lookthrough_scored_w == first + second  # resolved, but with no sector of its own


def test_an_empty_snapshot_is_zeroes_rather_than_a_crash() -> None:
    e = exposures(holdings("ivv").iloc[0:0])
    assert e.n_holdings == 0
    assert e.sum_abs_weight == Decimal(0)
    assert e.country_vec == {} and e.asset_vec == {}
    assert e.top_country is None and e.top10_w is None


# ── the filers do not agree about domicile ──


def test_two_funds_on_the_same_index_report_different_country_purity() -> None:
    """IVV and VOO both hold the S&P 500, and their country vectors do not match: iShares
    files a holding's ``invCountry`` as the ISSUER's domicile (Accenture Ireland, Everest
    Bermuda, 0.9717 US) while Vanguard files US for every line (1.0010).

    A country-purity threshold set at 0.98 would call one of these two US-pure and not the
    other, for the same index. Whatever the FM sets it to, it is a decision about filer
    convention as much as about funds — so it is recorded here rather than discovered later.
    """
    ishares, vanguard = exposure("ivv"), exposure("voo")
    assert ishares.top_country == vanguard.top_country == "US"
    assert ishares.top_country_w is not None and vanguard.top_country_w is not None
    assert ishares.top_country_w < Decimal("0.98") < vanguard.top_country_w
    assert len(ishares.country_vec) > 5  # IE, BM, CH, NL, JE …
    assert len(vanguard.country_vec) == 1

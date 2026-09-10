"""The name → country mapping, and that it stays in step with the classifier it reads.

Pure: no DB, no network. The fund names below are REAL US-listed products (rule #0 — these
are the actual titles the issuers publish, not invented strings).
"""

from __future__ import annotations

import re

import pytest

from atlas.global_market.classify import strategy as st
from atlas.global_market.classify.countries import (
    COUNTRIES,
    REGIONS,
    UNITED_STATES,
    Country,
    country_of,
    is_currency_hedged,
)


@pytest.fixture
def us() -> Country:
    """The one country the classifier reaches through `broad_market` rather than by name."""
    return UNITED_STATES


pytestmark = pytest.mark.unit


def test_a_single_country_fund_resolves_to_its_code() -> None:
    assert country_of("iShares MSCI Japan ETF") == Country("JP", "Japan", "asia_pacific")
    assert country_of("Franklin FTSE India ETF") == Country("IN", "India", "asia_pacific")
    assert country_of("iShares MSCI Brazil ETF") == Country("BR", "Brazil", "latam")
    assert country_of("iShares MSCI Germany ETF") == Country("DE", "Germany", "europe")


def test_an_ex_country_fund_is_not_a_bet_on_the_country_it_excludes() -> None:
    """The trap the whole rule exists for. "Asia ex Japan" is a bet AGAINST Japan's inclusion,
    and reading it as a Japan fund produces a wrong answer that looks perfectly right on a
    card. `strategy.py` carries the lookbehinds; this asserts they survive the mapping."""
    assert country_of("iShares MSCI All Country Asia ex Japan ETF") is None
    assert country_of("iShares MSCI Emerging Markets ex China ETF") is None


def test_a_region_or_broad_fund_names_no_country() -> None:
    assert country_of("Vanguard FTSE Emerging Markets ETF") is None
    assert country_of("Vanguard FTSE Developed Markets ETF") is None
    assert country_of("iShares Core MSCI EAFE ETF") is None


def test_a_us_broad_market_fund_is_the_united_states(us: Country) -> None:
    """The US IS a country row (FM, 2026-09-10), and it reaches one without naming itself.

    This test used to assert the opposite, and the reason it did is worth keeping: matching
    "U.S." at face value in strategy.py's COUNTRY pattern would file the entire American core
    of the universe as a country bet and leave `broad_market` empty, scrambling every peer
    group. That is still true, and strategy.py is still untouched — the grid reads the
    `broad_market` VERDICT instead, which the rule ordering makes US-only for free.
    """
    for name in (
        "State Street SPDR S&P 500 ETF Trust",  # SPY — the representative, on liquidity
        "Vanguard Morningstar Total Stock Market ETF",  # VTI
        "iShares Core S&P 500 ETF",  # IVV
        "iShares Core S&P Total U.S. Stock Market ETF",  # ITOT
        "State Street SPDR Dow Jones Industrial Average ETF Trust",  # DIA
    ):
        assert country_of(name) == us, name


def test_the_united_states_sits_in_north_america_beside_canada(us: Country) -> None:
    assert us.iso2 == "US"
    assert us.region == "north_america" == COUNTRIES["canada"].region


def test_a_foreign_fund_is_still_its_own_country_not_the_us(us: Country) -> None:
    """The guard on the branch above: `broad_market` is the FALLBACK, so a fund naming a
    country or a region must be claimed before it — otherwise every foreign fund on the board
    would quietly become American."""
    japan = country_of("iShares MSCI Japan Index Fund")
    assert japan is not None and japan.iso2 == "JP"
    assert country_of("iShares MSCI India ETF") != us
    assert country_of("Vanguard FTSE Emerging Markets ETF") is None


def test_every_country_the_classifier_can_match_has_a_code() -> None:
    """The round trip that stops a silent gap. A country added to strategy.py's regex without
    a row here would classify as `country` and then map to nothing — the fund would vanish
    from the grid with no error anywhere."""
    pattern = next(p for p, s, _ in st.RULES if s == "country")
    tokens = set(re.findall(r"[a-z ]+", pattern.pattern.split("(?:", 1)[1].split(")", 1)[0]))
    missing = sorted(t for t in tokens if t and t not in COUNTRIES)
    assert not missing, f"{missing} can be matched as a country but has no ISO code"


def test_every_code_is_two_upper_letters_and_every_region_is_known() -> None:
    for token, country in COUNTRIES.items():
        assert re.fullmatch(r"[A-Z]{2}", country.iso2), f"{token}: {country.iso2!r}"
        assert country.region in REGIONS, f"{token}: {country.region!r}"
        assert country.name.strip() == country.name and country.name


def test_the_two_codes_that_share_a_country_agree() -> None:
    """ "south korea" and "korea" are two spellings of one market; disagreeing would put the
    same funds under two rows of the grid."""
    assert COUNTRIES["korea"] == COUNTRIES["south korea"]


def test_a_hedged_share_class_is_recognised_from_its_name() -> None:
    """The grid wants THE Japan ETF. A currency-hedged one answers a different question with
    the same label, so it is excluded from being a representative — and only the name says so."""
    assert is_currency_hedged("iShares Currency Hedged MSCI Japan ETF")
    assert is_currency_hedged("WisdomTree Japan Hedged Equity Fund")
    assert not is_currency_hedged("iShares MSCI Japan ETF")

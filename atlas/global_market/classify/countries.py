"""Which country a fund's NAME says it is a bet on, and the ISO-3166 code for it.

    >>> country_of("iShares MSCI Japan ETF")
    Country(iso2='JP', name='Japan', region='asia_pacific')
    >>> country_of("iShares MSCI All Country Asia ex Japan ETF") is None
    True

WHY A NAME AND NOT HOLDINGS. The 2026-09-04 plan built the country view on look-through:
ingest every fund's holdings, sum weights by ``investment_country``, and call a fund
single-country when one country clears a threshold. ``seed_taxonomy.py`` says as much and
leaves ``atlas_global.country`` empty on the strength of it — "no fund can be proven
single-country without holdings anyway".

The FM reversed that on 2026-09-08, and the reversal is right for the product actually
wanted: **one ETF per country, so a client can take country exposure.** For that question a
holdings pipeline — N-PORT parsing, issuer CSVs, exposure vectors, a 60-day filing lag — is
enormous machinery to establish something the fund's own name states outright. "iShares MSCI
Japan ETF" is a Japan bet. The issuer says so in the title, under a regulator that does not
let them lie about it.

WHAT THIS GIVES UP, SAID PLAINLY. A name cannot tell you a fund holds 94 percent Japanese
equity rather than 71 percent; it cannot catch a fund whose mandate drifted from its title;
and it cannot compute ``country_pure``, which the basket rule in the plan is defined on. So
this is the membership rule for the country VIEW, and the day baskets need a proven
concentration, holdings come back — for that question, not this one.

The mitigation is not more data, it is arithmetic: there are about fifty countries here, so
the whole answer is fifty rows a human reads once. A wrong representative is visible in a
glance and fixable in a line, which is not true of a 5,000-fund exposure matrix.

THE MATCHING ITSELF is not repeated here. ``strategy.classify_strategy`` already owns it,
already ran against 5,655 real fund names, and already carries the one trap that matters:
``(?<!ex )(?<!ex-)`` stops "MSCI All Country Asia ex Japan" being filed as a Japan bet — a
wrong answer that reads perfectly plausibly on a card. This module maps that verdict onto a
code and a region; a second regex would be a second answer to drift from the first.

REGION is a display grouping for the country grid, not a licensed index classification.
``country.msci_class`` (developed | emerging | frontier) stays NULL: that IS MSCI's
proprietary determination and we do not hold a licence to restate it.
"""

from __future__ import annotations

from typing import NamedTuple

from atlas.global_market.classify.strategy import classify_strategy


class Country(NamedTuple):
    iso2: str
    name: str
    region: str


# Keyed by the exact lowercase token `strategy.py`'s country regex can match, so a country
# added to that pattern without a code here fails the round-trip test rather than silently
# classifying to nothing. ISO-3166-1 alpha-2 is a published standard, not a measurement.
#
# Region follows the common investment grouping and is deliberately coarse. Two are
# arguable and are called out so nobody mistakes them for settled: Mexico sits in `latam`
# (MSCI's Latin America, not its NAFTA geography), and Turkey in `mea` (the EMEA convention)
# rather than `europe`. Both are one-line changes if the FM reads them differently.
COUNTRIES: dict[str, Country] = {
    "japan": Country("JP", "Japan", "asia_pacific"),
    "china": Country("CN", "China", "asia_pacific"),
    "india": Country("IN", "India", "asia_pacific"),
    "hong kong": Country("HK", "Hong Kong", "asia_pacific"),
    "taiwan": Country("TW", "Taiwan", "asia_pacific"),
    "south korea": Country("KR", "South Korea", "asia_pacific"),
    "korea": Country("KR", "South Korea", "asia_pacific"),
    "singapore": Country("SG", "Singapore", "asia_pacific"),
    "indonesia": Country("ID", "Indonesia", "asia_pacific"),
    "vietnam": Country("VN", "Vietnam", "asia_pacific"),
    "thailand": Country("TH", "Thailand", "asia_pacific"),
    "malaysia": Country("MY", "Malaysia", "asia_pacific"),
    "philippines": Country("PH", "Philippines", "asia_pacific"),
    "pakistan": Country("PK", "Pakistan", "asia_pacific"),
    "bangladesh": Country("BD", "Bangladesh", "asia_pacific"),
    "australia": Country("AU", "Australia", "asia_pacific"),
    "new zealand": Country("NZ", "New Zealand", "asia_pacific"),
    "canada": Country("CA", "Canada", "north_america"),
    "mexico": Country("MX", "Mexico", "latam"),
    "brazil": Country("BR", "Brazil", "latam"),
    "chile": Country("CL", "Chile", "latam"),
    "colombia": Country("CO", "Colombia", "latam"),
    "peru": Country("PE", "Peru", "latam"),
    "argentina": Country("AR", "Argentina", "latam"),
    "united kingdom": Country("GB", "United Kingdom", "europe"),
    "germany": Country("DE", "Germany", "europe"),
    "france": Country("FR", "France", "europe"),
    "switzerland": Country("CH", "Switzerland", "europe"),
    "spain": Country("ES", "Spain", "europe"),
    "italy": Country("IT", "Italy", "europe"),
    "netherlands": Country("NL", "Netherlands", "europe"),
    "sweden": Country("SE", "Sweden", "europe"),
    "norway": Country("NO", "Norway", "europe"),
    "denmark": Country("DK", "Denmark", "europe"),
    "finland": Country("FI", "Finland", "europe"),
    "belgium": Country("BE", "Belgium", "europe"),
    "austria": Country("AT", "Austria", "europe"),
    "ireland": Country("IE", "Ireland", "europe"),
    "portugal": Country("PT", "Portugal", "europe"),
    "greece": Country("GR", "Greece", "europe"),
    "poland": Country("PL", "Poland", "europe"),
    "turkey": Country("TR", "Turkey", "mea"),
    "israel": Country("IL", "Israel", "mea"),
    "saudi": Country("SA", "Saudi Arabia", "mea"),
    "qatar": Country("QA", "Qatar", "mea"),
    "kuwait": Country("KW", "Kuwait", "mea"),
    "uae": Country("AE", "United Arab Emirates", "mea"),
    "egypt": Country("EG", "Egypt", "mea"),
    "nigeria": Country("NG", "Nigeria", "mea"),
    "south africa": Country("ZA", "South Africa", "mea"),
}

REGIONS: tuple[str, ...] = ("north_america", "europe", "asia_pacific", "latam", "mea")

# The country grid is one row per country, so a fund that hedges its currency, gears its
# exposure or bets against the market is not the thing a reader means by "the Japan ETF" —
# it answers a different question with the same label. Leverage and inverse come from
# `rules.leverage_flags`; the hedge is stated in the name and only there.
HEDGED_WORDS: tuple[str, ...] = ("hedged", "currency-hedged", "currency hedged")


def is_currency_hedged(name: str) -> bool:
    """True when the fund's own name says it hedges the currency back to USD."""
    lowered = name.lower()
    return any(word in lowered for word in HEDGED_WORDS)


# THE UNITED STATES IS THE ONE COUNTRY WHOSE FUNDS NEVER SAY ITS NAME (FM, 2026-09-10).
#
# The grid had 44 countries and no US row, and the reason is a nice piece of survivorship: every
# foreign fund states its country in the title, because it is FOREIGN EXPOSURE SOLD TO AMERICANS
# — "iShares MSCI Japan", "FTSE China", "MSCI India". The home market is the only one that never
# names itself. SPY is "SPDR S&P 500 ETF Trust"; VTI is "Vanguard Total Stock Market ETF".
# Neither says America, so a name-reading rule finds no country in them.
#
# `strategy.py` excluded the US from its `country` pattern deliberately, and that exclusion is
# still right: matching "U.S." at face value would file the entire American core of the universe
# as a country bet and leave `broad_market` holding nothing, which would scramble every peer
# group and therefore every ranking. So this does NOT touch the strategy verdict.
#
# What it uses instead is that verdict, already computed. `country` and `region` are ordered
# ABOVE `broad_market`, so anything naming a geography is claimed before the fallback is reached
# — which makes `broad_market` the US home-market bucket by construction rather than by
# assertion. Measured on the 5,655 real fund names in the directory snapshot: 74 funds classify
# `broad_market` and NOT ONE carries a foreign geography word. SPY, VOO, IVV, VTI, IWM, ITOT,
# DIA and the Russell trackers are all in it.
#
# The country view then treats the US exactly like Japan: `representative()` takes the
# most-traded unlevered, unhedged member, which is SPY — the same rule, no special case.
UNITED_STATES = Country("US", "United States", "north_america")


def country_of(name: str) -> Country | None:
    """The country this fund's name is a bet on, or ``None`` when it names none.

    ``None`` is the answer for a region fund ("Emerging Markets"), a fund that EXCLUDES a
    country ("Asia ex Japan"), and anything the pattern does not know.
    """
    match = classify_strategy(name)
    if match.strategy == "broad_market":
        return UNITED_STATES
    if match.strategy != "country" or not match.evidence:
        return None
    return COUNTRIES.get(match.evidence.strip().lower())

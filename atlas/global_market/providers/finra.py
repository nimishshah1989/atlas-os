"""FINRA consolidated short interest → the positioning against a stock. Pure: no I/O, no vendor.

WHAT THIS FEED IS. Every FINRA member reports its customers' and its own short positions twice a
month, and FINRA publishes the consolidated figure about eight business days after each settlement
date. It is free, it needs no key, and it covers every listed name — 208 settlement dates for
Apple reaching back to 2017-12-29 on the payload committed under ``tests/fixtures/global/finra/``.

WHY THE FLOW LENS IS BUILT ON THIS AND NOT ON FORM 4. plan.md §B orders the flow lens "Form 4
first, add 13F and short interest after IC ≥ floor". The Form 4 census in
``tests/fixtures/global/form4/SOURCE.md`` measured what that would give: across the eighteen most
recent filings from Apple, JPMorgan and Verizon there is not one open-market purchase, and every
sale is under a 10b5-1 plan adopted months earlier. Both halves of the insider signal are
mechanical for names like these. Short interest is the opposite in every way that matters — dense
(every name, every settlement), directly about positioning, and nine years deep, which is the only
reason the lens can ever be IC-validated at all. So it is first.

TWO FIELDS FINRA COMPUTES ITSELF, AND THAT IS WHY THEY ARE USED. ``daysToCoverQuantity`` is the
short position divided by average daily volume, and ``changePercent`` is the move since the last
settlement. Both are on the record as FINRA published them. The alternative — short interest as a
percent of FLOAT — is the measure everyone quotes and this repository cannot compute: nothing
here carries a float, and inferring one from shares outstanding minus insider holdings would be a
derived number wearing a real one's clothes (rule #0).

WHAT A RISE IN SHORT INTEREST DOES NOT MEAN. It is not necessarily a bearish view. Convertible
arbitrage, index arbitrage, merger arbitrage and market-making all short a name while holding an
offsetting position, and none of them is an opinion about the price. The lens therefore treats
the change as a modest input rather than a verdict, and the scorer's docstring says so where a
reader will meet it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = ["DATASET_URL", "ShortInterest", "parse_short_interest"]

#: The dataset endpoint. It is PARTITIONED BY ``settlementDate``: FINRA refuses a sorted query
#: unless every partition key is pinned with an EQUAL filter, so the natural access pattern is
#: one settlement date at a time (or one symbol across all of them, which is what the fixtures
#: are). Queried by POST with a JSON body — a filter in the query string has to be URL-encoded
#: JSON and is rejected unencoded.
DATASET_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"


@dataclass(frozen=True, slots=True)
class ShortInterest:
    """One symbol at one settlement date, as FINRA published it."""

    symbol: str
    settlement_date: dt.date
    issue_name: str
    short_shares: Decimal | None
    previous_short_shares: Decimal | None
    average_daily_volume: Decimal | None
    #: Short position ÷ average daily volume, FINRA's own arithmetic.
    days_to_cover: Decimal | None
    #: Percent change in the short position since the previous settlement, FINRA's own.
    change_percent: Decimal | None
    #: FINRA flags a settlement whose figures were revised after publication. A revision is a
    #: different fact from the original and the journal should be able to tell them apart.
    is_revision: bool
    #: A split between settlements makes the share COUNTS incomparable; the flag is the only
    #: warning, and a change percent computed across one is meaningless.
    split_flag: bool


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _date(value: Any) -> dt.date | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def _flag(value: Any) -> bool:
    """FINRA leaves these null when they do not apply, and sets a letter when they do."""
    return bool(value) and str(value).strip().upper() not in {"N", "FALSE", "0"}


def parse_short_interest(rows: Iterable[dict[str, Any]]) -> list[ShortInterest]:
    """The feed's JSON rows → records, oldest first.

    A row without a symbol or a settlement date is dropped: it cannot be attached to an
    instrument or placed in time, so it is not yet a fact about anything.
    """
    out: list[ShortInterest] = []
    for r in rows:
        symbol = str(r.get("symbolCode") or "").strip().upper()
        settled = _date(r.get("settlementDate"))
        if not symbol or settled is None:
            continue
        out.append(
            ShortInterest(
                symbol=symbol,
                settlement_date=settled,
                issue_name=str(r.get("issueName") or "").strip(),
                short_shares=_decimal(r.get("currentShortPositionQuantity")),
                previous_short_shares=_decimal(r.get("previousShortPositionQuantity")),
                average_daily_volume=_decimal(r.get("averageDailyVolumeQuantity")),
                days_to_cover=_decimal(r.get("daysToCoverQuantity")),
                change_percent=_decimal(r.get("changePercent")),
                is_revision=_flag(r.get("revisionFlag")),
                split_flag=_flag(r.get("stockSplitFlag")),
            )
        )
    out.sort(key=lambda s: (s.symbol, s.settlement_date))
    return out

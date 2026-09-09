"""L1 exposures: what ONE holdings snapshot says a fund is exposed to. Pure, no I/O, no clock.

The layer between ``etf_holdings`` and everything that reads a fund as a bet rather than a
price — the classification engine's country and sector evidence, the cost lens's concentration
sub-score, the quality lens's look-through gate, and the ``/countries`` and ``/sectors`` pages.

WEIGHTS ARE NOT RENORMALISED. Every vector is a share of the fund's TOTAL absolute weight, so a
fund that is 97 per cent Japanese equities and 3 per cent cash reads ``JP: 0.97`` and not
``JP: 1.00``. Cash is not Japan, and a country-purity threshold should see the 0.97. The
consequence is that a vector sums to at most ``sum_abs_weight`` and usually to less — the
difference is the weight whose attribute the filing did not carry, which is a fact worth
seeing rather than one to divide away.

THE ASSET-CATEGORY MAP GROWS FROM FILINGS, NOT FROM MEMORY. N-PORT's ``assetCat`` enum has more
members than this repo has met. :data:`ASSET_CLASS` maps only the codes OBSERVED in real
filings, each with the fund that showed it, and anything else becomes a bucket named by its own
code — visible in the vector, counted in :attr:`Exposures.unmapped_w`, and never silently
folded into ``equity``. A code guessed wrong would move weight between asset classes, which is
the one thing this module exists to get right.

  ============  ==============  ====================================================
  code          bucket          observed on (2026-09-09)
  ============  ==============  ====================================================
  EC            equity          IVV 0.9942, EWJ 0.9900, TQQQ 0.3035
  DBT           fixed_income    AGG 0.7343
  ABS-MBS       fixed_income    AGG 0.2471
  ABS-O         fixed_income    AGG 0.0035
  STIV          cash            AGG 0.0340, TQQQ 0.1458, EWJ 0.0010
  RA            cash            TQQQ 0.0094
  DE            derivative      TQQQ 0.3704, EWJ 0.0009
  ============  ==============  ====================================================

Everything else — ``OTHER/Exchange traded fund`` (TQQQ's 0.1835 in another fund),
``OTHER/currency`` (EWJ 0.0027), ``EP``, and every code no filing here has shown — keeps its
own name.

SECTOR IS LOOK-THROUGH, SO IT IS BOUNDED BY IT. A holding's sector is its own instrument's
``sector_gics``, which exists only for the scored S&P 500. So ``sector_vec`` covers at most
``lookthrough_scored_w``, and an international fund has no sector vector at all — which is the
honest answer, not a reason to guess from the fund's name.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd

EQUITY = "equity"
FIXED_INCOME = "fixed_income"
CASH = "cash"
DERIVATIVE = "derivative"

# Only codes seen in a real filing; the table in the module docstring says which one.
ASSET_CLASS: dict[str, str] = {
    "EC": EQUITY,
    "DBT": FIXED_INCOME,
    "ABS-MBS": FIXED_INCOME,
    "ABS-O": FIXED_INCOME,
    "STIV": CASH,
    "RA": CASH,
    "DE": DERIVATIVE,
}
MAPPED_BUCKETS = frozenset(ASSET_CLASS.values())

# The ten largest holdings — the concentration sub-score's own window (plan §C, "top-10 weight").
TOP_N = 10
ZERO = Decimal(0)


@dataclass(frozen=True)
class Exposures:
    """One snapshot's exposures. Every share is of the fund's total absolute weight."""

    n_holdings: int
    sum_abs_weight: Decimal
    country_vec: dict[str, Decimal] = field(default_factory=dict)
    sector_vec: dict[str, Decimal] = field(default_factory=dict)
    asset_vec: dict[str, Decimal] = field(default_factory=dict)
    top_country: str | None = None
    top_country_w: Decimal | None = None
    equity_w: Decimal | None = None
    top10_w: Decimal | None = None
    hhi: Decimal | None = None
    lookthrough_scored_w: Decimal | None = None
    unmapped_w: Decimal = ZERO


def _weights(holdings: pd.DataFrame) -> list[Decimal]:
    return [abs(w) for w in holdings["weight_frac"] if w is not None]


def _column(holdings: pd.DataFrame, name: str) -> list[object]:
    """A column, or a column of nothing where the frame does not carry it.

    ``holding_instrument_id`` is written by the ingest, not by the parser, so a snapshot that
    has not been through resolution is a legitimate input with no look-through — an empty
    sector vector and a zero scored weight, which is exactly what it has.
    """
    if name not in holdings.columns:
        return [None] * len(holdings)
    return list(holdings[name])


def _by(holdings: pd.DataFrame, column: str) -> dict[str, Decimal]:
    """Total absolute weight per value of ``column``, skipping rows with neither."""
    out: dict[str, Decimal] = {}
    for key, weight in zip(_column(holdings, column), holdings["weight_frac"], strict=True):
        if key is None or weight is None or (isinstance(key, float) and key != key):
            continue
        out[str(key)] = out.get(str(key), ZERO) + abs(weight)
    return out


def _asset_bucket(category: object) -> str | None:
    """The bucket a holding's ``assetCat`` belongs to, or its own code where none is known."""
    if category is None or (isinstance(category, float) and category != category):
        return None
    return ASSET_CLASS.get(str(category), str(category))


def exposures(
    holdings: pd.DataFrame, sector_by_instrument: Mapping[str, str] | None = None
) -> Exposures:
    """``DataFrame[etf_holdings-shaped]`` → :class:`Exposures`.

    ``sector_by_instrument`` maps a resolved ``holding_instrument_id`` to the taxonomy sector
    id of that stock. Absent, the sector vector is empty — which is what an international fund
    honestly has, since the look-through only reaches the scored S&P 500.

    An empty snapshot yields zeroed counts rather than raising: a fund that reported no
    positions is a real filing.
    """
    weights = _weights(holdings)
    total = sum(weights, ZERO)
    if not len(holdings) or not weights:
        return Exposures(n_holdings=len(holdings), sum_abs_weight=total)

    countries = _by(holdings, "country_iso2")
    top_country = max(countries, key=lambda k: countries[k]) if countries else None

    assets: dict[str, Decimal] = {}
    categories = _column(holdings, "asset_category")
    for category, weight in zip(categories, holdings["weight_frac"], strict=True):
        bucket = _asset_bucket(category)
        if bucket is None or weight is None:
            continue
        assets[bucket] = assets.get(bucket, ZERO) + abs(weight)

    sectors: dict[str, Decimal] = {}
    scored = ZERO
    lookup = sector_by_instrument or {}
    for held, weight in zip(
        _column(holdings, "holding_instrument_id"), holdings["weight_frac"], strict=True
    ):
        if held is None or weight is None or (isinstance(held, float) and held != held):
            continue
        scored += abs(weight)
        sector = lookup.get(str(held))
        if sector is not None:
            sectors[sector] = sectors.get(sector, ZERO) + abs(weight)

    largest = sorted(weights, reverse=True)[:TOP_N]
    return Exposures(
        n_holdings=len(holdings),
        sum_abs_weight=total,
        country_vec=countries,
        sector_vec=sectors,
        asset_vec=assets,
        top_country=top_country,
        top_country_w=None if top_country is None else countries[top_country],
        equity_w=assets.get(EQUITY, ZERO),
        top10_w=sum(largest, ZERO),
        # Herfindahl over the holdings' own shares: 1 for a single position, 1/n for n equal
        # ones. Computed on the weights as filed, not on a renormalised vector.
        hhi=sum((w * w for w in weights), ZERO),
        lookthrough_scored_w=scored,
        unmapped_w=sum((w for bucket, w in assets.items() if bucket not in MAPPED_BUCKETS), ZERO),
    )

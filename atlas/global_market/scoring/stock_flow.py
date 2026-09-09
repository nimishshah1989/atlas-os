"""The US flow lens: who is positioned against this stock, and which way that is moving.

WHY SHORT INTEREST AND NOT INSIDER BUYING. plan.md §B specs this lens on Form 4 — "net
open-market buying over 90 days as a percent of market cap" — with short interest and 13F added
later. The measurement in ``tests/fixtures/global/form4/SOURCE.md`` says that order is backwards
for this market: across the eighteen most recent Form 4s from Apple, JPMorgan and Verizon there
is not one open-market purchase, and all six sales were made under 10b5-1 plans adopted months
earlier. Both halves of the insider signal are mechanical for large-cap US issuers, so a lens
built on it would be silent almost always and would never accumulate enough observations to be
IC-tested. FINRA's consolidated short interest is dense (every name, twice a month), free, and
nine years deep. It goes first. Form 4 remains worth adding as a sparse, high-value overlay —
a code-``P`` purchase is a strong signal precisely because it is rare — but not as the whole lens.

TWO SUB-SCORES, BOTH ON FIGURES FINRA COMPUTES ITSELF.

  ``flow_short_level``   days to cover — the short position divided by average daily volume.
                         How crowded the trade is, and how hard it would be to leave. Fewer days
                         is calmer; the bands are the FM's.
  ``flow_short_change``  the move in the short position since the last settlement. Shorts
                         covering reads positive, shorts building reads negative.

Percent-of-FLOAT is the measure everyone quotes and this repository cannot compute: nothing here
carries a float, and deriving one from shares outstanding less insider holdings would be a made-up
number wearing a real one's clothes (rule #0). Days to cover answers the same question from data
that exists.

WHAT A RISING SHORT POSITION IS NOT. It is not necessarily a bearish view. Convertible arbitrage,
index arbitrage, merger arbitrage and market-making all short a name against an offsetting
position, and none of those is an opinion about the price. So the change sub-score is deliberately
gentler than the level one, and both are bands the FM sets rather than a formula anyone here
invented.

CENTRED AT 50. A stock nobody is short of is not a good stock; it is an unremarkable one. Points
move the score either way from neutral and the result is clamped into 0–100 — India's shape, for
India's reason.

STALENESS IS PART OF THE READING. FINRA publishes about eight business days after each settlement
date, and settlements are twice a month, so the newest figure is routinely three weeks old. The
scorer refuses a reading older than ``flow_si_max_age_days`` rather than scoring last quarter's
positioning as though it were today's, and it reports the age of what it used.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from atlas.global_market.providers.finra import ShortInterest

__all__ = ["FLOW_KEYS", "FlowResult", "missing_keys", "score_flow"]

_Q2 = Decimal("0.01")
NEUTRAL = Decimal(50)
FLOOR = Decimal(0)
CEILING = Decimal(100)

#: Every key this scorer reads. All-or-nothing, like the other US lenses: there are no defaults,
#: so a partial set is a KeyError on the first stock that carries a reading.
FLOW_KEYS: tuple[str, ...] = (
    "flow_si_max_age_days",
    # days-to-cover ladder, best rung first (fewest days = least crowded)
    "flow_dtc_low",
    "flow_dtc_ok",
    "flow_dtc_high",
    # No `flow_dtc_extreme` BOUND: anything beyond `flow_dtc_high` is the extreme rung, so a
    # fourth bound would be a row the FM could tune with no effect — the orphan-threshold trap.
    "flow_dtc_pts_low",
    "flow_dtc_pts_ok",
    "flow_dtc_pts_high",
    "flow_dtc_pts_extreme",
    # the move since the previous settlement, as a percent
    "flow_si_change_big",
    "flow_si_change_mod",
    "flow_si_pts_covering_big",
    "flow_si_pts_covering_mod",
    "flow_si_pts_building_mod",
    "flow_si_pts_building_big",
)


def missing_keys(th: Mapping[str, Decimal]) -> list[str]:
    """The keys this scorer reads that ``atlas_thresholds`` does not carry."""
    return sorted(set(FLOW_KEYS) - set(th))


@dataclass(frozen=True, slots=True)
class FlowResult:
    short_level: Decimal | None
    short_change: Decimal | None
    value: Decimal | None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def subs(self) -> dict[str, Decimal | None]:
        """``lens_scores_daily``'s flow sub-score columns. India's third slot,
        ``flow_smart_money``, has no US producer and stays NULL — not zero (rule #0)."""
        return {
            "flow_promoter": self.short_level,
            "flow_institutional": self.short_change,
            "flow_smart_money": None,
        }


def _t(th: Mapping[str, Decimal], key: str) -> Decimal:
    if key not in th:
        raise KeyError(
            f"atlas_thresholds is missing {key!r} — seed it; the flow lens has no defaults"
        )
    return Decimal(str(th[key]))


def _level_points(days: Decimal, th: Mapping[str, Decimal]) -> Decimal:
    """Where a days-to-cover reading sits on the FM's ladder. Fewer days is the good end, so the
    ladder is read from the bottom up — the inverse of a quality ladder, and the same trap the
    fundamental debt/equity bands carry."""
    if days <= _t(th, "flow_dtc_low"):
        return _t(th, "flow_dtc_pts_low")
    if days <= _t(th, "flow_dtc_ok"):
        return _t(th, "flow_dtc_pts_ok")
    if days <= _t(th, "flow_dtc_high"):
        return _t(th, "flow_dtc_pts_high")
    return _t(th, "flow_dtc_pts_extreme")


def _change_points(percent: Decimal, th: Mapping[str, Decimal]) -> Decimal:
    """Shorts covering (a negative change) is the positive read; shorts building is the negative
    one. Both are gentler than the level ladder because a rising short position has innocent
    explanations — see the module docstring."""
    big = _t(th, "flow_si_change_big")
    mod = _t(th, "flow_si_change_mod")
    if percent <= -big:
        return _t(th, "flow_si_pts_covering_big")
    if percent <= -mod:
        return _t(th, "flow_si_pts_covering_mod")
    if percent >= big:
        return _t(th, "flow_si_pts_building_big")
    if percent >= mod:
        return _t(th, "flow_si_pts_building_mod")
    return Decimal(0)


def latest_reading(history: Sequence[ShortInterest], as_of: dt.date) -> ShortInterest | None:
    """The newest settlement AT OR BEFORE ``as_of``.

    Point-in-time: FINRA publishes about eight business days after a settlement date, so a
    reading dated the 15th was not on the record until the 25th. Filtering on the settlement date
    is therefore slightly generous, and deliberately the only filter this repository can make —
    the feed does not carry its own publication date. Recorded here rather than left implicit,
    because a backfilled score that used a figure eight days before it existed is a real, small
    look-ahead and someone should be able to find this note when they go looking for it.
    """
    seen = [s for s in history if s.settlement_date <= as_of]
    return max(seen, key=lambda s: s.settlement_date) if seen else None


def score_flow(
    history: Sequence[ShortInterest],
    as_of: dt.date,
    th: Mapping[str, Decimal],
) -> FlowResult:
    """The flow lens (0–100) for one US stock, from its short-interest history.

    Returns every sub-score ``None`` when there is no usable reading — no short-interest figure,
    or one older than the FM's staleness limit. A stock nobody has measured is not a stock with
    no short interest, and ``blend()`` renormalises over the lenses that are present.
    """
    reading = latest_reading(history, as_of)
    if reading is None:
        return FlowResult(None, None, None, {"reason": "no settlement at or before the anchor"})

    age = (as_of - reading.settlement_date).days
    max_age = int(_t(th, "flow_si_max_age_days"))
    if age > max_age:
        return FlowResult(
            None,
            None,
            None,
            {
                "reason": "the newest settlement is stale",
                "settlement_date": reading.settlement_date.isoformat(),
                "age_days": age,
                "max_age_days": max_age,
            },
        )

    def clamp(points: Decimal) -> Decimal:
        return min(CEILING, max(FLOOR, NEUTRAL + points)).quantize(_Q2, rounding=ROUND_HALF_UP)

    level = (
        None if reading.days_to_cover is None else clamp(_level_points(reading.days_to_cover, th))
    )
    # A split between settlements makes the two share counts incomparable, so FINRA's own change
    # percent is meaningless across one. The flag is the only warning there is.
    change = (
        None
        if reading.change_percent is None or reading.split_flag
        else clamp(_change_points(reading.change_percent, th))
    )

    present = [v for v in (level, change) if v is not None]
    value = (
        (sum(present, Decimal(0)) / Decimal(len(present))).quantize(_Q2, rounding=ROUND_HALF_UP)
        if present
        else None
    )
    return FlowResult(
        short_level=level,
        short_change=change,
        value=value,
        evidence={
            "settlement_date": reading.settlement_date.isoformat(),
            "age_days": age,
            "days_to_cover": None if reading.days_to_cover is None else str(reading.days_to_cover),
            "change_percent": None
            if reading.change_percent is None
            else str(reading.change_percent),
            "short_shares": None if reading.short_shares is None else str(reading.short_shares),
            "split_between_settlements": reading.split_flag,
            "is_revision": reading.is_revision,
        },
    )

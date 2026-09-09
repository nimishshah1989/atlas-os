"""The US catalyst lens: what a company has TOLD the SEC about itself lately.

WHY THIS IS A REPLACEMENT, NOT A PORT. India's ``atlas.lenses.compute.catalyst`` reads NSE
announcement SUBJECTS and matches keywords — "bagging", "letter of award", "downgrade" — because
that is all an NSE filing gives you. A US 8-K carries ITEM CODES: 2.02 is "Results of Operations
and Financial Condition", 4.02 is "Non-Reliance on Previously Issued Financial Statements". The
registrant asserts that classification itself, on the form, under Regulation FD. So this scorer
reads item codes and never a headline. A keyword rule over English prose is a machine that
produces confident nonsense at a rate nobody measures; an item code is a fact.

WHAT IS DELIBERATELY NOT SCORED, AND WHY IT IS SAID OUT LOUD. plan.md §B asks for "dividend
increase or initiation +8" and "buyback authorisation +10". Neither has an item code: both are
announced in a press release attached to an 8.01 or a 7.01, and telling them apart needs a parser
of that release. Scoring them would mean keyword-matching exactly the way this module exists not
to. They are therefore ABSENT — a bucket that says less than it could, rather than one that says
more than it knows (rule #0). The same is true of "contract win" and "guidance raise".

MOST 8-K TRAFFIC IS NOT SCOREABLE, AND THE EVIDENCE SAYS SO. Item 9.01 (Financial Statements
and Exhibits) rides along with almost every filing that has a press release — 82 of Apple's 105
8-Ks — and 8.01 (Other Events) is a code that says only "something happened". Neither can be
scored without reading the prose. So the evidence carries ``items_not_scored`` beside the scored
ones and ``filings_with_no_scored_item``: a reader can see exactly how much of the flow this
lens is silent about, rather than reading the silence as "nothing happened".

THE BUCKET IS CENTRED AT 50, NOT AT 0. A company that has filed nothing is not a bad company; it
is an uneventful one, and the lens must say "neutral" rather than "worst". Points move it either
way and the result is clamped into 0–100. That is India's shape and the reason for it is the
same.

DECAY IS AN OPINION ABOUT HOW LONG NEWS LASTS, so it lives in ``atlas_thresholds`` like every
other opinion (rule #1) — both the windows and the multipliers. Nothing in this file is a
number: every point value, weight, window and multiplier is read from the table by name, and a
missing key raises rather than defaulting to India's.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

__all__ = [
    "BUCKETS",
    "BUCKET_WEIGHT_KEY",
    "CATALYST_KEYS",
    "ITEM_BUCKET",
    "CatalystResult",
    "Filing",
    "missing_keys",
    "score_catalyst",
]

_Q2 = Decimal("0.01")
NEUTRAL = Decimal(50)
FLOOR = Decimal(0)
CEILING = Decimal(100)

BUCKETS: tuple[str, ...] = ("earnings_strategy", "capital_action", "governance")

# Bucket → the ``atlas_thresholds`` key carrying its weight. The two are NOT the same string,
# and deliberately so: ``catalyst_w_earnings`` and ``catalyst_w_capital`` were seeded into prod
# before this scorer existed. Renaming them would leave two orphan rows in the live table that
# the FM could tune with no effect, which is a worse trap than a mapping one line wide.
BUCKET_WEIGHT_KEY: dict[str, str] = {
    "earnings_strategy": "catalyst_w_earnings",
    "capital_action": "catalyst_w_capital",
    "governance": "catalyst_w_governance",
}

# 8-K item code → the bucket it belongs to. The threshold key for its points is
# ``catalyst_pts_<code with the dot as an underscore>``: item 2.02 reads
# ``catalyst_pts_2_02``. Codes are the SEC's own Form 8-K items; a code absent from this map
# scores nothing and is counted as unmapped.
#
# The three buckets, and what each is asking:
#   earnings_strategy  is the business doing more or less than it was
#   capital_action     is the share count or the capital structure moving, and which way
#   governance         is anything wrong with the people, the auditor or the listing
ITEM_BUCKET: dict[str, str] = {
    # ── earnings and strategy ──
    "2.02": "earnings_strategy",  # Results of Operations and Financial Condition
    "1.01": "earnings_strategy",  # Entry into a Material Definitive Agreement
    "1.02": "earnings_strategy",  # Termination of a Material Definitive Agreement
    "2.01": "earnings_strategy",  # Completion of Acquisition or Disposition of Assets
    "2.05": "earnings_strategy",  # Costs Associated with Exit or Disposal Activities
    "2.06": "earnings_strategy",  # Material Impairments
    # ── capital and structure ──
    "2.03": "capital_action",  # Creation of a Direct Financial Obligation
    "2.04": "capital_action",  # Triggering Events That Accelerate an Obligation
    "3.02": "capital_action",  # Unregistered Sales of Equity Securities (dilution)
    "3.03": "capital_action",  # Material Modification to Rights of Security Holders
    "5.01": "capital_action",  # Changes in Control of Registrant
    # ── governance and distress ──
    "1.03": "governance",  # Bankruptcy or Receivership
    "3.01": "governance",  # Notice of Delisting / failure to satisfy a listing rule
    "4.01": "governance",  # Changes in the Registrant's Certifying Accountant
    "4.02": "governance",  # Non-Reliance on Previously Issued Financial Statements
    "5.02": "governance",  # Departure or Election of Directors or Certain Officers
}


def points_key(item: str) -> str:
    """``2.02`` → ``catalyst_pts_2_02`` — the threshold key carrying that item's points."""
    return f"catalyst_pts_{item.replace('.', '_')}"


#: Every key this scorer reads. ``score_stocks`` refuses to score the lens until the table
#: carries all of them, for the same reason the fundamental bands are all-or-nothing: a partial
#: set would weight the buckets by whatever happened to be seeded.
CATALYST_KEYS: tuple[str, ...] = (
    *(BUCKET_WEIGHT_KEY[b] for b in BUCKETS),
    "catalyst_recency_t1",
    "catalyst_recency_t2",
    "catalyst_recency_t3",
    "catalyst_decay_t1",
    "catalyst_decay_t2",
    "catalyst_decay_t3",
    "catalyst_decay_old",
    *(points_key(item) for item in sorted(ITEM_BUCKET)),
)


def missing_keys(th: Mapping[str, Decimal]) -> list[str]:
    """The keys this scorer reads that ``atlas_thresholds`` does not carry.

    The lens is all-or-nothing on them, the same rule the fundamental bands follow and for the
    same reason: there are no defaults, so a partial set is not a partly-tuned lens — it is a
    KeyError on the first company that files that item, at one in the morning.
    """
    return sorted(set(CATALYST_KEYS) - set(th))


@dataclass(frozen=True, slots=True)
class Filing:
    """One 8-K, as ``filings_8k`` holds it.

    ``filed`` is the EDGAR filed date and NOT the period of report: a reader could not have known
    about the event before the filing appeared, and the whole journal is point-in-time.
    """

    filed: dt.date
    items: Sequence[str]
    accession_no: str = ""


@dataclass(frozen=True, slots=True)
class CatalystResult:
    earnings_strategy: Decimal | None
    capital_action: Decimal | None
    governance: Decimal | None
    value: Decimal | None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def subs(self) -> dict[str, Decimal | None]:
        """The ``lens_scores_daily`` sub-score columns this lens fills."""
        return {
            "cat_earnings_strategy": self.earnings_strategy,
            "cat_capital_action": self.capital_action,
            "cat_governance": self.governance,
        }


def _t(th: Mapping[str, Decimal], key: str) -> Decimal:
    """A threshold BY NAME, or a KeyError naming it. There are no defaults here on purpose:
    India's ``.get(key, default)`` would put India's number into a US score invisibly."""
    if key not in th:
        raise KeyError(
            f"atlas_thresholds is missing {key!r} — seed it; the catalyst lens has no defaults"
        )
    return Decimal(str(th[key]))


def decay(days: int, th: Mapping[str, Decimal]) -> Decimal:
    """How much of an event's points survive ``days`` after it was filed.

    A step function, not a curve: the FM sets three windows and four multipliers, and a step is
    something he can reason about and edit. Negative days (a filing dated after the as-of, which
    a bad ingest could produce) take the freshest multiplier — the caller filters them out first.
    """
    if days <= int(_t(th, "catalyst_recency_t1")):
        return _t(th, "catalyst_decay_t1")
    if days <= int(_t(th, "catalyst_recency_t2")):
        return _t(th, "catalyst_decay_t2")
    if days <= int(_t(th, "catalyst_recency_t3")):
        return _t(th, "catalyst_decay_t3")
    return _t(th, "catalyst_decay_old")


def score_catalyst(
    filings: Iterable[Filing],
    as_of: dt.date,
    th: Mapping[str, Decimal],
) -> CatalystResult:
    """The catalyst lens (0–100) for one US stock, from its 8-K item codes.

    A bucket with no filing in the window is ``None`` — absent, not 50. The distinction matters:
    50 says "the news nets out to neutral", ``None`` says "there was no news", and a company
    that has filed nothing must not be averaged in as though something had been measured. The
    lens itself is the weighted mean over the buckets that ARE present, so a company with only
    governance filings is scored on governance rather than on two thirds of a guess.

    Every filing is counted in the evidence, including the ones no item code reached.
    """
    totals: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    by_item: dict[str, int] = {}
    unscored_items: dict[str, int] = {}
    unmapped = 0
    considered = 0
    oldest = int(_t(th, "catalyst_recency_t3"))

    for f in filings:
        days = (as_of - f.filed).days
        # Filed after the as-of date: a reader on that day could not have seen it. Dropping it is
        # the point-in-time rule, and it is enforced here rather than trusted to the query.
        if days < 0:
            continue
        considered += 1
        weight = decay(days, th)
        hit = False
        for item in f.items:
            bucket = ITEM_BUCKET.get(item)
            if bucket is None:
                unscored_items[item] = unscored_items.get(item, 0) + 1
                continue
            hit = True
            by_item[item] = by_item.get(item, 0) + 1
            totals[bucket] = totals.get(bucket, Decimal(0)) + _t(th, points_key(item)) * weight
            counts[bucket] = counts.get(bucket, 0) + 1
        if not hit:
            unmapped += 1

    buckets: dict[str, Decimal | None] = {}
    for name in BUCKETS:
        if name not in totals:
            buckets[name] = None
            continue
        raw = NEUTRAL + totals[name]
        buckets[name] = min(CEILING, max(FLOOR, raw)).quantize(_Q2, rounding=ROUND_HALF_UP)

    present = [(name, v) for name, v in buckets.items() if v is not None]
    if present:
        weights = {name: _t(th, BUCKET_WEIGHT_KEY[name]) for name, _v in present}
        total_weight = sum(weights.values(), Decimal(0))
        value = (
            None
            if total_weight == 0
            else (
                sum((v * weights[name] for name, v in present), Decimal(0)) / total_weight
            ).quantize(_Q2, rounding=ROUND_HALF_UP)
        )
    else:
        value = None

    return CatalystResult(
        earnings_strategy=buckets["earnings_strategy"],
        capital_action=buckets["capital_action"],
        governance=buckets["governance"],
        value=value,
        evidence={
            "as_of": as_of.isoformat(),
            "window_days": oldest,
            "filings_considered": considered,
            "filings_with_no_scored_item": unmapped,
            "items": dict(sorted(by_item.items())),
            # What the map passed over, and it is MOST of the traffic: on Apple's real filing
            # history 82 of 105 8-Ks carry 9.01 (Financial Statements and Exhibits), which is
            # boilerplate attached to almost every filing with a press release, and 8.01 (Other
            # Events) is the second most common — a code that says only "something happened".
            # Neither can be scored without reading the prose, so both are counted here instead.
            # A reader can see exactly how much of the flow the lens is silent about.
            "items_not_scored": dict(sorted(unscored_items.items())),
            "bucket_filings": {k: counts.get(k, 0) for k in BUCKETS},
        },
    )

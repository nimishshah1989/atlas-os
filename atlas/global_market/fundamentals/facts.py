"""A raw SEC company-facts payload → the periods a filer reported. Pure: no I/O, no vendor.

This is the half of the EDGAR ingest that has no network and no database in it, so it can be
run — and IS run, by ``tests/unit/global_market/test_ingest_financials.py`` — against the real
payloads committed under ``tests/fixtures/global/edgar/``. The fetching, the SQL and the
watermarks live in ``scripts/global_market/ingest_financials.py``, which imports this.

WHAT A ROW IS. One filing's own reporting period, keyed ``(form, filed, period_end)``. Every
10-Q and 10-K also carries prior periods as comparatives, and each of those is a real
point-in-time record — it is what stood on file that day — so they are rows too. The same
period_end reappearing under a later ``filed`` is the restatement journal working as designed:
Apple's FY2019 diluted share count is 4,648,913 thousand as filed in 2019 and 18,595,651
thousand as re-filed in 2020, restated for the four-for-one split.

THE ONE AMBIGUITY, resolved by form. Company facts publishes several durations that end on the
same date: a 10-Q carries the three-month quarter AND the six- or nine-month year-to-date; a
pre-2021 10-K carries a three-month Q4 beside the twelve-month year. ``stock_financials_pit``
admits one row per ``(period_end, form, filed)``, so a row takes the duration that IS the
filing's own period — a year for 10-K/20-F/40-F, a quarter for 10-Q — and year-to-date
durations are dropped outright. Storing a nine-month figure in a column read as a quarter is
the kind of wrong that a chart makes look like growth.

The consequence, measured and recorded in ``docs/global/data-sources.md``: a 10-Q's cash-flow
statement is cumulative, so operating cash flow, capex and dividends are present on FIRST
fiscal quarters and annual periods only. And no filer tags a discrete Q4 any more, so the
fourth quarter is the identity in :func:`atlas.global_market.fundamentals.ratios.implied_q4`.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from . import xbrl_map

# ddl/04_fundamentals_events.sql's CHECK. Company facts also serves 8-K and DEF 14A facts
# (earnings releases and proxy tables); they are periodic reports of a different kind and the
# table does not admit them.
ALLOWED_FORMS = frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F"})
ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "40-F"})
# Duration windows in days, wide enough for 52/53-week fiscal calendars and the odd
# transition period. Data shape, not methodology: a filer's "quarter" is 13 weeks give or
# take a few days, and anything outside these bands is a year-to-date or a stub period.
QUARTER = "quarter"
ANNUAL = "annual"
INSTANT = "instant"
QUARTER_DAYS = (80, 100)  # allow-threshold: XBRL duration shape, not a scoring band
ANNUAL_DAYS = (350, 380)  # allow-threshold: XBRL duration shape, not a scoring band


@dataclass
class PeriodRow:
    """One filing's report of one period: the PIT key, the period, and the picked values."""

    period_end: dt.date
    form: str
    filed: dt.date
    period_class: str
    period_start: dt.date | None = None
    accession_no: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    values: dict[str, Decimal] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def is_annual(self) -> bool:
        return self.period_class == ANNUAL


def period_class(start: str | None, end: str) -> str | None:
    """``instant`` (a balance), ``quarter``, ``annual``, or ``None`` for a duration this table
    has no column for — a six- or nine-month year-to-date, or a stub period."""
    if start is None:
        return INSTANT
    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
    if QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
        return QUARTER
    if ANNUAL_DAYS[0] <= days <= ANNUAL_DAYS[1]:
        return ANNUAL
    return None


@dataclass
class _Bucket:
    """Every fact one filing reported about one period_end, split by what it measures."""

    durations: dict[str, dict[str, Any]] = field(default_factory=dict)  # class → tag → fact
    instants: dict[str, Any] = field(default_factory=dict)  # tag → fact


def _buckets(us_gaap: Mapping[str, Any]) -> dict[tuple[str, str, str], _Bucket]:
    """Walk the payload once: ``(form, filed, period_end)`` → the facts filed about it."""
    out: dict[tuple[str, str, str], _Bucket] = {}
    for tag, concepts in xbrl_map.TAG_CONCEPTS.items():
        tag_facts = us_gaap.get(tag)
        if not tag_facts:
            continue
        wanted_units = {xbrl_map.UNITS[c] for c in concepts}
        for unit, facts in tag_facts.get("units", {}).items():
            if unit not in wanted_units:
                continue  # a dual-reporting filer's foreign-currency copy is not this value
            for fact in facts:
                form, end = fact.get("form"), fact.get("end")
                if form not in ALLOWED_FORMS or not end or not fact.get("filed"):
                    continue
                klass = period_class(fact.get("start"), end)
                if klass is None:
                    continue
                bucket = out.setdefault((form, fact["filed"], end), _Bucket())
                if klass == INSTANT:
                    bucket.instants[tag] = fact
                else:
                    bucket.durations.setdefault(klass, {})[tag] = fact
    return out


def _values_and_tags(
    bucket: _Bucket, klass: str
) -> tuple[dict[str, Decimal], dict[str, str], list[Any]]:
    """Pick every concept from one bucket: ``(values, tag used per concept, facts used)``."""
    durations = {t: f["val"] for t, f in bucket.durations.get(klass, {}).items()}
    instants = {t: f["val"] for t, f in bucket.instants.items()}
    values: dict[str, Decimal] = {}
    tags: dict[str, str] = {}
    used: list[Any] = []
    for concept in xbrl_map.CONCEPTS:
        instant = concept in xbrl_map.INSTANT_CONCEPTS
        raw, tag = xbrl_map.pick(concept, instants if instant else durations)
        if raw is None or tag is None:
            continue
        values[concept] = Decimal(str(raw))  # str(): a float literal must never become money
        tags[concept] = tag
        used.append((bucket.instants if instant else bucket.durations[klass])[tag])
    return values, tags, used


def extract_rows(payload: Mapping[str, Any]) -> list[PeriodRow]:
    """A raw company-facts payload → one :class:`PeriodRow` per ``(form, filed, period_end)``.

    A bucket with no duration fact of its own period class is dropped: it is a balance sheet
    comparative (a 10-Q restates the prior year end's balances) with no reporting period of its
    own, and a row of nothing but balances would read as a quarter that earned nothing.
    """
    us_gaap = payload.get("facts", {}).get("us-gaap", {})
    rows: list[PeriodRow] = []
    for (form, filed, end), bucket in _buckets(us_gaap).items():
        klass = ANNUAL if form in ANNUAL_FORMS else QUARTER
        if klass not in bucket.durations:
            continue
        values, tags, used = _values_and_tags(bucket, klass)
        if not values:
            continue
        starts = Counter(f["start"] for f in used if f.get("start"))
        accns = Counter(f["accn"] for f in used if f.get("accn"))
        rows.append(
            PeriodRow(
                period_end=dt.date.fromisoformat(end),
                form=form,
                filed=dt.date.fromisoformat(filed),
                period_class=klass,
                period_start=dt.date.fromisoformat(starts.most_common(1)[0][0]) if starts else None,
                accession_no=accns.most_common(1)[0][0] if accns else None,
                values=values,
                tags=tags,
            )
        )
    _label_fiscal_periods(rows, us_gaap)
    return sorted(rows, key=lambda r: (r.period_end, r.form, r.filed))


def _label_fiscal_periods(rows: list[PeriodRow], us_gaap: Mapping[str, Any]) -> None:
    """Fill ``fiscal_year`` / ``fiscal_period`` only where they are known to be right.

    Company facts stamps ``fy``/``fp`` on every fact with the FILING's fiscal year and period,
    not the fact's: the prior-year quarter shown as a comparative in a 2026 Q1 10-Q is stamped
    ``fy=2026 fp=Q1``. Copying that verbatim would label a 2025 quarter as 2026. So the stamp
    is taken only for the newest period of its class in a given filing — the filing's own
    period — and a comparative keeps ``FY`` (which its twelve-month duration proves) or
    nothing at all. A wrong label is worse than an absent one.
    """
    stamps = {
        (f["form"], f["filed"], f["end"]): (f.get("fy"), f.get("fp"))
        for tag in xbrl_map.TAG_CONCEPTS
        for facts in us_gaap.get(tag, {}).get("units", {}).values()
        for f in facts
    }
    own: dict[tuple[str, dt.date, str], dt.date] = {}
    for row in rows:
        key = (row.form, row.filed, row.period_class)
        own[key] = max(own.get(key, row.period_end), row.period_end)
    for row in rows:
        row.fiscal_period = "FY" if row.is_annual else None
        if own[(row.form, row.filed, row.period_class)] != row.period_end:
            continue  # a comparative: the filing's fy/fp describes a different period
        fy, fp = stamps.get(
            (row.form, row.filed.isoformat(), row.period_end.isoformat()), (None, None)
        )
        row.fiscal_year = int(fy) if fy is not None else None
        if fp in ("FY", "Q1", "Q2", "Q3", "Q4"):
            row.fiscal_period = fp


def quarter_count(rows: Sequence[PeriodRow]) -> int:
    """Distinct quarterly period ends the filer has ever reported — the coverage number P3-A's
    definition of done counts, and independent of how many rows this run happened to write."""
    return len({r.period_end for r in rows if not r.is_annual})


def tag_summary(rows: Sequence[PeriodRow]) -> str:
    """``concept=tag`` for the newest row's picks — the audit trail for the values stored.

    The table has no column for provenance, so the run's report carries it: which us-gaap
    element each number actually came from, which is the difference between "Verizon has no
    long-term debt" and "Verizon files it under a different element".
    """
    if not rows:
        return ""
    newest = max(rows, key=lambda r: (r.period_end, r.filed))
    return " ".join(f"{c}={t}" for c, t in sorted(newest.tags.items()))

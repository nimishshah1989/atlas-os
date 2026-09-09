"""SEC ``data.sec.gov/submissions/CIK##########.json`` → the filings a company has made.

WHY THIS ENDPOINT AND NOT THE FULL-TEXT INDEX. The submissions payload carries an ``items`` field
per filing: for an 8-K it is the SEC item codes as a comma-separated string — ``"2.02,9.01"`` on
Apple's results filings, ``"5.02"`` on a director change. That is the registrant's own legal
classification of what the filing IS, and it is the whole reason the US catalyst lens can read
item codes instead of keyword-matching press-release prose (see
``atlas.global_market.scoring.stock_catalyst``). Verified against real payloads for Apple,
JPMorgan and Verizon on 2026-09-09; the fixtures under ``tests/fixtures/global/submissions/``
are those downloads.

THE SHAPE IS PARALLEL ARRAYS, WHICH IS THE ONE WAY TO GET THIS WRONG. ``filings.recent`` is not
a list of objects: it is a dict of equal-length lists, one per field, and row *i* of the filing
is element *i* of each. A field list shorter than the others would silently shift every filing
after it onto another filing's date. :func:`parse_submissions` therefore refuses a payload whose
lists disagree rather than zipping to the shortest, which is what ``zip`` would do by default.

WHAT ``recent`` COVERS. Up to 1,000 filings of every form. For the S&P 500 that is years of
history — Apple's reaches 2015 — and the catalyst lens looks back one year, so nothing beyond it
is needed. Older filings live in ``filings.files`` as separate JSON documents; this parser
reports how many such batches exist (:attr:`Submissions.older_batches`) and does NOT fetch them.
A caller that needs deeper history must ask for it explicitly rather than get a silently
truncated answer.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Filing", "Submissions", "parse_submissions", "submissions_url"]

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

#: The form we read item codes from. ``8-K/A`` is an amendment of one and carries its own items,
#: so it is admitted too — an amended 8-K is a filing that happened.
FORM_8K = "8-K"


def submissions_url(cik: str | int) -> str:
    """The submissions document for a CIK, zero-padded to ten digits as the endpoint requires."""
    return SUBMISSIONS_URL.format(cik=int(cik))


@dataclass(frozen=True, slots=True)
class Filing:
    """One filing row. ``items`` is empty for every form but 8-K."""

    accession_no: str
    form: str
    filed: dt.date
    items: tuple[str, ...]
    period_of_report: dt.date | None = None
    primary_document: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class Submissions:
    cik: str
    name: str
    tickers: tuple[str, ...]
    filings: tuple[Filing, ...]
    #: How many ADDITIONAL batches of older filings exist in ``filings.files`` and were not read.
    older_batches: int = 0
    #: The oldest and newest filed dates actually parsed, so a caller can see its own horizon.
    covers: tuple[dt.date, dt.date] | None = field(default=None)


def _date(value: Any) -> dt.date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _items(value: Any) -> tuple[str, ...]:
    """``"2.02,9.01"`` → ``("2.02", "9.01")``. Whitespace and empties dropped; order kept.

    A duplicate is kept: a filing that lists an item twice has said it twice, and collapsing it
    here would silently change what the scorer counts.
    """
    if not isinstance(value, str):
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def parse_submissions(payload: dict[str, Any], *, forms: set[str] | None = None) -> Submissions:
    """The company's filings, from a raw submissions payload.

    ``forms`` filters by form (``{"8-K", "8-K/A"}`` for the catalyst feed); ``None`` keeps every
    form. Raises ``ValueError`` when the parallel arrays disagree in length — see the module
    docstring for why that must not be tolerated.
    """
    recent = payload.get("filings", {}).get("recent", {})
    accessions = recent.get("accessionNumber", [])
    columns = (
        "form",
        "filingDate",
        "items",
        "reportDate",
        "primaryDocument",
        "primaryDocDescription",
    )
    lengths = {name: len(recent.get(name, [])) for name in columns}
    bad = {name: n for name, n in lengths.items() if n != len(accessions)}
    if bad:
        raise ValueError(
            f"submissions payload is inconsistent: accessionNumber has {len(accessions)} row(s) "
            f"but {bad} — zipping these would shift filings onto other filings' dates"
        )

    out: list[Filing] = []
    for i, accession in enumerate(accessions):
        form = str(recent["form"][i])
        if forms is not None and form not in forms:
            continue
        filed = _date(recent["filingDate"][i])
        if filed is None:
            continue  # a filing with no date cannot be placed in time, so it is not a fact yet
        out.append(
            Filing(
                accession_no=str(accession),
                form=form,
                filed=filed,
                items=_items(recent["items"][i]),
                period_of_report=_date(recent["reportDate"][i]),
                primary_document=str(recent["primaryDocument"][i] or ""),
                description=str(recent["primaryDocDescription"][i] or ""),
            )
        )

    dates = [f.filed for f in out]
    return Submissions(
        cik=str(payload.get("cik", "")),
        name=str(payload.get("name", "")),
        tickers=tuple(str(t) for t in payload.get("tickers", [])),
        filings=tuple(out),
        older_batches=len(payload.get("filings", {}).get("files", []) or []),
        covers=(min(dates), max(dates)) if dates else None,
    )

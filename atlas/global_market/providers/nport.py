"""SEC EDGAR Form N-PORT-P — what a fund held, and what the fund is worth.

Every US registered investment company except a unit investment trust files Form N-PORT
MONTHLY; only the report for the third month of each of its FISCAL quarters is made public,
about sixty days after that month ends. So this feed is quarterly, lagged, and its as-of dates
follow each filer's own fiscal year — ProShares reports 31 May, iShares 30 June (verified on
the four filings in ``tests/fixtures/global/nport/``). Nothing here may assume a calendar
quarter end. SPY is absent from the feed entirely and that is not a bug: it is a unit
investment trust, and UITs do not file N-PORT.

WHERE THE HALVES SPLIT. :class:`NportProvider` is the off-box half — two GETs per fund, paced
by the same :data:`~atlas.global_market.providers.directories.SEC_MIN_INTERVAL_S` the identity
and company-facts readers use, so the three EDGAR readers can never disagree about the SEC's
ceiling. :func:`parse_nport` is pure: bytes in, facts and a holdings frame out, no clock, no
network, no database.

THE FOUR TRAPS, each of them measured on a real filing rather than assumed:

* ``pctVal`` IS A PERCENT. CBRE is ``0.061079735228`` of IVV, and ``valUSD / netAssets`` for
  that row is ``0.00061079…``. :data:`HOLDING_COLUMNS` carries ``weight_frac``, a FRACTION, so
  every ``pctVal`` is divided by a hundred exactly once, here.
* ``netAssets`` IS THE SERIES', NOT THE ETF'S. One filing covers one series, and a series may
  have several share classes — VOO is one of the FOUR classes of the Vanguard 500 Index Fund,
  whose filed net assets are the whole fund's. N-PORT carries no class-level assets at all
  (there is no ``classInfo`` element in any of the four fixtures), so this module reports
  ``net_assets`` beside ``class_ids`` and leaves it to the writer to refuse to call a
  multi-class figure an ETF's AUM.
* "N/A" IS A VALUE THE FILERS WRITE. It appears as a ``cusip``, an ``lei``, an ``isin``, an
  ``invCountry`` and a ``payoffProfile``. Every one of them becomes ``None``:
  a two-character country column would otherwise take ``"N/"``.
* THE "OTHER" CATEGORIES MOVE TO AN ATTRIBUTE. A holding whose category is off-enum has no
  ``assetCat``/``issuerCat`` element; it has ``<assetConditional assetCat="OTHER" desc="Right"/>``
  instead. Reading only the element loses every one of them — a Hologic CVR in IVV, an ETF
  position in TQQQ, and the futures line of both.

LEVERAGE IS NOT VISIBLE IN THE WEIGHTS. A swap's ``pctVal`` is its MARK, not its notional, so
TQQQ — a three-times fund — sums to 101.26% of net assets, barely different from IVV's 100.12%.
The only structural evidence of gearing in the form is ``derivativeInfo/*/notionalAmt``, which
:class:`FundFacts` totals as ``derivative_notional_usd``.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
import requests

from atlas.global_market.config import edgar_identity
from atlas.global_market.providers.directories import SEC_MIN_INTERVAL_S

NPORT_NS = "http://www.sec.gov/edgar/nport"
FORM = "NPORT-P"  # browse-edgar matches by prefix, so this also brings back NPORT-P/A
TIMEOUT = 180  # a bond fund's primary_doc runs to tens of megabytes
PERCENT = Decimal(100)

FILINGS_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={series_id}"
    "&type={form}&dateb=&owner=include&count={count}&output=atom"
)
PRIMARY_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/primary_doc.xml"

# What a filer writes where it has nothing to say. Applied to identifiers and codes only —
# never to a number, where "0" is a value and not an absence.
MISSING = frozenset({"", "N/A", "NA", "NONE", "N.A."})

HOLDING_COLUMNS: tuple[str, ...] = (
    "holding_key",
    "holding_name",
    "holding_ticker",
    "cusip",
    "isin",
    "lei",
    "title",
    "weight_frac",
    "market_value_usd",
    "balance",
    "units",
    "currency",
    "country_iso2",
    "asset_category",
    "issuer_category",
    "payoff_profile",
    "derivative_category",
    "notional_usd",
)


def _local(tag: str) -> str:
    """``{ns}invstOrSec`` → ``invstOrSec``. The N-PORT namespace has been stable, but nothing
    here depends on that: elements are found by local name."""
    return tag.rpartition("}")[2]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((c for c in element if _local(c.tag) == name), None)


def _clean(value: str | None) -> str | None:
    """A stripped value, with every filer spelling of "nothing" as ``None``."""
    if value is None:
        return None
    stripped = value.strip()
    return None if stripped.upper() in MISSING else stripped


def _text(element: ET.Element | None, name: str) -> str | None:
    """The stripped text of a DIRECT child. Direct on purpose: ``curCd`` names both the
    holding's currency and, three levels down, a swap leg's."""
    if element is None:
        return None
    found = _child(element, name)
    return None if found is None else _clean(found.text)


def _descendant_text(element: ET.Element, name: str) -> str | None:
    """The stripped text of the first descendant with that local name, at any depth.

    EDGAR's atom nests a filing's fields inside ``<content>``, so an entry's
    ``accession-number`` is a grandchild and not a child.
    """
    return next(
        (_clean(e.text) for e in element.iter() if _local(e.tag) == name),
        None,
    )


def _decimal(value: str | None, what: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as e:
        raise ValueError(f"{what}: {value!r} is not a number") from e


def _date(value: str | None, what: str) -> date | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValueError(f"{what}: {value!r} is not an ISO date") from e


def _iso2(value: str | None) -> str | None:
    """A two-letter country, or nothing. ``invCountry`` is ``N/A`` on every derivative line of
    the VOO filing, and a ``char(2)`` column would otherwise store ``N/``."""
    return value if value is not None and len(value) == 2 and value.isalpha() else None


@dataclass(frozen=True)
class FilingRef:
    """One row of a series' N-PORT filing index — what the atom feed knows before any
    document is fetched. The period is NOT here: only the document states it."""

    series_id: str
    cik: str  # the registrant's, zero-padded to ten as EDGAR prints it
    accession: str  # 0001234567-26-000123
    filed: date
    form: str  # NPORT-P | NPORT-P/A

    @property
    def primary_doc_url(self) -> str:
        return primary_doc_url_of(self.cik, self.accession)

    @property
    def is_amendment(self) -> bool:
        return self.form.upper().endswith("/A")


@dataclass(frozen=True)
class FundFacts:
    """The filing's own account of the SERIES — never of one share class.

    ``net_assets`` is the whole series'. ``class_ids`` says how many classes share it: one,
    and the ETF is the series; more, and the ETF's own assets are not in this form.
    """

    series_id: str | None
    series_name: str | None
    class_ids: tuple[str, ...]
    registrant_cik: str | None
    registrant_name: str | None
    period_date: date  # repPdDate — the date the holdings are as of
    fiscal_year_end: date | None  # repPdEnd — the filer's year end, not this report's date
    is_final_filing: bool
    total_assets: Decimal | None
    total_liabilities: Decimal | None
    net_assets: Decimal | None
    derivative_notional_usd: Decimal  # Σ|notionalAmt| — the only gearing evidence in the form

    @property
    def class_count(self) -> int:
        return len(self.class_ids)

    @property
    def derivative_notional_share(self) -> Decimal | None:
        """Σ|notional| ÷ net assets. About 2 for a three-times fund: the equity and the
        repos carry one times, the swaps the rest."""
        if not self.net_assets:
            return None
        return self.derivative_notional_usd / self.net_assets


def primary_doc_url_of(cik: str, accession: str) -> str:
    """The Archives path of a filing's ``primary_doc.xml``.

    EDGAR prints the CIK zero-padded to ten and the accession with dashes; the path wants the
    CIK's padding GONE and the accession's dashes gone. Either mistake is a 404 for every fund.
    """
    return PRIMARY_DOC_URL.format(cik=str(int(cik)), accession=accession.replace("-", ""))


def filings_url(series_id: str, count: int = 4) -> str:
    return FILINGS_URL.format(series_id=series_id, form=FORM, count=count)


def parse_filings_index(atom_bytes: bytes, series_id: str) -> list[FilingRef]:
    """The series' N-PORT filings, newest filing date first.

    EDGAR answers a series query with the REGISTRANT's ``<cik>`` in ``company-info`` — which
    is the CIK the Archives path needs — and one ``<entry>`` per filing. A series with no
    N-PORT on file (a young fund, or a unit investment trust) gets an index with no entries,
    which is an empty list and not an error.
    """
    root = ET.fromstring(atom_bytes)
    info = next((e for e in root.iter() if _local(e.tag) == "company-info"), None)
    cik = _descendant_text(info, "cik") if info is not None else None
    refs: list[FilingRef] = []
    for entry in (e for e in root.iter() if _local(e.tag) == "entry"):
        accession = _descendant_text(entry, "accession-number")
        filed = _date(_descendant_text(entry, "filing-date"), "filing-date")
        if accession is None or filed is None or cik is None:
            continue
        # filing-type is EDGAR's own word for the form (NPORT-P, NPORT-P/A); the title says
        # the same thing in prose, and is the fallback only if the field ever goes away.
        title = _descendant_text(entry, "title") or ""
        form = _descendant_text(entry, "filing-type") or title.split(" ", 1)[0] or FORM
        if not form.upper().startswith(FORM):
            continue  # the type filter is a prefix match; anything else is EDGAR's, not ours
        refs.append(
            FilingRef(series_id=series_id, cik=cik, accession=accession, filed=filed, form=form)
        )
    refs.sort(key=lambda r: (r.filed, r.accession), reverse=True)
    return refs


def _identifiers(holding: ET.Element) -> tuple[str | None, str | None, dict[str, str]]:
    """``(isin, ticker, {otherDesc: value})`` from the ``identifiers`` block.

    A ticker comes from the ``ticker`` ELEMENT, or from an ``other`` whose description IS
    "ticker" — never from one that merely contains the word. iShares labels a futures line
    ``Future Ticker`` (``ESU6 Index``); that is not an equity symbol and is kept only as an
    ``other``. Vanguard and iShares do put futures under the real ``ticker`` element
    (``ESU6``, ``TPXM26``), so a ticker is evidence and not an identity: those rows carry a
    ``derivative_category``, and holdings resolve to instruments by CUSIP and ISIN, never by
    this column.
    """
    block = _child(holding, "identifiers")
    if block is None:
        return None, None, {}
    isin: str | None = None
    ticker: str | None = None
    others: dict[str, str] = {}
    for child in block:
        name = _local(child.tag)
        value = (child.get("value") or "").strip()
        if not value or value.upper() in MISSING:
            continue
        if name == "isin":
            isin = isin or value
        elif name == "ticker":
            ticker = ticker or value
        elif name == "other":
            desc = (child.get("otherDesc") or "").strip()
            others.setdefault(desc, value)
            if desc.lower() == "ticker":
                ticker = ticker or value
    return isin, ticker, others


def _category(holding: ET.Element, element: str, conditional: str, attr: str) -> str | None:
    """``assetCat`` / ``issuerCat``, wherever the filer put it.

    The enumerated value is an element; anything off-enum is an attribute on a *Conditional*
    sibling with a free-text ``desc``. Off-enum is returned as ``OTHER/<desc>`` so the two
    cases stay distinguishable downstream and neither is silently lost.
    """
    plain = _text(holding, element)
    if plain is not None:
        return plain
    found = _child(holding, conditional)
    if found is None:
        return None
    category = (found.get(attr) or "").strip() or None
    desc = (found.get("desc") or "").strip()
    if category is None:
        return None
    return f"{category}/{desc}" if desc else category


def _derivative(holding: ET.Element) -> tuple[str | None, Decimal | None]:
    """``(derivCat, notionalAmt)`` of the one derivative on this line, if it is one.

    ``derivativeInfo`` wraps exactly one typed child — ``futrDeriv``, ``swapDeriv``,
    ``fwdDeriv``, ``optionSwaption`` and so on — carrying ``derivCat`` (FUT, SWP, …) and,
    somewhere below it, a single ``notionalAmt``.
    """
    info = _child(holding, "derivativeInfo")
    if info is None:
        return None, None
    kind = next(iter(info), None)
    if kind is None:
        return None, None
    category = (kind.get("derivCat") or "").strip() or None
    notional = next(
        (
            _decimal((n.text or "").strip() or None, "notionalAmt")
            for n in kind.iter()
            if _local(n.tag) == "notionalAmt"
        ),
        None,
    )
    return category, notional


def _currency(holding: ET.Element) -> str | None:
    """The holding's own currency. USD lines carry ``<curCd>``; a foreign line carries
    ``<currencyConditional curCd="JPY" exchangeRt="…"/>`` instead — 180 of EWJ's 182 rows.
    ``valUSD`` is US dollars either way; only this label changes."""
    plain = _text(holding, "curCd")
    if plain is not None:
        return plain
    found = _child(holding, "currencyConditional")
    if found is None:
        return None
    return (found.get("curCd") or "").strip() or None


def _holding_key(cusip: str | None, isin: str | None, others: dict[str, str], title: str) -> str:
    """The row's own identity, in the order of how widely the filers fill it in.

    CUSIP is missing on 176 of EWJ's 182 rows — Japanese equities have none — and ISIN is
    missing on 16 of VOO's 520. Neither alone is a key; the first that exists is, and a title
    is the last resort. Uniqueness WITHIN the snapshot is the caller's (:func:`parse_nport`
    suffixes repeats), because IVV really does hold one money-market CUSIP on two lines.
    """
    for candidate in (cusip, isin, *others.values()):
        if candidate:
            return candidate
    return title.strip()[:120] or "unidentified"


def _holding_rows(root: ET.Element) -> Iterator[dict[str, object]]:
    seen: Counter[str] = Counter()
    for holding in (e for e in root.iter() if _local(e.tag) == "invstOrSec"):
        cusip = _text(holding, "cusip")
        isin, ticker, others = _identifiers(holding)
        title = _text(holding, "title") or ""
        key = _holding_key(cusip, isin, others, title)
        seen[key] += 1
        if seen[key] > 1:  # one CUSIP, two lines: keep both, distinguish by occurrence
            key = f"{key}#{seen[key]}"
        pct = _decimal(_text(holding, "pctVal"), "pctVal")
        category, notional = _derivative(holding)
        yield {
            "holding_key": key,
            "holding_name": _text(holding, "name"),
            "holding_ticker": ticker,
            "cusip": cusip,
            "isin": isin,
            "lei": _text(holding, "lei"),
            "title": title or None,
            "weight_frac": None if pct is None else pct / PERCENT,
            "market_value_usd": _decimal(_text(holding, "valUSD"), "valUSD"),
            "balance": _decimal(_text(holding, "balance"), "balance"),
            "units": _text(holding, "units"),
            "currency": _currency(holding),
            "country_iso2": _iso2(_text(holding, "invCountry")),
            "asset_category": _category(holding, "assetCat", "assetConditional", "assetCat"),
            "issuer_category": _category(holding, "issuerCat", "issuerConditional", "issuerCat"),
            "payoff_profile": _text(holding, "payoffProfile"),
            "derivative_category": category,
            "notional_usd": notional,
        }


def parse_nport(xml_bytes: bytes) -> tuple[FundFacts, pd.DataFrame]:
    """``primary_doc.xml`` → ``(FundFacts, DataFrame[HOLDING_COLUMNS])``, in file order.

    Refuses a document that is not an N-PORT submission, and one with no ``repPdDate``: the
    holdings would have no date to be as of, and a snapshot without one is not a snapshot.
    A fund that reported no positions yields an EMPTY frame with the right columns — a money
    market in wind-down is a real filing, not a parse failure.
    """
    root = ET.fromstring(xml_bytes)
    if _local(root.tag) != "edgarSubmission":
        raise ValueError(f"not an EDGAR submission: root is {_local(root.tag)!r}")
    header = next((e for e in root.iter() if _local(e.tag) == "headerData"), None)
    submission = _text(header, "submissionType") or ""
    if not submission.upper().startswith(FORM):
        raise ValueError(f"not an {FORM} filing: submissionType is {submission!r}")

    general = next((e for e in root.iter() if _local(e.tag) == "genInfo"), None)
    fund = next((e for e in root.iter() if _local(e.tag) == "fundInfo"), None)
    period = _date(_text(general, "repPdDate"), "repPdDate")
    if period is None:
        raise ValueError("no repPdDate: the holdings have no date to be as of")

    series_block = next((e for e in root.iter() if _local(e.tag) == "seriesClassInfo"), None)
    class_ids = tuple(
        (c.text or "").strip()
        for c in (series_block if series_block is not None else ())
        if _local(c.tag) == "classId" and (c.text or "").strip()
    )

    frame = pd.DataFrame.from_records(list(_holding_rows(root)), columns=list(HOLDING_COLUMNS))
    notional = frame["notional_usd"].dropna()
    facts = FundFacts(
        series_id=_text(general, "seriesId") or _text(series_block, "seriesId"),
        series_name=_text(general, "seriesName"),
        class_ids=class_ids,
        registrant_cik=_text(general, "regCik"),
        registrant_name=_text(general, "regName"),
        period_date=period,
        fiscal_year_end=_date(_text(general, "repPdEnd"), "repPdEnd"),
        is_final_filing=(_text(general, "isFinalFiling") or "N").upper() == "Y",
        total_assets=_decimal(_text(fund, "totAssets"), "totAssets"),
        total_liabilities=_decimal(_text(fund, "totLiabs"), "totLiabs"),
        net_assets=_decimal(_text(fund, "netAssets"), "netAssets"),
        derivative_notional_usd=sum((abs(v) for v in notional), Decimal(0)),
    )
    return facts, frame


class NportProvider:
    """The fetch half: one index request per series, one document request per filing taken.

    ``calls`` counts requests by endpoint kind, and a failed request still counts — it spent
    the request. Request STARTS are spaced by :data:`SEC_MIN_INTERVAL_S`, the same ceiling the
    identity and company-facts readers hold themselves to.
    """

    name = "edgar"
    INDEX_ENDPOINT = "browse-edgar/nport-p"
    DOCUMENT_ENDPOINT = "Archives/nport-primary-doc"

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._identity = edgar_identity()  # read up front: a missing export costs no budget
        self._last = 0.0
        self.calls: Counter[str] = Counter()

    def _get(self, url: str, endpoint: str) -> bytes:
        self._pace()
        self.calls[endpoint] += 1
        response = self._session.get(url, headers={"User-Agent": self._identity}, timeout=TIMEOUT)
        response.raise_for_status()
        return response.content

    def _pace(self) -> None:
        gap = time.monotonic() - self._last
        if gap < SEC_MIN_INTERVAL_S:
            time.sleep(SEC_MIN_INTERVAL_S - gap)
        self._last = time.monotonic()

    def fetch_filings(self, series_id: str, count: int = 4) -> list[FilingRef]:
        """The series' most recent N-PORT filings, newest first."""
        return parse_filings_index(
            self._get(filings_url(series_id, count), self.INDEX_ENDPOINT), series_id
        )

    def fetch_primary_doc(self, ref: FilingRef) -> bytes:
        return self._get(ref.primary_doc_url, self.DOCUMENT_ENDPOINT)

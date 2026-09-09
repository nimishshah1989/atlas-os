"""SEC Form 4 ownership XML → the transactions an insider reported. Pure: no I/O, no vendor.

WHAT A FORM 4 IS. A Section 16 insider — an officer, a director, or a ten-per-cent owner —
reports a change in their holding within two business days. The document is small, structured
XML, and every field this module reads is one the SEC's own schema defines.

THE FIELD THAT DECIDES WHETHER A SALE MEANS ANYTHING. ``aff10b5One`` says the transaction was
made under a Rule 10b5-1 trading plan: a schedule the insider adopted MONTHS EARLIER, when they
were free to trade, and which then executes mechanically. Apple's 2026-09-03 filing carries it,
with the footnote naming a plan adopted on 5 May. Reading such a sale as "the insider turned
bearish this week" is precisely the confident nonsense this repository exists to keep off a
board — the decision was taken in May and the calendar, not the insider, chose the date. The
flag is machine-readable and :class:`Form4` carries it so the scorer can discount it.

TRANSACTION CODES ARE NOT ALL DECISIONS. ``P`` (open-market purchase) and ``S`` (open-market
sale) are the only two that are. ``A`` is a grant the company made, ``M`` an option exercise,
``F`` shares withheld to pay the tax on a vest, ``G`` a gift. None of those is a view on the
price, and counting them as buying or selling would make every vesting date look like insider
conviction. :data:`OPEN_MARKET` is the pair that counts.

TWO ENCODINGS OF THE SAME BOOLEAN, and a parser that misses it is silently wrong. Apple writes
``<isOfficer>true</isOfficer>``; JPMorgan writes ``<isOfficer>1</isOfficer>``. Both are valid.
A parser accepting only ``"true"`` reads every JPMorgan officer as not an officer — no error, no
missing row, just a relationship quietly lost. :func:`_flag` accepts both, and a test asserts it
on both filers' real documents.

THE DOCUMENT URL IS NOT THE ONE THE INDEX GIVES YOU. ``primaryDocument`` in the submissions
payload is ``xslF345X06/form4.xml`` — the path EDGAR serves as an HTML RENDERING (15,625 bytes
for Apple's filing). The raw XML is the same name with that prefix stripped (3,153 bytes).
:func:`document_url` strips it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

__all__ = [
    "OPEN_MARKET",
    "Form4",
    "Transaction",
    "document_url",
    "parse_form4",
]

ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

#: The two codes that are a DECISION about the price. Everything else on the form is a grant, a
#: vest, an exercise, a withholding or a gift — a corporate or tax event, not a view.
OPEN_MARKET = frozenset({"P", "S"})

#: The XSL prefix EDGAR puts on the rendered copy. ``primaryDocument`` carries it; the raw XML
#: is the same file without it.
_XSL_PREFIX = "xslF345X06/"


def document_url(cik: str | int, accession: str, primary_document: str) -> str:
    """The RAW ownership XML for a filing, from the fields the submissions index gives you.

    The accession loses its dashes in an Archives path, and the XSL prefix is stripped — see the
    module docstring for why fetching the prefixed path returns HTML instead.
    """
    document = (
        primary_document.split("/")[-1]
        if primary_document.startswith(_XSL_PREFIX)
        else primary_document
    )
    return ARCHIVES.format(cik=int(cik), accession=accession.replace("-", ""), document=document)


@dataclass(frozen=True, slots=True)
class Transaction:
    """One non-derivative transaction line."""

    seq: int
    security_title: str
    transaction_date: dt.date | None
    code: str
    shares: Decimal | None
    price_per_share: Decimal | None
    acquired_disposed: str | None
    shares_owned_after: Decimal | None

    @property
    def is_open_market(self) -> bool:
        return self.code in OPEN_MARKET

    @property
    def value_usd(self) -> Decimal | None:
        """Shares × price. ``None`` when either is missing — a grant reports no price, and a
        zero there would book a real transfer of stock as worth nothing."""
        if self.shares is None or self.price_per_share is None:
            return None
        return self.shares * self.price_per_share


@dataclass(frozen=True, slots=True)
class Form4:
    issuer_cik: str
    issuer_symbol: str
    period_of_report: dt.date | None
    owner_name: str
    owner_cik: str
    is_director: bool
    is_officer: bool
    is_ten_pct_owner: bool
    officer_title: str
    #: The transaction was made under a Rule 10b5-1 plan adopted earlier. The single most
    #: important qualifier on this form; see the module docstring.
    under_10b5_1: bool
    transactions: tuple[Transaction, ...]


def _text(node: ET.Element | None) -> str:
    return "" if node is None or node.text is None else node.text.strip()


def _value(parent: ET.Element | None, path: str) -> str:
    """A Form 4 wraps most leaves in a ``<value>`` — ``<transactionShares><value>1439</value>``.
    Some filers omit the wrapper, so both shapes are read."""
    if parent is None:
        return ""
    node = parent.find(path)
    if node is None:
        return ""
    inner = node.find("value")
    return _text(inner if inner is not None else node)


def _flag(parent: ET.Element | None, path: str) -> bool:
    """``true``/``false`` (Apple) and ``1``/``0`` (JPMorgan) are both valid. Accepting only one
    spelling loses a relationship with no error and no missing row."""
    raw = _value(parent, path).lower()
    return raw in {"true", "1", "y", "yes"}


def _date(raw: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _decimal(raw: str) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_form4(payload: bytes | str) -> Form4:
    """One ownership document → its issuer, its reporting owner and its non-derivative lines.

    Derivative transactions (options granted and exercised) are NOT read: an option grant is
    compensation and its exercise is a decision about an expiry date, neither of which is a view
    on the price. What the exercise DELIVERS shows up as a non-derivative ``M`` line, which is
    read and then excluded by ``OPEN_MARKET`` for the same reason.
    """
    root = ET.fromstring(
        payload if isinstance(payload, str) else payload.decode("utf-8", "replace")
    )
    issuer = root.find("issuer")
    owner = root.find("reportingOwner")
    owner_id = owner.find("reportingOwnerId") if owner is not None else None
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None

    transactions: list[Transaction] = []
    table = root.find("nonDerivativeTable")
    # An EMPTY table is a real filing: JPMorgan's 2026-07-08 Form 4 reports a holding with no
    # transaction at all. It is a document that happened and it moves nothing.
    if table is not None:
        for seq, node in enumerate(table.findall("nonDerivativeTransaction")):
            amounts = node.find("transactionAmounts")
            transactions.append(
                Transaction(
                    seq=seq,
                    security_title=_value(node, "securityTitle"),
                    transaction_date=_date(_value(node, "transactionDate")),
                    code=_value(node.find("transactionCoding"), "transactionCode"),
                    shares=_decimal(_value(amounts, "transactionShares")),
                    price_per_share=_decimal(_value(amounts, "transactionPricePerShare")),
                    acquired_disposed=_value(amounts, "transactionAcquiredDisposedCode") or None,
                    shares_owned_after=_decimal(
                        _value(
                            node.find("postTransactionAmounts"), "sharesOwnedFollowingTransaction"
                        )
                    ),
                )
            )

    return Form4(
        issuer_cik=_text(issuer.find("issuerCik")) if issuer is not None else "",
        issuer_symbol=_text(issuer.find("issuerTradingSymbol")) if issuer is not None else "",
        period_of_report=_date(_text(root.find("periodOfReport"))),
        owner_name=_text(owner_id.find("rptOwnerName")) if owner_id is not None else "",
        owner_cik=_text(owner_id.find("rptOwnerCik")) if owner_id is not None else "",
        is_director=_flag(rel, "isDirector"),
        is_officer=_flag(rel, "isOfficer"),
        is_ten_pct_owner=_flag(rel, "isTenPercentOwner"),
        officer_title=_value(rel, "officerTitle"),
        under_10b5_1=_flag(root, "aff10b5One"),
        transactions=tuple(transactions),
    )

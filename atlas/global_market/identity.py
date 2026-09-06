"""Identity rules for US listings — pure functions, no I/O.

The bridge between the four spellings of one listing and the ONE ``instrument_master`` row:

* **canonical** = the Nasdaq Trader **ACT symbol** (``BRK.B``, ``AAC.U``, ``AGM$D``, ``ACHR.W``,
  ``AIIA.R``; Nasdaq-listed names carry no punctuation: ``AAPL``, ``ACABW``). It is the
  ``instrument_master.symbol`` and the spelling every other source is bridged TO.
* **key** = ``us:{asset_class}:{cik}:{symbol}`` when the SEC identity is known, else
  ``us:{asset_class}:{symbol}:{listing_date}`` (:func:`instrument_key`); ``instrument_id`` =
  ``uuid5(NAMESPACE_URL, key)`` (:func:`mint`). The key is for MINTING only: build_identity
  keeps a row's uuid across re-runs and never re-derives it from a later, better estimate.
* **aliases** — how each source spells the listing (:func:`aliases_for`), one grammar rendered
  per source. Nasdaq's CQS column is the unambiguous form (the ACT column writes warrants and
  their class shares alike as ``.W`` / ``.A``; CQS says ``.WS`` / ``.WS.A``), so every rendering
  starts from the CQS spelling. Measured on the 2026-09-04 files (543 punctuation tickers):

  =========  ===========  ===========  ============  ===========  ===========
  security   ACT (canon)  CQS          Stooq         Tiingo       SEC
  =========  ===========  ===========  ============  ===========  ===========
  class B    ``BRK.B``    ``BRK.B``    ``BRK-B.US``  ``BRK-B``    ``BRK-B``
  unit       ``AAC.U``    ``AAC.U``    ``AAC-U.US``  ``AAC-U``    ``AAC-UN``
  warrant    ``ACHR.W``   ``ACHR.WS``  ``ACHR-WS.US``  ``ACHR-WS``  ``ACHR-WT``
  preferred  ``AGM$D``    ``AGMpD``    ``AGM_D.US``  ``AGM-P-D``  ``AGM-PD``
  pref, none ``ETI$``     ``ETIp``     ``ETI_.US``   ``ETI-P``    ``ETI-P``
  right      ``AIIA.R``   ``AIIAr``    ``AIIA-R.US`` ``AIIA-R``   (absent)
  =========  ===========  ===========  ============  ===========  ===========

  Stooq: 527 of the 527 punctuation tickers the archive holds round-trip; Tiingo: 542 of
  543 are in its public list under this spelling (the miss is a rights-when-issued line);
  SEC: 522 of 543 (rights are not in ``company_tickers*.json``, nor are a few new
  preferreds). A Tiingo alias is emitted only for a ticker PROVEN present
  in Tiingo's list (the caller passes the proven set); the Stooq alias is emitted for every
  row because it is the importer's lookup key and the archive is the proof.
* **names** — :func:`names_agree` is the one name comparison the planner and the frame use
  (a directory name against an SEC title, or against a stored name): the two share at least
  one significant token once form words (INC, ETF, TRUST, CLASS, …) are dropped. A heuristic,
  and reported as such; measured 2026-09-04: 117 of 7,650 directory names disagree with the
  SEC title under their ticker — bank-issued ETNs, translated foreign titles, and the stale
  SEC tickers the ``sec_conflict`` column also flags.

Nothing here reads a file or a table; the directory frame and the diff against the
database live in ``identity_frame`` / ``identity_plan`` and the script.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Collection, Mapping
from datetime import date
from typing import Any

from atlas.global_market.providers.symbology import STOOQ_MARKET_SUFFIX, stooq_symbol

ASSET_CLASSES = frozenset({"stock", "etf"})
NASDAQ = "NASDAQ"
# otherlisted.txt "Exchange" legend (nasdaqtrader.com/trader.aspx?id=symboldirdefs, read
# 2026-09-04): A = NYSE MKT, N = New York Stock Exchange, P = NYSE ARCA, Z = BATS Global
# Markets, V = Investors' Exchange. Any other code (the file's test issues carry "M") is
# refused by exchange_name() rather than guessed: an exchange is a fact, not a default.
EXCHANGE_BY_CODE: dict[str, str] = {
    "A": "NYSEMKT",
    "N": "NYSE",
    "P": "NYSEARCA",
    "Z": "BATS",
    "V": "IEX",
}
KEY_KIND_CIK = "cik"
KEY_KIND_FALLBACK = "fallback"

SOURCE_STOOQ = "stooq"
SOURCE_TIINGO = "tiingo"
SOURCE_SEC = "sec"
SOURCE_NASDAQ_SYMBOL = "nasdaq_symbol"
SOURCE_CQS = "cqs"

# Form words that carry no identity: dropped before two names are compared.
NAME_STOP_WORDS = frozenset(
    {
        "INC",
        "INCORPORATED",
        "CORP",
        "CORPORATION",
        "CO",
        "COMPANY",
        "LTD",
        "LIMITED",
        "PLC",
        "LLC",
        "LP",
        "ETF",
        "ETN",
        "TRUST",
        "FUND",
        "FUNDS",
        "THE",
        "CLASS",
        "SHARES",
        "SHARE",
        "COMMON",
        "STOCK",
        "ORDINARY",
        "OF",
        "AND",
        "A",
        "B",
        "C",
        "SERIES",
        "DEPOSITARY",
        "ADS",
        "ADR",
        "EACH",
        "REPRESENTING",
        "NEW",
        "GROUP",
        "HOLDINGS",
        "HOLDING",
    }
)

_CIK = re.compile(r"^\d{10}$")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.$]*$")
# CQS grammar: root, zero or more ".XX" components, then at most one lower-case marker —
# "p" preferred (+ optional series letter), "r" rights, "w" when-issued, "rw" rights w/i.
_CQS = re.compile(r"^(?P<root>[A-Z0-9]+)(?P<parts>(?:\.[A-Z]+)*)(?P<marker>p[A-Z]?|rw|r|w)?$")
_TOKEN = re.compile(r"[A-Z0-9]+")


# ── exchange, key, uuid ──


def exchange_name(code: str, symbol: str) -> str:
    """``otherlisted.txt`` exchange code → the ``instrument_master.exchange`` name."""
    if code not in EXCHANGE_BY_CODE:
        raise ValueError(
            f"{symbol}: exchange code {code!r} is not in the otherlisted.txt legend "
            f"{sorted(EXCHANGE_BY_CODE)} — add it from the legend, never guess"
        )
    return EXCHANGE_BY_CODE[code]


def key_kind(cik: str | None) -> str:
    return KEY_KIND_CIK if cik else KEY_KIND_FALLBACK


def instrument_key(
    asset_class: str, cik: str | None, symbol: str, listing_date: date | None
) -> str:
    """The STABLE identity string ``instrument_id`` is minted from.

    ``us:{asset_class}:{cik}:{symbol}`` when a CIK is known — the SEC registrant plus the
    ticker it trades under (a recycled ticker under a different registrant is a different
    key); otherwise ``us:{asset_class}:{symbol}:{listing_date}`` — the ticker plus the date
    it was first seen listed (Tiingo's ``startDate`` when it lists the ticker, else the run
    date), which is what separates two holders of one ticker when neither has a CIK.
    """
    if asset_class not in ASSET_CLASSES:
        raise ValueError(f"asset_class {asset_class!r} is not one of {sorted(ASSET_CLASSES)}")
    if not _SYMBOL.match(symbol):
        raise ValueError(f"not a canonical (ACT) symbol: {symbol!r}")
    if cik is not None:
        if not _CIK.match(cik):
            raise ValueError(f"{symbol}: cik must be 10 zero-padded digits, got {cik!r}")
        return f"us:{asset_class}:{cik}:{symbol}"
    if listing_date is None:
        raise ValueError(f"{symbol}: no CIK and no listing_date — the fallback key needs one")
    return f"us:{asset_class}:{symbol}:{listing_date:%Y-%m-%d}"


def mint(key: str) -> uuid.UUID:
    """``uuid5(NAMESPACE_URL, key)`` — deterministic, so the same identity string mints the
    same ``instrument_id`` on any machine, and a re-run can recognise its own rows. The RFC
    4122 URL namespace is used because the key is a URI-like path (``us:etf:…``); it is a
    fixed constant, never a per-market secret, so every market tree can reproduce an id."""
    return uuid.uuid5(uuid.NAMESPACE_URL, key)


# ── names ──


def name_tokens(name: str | None) -> frozenset[str]:
    """The significant tokens of a name: upper-cased alphanumeric runs minus the form words."""
    return frozenset(_TOKEN.findall((name or "").upper())) - NAME_STOP_WORDS


def names_agree(a: str | None, b: str | None) -> bool:
    """Two names describe one issuer when they share a significant token (``Apple Inc.`` /
    ``Apple Inc. - Common Stock``; ``C2 Blockchain, Inc.`` / ``Harbor AlphaEdge Mid Cap Core
    ETF`` do not). A name with no significant token never agrees."""
    return bool(name_tokens(a) & name_tokens(b))


# ── the CQS grammar, rendered per source ──


def parse_cqs(cqs: str) -> tuple[str, tuple[str, ...], str] | None:
    """``(root, parts, marker)``: ``NE.WS.A → ("NE", (".WS", ".A"), "")``, ``AGMpD → ("AGM",
    (), "pD")``; ``None`` outside the grammar."""
    m = _CQS.match(cqs)
    if not m:
        return None
    parts = tuple(f".{p}" for p in m.group("parts").split(".") if p)
    return m.group("root"), parts, m.group("marker") or ""


def act_from_cqs(cqs: str) -> str | None:
    """CQS → ACT (canonical): ``AGMpD → AGM$D``, ``ETIp → ETI$``, ``AIIAr → AIIA.R``,
    ``ACHR.WS → ACHR.W``, ``NE.WS.A → NE.A``, ``NMCOrw → NMCO.V``, ``BRK.B → BRK.B``.
    ``None`` when the marker has no ACT rendering on record (a bare ``w``)."""
    p = parse_cqs(cqs)
    if p is None:
        return None
    root, parts, marker = p
    parts = list(parts)
    if parts and parts[0] == ".WS":
        parts = parts[1:] if len(parts) > 1 else [".W"]
    out = root + "".join(parts)
    if marker.startswith("p"):
        return out + "$" + marker[1:]
    if marker == "r":
        return out + ".R"
    if marker == "rw":
        return out + ".V"
    return None if marker else out


def _render(cqs: str, dot: dict[str, str], marker: dict[str, str | None]) -> str | None:
    p = parse_cqs(cqs)
    if p is None:
        return None
    root, parts, mark = p
    out = root + "".join(dot.get(part, "-" + part[1:]) for part in parts)
    if not mark:
        return out
    if mark.startswith("p"):
        pref = marker["pX"] if len(mark) == 2 else marker["p"]
        return None if pref is None else out + pref.replace("X", mark[1:])
    tail = marker.get(mark)
    return None if tail is None else out + tail


def stooq_spelling(cqs: str) -> str | None:
    """CQS → Stooq ticker: ``BRK.B → BRK-B.US``, ``ACHR.WS → ACHR-WS.US``,
    ``AGMpD → AGM_D.US``, ``ETIp → ETI_.US``, ``AIIAr → AIIA-R.US``; ``None`` for a
    when-issued marker (no archive file has ever carried one)."""
    s = _render(cqs, {}, {"pX": "_X", "p": "_", "r": "-R", "w": None, "rw": None})
    return None if s is None else s + STOOQ_MARKET_SUFFIX


def tiingo_spelling(cqs: str) -> str | None:
    """CQS → Tiingo ticker: ``BRK.B → BRK-B``, ``ACHR.WS → ACHR-WS``, ``AGMpD → AGM-P-D``,
    ``ETIp → ETI-P``, ``AIIAr → AIIA-R``. Presence in Tiingo's list is the caller's proof."""
    return _render(cqs, {}, {"pX": "-P-X", "p": "-P", "r": "-R", "w": None, "rw": None})


def sec_spelling(cqs: str) -> str | None:
    """CQS → the SEC's ``company_tickers*.json`` spelling: ``BRK.B → BRK-B``,
    ``AAC.U → AAC-UN``, ``ACHR.WS → ACHR-WT``, ``AGMpD → AGM-PD``, ``ETIp → ETI-P``;
    rights and when-issued lines are not in the SEC files (``None``)."""
    return _render(
        cqs, {".U": "-UN", ".WS": "-WT"}, {"pX": "-PX", "p": "-P", "r": None, "w": None, "rw": None}
    )


def cqs_from_stooq(stooq_ticker: str) -> str | None:
    """Stooq stem or ticker → CQS: ``agm_d.us → AGMpD``, ``eti_ → ETIp``, ``aiia-r → AIIAr``,
    ``achr-ws → ACHR.WS``, ``brk-b → BRK.B``, ``spy.us → SPY``. The inverse of
    :func:`stooq_spelling`, built on ``symbology.stooq_symbol`` (``-`` → ``.``, the ``_``
    preferred marker kept); ``None`` for a stem outside Stooq's grammar."""
    try:
        s = stooq_symbol(stooq_ticker)  # AGM_D, ETI_, AIIA.R, ACHR.WS, BRK.B, SPY
    except ValueError:
        return None
    stem, pref, series = s.partition("_")
    if pref:
        return stem + "p" + series
    if stem.endswith(".R"):
        return stem[:-2] + "r"
    return stem


def canonical_from_stooq(stooq_ticker: str) -> str | None:
    """Stooq ticker → the ACT (canonical) symbol: ``AGM_D.US → AGM$D``, ``ACHR-WS.US →
    ACHR.W``, ``BRK-B.US → BRK.B``, ``SPY.US → SPY``. Used for archive members that are not
    in today's directory (delisted names), whose only spelling on record is Stooq's."""
    cqs = cqs_from_stooq(stooq_ticker)
    return None if cqs is None else act_from_cqs(cqs)


# ── aliases ──


def aliases_for(row: Mapping[str, Any], tiingo_tickers: Collection[str]) -> list[tuple[str, str]]:
    """``(source, source_symbol)`` pairs for one directory row (``symbol``, ``cqs_symbol``,
    ``nasdaq_symbol``, ``nasdaq_listed`` and, when a file matched, ``sec_ticker``).

    * ``stooq`` — always (when the CQS grammar renders): the importer's lookup key.
    * ``tiingo`` — only when the rendering is in ``tiingo_tickers``, the set of tickers the
      caller proved present in Tiingo's public list (a US exchange, priced in USD).
    * ``sec`` — the spelling that matched ``company_tickers*.json``, when one did.
    * ``nasdaq_symbol`` — Nasdaq's own symbology column (the symbol itself on nasdaqlisted).
    * ``cqs`` — the CQS column, otherlisted rows only (nasdaqlisted has none).
    """
    cqs = str(row["cqs_symbol"])
    out: list[tuple[str, str]] = []
    stooq = stooq_spelling(cqs)
    if stooq:
        out.append((SOURCE_STOOQ, stooq))
    tiingo = tiingo_spelling(cqs)
    if tiingo and tiingo in tiingo_tickers:
        out.append((SOURCE_TIINGO, tiingo))
    if row.get("sec_ticker"):
        out.append((SOURCE_SEC, str(row["sec_ticker"])))
    out.append((SOURCE_NASDAQ_SYMBOL, str(row["nasdaq_symbol"])))
    if not row["nasdaq_listed"]:
        out.append((SOURCE_CQS, cqs))
    return out

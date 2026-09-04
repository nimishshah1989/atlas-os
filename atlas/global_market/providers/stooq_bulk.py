"""Stooq bulk archive — the FM's hand-downloaded ``d_us_txt.zip`` as a ``PriceProvider``.

Stooq's bulk daily download is CAPTCHA-gated, so the FM fetches it by hand. It is a zip of
one CSV per listing::

    data/daily/us/{nasdaq|nyse|nysemkt} {etfs|stocks}[/<n>]/<ticker>.us.txt
    <TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>
    SPY.US,D,20050225,000000,92.7949,93.8716,92.7097,93.6948,79289004,0

Folder names carry spaces and numbered sub-folders, so members are found by walking the zip's
central directory, never by globbing a path. ``bars()`` opens only the requested members; the
archive is never extracted.

Why ``adjustment`` must be ``"unknown"``
---------------------------------------
Stooq documents neither whether its daily prices are raw, split-adjusted or split-and-
dividend-adjusted, nor when a file was last re-adjusted. The FM's 2026-09-04 archive shows
dividend adjustment on SPY (a 2005 close near 93.7 against ~120 raw) and fractional,
split-adjusted volumes in roughly half of all rows. A caller asking for ``"raw"``,
``"split"`` or ``"all"`` is asking for a promise the source cannot make, so this adapter
raises ``ValueError`` for them and accepts only :data:`ADJUSTMENT_UNKNOWN`. The importer
labels every row ``adjustment_source='stooq:unknown'`` and leaves ``close_adj`` /
``close_tr`` NULL until the cross-source check against Alpaca labels the file
(docs/global/data-sources.md, "Stooq importer").

Prices are ``Decimal`` built from the file's own digits — no float round-trip (money is
Decimal).
Volume is the file's value rounded to the nearest whole share (``ohlcv_daily.volume`` is a
``bigint``; the fractional part is an artefact of Stooq's split adjustment and is tallied in
:attr:`StooqBulkProvider.fractional_volume_rows`). ``trade_count`` / ``vwap`` are ``None``:
the archive has neither.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import pandas as pd

from atlas.global_market.providers.base import BAR_COLUMNS
from atlas.global_market.providers.symbology import stooq_symbol

ADJUSTMENT_UNKNOWN = "unknown"
ARCHIVE_ROOT = "data/daily/us/"
MEMBER_SUFFIX = ".us.txt"
HEADER = (
    "<TICKER>",
    "<PER>",
    "<DATE>",
    "<TIME>",
    "<OPEN>",
    "<HIGH>",
    "<LOW>",
    "<CLOSE>",
    "<VOL>",
    "<OPENINT>",
)
DAILY = "D"
_KIND = {"etfs": "etf", "stocks": "stock"}
_EXCHANGE = {"nasdaq": "NASDAQ", "nyse": "NYSE", "nysemkt": "NYSEMKT"}
_WHOLE = Decimal(1)


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    """One price file in the archive. ``(size, crc)`` is the fingerprint the importer's
    resume keys on: same fingerprint, same file, nothing to redo."""

    name: str  # zip member path, e.g. "data/daily/us/nyse etfs/2/spy.us.txt"
    stooq_ticker: str  # "SPY.US" — Stooq's own spelling, the symbol_alias(source='stooq') key
    symbol: str  # "SPY" — symbology.stooq_symbol(), the instrument_master.symbol spelling
    kind: str  # stock | etf (from the folder name)
    exchange: str  # NASDAQ | NYSE | NYSEMKT (from the folder name)
    size: int  # uncompressed bytes; 0 = Stooq shipped an empty file
    crc: int  # zip CRC-32 of the member


def parse_member_path(name: str) -> tuple[str, str, str] | None:
    """``data/daily/us/nyse etfs/2/spy.us.txt`` → ``("SPY.US", "etf", "NYSE")``.

    ``None`` for directories, non-``.us.txt`` members and anything outside the six known
    ``<exchange> <kind>`` folders — such members are not price files and are not listed.
    """
    if not name.startswith(ARCHIVE_ROOT) or not name.endswith(MEMBER_SUFFIX):
        return None
    folder, _, tail = name[len(ARCHIVE_ROOT) :].partition("/")
    exchange_word, _, kind_word = folder.partition(" ")
    exchange = _EXCHANGE.get(exchange_word)
    kind = _KIND.get(kind_word)
    if exchange is None or kind is None or not tail:
        return None
    stem = tail.rsplit("/", 1)[-1][: -len(".txt")]  # "spy.us"
    return stem.upper(), kind, exchange


def _empty() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=object) for c in BAR_COLUMNS})


def _ymd(text: str) -> date:
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


class StooqBulkProvider:
    """``PriceProvider`` over one Stooq ``d_us_txt.zip``; construct with the zip path."""

    name = "stooq_bulk"

    def __init__(self, zip_path: str | Path) -> None:
        self.path = Path(zip_path)
        if not self.path.is_file():
            raise FileNotFoundError(f"Stooq archive not found: {self.path}")
        self.calls: Counter[str] = Counter()  # zip members opened, by endpoint name
        self.fractional_volume_rows = 0  # rows whose volume had a fractional part
        self._index: dict[str, ArchiveMember] | None = None

    # ── listing ──

    def members(self) -> list[ArchiveMember]:
        """Every price file in the archive, sorted by symbol (central directory read once)."""
        return list(self._members().values())

    def list_symbols(self) -> list[tuple[str, str, str]]:
        """``(symbol, kind, exchange)`` per member, derived from the archive's folder names."""
        return [(m.symbol, m.kind, m.exchange) for m in self.members()]

    def _members(self) -> dict[str, ArchiveMember]:
        if self._index is None:
            found: dict[str, ArchiveMember] = {}
            with zipfile.ZipFile(self.path) as zf:
                for info in zf.infolist():
                    parsed = parse_member_path(info.filename)
                    if parsed is None:
                        continue
                    ticker, kind, exchange = parsed
                    symbol = stooq_symbol(ticker)
                    if symbol in found:
                        raise ValueError(
                            f"{self.path.name}: {symbol} appears twice "
                            f"({found[symbol].name}, {info.filename})"
                        )
                    found[symbol] = ArchiveMember(
                        info.filename, ticker, symbol, kind, exchange, info.file_size, info.CRC
                    )
            self._index = dict(sorted(found.items()))
        return self._index

    # ── bars ──

    def bars(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        adjustment: str,
    ) -> pd.DataFrame:
        """Daily bars for ``symbols`` (instrument_master spelling, e.g. ``BRK.B``) with
        ``start <= date <= end``, one row per (symbol, session) in :data:`BAR_COLUMNS`,
        sorted by symbol then date. Symbols absent from the archive contribute no rows;
        an empty frame with the contract columns when nothing matches.

        Only ``adjustment="unknown"`` is accepted — see the module docstring.
        """
        if adjustment != ADJUSTMENT_UNKNOWN:
            raise ValueError(
                f"StooqBulkProvider cannot honour adjustment={adjustment!r}: Stooq does not "
                f"say what adjustment its files carry. Pass {ADJUSTMENT_UNKNOWN!r}; the "
                "cross-source check against Alpaca labels the rows later."
            )
        index = self._members()
        rows: list[tuple[object, ...]] = []
        with zipfile.ZipFile(self.path) as zf:
            for symbol in sorted(dict.fromkeys(symbols)):
                member = index.get(symbol)
                if member is None:
                    continue
                self.calls["zip/member"] += 1
                self._read(zf, member, start, end, rows)
        if not rows:
            return _empty()
        return pd.DataFrame.from_records(rows, columns=list(BAR_COLUMNS))

    def _read(
        self,
        zf: zipfile.ZipFile,
        member: ArchiveMember,
        start: date,
        end: date,
        rows: list[tuple[object, ...]],
    ) -> int:
        """Append ``member``'s bars in the window to ``rows``; return how many.

        Strict on purpose: an unexpected header, a non-daily row, a ticker that is not the
        file's own, or dates out of order mean Stooq changed something — fail loudly rather
        than import a misread file. Callers are iterated in symbol order and every file is
        ascending by date, so the output is sorted by construction.
        """
        if member.size == 0:
            return 0
        n = 0
        prev: date | None = None
        with zf.open(member.name) as fh:
            reader = csv.reader(io.TextIOWrapper(fh, encoding="ascii", newline=""))
            header = next(reader, None)
            if tuple(header or ()) != HEADER:
                raise ValueError(f"{member.name}: unexpected header {header!r}")
            for row in reader:
                if len(row) != len(HEADER) or row[1] != DAILY or row[0] != member.stooq_ticker:
                    raise ValueError(f"{member.name}: not a daily bar of this file: {row!r}")
                d = _ymd(row[2])
                if prev is not None and d <= prev:
                    raise ValueError(f"{member.name}: dates not strictly increasing at {d}")
                prev = d
                if d < start or d > end:
                    continue
                rows.append(
                    (
                        member.symbol,
                        d,
                        Decimal(row[4]),
                        Decimal(row[5]),
                        Decimal(row[6]),
                        Decimal(row[7]),
                        self._volume(row[8]),
                        None,
                        None,
                    )
                )
                n += 1
        return n

    def _volume(self, text: str) -> int:
        raw = Decimal(text)
        whole = raw.quantize(_WHOLE, rounding=ROUND_HALF_EVEN)
        if whole != raw:
            self.fractional_volume_rows += 1
        return int(whole)

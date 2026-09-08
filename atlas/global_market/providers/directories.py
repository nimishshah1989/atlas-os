"""The identity directories — the ONLY network in the identity chunk (P1-A).

Six public files, plain GETs, no keys (:data:`FILES`):

* Nasdaq Trader ``nasdaqlisted.txt`` / ``otherlisted.txt`` (daily, ~07:00 ET);
* SEC ``company_tickers.json``, ``company_tickers_mf.json`` and the optional
  ``company_tickers_exchange.json`` (it added no identity the other two lacked on
  2026-09-04 — measured — so a snapshot may omit it) — under the SEC's fair-access rule: a
  ``User-Agent`` naming a real contact (``EDGAR_IDENTITY``; the fetch refuses to run without
  it) and at most 10 requests per second (:data:`SEC_MIN_INTERVAL_S` spaces request STARTS,
  the ``ingest_kite`` pattern);
* Tiingo ``supported_tickers.zip`` (its public symbol list; listing dates and the proof that
  a Tiingo spelling exists; optional in a snapshot).

Every request counts in ``calls`` (per endpoint = the URL path; a failed request included —
it spent budget; the script writes the counter to ``provider_calls``). A 429 or a 5xx is
retried ONCE after :data:`RETRY_BACKOFF_S`, then the run fails loudly. A run saves what it
fetched, byte for byte, with its sha256 into a snapshot directory (:func:`write_snapshot`) so
the identity build is reproducible from files (``build_identity.py --from-snapshot``);
:func:`read_snapshot` reads one back — the dated fixture directory
``tests/fixtures/global/symbology/`` is such a snapshot (without a manifest: provenance
``fixture``, ``fetched_at`` unknown — never a file's modification time).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import time
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from atlas.global_market.config import edgar_identity

PROVIDER_NASDAQ_TRADER = "nasdaq_trader"
PROVIDER_EDGAR = "edgar"
PROVIDER_TIINGO = "tiingo"

NASDAQ_LISTED = "nasdaqlisted.txt"
OTHER_LISTED = "otherlisted.txt"
SEC_COMPANY_TICKERS = "company_tickers.json"
SEC_COMPANY_TICKERS_MF = "company_tickers_mf.json"
SEC_COMPANY_TICKERS_EXCHANGE = "company_tickers_exchange.json"
TIINGO_SUPPORTED_TICKERS = "supported_tickers.zip"

# file name → (provider, url); the provider_calls endpoint is the URL path (endpoint()).
FILES: dict[str, tuple[str, str]] = {
    NASDAQ_LISTED: (
        PROVIDER_NASDAQ_TRADER,
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    ),
    OTHER_LISTED: (
        PROVIDER_NASDAQ_TRADER,
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    ),
    SEC_COMPANY_TICKERS: (PROVIDER_EDGAR, "https://www.sec.gov/files/company_tickers.json"),
    SEC_COMPANY_TICKERS_MF: (PROVIDER_EDGAR, "https://www.sec.gov/files/company_tickers_mf.json"),
    SEC_COMPANY_TICKERS_EXCHANGE: (
        PROVIDER_EDGAR,
        "https://www.sec.gov/files/company_tickers_exchange.json",
    ),
    TIINGO_SUPPORTED_TICKERS: (
        PROVIDER_TIINGO,
        "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip",
    ),
}
OPTIONAL = frozenset({SEC_COMPANY_TICKERS_EXCHANGE, TIINGO_SUPPORTED_TICKERS})
REQUIRED = tuple(n for n in FILES if n not in OPTIONAL)

SEC_MIN_INTERVAL_S = 0.11  # ≥ 0.11 s between request starts ≈ 9/s (SEC ceiling 10/s)
TIMEOUT_S = 120
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RETRY_BACKOFF_S = 60  # courtesy wait before the ONE retry (SOURCE.md: a 429 cleared in a minute)
USER_AGENT = "atlas-os identity (github.com/nimishshah1989/atlas-os)"
MANIFEST = "MANIFEST.json"
PROVENANCE_FETCHED = "fetched"
PROVENANCE_SNAPSHOT = "snapshot"  # read back with the manifest a fetch wrote
PROVENANCE_FIXTURE = "fixture"  # files without a manifest: fetch times unknown
_DATED_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def endpoint(name: str) -> str:
    """The ``provider_calls`` endpoint key for a file: its URL path."""
    return urlparse(FILES[name][1]).path.lstrip("/")


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The files (bytes, verbatim), their hashes, when each was fetched, and how we know."""

    files: dict[str, bytes]
    sha256s: dict[str, str]
    fetched_at: dict[str, str | None]  # ISO-8601 UTC per file; None when unknown
    provenance: str  # fetched | snapshot | fixture

    def text(self, name: str) -> str:
        return self.files[name].decode("utf-8")

    def tiingo_csv(self) -> str | None:
        """The Tiingo list as CSV text from the zip; ``None`` when the snapshot lacks it."""
        if TIINGO_SUPPORTED_TICKERS not in self.files:
            return None
        with zipfile.ZipFile(io.BytesIO(self.files[TIINGO_SUPPORTED_TICKERS])) as zf:
            (member,) = zf.namelist()
            return zf.read(member).decode("utf-8")


class DirectoryProvider:
    """Fetches the files in :data:`FILES`; ``calls`` counts requests per endpoint. The
    clock and the sleep are injectable so the pacing and the retry are testable."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session or requests.Session()
        self._clock = clock
        self._sleep = sleep
        self._identity: str | None = None  # resolved lazily: Nasdaq/Tiingo need none
        self._last_sec_call = float("-inf")
        self.calls: Counter[str] = Counter()

    def fetch(self, name: str) -> bytes:
        """One file's bytes. A 429 / 5xx is retried once after :data:`RETRY_BACKOFF_S`;
        anything else than a 200 with a body raises."""
        provider, url = FILES[name]
        headers = {"User-Agent": self._user_agent(provider), "Accept-Encoding": "gzip, deflate"}
        for attempt in (1, 2):
            self._pace(provider)
            self.calls[endpoint(name)] += 1
            resp = self._session.get(url, headers=headers, timeout=TIMEOUT_S)
            if resp.status_code == 200:
                if not resp.content:
                    raise RuntimeError(f"{provider} {endpoint(name)}: empty response")
                return resp.content
            if resp.status_code in RETRY_STATUSES and attempt == 1:
                self._sleep(RETRY_BACKOFF_S)
                continue
            raise RuntimeError(
                f"{provider} {endpoint(name)}: HTTP {resp.status_code}"
                + (" (SEC rate threshold — wait ten minutes)" if resp.status_code == 429 else "")
            )
        raise AssertionError("unreachable")

    def fetch_all(self) -> Snapshot:
        """Every file, in :data:`FILES` order; the SEC identity is checked BEFORE the first
        request so a missing ``EDGAR_IDENTITY`` fails without spending anyone's budget."""
        self._user_agent(PROVIDER_EDGAR)
        files: dict[str, bytes] = {}
        fetched: dict[str, str | None] = {}
        for name in FILES:
            files[name] = self.fetch(name)
            fetched[name] = datetime.now(UTC).isoformat(timespec="seconds")
        hashes = {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}
        return Snapshot(files, hashes, fetched, PROVENANCE_FETCHED)

    # ── plumbing ──

    def _user_agent(self, provider: str) -> str:
        """SEC requests carry the fair-access contact; the others a plain product string."""
        if provider != PROVIDER_EDGAR:
            return USER_AGENT
        if self._identity is None:
            self._identity = edgar_identity()
        return self._identity

    def _pace(self, provider: str) -> None:
        if provider != PROVIDER_EDGAR:
            return
        gap = self._clock() - self._last_sec_call
        if gap < SEC_MIN_INTERVAL_S:
            self._sleep(SEC_MIN_INTERVAL_S - gap)
        self._last_sec_call = self._clock()


# ── snapshots ──


def write_snapshot(directory: Path, snap: Snapshot) -> Path:
    """Save every file verbatim plus ``MANIFEST.json`` (sha256, url, fetched_at, bytes)."""
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict[str, str | int | None]] = {}
    for name, data in snap.files.items():
        (directory / name).write_bytes(data)
        manifest[name] = {
            "sha256": snap.sha256s[name],
            "url": FILES[name][1],
            "fetched_at": snap.fetched_at.get(name),
            "bytes": len(data),
        }
    path = directory / MANIFEST
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def read_snapshot(directory: Path) -> Snapshot:
    """Read a snapshot back: the :data:`REQUIRED` files must be present, the optional ones
    are taken when there. Hashes are recomputed from the bytes, never trusted from the
    manifest; ``fetched_at`` comes from the manifest when there is one, else stays unknown
    (``None``) and the provenance is ``fixture``."""
    missing = [n for n in REQUIRED if not (directory / n).is_file()]
    if missing:
        raise FileNotFoundError(f"{directory}: snapshot lacks {missing}")
    manifest: dict[str, dict[str, str]] | None = None
    if (directory / MANIFEST).is_file():
        manifest = json.loads((directory / MANIFEST).read_text())
    files = {n: (directory / n).read_bytes() for n in FILES if (directory / n).is_file()}
    fetched = {n: (manifest or {}).get(n, {}).get("fetched_at") or None for n in files}
    hashes = {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}
    provenance = PROVENANCE_FIXTURE if manifest is None else PROVENANCE_SNAPSHOT
    return Snapshot(files, hashes, fetched, provenance)


def prune_snapshots(parent: Path, keep: int) -> list[Path]:
    """Remove the dated (``YYYY-MM-DD``) snapshot directories under ``parent`` beyond the
    newest ``keep``; returns what was removed. Anything not named as a date is left alone."""
    dated = sorted(p for p in parent.iterdir() if p.is_dir() and _DATED_DIR.match(p.name))
    stale = dated[: max(len(dated) - keep, 0)]
    for p in stale:
        shutil.rmtree(p)
    return stale

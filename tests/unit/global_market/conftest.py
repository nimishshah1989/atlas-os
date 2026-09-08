"""Shared fixtures of the global-market unit tests: the LIVE SSGA workbooks, fetched (or read
from the daily cache) once per session, parsed once — and, below, the identity chunk's
REAL-snapshot frames (``tests/fixtures/global/symbology/``), parsed once per module.

Marker discipline, enforced at collection: a test whose fixture closure reaches one of
``LIVE_FIXTURES`` (directly, or through ``live_cache`` as the fja05680 downloads do) must
carry ``live`` and must NOT carry ``unit`` — ``make test`` / ``make gate`` (``-m unit``) stay
fast and offline; ``make test-live`` (``-m live``, ``ATLAS_LIVE_FIXTURES=required``) runs
the fetching tests and fails, never skips, when a source is unreachable.
"""

from __future__ import annotations

import os
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from atlas.global_market import identity_frame as frame_mod
from atlas.global_market.providers.ssga import (
    HOLDINGS_URL,
    SECTOR_ETFS,
    SPY,
    holdings_endpoint,
    parse_holdings,
    parse_sector_holdings,
)
from atlas.global_market.providers.symbology import (
    parse_nasdaq_symbol_directory,
    parse_sec_company_tickers,
    parse_sec_company_tickers_mf,
    parse_tiingo_supported_tickers,
)
from tests.unit.global_market.live_files import cache_dir, fetch_or_skip

LIVE_FIXTURES = frozenset(
    {"live_cache", "spy_bytes", "spy_holdings", "sector_holdings", "sector_frames"}
)
HERE = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def live_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return cache_dir(tmp_path_factory)


@pytest.fixture(scope="session")
def spy_bytes(live_cache: Path) -> bytes:
    url = HOLDINGS_URL.format(ticker=SPY.lower())
    return fetch_or_skip(url, holdings_endpoint(SPY), live_cache).read_bytes()


@pytest.fixture(scope="session")
def spy_holdings(spy_bytes: bytes) -> tuple[date, pd.DataFrame]:
    return parse_holdings(spy_bytes, SPY)


@pytest.fixture(scope="session")
def sector_holdings(live_cache: Path) -> dict[str, tuple[date, pd.DataFrame]]:
    """The eleven Select Sector SPDR workbooks → ``{etf: (as_of, ticker rows)}``."""
    out: dict[str, tuple[date, pd.DataFrame]] = {}
    for etf in SECTOR_ETFS:
        url = HOLDINGS_URL.format(ticker=etf.lower())
        path = fetch_or_skip(url, holdings_endpoint(etf), live_cache)
        out[etf] = parse_sector_holdings(path.read_bytes(), etf)
    return out


@pytest.fixture(scope="session")
def sector_frames(sector_holdings: dict[str, tuple[date, pd.DataFrame]]) -> dict[str, pd.DataFrame]:
    return {etf: df for etf, (_, df) in sector_holdings.items()}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if not isinstance(item, pytest.Function) or not item.path.is_relative_to(HERE):
            continue
        if not LIVE_FIXTURES & set(item.fixturenames):
            continue
        marks = {m.name for m in item.iter_markers()}
        if "live" not in marks or "unit" in marks:
            raise pytest.UsageError(
                f"{item.nodeid} reaches a live file: mark it `live`, not `unit` "
                "(tests/unit/global_market/conftest.py)"
            )


# ── the identity snapshot: test_identity / _identity_frame / _identity_plan / _directories ──
# Every fixture reads the dated verbatim snapshot (``SYMBOLOGY_DIR=<dir>`` points at fresher
# downloads; provenance in its SOURCE.md). A missing file SKIPS the tests that need it —
# never a vacuous pass (rule #0: no fabricated fixture, no invented record).

_SNAPSHOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "symbology"
SYMBOLOGY_DIR = Path(os.environ.get("SYMBOLOGY_DIR", "") or str(_SNAPSHOT))
RUN_DATE = date(2026, 9, 4)  # the snapshot's own date


def _read(name: str) -> str:
    path = SYMBOLOGY_DIR / name
    if not path.is_file():
        pytest.skip(f"{path} missing — the real snapshot file is the only fixture")
    return path.read_text()


@pytest.fixture(scope="module")
def symbology_dir() -> Path:
    return SYMBOLOGY_DIR


@pytest.fixture(scope="module")
def nasdaq() -> pd.DataFrame:
    return parse_nasdaq_symbol_directory(_read("nasdaqlisted.txt"))


@pytest.fixture(scope="module")
def other() -> pd.DataFrame:
    return parse_nasdaq_symbol_directory(_read("otherlisted.txt"))


@pytest.fixture(scope="module")
def company_tickers() -> pd.DataFrame:
    return parse_sec_company_tickers(_read("company_tickers.json"))


@pytest.fixture(scope="module")
def company_tickers_mf() -> pd.DataFrame:
    return parse_sec_company_tickers_mf(_read("company_tickers_mf.json"))


@pytest.fixture(scope="module")
def tiingo() -> pd.DataFrame:
    path = SYMBOLOGY_DIR / "supported_tickers.zip"
    if not path.is_file():
        pytest.skip(f"{path} missing — the real snapshot file is the only fixture")
    with zipfile.ZipFile(path) as zf:
        (member,) = zf.namelist()
        return parse_tiingo_supported_tickers(zf.read(member).decode("utf-8"))


@pytest.fixture(scope="module")
def directory(nasdaq: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    return frame_mod.directory_frame(nasdaq, other)


@pytest.fixture(scope="module")
def with_sec(
    directory: pd.DataFrame, company_tickers: pd.DataFrame, company_tickers_mf: pd.DataFrame
) -> pd.DataFrame:
    return frame_mod.attach_sec(directory, company_tickers, company_tickers_mf)


@pytest.fixture(scope="module")
def listings(tiingo: pd.DataFrame) -> pd.DataFrame:
    return frame_mod.tiingo_listings(tiingo)


@pytest.fixture(scope="module")
def tiingo_tickers(listings: pd.DataFrame) -> frozenset[str]:
    """The tickers proven present in Tiingo's list on a US exchange, in USD."""
    return frozenset(listings["ticker"])


@pytest.fixture(scope="module")
def desired(with_sec: pd.DataFrame, listings: pd.DataFrame) -> pd.DataFrame:
    """The full desired frame as build_identity assembles it for the snapshot's run date."""
    return frame_mod.attach_listing_dates(with_sec, listings, RUN_DATE)

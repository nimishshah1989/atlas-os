"""Unit tests for scripts/foundation/etf_sector.py — the name→sector classifier that
gives every tradeable ETF a sector.

RULE #0: every (symbol, name) pair below is a REAL row from
`atlas_foundation.instrument_master` where asset_class='etf' AND is_active
(snapshot 2026-07-30, 318 rows). No name is invented.

Why this exists: 318 active ETFs had a NULL sector and de_etf_master only covers 43
of them, so the FM's model portfolios rendered ~43% of their weight as "Unmapped" on
the sector pie. An ETF's underlying index is encoded in its name, so the sector is
derivable rather than something to hand-maintain.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# pyright cannot see scripts/foundation (not on extraPaths — adding it would newly
# type-check unrelated modules), but the sys.path insert above makes this work at runtime.
from etf_sector import etf_sector  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.unit


# --- commodity: the asset IS the sector -------------------------------------
@pytest.mark.parametrize(
    ("symbol", "name"),
    [
        ("GOLD360", "360 ONE GOLD ETF"),
        ("AONEGOLD", "ANGEL ONE GOLD ETF"),
        ("BSLGOLDETF", "BIRLA SUN LIFE GOLD ETF"),
        ("GOLDAXIS", "AXISAMC-GOLDAXIS"),  # vendor-mangled name, no "ETF" token
    ],
)
def test_gold_etfs_classify_as_gold(symbol: str, name: str) -> None:
    assert etf_sector(symbol, name) == "Gold"


@pytest.mark.parametrize(
    ("symbol", "name"),
    [
        ("SILVER360", "360 ONE SILVER ETF"),
        ("AONESILVER", "AONEAMC - AONESILVER"),
        ("SILVERAXIS", "AXISAMC-SILVERAXIS"),
    ],
)
def test_silver_etfs_classify_as_silver(symbol: str, name: str) -> None:
    assert etf_sector(symbol, name) == "Silver"


# --- cash and debt must beat the index token in the same name ---------------
@pytest.mark.parametrize(
    ("symbol", "name"),
    [
        ("AONELIQUID", "ANGEL ONE NIFTY 1D RATE LIQUID ETF - GROWTH"),
        ("ABSLLIQUID", "ADITYA BIRLA SUN LIFE CRISIL LIQUID OVERNIGHT ETF"),
        ("LIQUIDADD", "DSP BSE LIQUID RATE ETF"),
    ],
)
def test_liquid_etfs_are_debt_not_broad_index(symbol: str, name: str) -> None:
    # "NIFTY 1D RATE LIQUID" contains NIFTY — cash must win over the index token.
    assert etf_sector(symbol, name) == "Debt"


@pytest.mark.parametrize(
    ("symbol", "name"),
    [
        ("EBBETF0430", "BHARAT BOND ETF - APRIL 2030"),
        ("BBETF0432", "BHARAT BOND ETF - APRIL 2032"),
        ("ABGSEC", "ADITYA BIRLA SUN LIFE CRISIL BROAD BASED GILT ETF"),
        ("SETF10GILT", "SBI-ETF NIFTY 10 YR BENCHMARK G-SEC"),
        ("LIQUIDBEES", "NIPPON INDIA ETF NIFTY 1D RATE LIQUID BEES"),
    ],
)
def test_bond_and_gilt_etfs_classify_as_debt(symbol: str, name: str) -> None:
    assert etf_sector(symbol, name) == "Debt"


# --- sectoral ETFs map onto the canonical 21 -------------------------------
@pytest.mark.parametrize(
    ("symbol", "name", "expected"),
    [
        ("ABSLBANETF", "ADITYA BIRLA SUN LIFE NIFTY BANK ETF", "Banking"),
        ("BANKBETF", "BAJAJ FINSERV NIFTY BANK ETF", "Banking"),
        ("BANKPSU", "MIRAE ASSET NIFTY PSU BANK ETF", "Banking"),
        ("BNKETFAXIS", "AXISAMC-BNKETFAXIS", "Banking"),  # only "BNK", no "BANK"
        ("TECH", "ADITYA BIRLA SUN LIFE NIFTY IT ETF", "IT"),
        ("AXISTECETF", "AXIS NIFTY IT ETF", "IT"),
        ("HEALTHY", "ADITYA BIRLA SUN LIFE NIFTY HEALTHCARE ETF", "Healthcare"),
        ("AXISHCETF", "AXIS NIFTY HEALTHCARE ETF", "Healthcare"),
        ("PHARMABEES", "NIPPON INDIA NIFTY PHARMA ETF", "Pharma"),
        ("MOREALTY", "MOTILAL OSWAL NIFTY REALTY ETF", "Realty"),
        ("CHEMICAL", "KOTAK NIFTY CHEMICALS ETF", "Chemicals"),
        ("AUTOIETF", "ICICI PRUDENTIAL NIFTY AUTO ETF", "Automobile"),
        ("AXISCETF", "AXIS NIFTY INDIA CONSUMPTION ETF", "FMCG"),
        ("BFSI", "MIRAE ASSET NIFTY FINANCIAL SERVICES ETF", "Financial Services"),
        ("MODEFENCE", "MOTILAL OSWAL NIFTY INDIA DEFENCE ETF", "Defence"),
        ("MOENERGY", "MOTILAL OSWAL NIFTY ENERGY ETF", "Energy"),
        ("MOCAPITAL", "MOTILAL OSWAL NIFTY CAPITAL MARKET ETF", "Capital Markets"),
    ],
)
def test_sectoral_etfs_map_to_canonical_sectors(symbol: str, name: str, expected: str) -> None:
    assert etf_sector(symbol, name) == expected


# --- smart-beta is a factor bet, not a plain index -------------------------
@pytest.mark.parametrize(
    ("symbol", "name"),
    [
        ("MOMENTUM", "ADITYA BIRLA SUN LIFE NIFTY 200 MOMENTUM 30 ETF"),
        ("NIFTYQLITY", "ADITYA BIRLA SUN LIFE NIFTY 200 QUALITY 30 ETF"),
        ("AXISVALUE", "AXIS NIFTY500 VALUE 50 ETF"),
        ("VALUEAXIS", "AXISAMC-VALUEAXIS"),
        ("ALPHA", "KOTAK NIFTY ALPHA 50 ETF"),
    ],
)
def test_smart_beta_etfs_are_diversified_equity(symbol: str, name: str) -> None:
    # Smart beta is diversified equity, so it shares the Broad Index bucket rather
    # than being forced onto a sector it does not track.
    assert etf_sector(symbol, name) == "Broad Index"


# --- state-owned baskets ---------------------------------------------------
@pytest.mark.parametrize(
    ("symbol", "name"),
    [
        ("CPSEETF", "CPSE ETF"),
        ("ABSLPSE", "ADITYA BIRLA SUN LIFE NIFTY PSE ETF"),
        ("ICICIB22", "BHARAT 22 ETF"),
    ],
)
def test_state_owned_baskets_are_diversified_equity(symbol: str, name: str) -> None:
    # CPSE/Bharat 22 span energy, banking and metals — no single sector is truthful.
    assert etf_sector(symbol, name) == "Broad Index"


# --- plain market-cap trackers --------------------------------------------
@pytest.mark.parametrize(
    ("symbol", "name"),
    [
        ("AXISNIFTY", "AXIS NIFTY 50 ETF"),
        ("AXSENSEX", "AXIS BSE SENSEX ETF"),
        ("SENSEXAXIS", "AXISAMC-SENSEXAXIS"),
        ("AONETOTAL", "ANGEL ONE NIFTY TOTAL MARKET ETF"),
        ("HDFCSML250", "HDFC NIFTY SMALLCAP 250 ETF"),
        ("MID150BEES", "NIPPON INDIA ETF NIFTY MIDCAP 150"),
        ("MSCIADD", "DSP MSCI INDIA ETF"),
        ("ABSLNN50ET", "ADITYA BIRLA SUN LIFE NIFTY NEXT 50 ETF"),
    ],
)
def test_cap_trackers_classify_as_broad_index(symbol: str, name: str) -> None:
    assert etf_sector(symbol, name) == "Broad Index"


@pytest.mark.parametrize(
    ("symbol", "name"),
    [
        ("HNGSNGBEES", "NIPPON INDIA ETF HANG SENG BEES"),
        ("MAFANG", "MIRAE ASSET NYSE FANG+ ETF"),  # NYSE-listed basket, not Indian
    ],
)
def test_overseas_trackers_classify_as_international(symbol: str, name: str) -> None:
    assert etf_sector(symbol, name) == "International"


def test_financial_services_ex_bank_is_not_misread_as_banking() -> None:
    # The name literally contains "BANK" ("EX-BANK") — Financial Services must win.
    assert (
        etf_sector("FINIETF", "ICICI PRUDENTIAL NIFTY FINANCIAL SERVICES EX-BANK ETF")
        == "Financial Services"
    )


def test_every_classification_is_a_non_empty_string() -> None:
    # The backfill asserts 100% coverage, so the classifier must never return None.
    assert etf_sector("WHOKNOWS", "SOME UNRECOGNISED ETF") == "Broad Index"


def test_label_vocabulary_is_canonical_21_plus_five_asset_classes() -> None:
    """FM decision 2026-07-30: sectoral ETFs use the canonical 21; everything with no
    equity sector collapses to exactly five asset-class labels. Anything else would
    re-introduce the inconsistent vocabulary this module exists to remove."""
    from etf_sector import _NON_SECTORAL  # pyright: ignore[reportMissingImports]

    assert _NON_SECTORAL == {"Gold", "Silver", "Debt", "Broad Index", "International"}

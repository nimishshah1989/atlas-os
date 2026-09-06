"""The identity rules (atlas.global_market.identity), proven on the REAL directory rows.

The key/uuid rules are pure string arithmetic and are tested as such. Every spelling rule is
asserted against the dated verbatim snapshot in ``tests/fixtures/global/symbology/`` (the
frames come from ``conftest.py``): the Nasdaq Trader files supply the ACT/CQS/NASDAQ columns,
Tiingo's list and the SEC files supply the proof that a rendered alias exists (rule #0: no
invented ticker). Without the files the file-backed tests skip; they never pass vacuously.
"""

from __future__ import annotations

import uuid
from datetime import date

import pandas as pd
import pytest

from atlas.global_market import identity as ident

pytestmark = pytest.mark.unit

# The plan's "20 punctuation tickers": (ACT, CQS, NASDAQ, Stooq, Tiingo, SEC) as the real
# 2026-09-04 files spell them. None is "this source has no spelling for the line".
PUNCTUATION_ROWS = [
    ("BRK.B", "BRK.B", "BRK.B", "BRK-B.US", "BRK-B", "BRK-B"),
    ("AKO.A", "AKO.A", "AKO.A", "AKO-A.US", "AKO-A", "AKO-A"),
    ("AKO.B", "AKO.B", "AKO.B", "AKO-B.US", "AKO-B", "AKO-B"),
    ("AGM.A", "AGM.A", "AGM.A", "AGM-A.US", "AGM-A", "AGM-A"),
    ("AAC.U", "AAC.U", "AAC=", "AAC-U.US", "AAC-U", "AAC-UN"),
    ("AIIA.U", "AIIA.U", "AIIA=", "AIIA-U.US", "AIIA-U", "AIIA-UN"),
    ("ALUB.U", "ALUB.U", "ALUB=", "ALUB-U.US", "ALUB-U", "ALUB-UN"),
    ("ACHR.W", "ACHR.WS", "ACHR+", "ACHR-WS.US", "ACHR-WS", "ACHR-WT"),
    ("AAC.W", "AAC.WS", "AAC+", "AAC-WS.US", "AAC-WS", "AAC-WT"),
    ("ALUB.W", "ALUB.WS", "ALUB+", "ALUB-WS.US", "ALUB-WS", "ALUB-WT"),
    ("NE.A", "NE.WS.A", "NE+A", "NE-WS-A.US", "NE-WS-A", "NE-WT-A"),
    ("AIIA.R", "AIIAr", "AIIA^", "AIIA-R.US", "AIIA-R", None),
    ("AGM$D", "AGMpD", "AGM-D", "AGM_D.US", "AGM-P-D", "AGM-PD"),
    ("AGM$E", "AGMpE", "AGM-E", "AGM_E.US", "AGM-P-E", "AGM-PE"),
    ("ABR$D", "ABRpD", "ABR-D", "ABR_D.US", "ABR-P-D", "ABR-PD"),
    ("ALL$B", "ALLpB", "ALL-B", "ALL_B.US", "ALL-P-B", "ALL-PB"),
    ("ETI$", "ETIp", "ETI-", "ETI_.US", "ETI-P", "ETI-P"),
    ("TY$", "TYp", "TY-", "TY_.US", "TY-P", "TY-P"),
    ("DCOM$", "DCOMp", "DCOM-", "DCOM_.US", "DCOM-P", "DCOM-P"),
    ("NMCO.V", "NMCOrw", "NMCO^#", None, None, None),
]


# ── key + uuid (pure) ──


def test_key_uses_the_cik_when_known() -> None:
    assert ident.instrument_key("etf", "0000884394", "SPY", None) == "us:etf:0000884394:SPY"
    assert ident.instrument_key("stock", "0001067983", "BRK.B", date(2026, 9, 4)) == (
        "us:stock:0001067983:BRK.B"
    )


def test_key_falls_back_to_symbol_and_listing_date() -> None:
    # BZZ: a real 2026-09-04 ETF with no SEC row and no Tiingo row — the run date is its date.
    assert ident.instrument_key("etf", None, "BZZ", date(2026, 9, 4)) == "us:etf:BZZ:2026-09-04"
    with pytest.raises(ValueError, match="listing_date"):
        ident.instrument_key("etf", None, "BZZ", None)


@pytest.mark.parametrize(
    ("asset_class", "cik", "symbol"),
    [("fund", "0000884394", "SPY"), ("etf", "884394", "SPY"), ("etf", "0000884394", "spy")],
)
def test_key_refuses_malformed_inputs(asset_class: str, cik: str, symbol: str) -> None:
    with pytest.raises(ValueError):
        ident.instrument_key(asset_class, cik, symbol, None)


def test_mint_is_uuid5_over_the_url_namespace() -> None:
    key = "us:etf:0000884394:SPY"
    assert ident.mint(key) == uuid.uuid5(uuid.NAMESPACE_URL, key)
    assert ident.mint(key) == ident.mint(key)  # deterministic
    assert ident.mint(key) != ident.mint("us:etf:0000884394:SPY ")  # the string is the identity


def test_key_kind() -> None:
    assert ident.key_kind("0000884394") == "cik"
    assert ident.key_kind(None) == "fallback"
    assert ident.key_kind("") == "fallback"


def test_exchange_legend_is_the_files_own_and_unknown_codes_are_refused() -> None:
    assert ident.exchange_name("P", "SPY") == "NYSEARCA"
    assert ident.exchange_name("N", "BRK.B") == "NYSE"
    assert ident.exchange_name("Z", "X") == "BATS"
    assert ident.exchange_name("A", "X") == "NYSEMKT"
    with pytest.raises(ValueError, match="legend"):
        ident.exchange_name("M", "MTEST")


# ── names (the real 2026-09-04 directory names and SEC titles) ──


def test_names_agree_on_a_shared_significant_token() -> None:
    assert ident.names_agree("Apple Inc. - Common Stock", "Apple Inc.")
    assert ident.names_agree("Berkshire Hathaway Inc. New Common Stock", "BERKSHIRE HATHAWAY INC")
    # AEMC: the directory's ETF vs the stale company_tickers registrant under that ticker.
    assert not ident.names_agree("Harbor AlphaEdge Mid Cap Core ETF", "C2 Blockchain, Inc.")
    # ISRL: the ETF and the SPAC that used the ticker before it share ISRAEL — the token
    # rule calls that agreement; the sec_conflict column is what flags the ticker.
    assert ident.names_agree("Defiance KSM Israel 120 ETF", "Israel Acquisitions Corp")
    # Form words alone never agree; a missing name never agrees.
    assert ident.name_tokens("The Class A Common Shares Inc.") == frozenset()
    assert not ident.names_agree("Corgi Drones & Urban Air Mobility ETF", None)


# ── spellings on the 20 punctuation tickers ──


@pytest.mark.parametrize(("act", "cqs", "nasdaq", "stooq", "tiingo", "sec"), PUNCTUATION_ROWS)
def test_each_source_spelling_renders_from_the_cqs_form(
    act: str, cqs: str, nasdaq: str, stooq: str | None, tiingo: str | None, sec: str | None
) -> None:
    assert ident.act_from_cqs(cqs) == act
    assert ident.stooq_spelling(cqs) == stooq
    assert ident.tiingo_spelling(cqs) == tiingo
    assert ident.sec_spelling(cqs) == sec
    if stooq is not None:
        assert ident.cqs_from_stooq(stooq) == cqs  # round trip
        assert ident.canonical_from_stooq(stooq) == act


def test_plain_tickers_render_unchanged() -> None:
    for s in ("SPY", "QQQ", "AAPL", "ACABW"):
        assert ident.stooq_spelling(s) == f"{s}.US"
        assert ident.tiingo_spelling(s) == s
        assert ident.sec_spelling(s) == s
        assert ident.canonical_from_stooq(f"{s.lower()}.us") == s
    assert ident.cqs_from_stooq("SPY.UK") is None  # outside Stooq's US grammar


# ── the real directory: every row, both directions ──


@pytest.fixture(scope="module")
def sec_tickers(company_tickers: pd.DataFrame) -> frozenset[str]:
    return frozenset(company_tickers["ticker"])


class TestRealDirectory:
    def test_the_act_symbol_is_recovered_from_every_cqs_symbol(self, other: pd.DataFrame) -> None:
        pairs = list(zip(other["act_symbol"], other["cqs_symbol"], strict=True))
        assert len(pairs) > 7000
        assert [(a, c) for a, c in pairs if ident.act_from_cqs(c) != a] == []

    def test_stooq_spelling_round_trips_on_every_row(self, other: pd.DataFrame) -> None:
        misses = []
        no_rule = []
        for act, cqs in zip(other["act_symbol"], other["cqs_symbol"], strict=True):
            stooq = ident.stooq_spelling(cqs)
            if stooq is None:
                no_rule.append(act)
            elif ident.cqs_from_stooq(stooq) != cqs or ident.canonical_from_stooq(stooq) != act:
                misses.append(act)
        assert misses == []
        assert no_rule == ["NMCO.V"]  # rights when-issued: no Stooq file has ever carried one

    def test_the_punctuation_rows_are_in_the_file_as_listed_above(
        self, other: pd.DataFrame
    ) -> None:
        by_act = dict(zip(other["act_symbol"], other["cqs_symbol"], strict=True))
        by_nasdaq = dict(zip(other["act_symbol"], other["nasdaq_symbol"], strict=True))
        for act, cqs, nasdaq, _s, _t, _e in PUNCTUATION_ROWS:
            assert by_act[act] == cqs, act
            assert by_nasdaq[act] == nasdaq, act

    def test_tiingo_lists_all_but_one_punctuation_ticker(
        self, other: pd.DataFrame, tiingo: pd.DataFrame
    ) -> None:
        listed = frozenset(tiingo["ticker"])  # every row, any exchange
        punct = [
            c
            for a, c in zip(other["act_symbol"], other["cqs_symbol"], strict=True)
            if not a.isalnum()
        ]
        assert len(punct) >= 500
        missing = [c for c in punct if (ident.tiingo_spelling(c) or "") not in listed]
        assert missing == ["NMCOrw"]
        assert "AGM-D" not in listed  # the NASDAQ-column spelling is NOT Tiingo's

    def test_sec_lists_the_preferreds_units_and_warrants_but_no_rights(
        self, other: pd.DataFrame, sec_tickers: frozenset[str]
    ) -> None:
        rows = list(zip(other["act_symbol"], other["cqs_symbol"], strict=True))
        pref = [c for a, c in rows if "$" in a]
        units = [c for a, c in rows if a.endswith(".U")]
        warrants = [c for a, c in rows if a.endswith(".W")]
        rights = [c for a, c in rows if a.endswith(".R")]
        hit = lambda cs: sum(1 for c in cs if (ident.sec_spelling(c) or "") in sec_tickers)
        assert hit(pref) / len(pref) > 0.95, (hit(pref), len(pref))
        assert hit(units) / len(units) > 0.9, (hit(units), len(units))
        assert hit(warrants) / len(warrants) > 0.9, (hit(warrants), len(warrants))
        assert hit(rights) == 0 and len(rights) >= 15

    def test_nasdaq_listed_symbols_carry_no_punctuation(self, nasdaq: pd.DataFrame) -> None:
        assert nasdaq["symbol"].str.fullmatch(r"[A-Z0-9]+").all()


# ── aliases_for, on the real desired rows ──


@pytest.fixture(scope="module")
def rows(desired: pd.DataFrame) -> dict[str, dict]:
    return {r["symbol"]: r for r in desired.to_dict("records")}


def test_aliases_for_brk_b(rows: dict[str, dict], tiingo_tickers: frozenset[str]) -> None:
    assert ident.aliases_for(rows["BRK.B"], tiingo_tickers) == [
        ("stooq", "BRK-B.US"),
        ("tiingo", "BRK-B"),
        ("sec", "BRK-B"),
        ("nasdaq_symbol", "BRK.B"),
        ("cqs", "BRK.B"),
    ]


def test_aliases_for_a_preferred_and_a_warrant(
    rows: dict[str, dict], tiingo_tickers: frozenset[str]
) -> None:
    assert ident.aliases_for(rows["AGM$D"], tiingo_tickers) == [
        ("stooq", "AGM_D.US"),
        ("tiingo", "AGM-P-D"),
        ("sec", "AGM-PD"),
        ("nasdaq_symbol", "AGM-D"),
        ("cqs", "AGMpD"),
    ]
    assert ident.aliases_for(rows["ACHR.W"], tiingo_tickers) == [
        ("stooq", "ACHR-WS.US"),
        ("tiingo", "ACHR-WS"),
        ("sec", "ACHR-WT"),
        ("nasdaq_symbol", "ACHR+"),
        ("cqs", "ACHR.WS"),
    ]


def test_aliases_for_a_unit_and_a_right(
    rows: dict[str, dict], tiingo_tickers: frozenset[str]
) -> None:
    assert ident.aliases_for(rows["AAC.U"], tiingo_tickers) == [
        ("stooq", "AAC-U.US"),
        ("tiingo", "AAC-U"),
        ("sec", "AAC-UN"),
        ("nasdaq_symbol", "AAC="),
        ("cqs", "AAC.U"),
    ]
    # Rights: no SEC spelling; Tiingo lists AIIA-R.
    assert ident.aliases_for(rows["AIIA.R"], tiingo_tickers) == [
        ("stooq", "AIIA-R.US"),
        ("tiingo", "AIIA-R"),
        ("nasdaq_symbol", "AIIA^"),
        ("cqs", "AIIAr"),
    ]


def test_aliases_for_plain_and_nasdaq_listed_tickers(
    rows: dict[str, dict], tiingo_tickers: frozenset[str]
) -> None:
    assert ident.aliases_for(rows["SPY"], tiingo_tickers) == [
        ("stooq", "SPY.US"),
        ("tiingo", "SPY"),
        ("sec", "SPY"),
        ("nasdaq_symbol", "SPY"),
        ("cqs", "SPY"),
    ]
    # nasdaqlisted rows have no CQS column: no cqs alias; the symbol is the Nasdaq symbol.
    for s in ("QQQ", "AAPL"):
        assert ident.aliases_for(rows[s], tiingo_tickers) == [
            ("stooq", f"{s}.US"),
            ("tiingo", s),
            ("sec", s),
            ("nasdaq_symbol", s),
        ]


def test_a_tiingo_alias_is_never_emitted_without_proof(
    rows: dict[str, dict], tiingo_tickers: frozenset[str]
) -> None:
    # BZZ is in the 2026-09-04 directory (BATS) but not in Tiingo's list, and no SEC file
    # carries it: only the two spellings the directory itself proves.
    assert ident.aliases_for(rows["BZZ"], tiingo_tickers) == [
        ("stooq", "BZZ.US"),
        ("nasdaq_symbol", "BZZ"),
        ("cqs", "BZZ"),
    ]

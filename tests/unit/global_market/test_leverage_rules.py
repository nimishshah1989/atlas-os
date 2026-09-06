"""``leverage_flags`` on REAL instrument names (rule #0), read from the committed Nasdaq/SEC
directory snapshot — the same files ``identity_frame.directory_frame`` builds the market from,
so every case below is a row that exists and no name here was written for a test.

The traps are the point. "Ultra", "Short", "Bull", "Bear" and "Leveraged" all appear in names
that carry no leverage at all, and the leveraged funds that DO use them are, in this market,
one issuer. Each parameter carries its symbol and why it is a trap; a name that has left the
directory fails ``test_every_case_is_a_real_row`` rather than passing vacuously.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from atlas.global_market.classify import LeverageFlags, leverage_flags
from atlas.global_market.identity_frame import directory_frame

pytestmark = pytest.mark.unit

# ── the traps: names that LOOK leveraged and are not ───────────────────────────────────────
# (symbol, why the name is a trap). Asserted flag-by-flag in test_a_trap_name_is_not_flagged.
CLEAN_CASES = [
    ("AMUN", "'Ultra Short' is bond DURATION, not 2x — abrdn is not a geared house"),
    ("BAMU", "'Ultra-Short' hyphenated, still duration"),
    ("BILZ", "'Ultra Short Government' — duration, and not even named 'ETF'"),
    ("BKUI", "'Ultra Short Income' — duration"),
    ("CGUI", "'Ultra Short Income' — duration"),
    ("CVSB", "'Ultra-Short Investment Grade' — duration"),
    ("DLUX", "'Ultrashort' as ONE word is still duration when the issuer is DoubleLine"),
    ("DUSB", "'Ultrashort Fixed Income' — duration"),
    ("BUSM", "'Ultra-Small' is a SIZE band, not a multiple"),
    ("BSV", "'Short-Term' is duration; Vanguard lists no geared fund"),
    ("AVSF", "'Short-Term Fixed Income' — duration"),
    ("CGSD", "'Short Duration Income' — duration"),
    ("DFSD", "'Short-Duration Fixed Income' — duration"),
    ("CLIX", "long/short equity FROM ProShares: an issuer-only rule gets this one wrong"),
    ("CLSE", "'Long/Short Equity' is a strategy, not an inverse product"),
    ("UAPR", "Innovator's 'Ultra Buffer' is a defined-outcome buffer, not 2x"),
    ("LVLN", "'Leveraged Loan' is the ASSET CLASS (loans to geared borrowers)"),
    ("ULTY", "YieldMax's 'Ultra' is option-income branding"),
    ("RDIV", "'Ultra Dividend Revenue' — a yield tilt"),
    ("WBIG", "'BullBear' is the strategy's name; the fund is not geared"),
    ("BSCQ", "'BulletShares' opens with the letters of 'Bull'"),
]

# ── the traps in the other direction: names that ARE geared or inverse ─────────────────────
# (symbol, leveraged, inverse, multiple, rule, why). ``multiple`` is only ever a number the
# NAME states — see the module docstring of atlas.global_market.classify.rules.
FLAGGED_CASES = [
    ("AAPU", True, False, "2", "explicit_multiple", "'Bull 2X' — stated multiple, long"),
    ("AAPD", False, True, "1", "explicit_multiple", "'Bear 1X' — inverse WITHOUT gearing"),
    ("AAPB", True, False, "2", "explicit_multiple", "'2x Long' from GraniteShares"),
    ("AAOZ", True, True, "2", "explicit_multiple", "'2X Short' — geared AND inverse"),
    ("ACHX", True, False, "2", "explicit_multiple", "'2x Daily' with no direction word = long"),
    ("AMA", True, False, "2", "explicit_multiple", "Defiance 'Daily Target 2X Long'"),
    ("AKAL", True, False, "2", "explicit_multiple", "T-REX '2X Long … Daily Target'"),
    ("AALG", True, False, "2", "explicit_multiple", "Leverage Shares '2X Long … Daily'"),
    ("AGQ", True, False, None, "proshares_ultra", "ProShares 'Ultra' IS 2x"),
    ("DIG", True, False, None, "proshares_ultra", "ProShares 'Ultra' IS 2x"),
    ("BITU", True, False, None, "proshares_ultra", "ProShares 'Ultra' IS 2x"),
    ("COIA", True, False, None, "proshares_ultra", "ProShares 'Ultra', no 'ETF' suffix"),
    ("ETHT", True, False, None, "proshares_ultra", "ProShares 'Ultra' IS 2x"),
    ("DUG", True, True, None, "proshares_ultrashort", "'UltraShort' is geared AND inverse"),
    ("EPV", True, True, None, "proshares_ultrashort", "'UltraShort' is geared AND inverse"),
    ("EUO", True, True, None, "proshares_ultrashort", "'UltraShort' is geared AND inverse"),
    ("ETHD", True, True, None, "proshares_ultrashort", "'UltraShort' is geared AND inverse"),
    ("BITI", False, True, None, "proshares_short", "ProShares 'Short' IS inverse"),
    ("DOG", False, True, None, "proshares_short", "ProShares 'Short' IS inverse"),
    ("AIQD", True, True, "3", "explicit_multiple", "'-3?' — the source's mangled X, matched raw"),
    ("SDOW", True, True, None, "proshares_ultrashort", "the directory drops ProShares from it"),
    ("UMDD", True, False, None, "proshares_ultra", "'UltraPro MidCap400', issuer dropped too"),
    ("SPXU", True, True, None, "proshares_ultrashort", "'UltraPro Short' is 3x inverse"),
    ("UVXY", True, False, None, "proshares_ultra", "'Ultra VIX SHORT TERM Futures' is LONG"),
    ("SVXY", False, True, None, "proshares_short", "'Short VIX Short Term Futures' is inverse"),
    ("BNKD", True, True, None, "inverse_leveraged_words", "'-3 Inverse Leveraged': no X, no ×"),
    ("BNKU", True, False, None, "leverage_word", "'3 Leveraged' — geared, long"),
    ("VYLD", False, True, None, "inverse_word", "'Inverse VIX …' with the issuer stripped"),
    ("SVIX", False, True, "1", "explicit_multiple", "'-1x Short' — the sign carries it"),
    ("MSOX", True, False, None, "leverage_word", "'Daily Leveraged' — the word, not a number"),
    ("HDLB", True, False, "2", "explicit_multiple", "'2xLeveraged' unspaced, X before a letter"),
]

ALL_SYMBOLS = [c[0] for c in CLEAN_CASES] + [c[0] for c in FLAGGED_CASES]


@pytest.fixture(scope="module")
def directory(nasdaq: pd.DataFrame, other: pd.DataFrame) -> dict[str, str]:
    """symbol → the REAL security name, through the production directory frame."""
    frame = directory_frame(nasdaq, other)
    return dict(zip(frame["symbol"], frame["name"], strict=True))


def test_every_case_is_a_real_row(directory: dict[str, str]) -> None:
    """A case whose symbol has left the directory proves nothing — fail, never skip."""
    missing = [s for s in ALL_SYMBOLS if s not in directory]
    assert not missing, f"no longer in the directory snapshot: {missing}"
    assert len(set(ALL_SYMBOLS)) == len(ALL_SYMBOLS), "a symbol is asserted twice"


@pytest.mark.parametrize(("symbol", "why"), CLEAN_CASES, ids=[c[0] for c in CLEAN_CASES])
def test_a_trap_name_is_not_flagged(directory: dict[str, str], symbol: str, why: str) -> None:
    name = directory[symbol]
    flags = leverage_flags(name)
    assert not flags.leveraged, f"{symbol} :: {name} — {why}"
    assert not flags.inverse, f"{symbol} :: {name} — {why}"
    assert flags.multiple is None, f"{symbol} :: {name} — {why}"


@pytest.mark.parametrize(
    ("symbol", "leveraged", "inverse", "multiple", "rule", "why"),
    FLAGGED_CASES,
    ids=[c[0] for c in FLAGGED_CASES],
)
def test_a_geared_or_inverse_name_is_flagged_with_its_rule(
    directory: dict[str, str],
    symbol: str,
    leveraged: bool,
    inverse: bool,
    multiple: str | None,
    rule: str,
    why: str,
) -> None:
    name = directory[symbol]
    flags = leverage_flags(name)
    context = f"{symbol} :: {name} — {why}"
    assert flags.leveraged is leveraged, context
    assert flags.inverse is inverse, context
    assert flags.multiple == (None if multiple is None else Decimal(multiple)), context
    assert flags.rule == rule, context


def test_an_unremarkable_name_matches_nothing(directory: dict[str, str]) -> None:
    """The default is clean and says so, so a board can tell "no pattern" from "excluded"."""
    flags = leverage_flags(directory["SPY"])
    assert flags == (False, False, None, "no_leverage_pattern")


# ── the properties the ordered table exists to hold, over the whole real directory ─────────


@pytest.fixture(scope="module")
def etf_flags(nasdaq: pd.DataFrame, other: pd.DataFrame) -> list[tuple[str, LeverageFlags]]:
    frame = directory_frame(nasdaq, other)
    names = frame.loc[frame["asset_class"] == "etf", "name"]
    return [(str(n), leverage_flags(str(n))) for n in names]


def test_only_proshares_needs_the_word_rules(etf_flags: list[tuple[str, LeverageFlags]]) -> None:
    """The measured reason the three anchored rules are anchored: every OTHER geared house in
    this market states its multiple, so 'Ultra'/'Short' from anyone else is a description."""
    stripped = ("ProShares ", "UltraPro", "UltraShort")  # the directory drops the issuer on a few
    by_word = [n for n, f in etf_flags if f.rule.startswith("proshares_")]
    assert len(by_word) > 100, len(by_word)
    assert all(n.startswith(stripped) for n in by_word), [
        n for n in by_word if not n.startswith(stripped)
    ]


def test_no_ultra_short_bond_fund_is_flagged(etf_flags: list[tuple[str, LeverageFlags]]) -> None:
    """The largest trap family: 'Ultra Short'/'Ultrashort' duration funds. Every one of them
    must come out clean, and there must be enough of them for the case to mean something."""
    duration = [
        (n, f)
        for n, f in etf_flags
        if "ultra" in n.lower()
        and "short" in n.lower()
        and not n.startswith(("ProShares", "UltraPro", "UltraShort"))
    ]
    assert len(duration) > 30, len(duration)
    assert [n for n, f in duration if f.leveraged or f.inverse] == []


def test_a_stated_multiple_is_read_as_a_magnitude_with_a_separate_direction(
    etf_flags: list[tuple[str, LeverageFlags]],
) -> None:
    """Every ``multiple`` is positive and comes with the direction in ``inverse`` — a signed
    multiple would put the same fact in two places and let them disagree."""
    stated = [f for _, f in etf_flags if f.multiple is not None]
    assert len(stated) > 600, len(stated)
    assert all(f.multiple is not None and f.multiple > 0 for f in stated)
    assert all(f.rule == "explicit_multiple" for f in stated)
    # |x| > 1 is what "leveraged" means here; the 1x inverse funds are inverse and nothing more.
    assert all(f.leveraged == (f.multiple is not None and f.multiple > 1) for f in stated)
    assert any(not f.leveraged and f.inverse for f in stated)


def test_a_company_name_is_not_a_fund_name(nasdaq: pd.DataFrame, other: pd.DataFrame) -> None:
    """Why ``build_universe_snapshot`` runs these rules over ETFs ONLY: a company can be called
    10x Genomics. The rule has no way to know, and it must not be asked to — a stock's universe
    test is S&P 500 membership (FM, 2026-09-06), never a word in its name."""
    frame = directory_frame(nasdaq, other)
    stocks = frame.loc[frame["asset_class"] == "stock"]
    assert len(stocks) > 5000, len(stocks)
    hits = {
        str(s): f
        for s, n in zip(stocks["symbol"], stocks["name"], strict=True)
        if (f := leverage_flags(str(n))).leveraged or f.inverse
    }
    assert "TXG" in hits and hits["TXG"].multiple == Decimal(10), sorted(hits)
    # The rest are geared ETNs the directory flags ETF=N (a note is not a fund); they are out
    # of the universe on the S&P 500 rule, not on this one.
    assert set(hits) - {"TXG"} == {"FNGD", "FNGO", "PFFL", "SMHB"}, sorted(hits)

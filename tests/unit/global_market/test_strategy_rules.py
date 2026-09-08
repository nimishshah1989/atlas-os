"""``classify_strategy`` on REAL fund names (rule #0), read from the committed Nasdaq/SEC
directory snapshot — the same files ``identity_frame.directory_frame`` builds the market from,
so every case below is a row that exists and no name here was written for a test.

Three classes of assertion, and the second two are the ones that earn their keep:

1. Each of the 17 strategy values fires on a named real fund.
2. PRECEDENCE. The order of the rule table is its whole design, and every case here is a name
   whose words match two or more rules — so the test fails if anyone reorders the table.
3. REGRESSIONS for bugs this classifier actually shipped during its build: four patterns
   written as ``\\bprefix\\b`` that could never match the longer word every real name uses, a
   country named after "ex" read as the bet rather than the exclusion, and bare "Volatility"
   pulling equity factor funds into ``alternative``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.global_market.classify.strategy import RULES, STRATEGIES, classify_strategy
from atlas.global_market.identity_frame import directory_frame

pytestmark = pytest.mark.unit

# (symbol, strategy, why this row and not another). One per value, all 17 covered.
STRATEGY_CASES = [
    ("AAPB", "single_stock", "'2x Long AAPL Daily' — a real ticker AND stated gearing"),
    ("ACQQ", "defined_outcome", "'Autocallable Income' — the payoff shape IS the product"),
    ("AMYY", "options_income", "GraniteShares 'YieldBOOST' — an options wrapper on AMD"),
    ("BHDG", "crypto", "'Bitcoin' — the asset itself, not the equity of miners"),
    ("AAAP", "fixed_income", "'CLO' — collateralised loan obligations are credit"),
    ("AUMI", "commodity", "'Gold Miners'"),
    ("CEW", "currency", "'Emerging Currency Strategy'"),
    ("AAAA", "multi_asset", "'Aggressive Asset Allocation'"),
    ("ALTY", "alternative", "'Alternative Income'"),
    ("AIQ", "thematic", "'Artificial Intelligence' is narrower than a GICS sector"),
    ("BBH", "sector", "VanEck 'Biotech' — a sector, not a theme"),
    ("CNQQ", "country", "'China' as the target, not an exclusion"),
    ("ACWI", "region", "'ACWI' — all country world"),
    ("AMEI", "dividend_income", "'Equity Income' below the wrappers, so it is not options"),
    ("AVUQ", "factor", "'Quality'"),
    ("ABIG", "size_style", "'Large Cap'"),
    ("MNZL", "broad_market", "'Broad Market' — the fallback, still a positive match"),
]

# (symbol, strategy, the rule it must BEAT, why). These fail if the table is reordered.
PRECEDENCE_CASES = [
    ("AIPI", "options_income", "thematic", "'AI Equity Premium Income' — the wrapper wins"),
    ("AAPD", "single_stock", "size_style", "'AAPL Bear 1X' — geared single name beats 'Bear'"),
    ("AGMI", "commodity", "sector", "'Silver Miners' — the metal, not 'materials'"),
    ("EUO", "currency", "region", "'UltraShort Euro' — the currency, not Europe"),
]

# Not precedence cases: `country` correctly outranks `region`, and these two reach `region`
# because the country pattern DECLINES to match an excluded country — a different mechanism,
# asserted in test_a_country_named_after_ex_is_not_the_bet.
EXCLUSION_CASES = [
    ("AAXJ", "'iShares MSCI All Country Asia ex Japan'"),
    ("AVXC", "'Avantis Emerging Markets ex-China Equity'"),
]

ALL_SYMBOLS = (
    [c[0] for c in STRATEGY_CASES]
    + [c[0] for c in PRECEDENCE_CASES]
    + [c[0] for c in EXCLUSION_CASES]
)


@pytest.fixture(scope="module")
def directory(nasdaq: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    return directory_frame(nasdaq, other)


@pytest.fixture(scope="module")
def names(directory: pd.DataFrame) -> dict[str, str]:
    """symbol → the REAL security name, through the production directory frame."""
    return dict(zip(directory["symbol"], directory["name"], strict=True))


@pytest.fixture(scope="module")
def stock_symbols(directory: pd.DataFrame) -> set[str]:
    """The real listed-equity symbols — the evidence the single-stock rule needs."""
    return set(directory.loc[directory["asset_class"] == "stock", "symbol"])


@pytest.fixture(scope="module")
def etf_names(directory: pd.DataFrame) -> list[str]:
    return list(directory.loc[directory["asset_class"] == "etf", "name"])


def test_every_case_is_a_real_row(names: dict[str, str]) -> None:
    """A case whose symbol has left the directory proves nothing — fail, never skip."""
    missing = [s for s in ALL_SYMBOLS if s not in names]
    assert not missing, f"no longer in the directory snapshot: {missing}"
    assert len(set(ALL_SYMBOLS)) == len(ALL_SYMBOLS), "a symbol is asserted twice"


@pytest.mark.parametrize(("symbol", "expected", "why"), STRATEGY_CASES)
def test_strategy_on_a_real_fund(
    symbol: str, expected: str, why: str, names: dict[str, str], stock_symbols: set[str]
) -> None:
    got = classify_strategy(names[symbol], stock_symbols)
    assert got.strategy == expected, f"{symbol} ({names[symbol]}): {why} — got {got}"


@pytest.mark.parametrize(("symbol", "expected", "beaten", "why"), PRECEDENCE_CASES)
def test_precedence_decides(
    symbol: str,
    expected: str,
    beaten: str,
    why: str,
    names: dict[str, str],
    stock_symbols: set[str],
) -> None:
    got = classify_strategy(names[symbol], stock_symbols)
    assert got.strategy == expected, f"{symbol} ({names[symbol]}): {why} — got {got}"
    assert STRATEGIES.index(expected) < STRATEGIES.index(beaten), (
        f"{expected} must rank above {beaten} for this case to mean anything"
    )


def test_every_case_covers_a_distinct_strategy() -> None:
    """All 17 values are exercised, so a new value cannot land untested."""
    assert {c[1] for c in STRATEGY_CASES} == set(STRATEGIES)


def test_no_rule_is_dead(etf_names: list[str], stock_symbols: set[str]) -> None:
    """Every rule fires on the real universe.

    This is the regression for the bug that cost the most: four patterns were written
    ``\\bbiotech\\b``, ``\\bgenomic\\b``, ``\\bdisrupt\\b``, ``\\bprofitab\\b`` — each reads as a
    prefix and each can never match, because every real name says "Biotechnology",
    "Genomics", "Disruptive", "Profitability". They passed review and classified nothing.
    """
    fired = {classify_strategy(n, stock_symbols).rule for n in etf_names}
    dead = [rule for _, _, rule in RULES if rule not in fired]
    assert not dead, f"rules that match no real fund name: {dead}"


def test_a_country_named_after_ex_is_not_the_bet(
    names: dict[str, str], stock_symbols: set[str]
) -> None:
    """'Asia ex Japan' is not a bet on Japan. The failure mode is silent: a plausible-looking
    country label on the one market the fund deliberately leaves out."""
    for symbol, why in EXCLUSION_CASES:
        got = classify_strategy(names[symbol], stock_symbols)
        assert got.strategy == "region", f"{symbol} {why} -> {got}"


def test_coverage_is_what_we_claim(etf_names: list[str], stock_symbols: set[str]) -> None:
    """The rules layer exists for precision, not recall, and the unmatched share is a
    published number (``docs/global/taxonomy.md``) that the LLM layer is sized against. A
    large move in either direction is a finding: patterns overfitted to chase coverage, or a
    vocabulary that has drifted away from the market."""
    matched = sum(1 for n in etf_names if classify_strategy(n, stock_symbols).strategy)
    share = matched / len(etf_names)
    assert 0.70 <= share <= 0.85, f"rules matched {share:.1%} of {len(etf_names)} real names"

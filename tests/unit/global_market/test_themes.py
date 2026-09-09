"""``classify_theme`` on REAL fund names (rule #0), read from the committed Nasdaq/SEC
directory snapshot — the same files ``identity_frame.directory_frame`` builds the market from,
so every case below is a row that exists and no name here was written for a test.

Four classes of assertion, and the last three are the ones that earn their keep:

1. Each of the 32 themes fires on a named real fund.
2. PRECEDENCE. 56 of the 5,655 real names match two or more rules, and the table's order is
   the only thing that decides them. Every case in ``PRECEDENCE_CASES`` is one of those 56, so
   reordering the table fails here with the fund and the reason.
3. WORDS THAT MEAN SOMETHING ELSE. Six phrases in this market read as a theme and are not one
   — three of them are issuer names — and each of them produced a wrong answer during the
   build. They are the reason the theme layer can be trusted at all.
4. AN HONEST CENSUS. ``test_which_themes_no_real_fund_reaches`` and
   ``test_the_smallest_themes_are_as_small_as_the_taxonomy_says`` publish what the layer
   actually covers, including the theme with exactly one fund, instead of leaving the FM to
   discover it on a board page.
"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.global_market.classify.themes import RULES, THEMES, classify_theme
from atlas.global_market.identity_frame import directory_frame
from tests.unit.global_market.script_loader import load_global_script

pytestmark = pytest.mark.unit

# (symbol, theme, why this row and not another). One per theme, all 32 covered.
THEME_CASES = [
    ("GDX", "gold_silver_miners", "'Gold Miners' — the FM's own example of a centred fund"),
    ("GLD", "precious_metals", "'SPDR Gold Shares' holds the metal, not the miner"),
    ("CPER", "copper", "'United States Copper Index Fund'"),
    ("LIT", "lithium", "'Lithium & Battery Tech'"),
    ("EART", "critical_minerals", "'Rare Earth & Critical Materials'"),
    ("TAN", "solar", "'Invesco Solar' — the only solar ETF the market has listed"),
    ("URA", "nuclear_uranium", "'Uranium' — an energy SOURCE, which is what the FM asked for"),
    ("ZAP", "grid_electrification", "'U.S. Electrification'"),
    ("ICLN", "clean_energy", "'Global Clean Energy'"),
    ("FIW", "water", "'First Trust Water' — named by the FM"),
    ("MOO", "food_agriculture", "'Agribusiness' — the food-security bet, named by the FM"),
    ("WOOD", "timber_forestry", "'Global Timber & Forestry'"),
    ("SMH", "semiconductors", "'VanEck Semiconductor'"),
    ("QTUM", "quantum", "'Defiance Quantum'"),
    ("IBOT", "robotics", "'VanEck Robotics'"),
    ("BUG", "cybersecurity", "'Global X Cybersecurity'"),
    ("SKYY", "cloud", "'Cloud Computing'"),
    ("DTCR", "data_centres", "'Data Center & Digital Infrastructure'"),
    ("BKCH", "blockchain", "'Blockchain' — the equity of the chain, not the coin"),
    ("FINX", "fintech", "'FinTech'"),
    ("UFO", "space", "'Procure Space'"),
    ("ITA", "defence", "'U.S. Aerospace & Defense'"),
    ("DRIV", "ev_battery", "'Autonomous & Electric Vehicles'"),
    ("AIQ", "ai", "'Artificial Intelligence & Technology' — the theme the FM opened with"),
    ("ARKG", "genomics", "'Genomic Revolution'"),
    ("AGNG", "longevity", "'Aging Population'"),
    ("HERO", "gaming_esports", "'Video Games & Esports'"),
    ("MSOS", "cannabis", "'Pure US Cannabis'"),
    ("XHB", "homebuilders", "'S&P Homebuilders'"),
    ("BOAT", "shipping", "'Global Shipping'"),
    ("SCHH", "reits", "'Schwab U.S. REIT'"),
    ("PAVE", "infrastructure", "'U.S. Infrastructure Development'"),
]

# (symbol, theme, the theme it must BEAT, why). Every name here matches BOTH rules, so each
# case fails if the table is reordered — that is the whole point of the list.
PRECEDENCE_CASES = [
    (
        "GDX",
        "gold_silver_miners",
        "precious_metals",
        "'VanEck Gold Miners' holds equity levered to the metal, not the metal. 27 names read "
        "this way and the FM asked for exactly this distinction, so the miner rule sits "
        "directly above the metal rule",
    ),
    (
        "GOAU",
        "gold_silver_miners",
        "precious_metals",
        "'GO Gold and Precious Metal Miners' states BOTH vocabularies in one name — the case "
        "that proves the order rather than merely surviving it",
    ),
    (
        "LIT",
        "lithium",
        "ev_battery",
        "'Lithium & Battery Tech': the input beats the trend. LIT is the lithium fund the "
        "market prices off the metal, and filing it under electric vehicles would rank it "
        "against car makers",
    ),
    (
        "EMET",
        "copper",
        "grid_electrification",
        "'Copper and Electrification Metals' — same principle: the metal is the physical "
        "thing, electrification is the story it is sold on",
    ),
    (
        "GRID",
        "grid_electrification",
        "clean_energy",
        "'Clean Edge Smart Grid Infrastructure' carries THREE themes' words. The grid is what "
        "it holds, so grid_electrification is above both clean_energy and infrastructure",
    ),
    (
        "TPZ",
        "grid_electrification",
        "infrastructure",
        "'Electrification Infrastructure' — infrastructure is the last rule in the table for "
        "this reason: 10 of the 51 names carrying the word are something narrower first",
    ),
    (
        "DTCR",
        "data_centres",
        "infrastructure",
        "'Data Center & Digital Infrastructure' is the AI build-out, not a toll road",
    ),
    (
        "CHPX",
        "semiconductors",
        "ai",
        "'AI Semiconductor & Quantum' names three themes and holds chips. This is the "
        "decision the ordering makes most often: `ai` is LAST in the technology group because "
        "half of these funds name it in passing, and a theme that absorbs every fund that "
        "says 'AI' is the undifferentiated bucket the FM already rejected",
    ),
    (
        "AINF",
        "semiconductors",
        "ai",
        "'Inference AI Chip' — the same call on the clearest possible name: it is a chip fund",
    ),
    (
        "BOTZ",
        "robotics",
        "ai",
        "'Robotics & Artificial Intelligence' is the market's robotics fund. Robots are the "
        "physical thing; AI is what they run on",
    ),
    (
        "XA",
        "cybersecurity",
        "ai",
        "'AI Cybersecurity' — a cybersecurity fund whose companies use AI, which is a "
        "different claim from a fund that holds the AI companies",
    ),
    (
        "ARKX",
        "space",
        "defence",
        "'Space & Defense Innovation' is the one name claiming both mandates, and ARKX is the "
        "market's space fund. Nine aerospace-and-defence funds are unaffected because "
        "`\\bspace\\b` cannot match inside 'Aerospace'",
    ),
    (
        "BLCK",
        "blockchain",
        "infrastructure",
        "'Crypto Infrastructure' holds the chain's equity — the same line strategy.py draws "
        "from the other side when it keeps blockchain OUT of its crypto rule",
    ),
    (
        "NBET",
        "clean_energy",
        "infrastructure",
        "'Energy Transition & Infrastructure' is a transition fund, not a toll road",
    ),
    (
        "WEPN",
        "critical_minerals",
        "defence",
        "'Defense and Rare Earth Income' is the case where the ordering COSTS something, and "
        "it is asserted so the cost stays visible: both labels are true, the table has one "
        "answer per fund, and the principle in the module docstring picks the metal. If the "
        "FM would rather this read `defence`, that is a one-line move and this test names it",
    ),
]

# (symbol, the theme it must NOT reach, why). Six phrases that read as a theme and are not
# one; three of them are issuer names, which is the same defect that once put a Treasury-bill
# fund on the world map because its issuer is called "Global X".
FALSE_POSITIVE_CASES = [
    (
        "BBLU",
        "semiconductors",
        "'EA Bridgeway Blue Chip' — a bare `chip` filed all six Blue Chip funds as "
        "semiconductor funds, T. Rowe's and Fidelity's among them",
    ),
    (
        "QVOL",
        "infrastructure",
        "'Infrastructure Capital Nasdaq Option Income' — an ISSUER's name. It is an "
        "options-income fund on the Nasdaq and holds no infrastructure at all",
    ),
    (
        "BNDS",
        "infrastructure",
        "'Infrastructure Capital Bond Income' — the same issuer, and a BOND fund, which is "
        "how visible the defect gets if the guard is removed",
    ),
    (
        "BBB",
        "cybersecurity",
        "'CYBER HORNET S&P 500 and Bitcoin 75/25 Strategy' — an issuer brand again; the fund "
        "is an S&P 500 and bitcoin blend, and four of them carry the name",
    ),
    (
        "HIAI",
        "ai",
        "'Ai Funds High Conviction US Equity AI-Managed' — issuer, and AI as the METHOD twice "
        "over. strategy.py still reads this one as thematic; the theme layer does not",
    ),
    (
        "AIVL",
        "ai",
        "'U.S. AI Enhanced Value' is a value fund run by a model. The lookahead that stops it "
        "is strategy.py's own, word for word, so the two layers cannot disagree here",
    ),
    (
        "BTC",
        "blockchain",
        "'Grayscale Bitcoin MINI Trust' is not a bitcoin MINER. A `bitcoin min\\w+` prefix "
        "reads it as one, which is why the rule spells both words out",
    ),
    (
        "LFAI",
        "longevity",
        "'LifeX 2050 Longevity Income' is an annuity-shaped income ladder. Eight of them exist "
        "and they would have outnumbered the two real ageing-demographics funds four to one",
    ),
    (
        "GIND",
        "precious_metals",
        "'Goldman Sachs India Equity' — `\\bgold\\b` and not `gold`, or 46 Goldman Sachs funds "
        "and two 'Golden Dragon'/'Golden Eagle' funds become bullion",
    ),
    (
        "FTSL",
        "longevity",
        "'First Trust Senior Loan' is why `senior` is not in the longevity rule, however "
        "naturally it reads: the market uses the word for loan seniority, 9 times over",
    ),
    (
        "CABZ",
        "robotics",
        "'Robotaxi, Autonomous Vehicles & Technology' is a mobility fund. A `robot\\w*` prefix "
        "reads 'Robotaxi' as robotics, so the rule spells `robotic\\w*` out",
    ),
]

ALL_SYMBOLS = (
    [c[0] for c in THEME_CASES]
    + [c[0] for c in PRECEDENCE_CASES]
    + [c[0] for c in FALSE_POSITIVE_CASES]
)


@pytest.fixture(scope="module")
def directory(nasdaq: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    return directory_frame(nasdaq, other)


@pytest.fixture(scope="module")
def names(directory: pd.DataFrame) -> dict[str, str]:
    """symbol → the REAL security name, through the production directory frame."""
    return dict(zip(directory["symbol"], directory["name"], strict=True))


@pytest.fixture(scope="module")
def etf_names(directory: pd.DataFrame) -> list[str]:
    return list(directory.loc[directory["asset_class"] == "etf", "name"])


def test_every_case_is_a_real_row(names: dict[str, str]) -> None:
    """A case whose symbol has left the directory proves nothing — fail, never skip. This is
    also the guard on rule #0 for this file: if a name here were invented, it would not be in
    the snapshot and this test would say so."""
    missing = [s for s in ALL_SYMBOLS if s not in names]
    assert not missing, f"no longer in the directory snapshot: {missing}"


@pytest.mark.parametrize(("symbol", "expected", "why"), THEME_CASES)
def test_theme_on_a_real_fund(symbol: str, expected: str, why: str, names: dict[str, str]) -> None:
    got = classify_theme(names[symbol])
    assert got is not None, f"{symbol} ({names[symbol]}): {why} — no rule read it"
    assert got.theme == expected, f"{symbol} ({names[symbol]}): {why} — got {got.theme}"
    assert got.evidence in names[symbol], "the evidence must be text from the name itself"


def test_every_case_covers_a_distinct_theme() -> None:
    """All 32 themes are exercised, so a new theme cannot land untested."""
    assert {c[1] for c in THEME_CASES} == set(THEMES)


@pytest.mark.parametrize(("symbol", "expected", "beaten", "why"), PRECEDENCE_CASES)
def test_precedence_decides(
    symbol: str, expected: str, beaten: str, why: str, names: dict[str, str]
) -> None:
    got = classify_theme(names[symbol])
    assert got is not None and got.theme == expected, f"{symbol} ({names[symbol]}): {why}"
    assert THEMES.index(expected) < THEMES.index(beaten), (
        f"{expected} must rank above {beaten} for this case to mean anything"
    )
    beaten_pattern = next(p for p, t, _ in RULES if t == beaten)
    assert beaten_pattern.search(names[symbol]) is not None, (
        f"{symbol} does not match the {beaten} rule at all, so it tests nothing about order — "
        "a precedence case must be a name that genuinely claims both themes"
    )


@pytest.mark.parametrize(("symbol", "wrong", "why"), FALSE_POSITIVE_CASES)
def test_a_word_that_means_something_else_does_not_reach_the_theme(
    symbol: str, wrong: str, why: str, names: dict[str, str]
) -> None:
    got = classify_theme(names[symbol])
    assert got is None or got.theme != wrong, f"{symbol} ({names[symbol]}) is not {wrong}: {why}"


def test_no_rule_is_dead(etf_names: list[str]) -> None:
    """Every rule fires on the real universe.

    This is the regression for the defect that cost ``strategy.py`` the most: four patterns
    written ``\\bbiotech\\b`` read as prefixes and could never match, because every real name
    says "Biotechnology". They passed review and classified nothing.
    """
    fired = {m.rule for n in etf_names if (m := classify_theme(n)) is not None}
    dead = [rule for _, _, rule in RULES if rule not in fired]
    assert not dead, f"rules that match no real fund name: {dead}"


def test_which_themes_no_real_fund_reaches(etf_names: list[str]) -> None:
    """The honest census, and it is deliberately an assertion rather than a printed note.

    Today every one of the 32 themes is reached by at least one real listed fund, so this
    passes with an empty list. It is here for the day it does not: seeding a theme no fund can
    reach gives the board a page that is always empty and gives the LLM layer a category it
    will reach for anyway, and the FM should learn that from a red test rather than from a
    blank screen.
    """
    reached = {m.theme for n in etf_names if (m := classify_theme(n)) is not None}
    unreachable = [t for t in THEMES if t not in reached]
    assert not unreachable, (
        f"themes no real ETF name reaches: {unreachable} — either the vocabulary is wrong or "
        "the theme should not be seeded"
    )


def test_the_smallest_themes_are_as_small_as_the_taxonomy_says(etf_names: list[str]) -> None:
    """``solar`` has ONE fund and ``timber_forestry``, ``data_centres`` and ``longevity`` have
    two. That is not a bug and it is not hidden: the FM named solar as an energy source, the
    market has listed exactly one solar ETF, and a theme page reading "1 fund" is a truer
    answer than folding it into ``clean_energy`` and losing the question.

    The assertion is that the seeded count and the classifier agree, for every theme. They are
    written in two files by hand and would otherwise drift the first time a rule is widened —
    at which point ``taxonomy.md`` and the board would be quoting a number nothing produces.
    """
    counted: dict[str, int] = dict.fromkeys(THEMES, 0)
    for name in etf_names:
        match = classify_theme(name)
        if match is not None:
            counted[match.theme] += 1
    seeded = {tid: funds for tid, _, _, funds in load_global_script("seed_taxonomy").THEMES}
    disagree = {t: (counted[t], seeded[t]) for t in THEMES if counted[t] != seeded[t]}
    assert not disagree, (
        f"theme (measured, seeded) disagree: {disagree} — re-run the count and update "
        "seed_taxonomy.py and docs/global/taxonomy.md together"
    )
    assert counted["solar"] == 1, "the one-fund theme, asserted so nobody has to trust a doc"


def test_the_taxonomy_seeds_exactly_the_themes_the_rules_can_produce() -> None:
    """``theme_ids`` is a ``text[]`` with no foreign key, so nothing in Postgres catches a
    theme that has no ``taxonomy_sector`` row — a fund would simply point at a category that
    does not exist. In the other direction, a seeded theme with no rule is a filter that
    returns nothing forever. Both are one set comparison."""
    seeded = {row[0] for row in load_global_script("seed_taxonomy").THEMES}
    assert seeded == set(THEMES), (
        f"seeded but unreachable: {sorted(seeded - set(THEMES))}; "
        f"produced but unseeded: {sorted(set(THEMES) - seeded)}"
    )


def test_every_theme_hangs_off_a_real_gics_sector() -> None:
    """Level 3 rows carry ``parent_id`` as a FK to ``taxonomy_sector``, and the seed inserts
    all three levels in one statement — so a theme whose parent is misspelled fails the whole
    seed on the box, after ``make gate`` went green."""
    seed = load_global_script("seed_taxonomy")
    sectors = {sid for sid, _, _ in seed.SECTORS_L1}
    orphans = {tid: parent for tid, parent, _, _ in seed.THEMES if parent not in sectors}
    assert not orphans, f"themes whose parent is not a GICS level-1 sector: {orphans}"


def test_a_fund_with_no_theme_returns_none_rather_than_a_default(names: dict[str, str]) -> None:
    """The rules layer exists for precision, not recall. Most of the market has no theme, and
    a wrong ``infrastructure`` is worse than an honest gap — the same stance ``strategy.py``
    takes, one layer down."""
    for symbol in ("BIL", "SPY", "AGG"):
        assert symbol in names, f"{symbol} has left the snapshot — this test would pass vacuously"
        assert classify_theme(names[symbol]) is None, f"{symbol} ({names[symbol]}) has no theme"


def test_coverage_is_what_we_claim(etf_names: list[str]) -> None:
    """The themed share is a published number (``docs/global/taxonomy.md``) and the LLM layer
    is sized against it. A large move in either direction is a finding: patterns overfitted to
    chase coverage, or a vocabulary that has drifted away from the market."""
    themed = sum(1 for n in etf_names if classify_theme(n) is not None)
    share = themed / len(etf_names)
    assert 0.06 <= share <= 0.11, f"themes matched {share:.1%} of {len(etf_names)} real names"

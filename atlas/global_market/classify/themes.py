"""What an ETF is a bet ON — the theme, from its NAME, as an ordered first-match rule table.
Pure: no I/O, no DB, no thresholds.

``strategy.py`` answers "what job does this fund do" and stops: it marks 272 funds
``thematic`` and never says WHICH theme, so an artificial-intelligence fund, a uranium fund
and a water fund all landed in one undifferentiated bucket. That is the FM's complaint —
"it's not just energy, it's energy sources … funds around gold and silver miners … water and
food security" — and this module is the answer to it. It runs BESIDE the strategy table, not
under it: a gold-bullion trust is ``commodity`` by strategy and ``precious_metals`` by theme,
a uranium fund is ``thematic`` by strategy and ``nuclear_uranium`` by theme. Neither reading
replaces the other, and the theme is what the board can build a page around.

ORDER IS THE DESIGN, and one principle sets almost all of it:

    **THE INPUT BEATS THE TREND.** A fund that names a physical thing it holds — a metal, a
    fuel, a molecule, a machine — is a fund about that thing. The trend it is sold on
    (AI, electrification, clean energy, "infrastructure") is the story, and the stories are
    the widest rules at the BOTTOM of the table. So "Themes Lithium & Battery Metal Miners"
    is ``lithium``, not ``ev_battery``; "Global X AI Semiconductor & Quantum" is
    ``semiconductors``, not ``ai``; "First Trust NASDAQ Clean Edge Smart Grid Infrastructure"
    is ``grid_electrification``, not ``clean_energy`` and not ``infrastructure``.

The table therefore runs: metals and mining → energy sources → water, food and timber →
technology (narrow first, ``ai`` last as its umbrella) → life sciences → consumer → the two
widest umbrellas, ``reits`` and ``infrastructure``, last.

Three consequences of that order are worth stating, because each is a real fund:

* "US Global GO Gold and Precious Metal Miners" is ``gold_silver_miners``, NOT
  ``precious_metals``. The miner rule sits directly above the metal rule because a miners
  fund holds equity whose behaviour is levered to the metal, not the metal — and 39 names
  say "Miners" while carrying the metal's word.
* "ARK Space & Defense Innovation" is ``space``: ``space`` is above ``defence`` because it is
  the narrower mandate and ARKX is the market's space fund. "Aerospace" does NOT reach the
  space rule — ``\\bspace\\b`` needs a word boundary and "Aerospace" gives it none — which is
  the only reason 9 aerospace-and-defence funds are not misfiled as space funds.
* "Nicholas Defense and Rare Earth Income" is ``critical_minerals``, and that is the price of
  the principle above, stated rather than hidden: the fund names both, the metal is the
  physical thing, and the rule table has one answer per fund. It is asserted in the tests as
  a cost, not as a win.

SIX PHRASES IN THIS MARKET MEAN SOMETHING ELSE, and every one of them produced a wrong answer
before it was measured over all 5,655 listed names:

* "Blue Chip" is not a semiconductor (6 funds). ``chip`` refuses to match after "blue".
* "Infrastructure Capital" is an ISSUER, not an asset (4 funds, one of them a bond fund) —
  the same defect as "Global X" being read as a region in ``strategy.py``. "CYBER HORNET"
  (4 funds) and "Ai Funds" (1) are the same defect again, from two more issuers.
* "Grayscale Bitcoin MINI Trust" is not a bitcoin MINER, so the blockchain rule spells the
  two words out rather than reaching for a ``min\\w+`` prefix.
* "LifeX … Longevity Income" is an annuity-shaped income product, not a bet on ageing
  (8 funds). ``longevity`` refuses to match before "income", which is what keeps a
  bond-ladder line out of a demographics theme page.
* "AI Enhanced / Managed / Powered / Driven / Select" is AI as the METHOD — the fund is run
  by a model, it does not hold AI companies (11 funds). That lookahead is ``strategy.py``'s,
  word for word, so the two layers cannot drift apart on the same funds; the one term added
  to it here is the "Ai Funds" issuer above, which ``strategy.py`` still reads as a theme.

EVERY ALTERNATIVE IN EVERY PATTERN BELOW MATCHES AT LEAST ONE REAL LISTED NAME. Twenty-one
plausible terms were written first and deleted after measurement — ``photovoltaic``,
``atomic``, ``military``, ``homeland security``, ``marijuana``, ``maritime``, ``fertilizer``,
``gene editing`` and thirteen more — because vocabulary no issuer uses cannot be reviewed, cannot
be tested, and hides the fact that the theme it was meant to widen is smaller than it looks.

NO MATCH IS NOT A FAILURE. ``classify_theme`` returns ``None`` for a name whose theme the
words do not settle, which is most of the universe — the majority of ETFs are index, bond and
wrapper products with no theme to find. The caller records ``NO_MATCH`` as the rule that ran
and writes an EMPTY theme list, and the row's ``status`` is unchanged: a fund with no theme is
not a fund needing review, it is a fund with no theme.

    >>> classify_theme("VanEck Gold Miners ETF").theme
    'gold_silver_miners'
    >>> classify_theme("iShares 20+ Year Treasury Bond ETF") is None
    True
"""

from __future__ import annotations

import re
from typing import NamedTuple

# The 32 theme ids, in precedence order. This IS the set of level-3 ids
# ``scripts/global_market/seed_taxonomy.py`` seeds and ``etf_classification.theme_ids``
# holds; a theme here that is not seeded there is a fund pointing at a category that does
# not exist, which ``tests/unit/global_market/test_themes.py`` fails on.
THEMES: tuple[str, ...] = (
    "gold_silver_miners",
    "precious_metals",
    "copper",
    "lithium",
    "critical_minerals",
    "solar",
    "nuclear_uranium",
    "grid_electrification",
    "clean_energy",
    "water",
    "food_agriculture",
    "timber_forestry",
    "semiconductors",
    "quantum",
    "robotics",
    "cybersecurity",
    "cloud",
    "data_centres",
    "blockchain",
    "fintech",
    "space",
    "defence",
    "ev_battery",
    "ai",
    "genomics",
    "longevity",
    "gaming_esports",
    "cannabis",
    "homebuilders",
    "shipping",
    "reits",
    "infrastructure",
)

NO_MATCH = "no_theme_pattern"


class ThemeMatch(NamedTuple):
    """``rule`` names the pattern that fired, so a theme label is explainable on the board and
    reviewable in ``/admin/classify``, exactly as ``StrategyMatch.rule`` is. ``theme`` is
    always a real id — the absence of a theme is a ``None`` RESULT, not a ``None`` field, so
    no caller can write a row whose theme is half-present."""

    theme: str
    rule: str
    evidence: str  # the matched text, for the review queue


# ── the ordered rule table ──────────────────────────────────────────────────────────────
# (pattern, theme, rule name). FIRST match wins. Every pattern is vocabulary read off the
# 5,655 real listed ETF names, never a threshold, and every theme's count in
# `docs/global/taxonomy.md` is this table's own first-claim output.
#
# A prefix meant to catch a longer word carries `\w*`, never a bare `\b` — the defect that
# cost `strategy.py` four silent dead rules ("\bbiotech\b" matches nothing, because every
# real name says "Biotechnology").
RULES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    # ── metals and mining: the physical thing, most specific first ──────────────────────
    (
        # BOTH words, in this order, within one clause: 39 names say "Miners" and 6 say
        # "Mining", but "Sprott Junior Uranium Miners" and "Grayscale Bitcoin Miners" are not
        # precious-metal funds. Requiring the metal beside the miner word is what separates
        # them without listing every metal that is not gold.
        re.compile(
            r"\b(?:gold|silver|precious metals?)\b.{0,30}?\b(?:miner|mining|explorer|producer)\w*",
            re.I,
        ),
        "gold_silver_miners",
        "precious_metal_miners",
    ),
    (
        # `\bgold\b` and not `gold`: "Goldman Sachs" files 46 funds and "Golden Dragon"
        # another two, and every one of them would have been a bullion fund.
        re.compile(r"\b(?:gold|silver|platinum|palladium|bullion)\b|precious metals?", re.I),
        "precious_metals",
        "precious_metal_words",
    ),
    (re.compile(r"\bcopper\b", re.I), "copper", "copper_word"),
    (re.compile(r"\blithium\b", re.I), "lithium", "lithium_word"),
    (
        re.compile(
            r"rare earths?\b|critical (?:mineral|material|metal)\w*|strategic metals|"
            r"\bnickel\b|battery metals",
            re.I,
        ),
        "critical_minerals",
        "critical_minerals_words",
    ),
    # ── energy SOURCES, which is the distinction the FM asked for by name: a sector called
    # "energy" answers nothing, and these four funds' sources behave nothing alike ─────────
    (re.compile(r"\bsolar\b", re.I), "solar", "solar_word"),
    (
        re.compile(r"\buranium\b|\bnuclear\b|\bsmr\b", re.I),
        "nuclear_uranium",
        "nuclear_words",
    ),
    (
        # Above `clean_energy` and above `infrastructure`: "Clean Edge Smart Grid
        # Infrastructure" and "Electrification Infrastructure" are grid funds that carry both
        # of the wider words, and the grid is the thing they hold.
        re.compile(r"\bgrid\b|electrification|high voltage", re.I),
        "grid_electrification",
        "grid_words",
    ),
    (
        re.compile(
            r"clean energy|green energy|renewable\w*|\bwind\b|clean edge|energy transition",
            re.I,
        ),
        "clean_energy",
        "clean_energy_words",
    ),
    # ── the two the FM named that nothing in a sector hierarchy can express ──────────────
    (re.compile(r"\bwater\b", re.I), "water", "water_word"),
    (
        # "Food security" in the FM's words. Agriculture COMMODITY funds are here too and
        # deliberately: DBA and TAGS hold the crop rather than the farmer, but the question
        # "what is this fund a bet on" has the same answer for both, and the strategy column
        # already says which of the two it is.
        re.compile(r"\bfood\b|agricultur\w*|agribusiness|\bagtech\b", re.I),
        "food_agriculture",
        "food_agriculture_words",
    ),
    (re.compile(r"\btimber\b|forestry", re.I), "timber_forestry", "timber_words"),
    # ── technology, narrow first; `ai` last because it is the umbrella every one of these
    # funds is sold under and half of them name in passing ───────────────────────────────
    (
        # `(?<!blue )` is load-bearing and fixed-width so Python accepts it: six funds are
        # "Blue Chip" growth or value funds, and a bare `\bchips?\b` filed every one of them
        # as a semiconductor fund.
        re.compile(r"semiconductor\w*|(?<!blue )\bchips?\b|lithograph\w*|\bfabless\b", re.I),
        "semiconductors",
        "semiconductor_words",
    ),
    (re.compile(r"\bquantum\b", re.I), "quantum", "quantum_word"),
    (
        # `robotic\w*` and NOT `robot\w*`: "Robotaxi, Autonomous Vehicles" is a mobility fund,
        # and the bare prefix pulled it in here.
        re.compile(r"robotic\w*|\bautomation\b|humanoid\w*", re.I),
        "robotics",
        "robotics_words",
    ),
    (re.compile(r"\bcyber(?!\s+hornet)\w*", re.I), "cybersecurity", "cyber_word"),
    (re.compile(r"\bcloud\b", re.I), "cloud", "cloud_word"),
    (re.compile(r"data cent(?:er|re)\w*", re.I), "data_centres", "data_centre_words"),
    (
        # The EQUITY of the chain, never the coin: a bitcoin trust is `crypto` by strategy and
        # has no theme, while "Bitcoin Mining and Digital Power" holds listed miners. Same
        # distinction `strategy.py` draws in its crypto rule, from the other side.
        re.compile(r"blockchain|bitcoin mining|bitcoin miners\b|crypto infrastructure", re.I),
        "blockchain",
        "blockchain_words",
    ),
    (
        re.compile(r"fintech|digital banking|digital payment\w*", re.I),
        "fintech",
        "fintech_words",
    ),
    (
        # Above `defence` for ARKX ("Space & Defense Innovation"), the one name that claims
        # both. "Aerospace" cannot reach this rule — no word boundary before its "space" —
        # which is the whole reason the aerospace-and-defence funds below stay put.
        re.compile(r"\bspace\b|satellite\w*", re.I),
        "space",
        "space_words",
    ),
    (
        re.compile(r"\bdefen[cs]e\b|aerospace|warfare", re.I),
        "defence",
        "defence_words",
    ),
    (
        # `\bev\b` is safe under re.I here because exactly one real name uses it as a word
        # ("Self-Driving EV and Tech"); it is kept because that is the fund it was written for.
        re.compile(
            r"electric vehicle\w*|\bevs?\b|\bbatter(?:y|ies)\b|autonomous vehicle\w*|"
            r"self-?driving|robotaxi\w*|future mobility",
            re.I,
        ),
        "ev_battery",
        "ev_battery_words",
    ),
    (
        # The exclusion is copied verbatim from `strategy.py`'s thematic rule so the two
        # layers cannot disagree about the same eleven funds: "AI Enhanced Value" is a value
        # fund whose manager is a model, not a fund that holds AI companies.
        re.compile(
            r"artificial intelligence|generative ai|\bagentic\b|\bllm\b|"
            r"\bai\b(?![- ](?:enhanced|managed|powered|driven|select)|\s+funds\b)",
            re.I,
        ),
        "ai",
        "ai_words",
    ),
    # ── life sciences ───────────────────────────────────────────────────────────────────
    (
        # NOT `biotech`: biotechnology is a GICS sub-industry and `strategy.py` already files
        # those 17 funds as `sector`. The theme is the narrower claim the sector cannot make.
        re.compile(r"genomic\w*|\bgenome\b|precision medicine", re.I),
        "genomics",
        "genomics_words",
    ),
    (
        # `(?!\s+income)` keeps the eight LifeX products out. They are longevity-RISK income
        # ladders — the word is in the name because of what they insure against, not what
        # they hold, and eight bond-shaped funds on a demographics page is the kind of wrong
        # answer that reads perfectly plausibly.
        re.compile(r"longevity(?!\s+income)|\baging\b", re.I),
        "longevity",
        "longevity_words",
    ),
    # ── consumer ────────────────────────────────────────────────────────────────────────
    (
        re.compile(r"\besports\b|video gam\w*|\bi?gaming\b|metaverse", re.I),
        "gaming_esports",
        "gaming_words",
    ),
    (re.compile(r"cannabis|psychedelic\w*", re.I), "cannabis", "cannabis_words"),
    (
        re.compile(r"homebuilder\w*|home construction", re.I),
        "homebuilders",
        "homebuilder_words",
    ),
    (
        re.compile(r"\bshipping\b|\btankers?\b|dry bulk", re.I),
        "shipping",
        "shipping_words",
    ),
    # ── the two widest umbrellas, last, so every narrower claim above has already been
    # taken: 12 of the 51 "Infrastructure" names are a data centre, a grid or an energy
    # pipeline first ────────────────────────────────────────────────────────────────────
    (re.compile(r"\breits?\b", re.I), "reits", "reit_word"),
    (
        # `(?! capital)` excludes InfraCap's four funds — "Infrastructure Capital Bond
        # Income" is a bond fund from an issuer whose NAME is the word. Reading an issuer as
        # an asset is the same defect that once put a Treasury-bill fund on the world map.
        re.compile(r"\binfrastructure\b(?! capital)", re.I),
        "infrastructure",
        "infrastructure_word",
    ),
)


def classify_theme(name: str) -> ThemeMatch | None:
    """The one theme a fund name settles, or ``None`` when the words settle none.

    ``None`` is the common answer and is not a failure: most of the universe is index, bond
    and wrapper product with no theme to find. Callers record ``NO_MATCH`` as the rule that
    ran and write an empty theme list — never a guessed theme, and never a review flag, since
    "this fund has no theme" is an answer, not a gap.
    """
    for pattern, theme, rule in RULES:
        m = pattern.search(name)
        if m is not None:
            return ThemeMatch(theme, rule, m.group(0))
    return None

"""What an ETF IS — the primary classification axis, from its NAME, as an ordered first-match
rule table. Pure: no I/O, no DB, no thresholds.

The plan built the taxonomy around sector first, with strategy as a secondary attribute.
Counting the 5,655 real ETF names in the Nasdaq Trader directories overturned that: sector
funds are 6.2% of the universe, while buffer and defined-outcome products alone are 9.6%, and
under the schema's original eight strategy values the 543 buffer funds, 394 single-stock funds,
188 options-income funds, 114 crypto funds and 87 multi-asset funds had no value at all — every
one of them would have been filed as ``broad``. So strategy is the primary axis and the sector
hierarchy applies to the minority of funds for which it is the right question. The reasoning and
the counts are in ``docs/global/taxonomy.md``; this module is that document's executable half.

ORDER IS THE DESIGN. Each rule sits above the ones below it for a stated reason, and moving one
silently reclassifies hundreds of funds:

* ``single_stock`` and the three wrapper strategies come first because the WRAPPER is the
  product. A covered-call fund on the S&P 500 is an options-income fund, not a broad-market
  fund that happens to sell calls; a 2x bitcoin fund is crypto, not "leveraged".
* Asset classes come next, most specific first: crypto above alternative so a bitcoin fund is
  not merely "alternative"; ``fixed_income`` replaces the plan's ``bond_duration`` because
  duration is one attribute of 873 funds that differ at least as much by credit type.
* Equity shape comes last, narrow to broad: ``thematic`` above ``sector`` (a robotics fund is
  thematic, not "industrials"), ``country`` above ``region`` (a Japan fund is not "Asia"), and
  ``broad_market`` dead last because it is the fallback for a fund making no narrower claim.

GEARING IS NOT A STRATEGY. ``leveraged``/``inverse`` are boolean columns that ``rules.py``
already fills. A 2x bitcoin fund is ``crypto`` with ``leveraged=true``, which says both what it
tracks and how it is built; the plan's ``leveraged`` strategy value said only the second and
threw the first away.

NO MATCH IS NOT A FAILURE. ``classify_strategy`` returns ``None`` for a name whose strategy the
words do not settle, and that row goes to the LLM layer with ``status='review'``. The rules
layer exists for precision, not recall: a wrong ``broad_market`` is worse than an honest gap.

    >>> classify_strategy("First Trust Nasdaq Cybersecurity ETF").strategy
    'thematic'
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import NamedTuple

from atlas.global_market.classify.rules import leverage_flags

# The 17 values, in precedence order. This IS `etf_classification.strategy`'s CHECK list.
STRATEGIES: tuple[str, ...] = (
    "single_stock",
    "defined_outcome",
    "options_income",
    "crypto",
    "fixed_income",
    "commodity",
    "currency",
    "multi_asset",
    "alternative",
    "thematic",
    "sector",
    "country",
    "region",
    "dividend_income",
    "factor",
    "size_style",
    "broad_market",
)

NO_MATCH = "no_strategy_pattern"


class StrategyMatch(NamedTuple):
    """``rule`` names the pattern that fired, so every classification is explainable on the
    board and reviewable in ``/admin/classify``. ``strategy`` is None when the name does not
    settle it — that row is the LLM layer's job, not a silent ``broad_market``."""

    strategy: str | None
    rule: str
    evidence: str | None = None  # the matched text, for the review queue


# ── single_stock ────────────────────────────────────────────────────────────────────────
# A whole uppercase word of 2-5 characters — the shape a ticker takes inside a fund name
# ("2X Long AAPL Daily"). The boundary guards keep it from firing inside a word: without them
# "Pacer" yielded "P" and 5,639 of 5,655 names looked like single-stock funds.
TICKER_TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,5})(?![A-Za-z0-9])")

# Real listed tickers that appear in fund names as something OTHER than the underlying.
# Measured across all 5,655 names (2026-09-04 directories), each anchored to a real row; a
# guessed list here would silently mint or lose single-stock funds.
SYMBOL_COLLISIONS = frozenset(
    {
        # Issuer brands that are also tickers. Both keep their real underlying in the same
        # name, so dropping the brand costs nothing: T-REX names AFRM, MAX names its industry.
        "REX",  # T-REX 2X Long AFRM Daily Target ETF  (33 names)
        "MAX",  # MAX Auto Industry -3x Inverse Leveraged ETN
        # Product structure, not a company.
        "ETN",  # MicroSectors FANG & Innovation -3x Inverse Leveraged ETN  (15 names)
        # Index providers.
        "MSCI",  # ProShares UltraShort MSCI Brazil Capped  (12 names)
        # Basket and theme acronyms that collide with a real ticker. Both are the collision in
        # every occurrence measured, so they are excluded and the loss is stated: a genuine
        # single-stock fund on C3.ai or Diamondback Energy is a KNOWN MISS here and is answered
        # by holdings in Phase 2, never by widening this pattern.
        "AI",  # Direxion Daily AI and Big Data Bear 2X ETF
        "FANG",  # MicroSectors FANG & Innovation 3x Leveraged ETN
    }
)

# ── the ordered rule table ──────────────────────────────────────────────────────────────
# A prefix meant to catch a longer word carries `\w*`, never a bare `\b`: `\bbiotech\b`
# looks right and matches nothing, because every real name says "Biotechnology". Four
# patterns here were written that way and silently never fired until measured.
# (pattern, strategy, rule name). FIRST match wins. Every pattern is vocabulary read off the
# real names, not a threshold — see `docs/global/taxonomy.md` for the counts behind each.
RULES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    # Wrappers: the payoff shape IS the product, so it outranks whatever it references.
    (
        re.compile(
            r"\b(?:buffer(?:ed)?|defined outcome|target outcome|autocallable|"
            r"(?<!dividend )accelerat\w+|premium outcome|floor|defined protection|"
            r"target range|"
            r"dual directional|managed floor|structured (?:alt|outcome)|"
            # "protection" alone: Innovator files 42 funds as "Equity Defined Protection"
            # and Calamos as "Structured Alt Protection". No other product type in the real
            # 5,656-name directory uses the word, so it is specific enough to stand alone.
            r"protection)\b|\bbuffer\s?\d+",
            re.I,
        ),
        "defined_outcome",
        "defined_outcome_words",
    ),
    (
        re.compile(
            r"\b(?:covered call|buy-?write|option income|options income|"
            r"premium income|yieldmax|yieldboost|call writing|put write|"
            r"weekly ?pay|premium yield|enhanced yield|income boost|max income|"
            # "hedged equity" is NOT here, and that is the whole lesson of this rule group.
            # Fidelity and Calamos use it for an options overlay; Xtrackers and WisdomTree use
            # it for CURRENCY hedging ("MSCI Japan Hedged Equity"). Adding it filed seven
            # well-known currency-hedged country funds as options income. The currency case is
            # already captured by is_currency_hedged, so the term buys 16 funds at the price of
            # being wrong about ones anybody would recognise. Precision over recall.
            r"option strategy|collar\w*|target income)\b",
            re.I,
        ),
        "options_income",
        "options_income_words",
    ),
    # Asset classes, most specific first.
    (
        # `blockchain` is deliberately NOT here: a blockchain fund holds the equity of
        # companies using the technology, while a bitcoin fund holds the asset. It is caught
        # by `thematic` below. Coins and coin-trusts only.
        re.compile(
            r"\b(?:bitcoin|btc|ether(?:eum)?|crypto(?:currency)?|digital asset|"
            r"solana|litecoin|dogecoin|xrp|avalanche|cardano|chainlink|polkadot|"
            r"hedera|hbar|toncoin)\b",
            re.I,
        ),
        "crypto",
        "crypto_words",
    ),
    (
        re.compile(
            r"\b(?:bond|bonds|treasur(?:y|ies)|municipal|muni|aggregate|"
            # "High Yield" alone is a junk-bond fund; "High Yield EQUITY Dividend Achievers"
            # is an equity fund that happens to use the same two words. The lookahead is what
            # keeps Invesco's PEY in dividend_income where it belongs.
            r"investment grade|high[- ]yield(?!\s+(?:equity|dividend|stock))|"
            r"senior loan|leveraged loan|clo|"
            r"mortgage|mbs|tips|duration|maturity|fixed income|credit|debt|"
            r"convertible|preferred|t-?bills?|treasury bills?|"
            r"floating rate|securitiz\w+|cash management|money market|"
            # A SEPARATOR is required: ProShares spells -2x leverage "UltraShort" as one
            # word ("UltraShort MSCI Brazil Capped"), which is not a duration at all.
            r"ultra[- ]short|"
            r"government|govt|income bucket|yield curve)\b",
            re.I,
        ),
        "fixed_income",
        "fixed_income_words",
    ),
    (
        re.compile(
            r"\b(?:gold|silver|copper|platinum|palladium|crude oil|natural gas|"
            r"commodit(?:y|ies)|agriculture|precious metals|base metals|"
            r"livestock|wheat|corn|soybean|cocoa|coffee|sugar|"
            r"oil fund|gas fund|gasoline|heating oil|brent|carbon allowance|"
            r"carbon credit|bullion)\b",
            re.I,
        ),
        "commodity",
        "commodity_words",
    ),
    (
        re.compile(
            r"\b(?:currency|currencies|yen|euro\b|swiss franc|british pound|"
            r"sterling|peso|renminbi|yuan|forex)\b",
            re.I,
        ),
        "currency",
        "currency_words",
    ),
    (
        re.compile(
            r"\b(?:asset allocation|balanced|target date|multi-?asset|"
            r"target risk|retirement \d{4}|conservative allocation|aggressive allocation|"
            r"moderate allocation|growth allocation)\b",
            re.I,
        ),
        "multi_asset",
        "multi_asset_words",
    ),
    (
        re.compile(
            r"\b(?:managed futures|merger arbitrage|arbitrage|market neutral|"
            r"long/short|long-short|hedge fund|alternative|trend following|"
            # `volatility` ALONE is not an alternative strategy: "Disciplined
            # Volatility Equity" and "Income Enhanced Volatility Wtd" are equity
            # funds that were landing here. Only the volatility ASSET qualifies;
            # "low volatility" and "minimum volatility" are factor tilts, below.
            r"vix|volatility index|long volatility|short volatility|"
            r"absolute return|event driven)\b",
            re.I,
        ),
        "alternative",
        "alternative_words",
    ),
    # Equity shape, narrow to broad.
    (
        re.compile(
            r"\b(?:artificial intelligence|robotics|cybersecurity|cyber security|"
            r"semiconductor|genomic\w*|biotech innovation|clean energy|solar|wind|"
            r"uranium|nuclear|lithium|battery|electric vehicle|cloud computing|"
            r"fintech|blockchain|quantum|space|defense tech|cannabis|"
            r"esports|gaming|water|infrastructure|innovation|disrupt\w*|"
            r"self-?driving|autonomous|3d printing|smart factor\w+|next gen\w*|"
            r"\bai\b(?![- ](?:enhanced|managed|powered|driven|select))|"
            r"agentic|metaverse|obesity|longevity|drone|satellite|"
            r"rare earth|electrification|megatrend|thematic)\b",
            re.I,
        ),
        "thematic",
        "thematic_words",
    ),
    (
        re.compile(
            # `industrials?(?! average)` — "Dow Jones INDUSTRIAL Average" is the third-most
            # quoted index in the world and this rule filed it as an industrials SECTOR bet,
            # because `sector` is ordered above `broad_market` and the word is right there in
            # the name. DIA then ranked against XLI and friends instead of against SPY. The
            # lookahead is the whole fix: no sector fund is called "... Industrial Average".
            r"\b(?:technology|financials?|health ?care|energy|utilities|"
            r"industrials?(?! average)|materials|real estate|consumer discretionary|"
            r"consumer staples|communication services|banks?|insurance|"
            r"biotech\w*|pharmaceutical|retail|transportation|aerospace|mining|"
            r"homebuilder|semiconductors?|software|internet|media|telecom\w*|"
            r"reits?|agribusiness|food|beverage|staples|discretionary|airlines?|"
            r"auto(?:s|motive| industry)?|chemicals|leisure|travel|hotels?|"
            r"restaurants?|steel|shipping)\b",
            re.I,
        ),
        "sector",
        "sector_words",
    ),
    # `country` is a FOREIGN single-country bet, and the US is deliberately excluded.
    # The taxonomy does not settle this and the naive reading is unusable: every S&P 500
    # tracker states "U.S.", so a rule that took the word at face value would file the whole
    # American core of the universe as "country: United States" and leave `broad_market`
    # holding nothing. A US-listed fund's home market is the default, not a bet on it — so a
    # US fund falls through to `size_style` or `broad_market` below. OPEN FOR THE FM.
    (
        # `(?<!ex )(?<!ex-)` is load-bearing, and both lookbehinds are fixed-width so Python
        # accepts them: "iShares MSCI All Country Asia ex Japan" and "Emerging Markets
        # ex-China" name a country they deliberately EXCLUDE. Without this they classified as
        # single-country bets on exactly the market they leave out — a wrong answer that reads
        # perfectly plausibly on a card, which is the worst kind.
        re.compile(
            r"\b(?<!ex )(?<!ex-)(?:japan|china|india|brazil|mexico|canada|germany|france|"
            r"united kingdom|switzerland|australia|south korea|korea|taiwan|"
            r"indonesia|vietnam|thailand|malaysia|singapore|philippines|"
            r"turkey|poland|israel|saudi|south africa|nigeria|egypt|chile|"
            r"colombia|peru|argentina|spain|italy|netherlands|sweden|norway|"
            r"denmark|finland|belgium|austria|ireland|portugal|greece|"
            r"new zealand|hong kong|pakistan|bangladesh|qatar|kuwait|uae)\b",
            re.I,
        ),
        "country",
        "country_name",
    ),
    (
        re.compile(
            r"\b(?:emerging markets?|developed markets?|frontier markets?|"
            r"developing world|international|global|world|ex-?u\.?s\.?|"
            r"ex-?china|asia|europe|eurozone|latin america|"
            r"pacific|nordic|acwi|eafe|africa|middle east|"
            r"all country|worldwide|foreign|emerging|developed|em\b|"
            r"ex-?japan|asean|brics|chinext)\b",
            re.I,
        ),
        "region",
        "region_words",
    ),
    # Below the wrappers above, so a covered-call fund is not merely "income".
    (
        re.compile(
            r"\b(?:dividend|equity income|income equity|high dividend|"
            r"dividend growth|dividend aristocrat|distribution|payout|"
            r"shareholder yield)\b",
            re.I,
        ),
        "dividend_income",
        "dividend_words",
    ),
    (
        re.compile(
            r"\b(?:quality|momentum|low volatility|minimum volatility|"
            r"equal ?weight|multi-?factor|factor|smart beta|"
            r"fundamental index|research enhanced|moat|buyback|"
            r"free cash flow|\bfcf\b|profitab\w*)\b",
            re.I,
        ),
        "factor",
        "factor_words",
    ),
    (
        re.compile(
            r"\b(?:large[ -]?cap|mid[ -]?cap|small[ -]?cap|micro[ -]?cap|"
            r"mega[ -]?cap|smid|small[ -]?(?:and[ -]?)?mid|ultra[- ]small|"
            r"growth|value|blend|"
            r"top \d{2,4})\b",
            re.I,
        ),
        "size_style",
        "size_style_words",
    ),
    # Last: the fallback for a fund making no narrower claim. Still a POSITIVE match — a name
    # with none of this vocabulary returns None and goes to the LLM, never silently here.
    (
        re.compile(
            # `total (u.s. )?(stock )?market` — the country word sits INSIDE the phrase on the
            # biggest names: "iShares Core S&P Total U.S. Stock Market" (ITOT) matched nothing
            # at all, because the pattern expected "total stock market" unbroken. A total-market
            # tracker that the rules cannot read is not a small gap; it is the fallback bucket
            # failing on the funds it exists for.
            r"\b(?:total (?:u\.?s\.?\s+)?(?:stock )?market|broad market|s&p 500|"
            r"russell \d{4}|nasdaq-?100|dow jones industrial|"
            r"total market|core equity|equity index|market index|"
            r"\d{3,4} index)\b",
            re.I,
        ),
        "broad_market",
        "broad_market_words",
    ),
)


def _stated_symbol(name: str, active_symbols: Iterable[str] | set[str]) -> str | None:
    """The one real ticker a name states, or None. Collisions are excluded by measurement."""
    known = active_symbols if isinstance(active_symbols, set) else set(active_symbols)
    for token in TICKER_TOKEN.findall(name):
        if token in SYMBOL_COLLISIONS:
            continue
        if token in known:
            return token
    return None


def classify_strategy(name: str, active_symbols: Iterable[str] | set[str] = ()) -> StrategyMatch:
    """Strategy for one fund name. ``active_symbols`` is the real listed-equity symbol set —
    empty disables the single-stock rule rather than guessing, because that rule is the only
    one needing evidence from outside the name."""
    # single_stock is first and needs BOTH signals. A ticker alone is not enough: "MSCI Brazil"
    # and "FANG & Innovation" state real tickers and track neither company. Gearing alone is not
    # enough either — most geared funds track an index. Requiring both is what the 2026-09-04
    # census supports; an ungeared single-stock fund (YieldMax's TSLY) is an options-income
    # wrapper and is correctly caught one rule below.
    flags = leverage_flags(name)
    if flags.leveraged or flags.inverse:
        symbol = _stated_symbol(name, active_symbols)
        if symbol is not None:
            return StrategyMatch("single_stock", "geared_single_symbol", symbol)

    for pattern, strategy, rule in RULES:
        m = pattern.search(name)
        if m is not None:
            return StrategyMatch(strategy, rule, m.group(0))

    return StrategyMatch(None, NO_MATCH, None)

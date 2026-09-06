"""Leveraged / inverse structure flags from an instrument's NAME — one pure function over an
ordered first-match rule table, in the shape of India's ``scripts/foundation/etf_sector.py``.

Why it exists now: the FM's universe decision of 2026-09-06 excludes leveraged and inverse
ETFs (``docs/global/plan.md`` "Universe"), and the only L0 fact Phase 1 has for every one of
the 5,656 active ETFs is the Nasdaq/SEC directory name. This IS the ``rules.py`` the
classification engine plans as its L2 layer, started early for that one filter — Phase 2
SUPERSEDES the name evidence with holdings, ``derivatives_share`` and issuer data from
``etf_meta``/N-PORT, at which point the flags this file guesses at from marketing words become
flags read off the portfolio. Nothing here is a threshold: the patterns are the vocabulary of
the real names, and every one of them is anchored in a row that exists (see the tests).

The vocabulary is ambiguous and the ORDER is the whole design, derived by reading all 5,656
active ETF names (2026-09-06):

* A stated multiple ("2X Long", "-3x Short", "1.5X", "2xLeveraged") is unambiguous from any
  issuer — 665 of the names carry one, and every leveraged fund outside ProShares does.
* "Ultra" and "Short" are ProShares' words for 2x and -1x (AGQ, DUG, DOG) and everyone else's
  words for bond DURATION (AMUN, BSV, DLUX) or a size band (BUSM :: Ultra-Small). Only the
  ISSUER separates them, so those three rules are anchored at the start of the name. That
  anchoring is also what keeps ``CLIX :: ProShares Long Online/Short Stores ETF`` — a
  long/short equity fund from the leveraged house — out of the inverse bucket.
* "Leveraged" is a fund structure (MSOX, BNKU) except in "Leveraged Loan", which is an asset
  class (LVLN), so the asset class is excluded first.

``multiple`` is filled ONLY from a number the name states. ProShares' words do not carry one:
"Ultra" is 2x for 50 funds but 1.5x for UVXY, and "Short" is -1x for 16 funds but -0.5x for
SVXY — a constant here would be a number no source printed (rule #0). Absent is absent.

KNOWN MISSES, measured 2026-09-06 and left for Phase 2 rather than guessed at here: a fund whose
gearing is stacked exposure states no multiple at all — the 8 ``Return Stacked …`` funds, ``BTGD``
(STKd 100% Bitcoin & 100% Gold), ``ISBG`` / ``ISSB`` (IncomeSTKd 1x A & 1x B), ``UPAR`` (a 1.4x
risk-parity fund) — and YieldMax's ``FIAT`` / ``WNTR`` / ``CRSH`` / ``DIPS`` / ``YQQQ`` wrap short
exposure in an option-income strategy. Summing "1x A & 1x B" to 2 would invent an allocation the
name never gives; ``derivatives_share`` and holdings answer all of them in Phase 2.

    >>> leverage_flags("ProShares UltraShort Energy")
    LeverageFlags(leveraged=True, inverse=True, multiple=None, rule='proshares_ultrashort')
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import NamedTuple


class LeverageFlags(NamedTuple):
    """``rule`` names the pattern that fired, so every exclusion is explainable on the board
    and in the universe report. ``multiple`` is the MAGNITUDE (direction is ``inverse``)."""

    leveraged: bool
    inverse: bool
    multiple: Decimal | None
    rule: str


EXPLICIT_MULTIPLE = "explicit_multiple"
NO_MATCH = "no_leverage_pattern"

# A multiple the name states: "2X Long", "-3x Short", "1.5X", "1.25x", and ETRACS' unspaced
# "2xLeveraged". `?` is an alternative to X, not a wildcard: the Nasdaq directory carries
# MicroSectors' "-3? Short …" / "3? Long …" (AIQD, AIQU) where the X was mangled upstream —
# the real bytes are matched as they are, never repaired. The trailing (?![a-z0-9]) keeps
# "LifeX 2050" and "1a??10 Year TIPS" out; the leading guard keeps "…X 2050" out.
MULTIPLE_RE = re.compile(r"(?<![A-Za-z0-9])(-?\d+(?:\.\d+)?)\s*[xX?](?![a-z0-9])")

# Which way a stated multiple points. "Bull"/"Long" are the other half of the same vocabulary
# and need no pattern: not-inverse is the default. Checked only for names that already carry
# a multiple, where all 49 "Short", 40 "Bear" and 16 "Inverse" occurrences are directional.
DIRECTION_RE = re.compile(r"\b(?:short|bear|inverse)\b", re.IGNORECASE)

# (pattern, rule name, leveraged, inverse) — FIRST match wins. EXPLICIT_MULTIPLE's flags are
# recomputed from the number it captured; every other row states its flags outright.
RULES: tuple[tuple[re.Pattern[str], str, bool, bool], ...] = (
    # An asset class, not a structure: LVLN :: State Street SPDR S&P Leveraged Loan ETF makes
    # senior loans to leveraged BORROWERS. Must beat the bare word below.
    (re.compile(r"\bleveraged loan", re.IGNORECASE), "leveraged_loan_asset_class", False, False),
    (MULTIPLE_RE, EXPLICIT_MULTIPLE, True, False),
    # ProShares, anchored. UltraShort / UltraPro Short are geared AND inverse, so they come
    # before plain Ultra; a handful of directory rows drop the issuer from the compound word
    # ProShares alone coins (SDOW :: "UltraPro Short Dow30", UMDD :: "UltraPro MidCap400").
    (
        re.compile(r"^(?:ProShares UltraShort|(?:ProShares )?UltraPro Short)"),
        "proshares_ultrashort",
        True,
        True,
    ),
    (re.compile(r"^(?:ProShares Ultra|UltraPro)"), "proshares_ultra", True, False),
    (re.compile(r"^ProShares Short\b"), "proshares_short", False, True),
    # MicroSectors writes the pair out in full ("-3 Inverse Leveraged ETNs"); the bare number
    # there carries no X, so the multiple stays absent.
    (re.compile(r"\binverse leveraged\b", re.IGNORECASE), "inverse_leveraged_words", True, True),
    (re.compile(r"\bleverage[ds]?\b", re.IGNORECASE), "leverage_word", True, False),
    (re.compile(r"\binverse\b", re.IGNORECASE), "inverse_word", False, True),
)

CLEAN = LeverageFlags(False, False, None, NO_MATCH)


def leverage_flags(name: str) -> LeverageFlags:
    """Structure flags for one instrument name. Pure: no I/O, no DB, no thresholds."""
    for pattern, rule, leveraged, inverse in RULES:
        m = pattern.search(name)
        if m is None:
            continue
        if rule != EXPLICIT_MULTIPLE:
            return LeverageFlags(leveraged, inverse, None, rule)
        stated = Decimal(m.group(1))
        # |x| = 1 is inverse without gearing (AAPD :: Direxion Daily AAPL Bear 1X ETF).
        return LeverageFlags(
            abs(stated) > 1,
            stated < 0 or DIRECTION_RE.search(name) is not None,
            abs(stated),
            rule,
        )
    return CLEAN

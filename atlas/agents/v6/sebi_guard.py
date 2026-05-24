"""Keyword-based SEBI guard for generated briefs.

This module implements the **basic** SEBI guard — case-insensitive
forbidden-phrase substring detection. It catches the recommendation
language that the SEBI RA regulations forbid in research output.

The **full** factuality guard (per-claim numeric verification +
hallucinated-entity check) is the scope of issue #29; it replaces this
keyword check with a layered guard. Until then, this module is the
final layer between LLM output and the cache.

Reference: CONTEXT.md "LLM factuality guard" section + the v5 SP07
``atlas.agents.specialists._sebi`` constants.

Examples
========
>>> check_brief("INFY ranks highly in the RS framework today.")
>>> # returns silently — no forbidden phrase
>>> check_brief("You should buy INFY today for guaranteed returns.")
Traceback (most recent call last):
    ...
atlas.agents.v6.sebi_guard.SEBIGuardTripped: ...
"""

from __future__ import annotations


class SEBIGuardTripped(RuntimeError):  # noqa: N818 — descriptive name; "TrippedError" is awkward
    """Raised when a brief contains a SEBI-forbidden phrase.

    Carries the offending phrase in :attr:`phrase` so the caller can log
    which keyword tripped (the brief text itself is NOT included on the
    exception per the no-PII-in-logs rule — at runtime the brief content
    can reference live tickers, which we treat as sensitive context).
    """

    def __init__(self, phrase: str) -> None:
        super().__init__(f"forbidden phrase detected: {phrase!r}")
        self.phrase = phrase


# Forbidden phrase allowlist. Case-insensitive substring match (so
# variants like "BUY", "Buy", "you Should buy" all trip).
#
# Categories covered:
#   * Guarantee / risk-free claims (SEBI RA: no return guarantees)
#   * Direct action verbs in 2nd person ("you should buy")
#   * 1st-person recommendation ("I recommend", "we suggest")
#   * Target-price language ("target of Rs", "price target")
#
# Single-word verbs (buy, sell) are intentionally NOT in the list — the
# v5 SP07 specialists' system prompt forbids them but a substring check
# would false-positive on "buyer", "selling pressure", "investment
# horizon". Phrase-level matches catch the regulated-action language
# without those false positives.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    # Guarantee / risk-free language
    "guaranteed return",
    "guaranteed returns",
    "guaranteed profit",
    "guaranteed profits",
    "risk-free",
    "risk free return",
    "definite profit",
    "definite return",
    "assured return",
    "assured profit",
    "no risk",
    "zero risk",
    "sure-shot",
    "sure shot",
    "100% return",
    "100% profit",
    # Direct action verbs (2nd person)
    "you should buy",
    "you should sell",
    "you must buy",
    "you must sell",
    "must buy",
    "must sell",
    "buy now",
    "sell now",
    "buy today",
    "sell today",
    "buy this stock",
    "sell this stock",
    # 1st-person recommendation
    "i recommend",
    "we recommend",
    "i advise",
    "we advise",
    "i suggest you",
    "we suggest you",
    # Target-price language (SEBI RA: forecasts forbidden)
    "target price of",
    "price target of",
    "target of rs",
    "target of ₹",
    "will reach",
    "will hit",
)


def check_brief(brief: str) -> None:
    """Raise :exc:`SEBIGuardTripped` if ``brief`` contains a forbidden phrase.

    Case-insensitive substring match against :data:`FORBIDDEN_PHRASES`.
    Returns silently on success.

    Parameters
    ----------
    brief:
        The LLM-generated brief text (or any candidate string).

    Raises
    ------
    SEBIGuardTripped
        If any forbidden phrase is detected.
    """
    if not isinstance(brief, str):
        raise TypeError(f"brief must be str, got {type(brief).__name__}")
    lower = brief.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lower:
            raise SEBIGuardTripped(phrase)


def is_safe(brief: str) -> bool:
    """Return True iff :func:`check_brief` would pass.

    Convenience wrapper for code paths that want a boolean rather than
    exception flow.
    """
    try:
        check_brief(brief)
    except SEBIGuardTripped:
        return False
    return True

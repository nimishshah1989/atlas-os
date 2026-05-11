"""SP03: keyword-based intent classifier for OpenBB query routing.

``classify_intent()`` is a pure function — no DB, no FastAPI, no async.
It is deliberately isolated here so it can be unit-tested without any
infrastructure setup.

V1 strategy: case-insensitive substring matching, first-match wins.
V2 upgrade path: when no keyword matches, call Claude with Atlas-context
system prompt (stub noted below, out of scope for SP03).

Intent keys match the keys in ``HANDLER_DISPATCH`` in ``handlers/__init__.py``.
"""

from __future__ import annotations

# Keyword table: (intent_key, tuple_of_trigger_phrases).
# Order matters — more-specific phrases must appear before general ones.
# All phrases are matched case-insensitively against the full query text.
_KEYWORD_TABLE: list[tuple[str, tuple[str, ...]]] = [
    (
        "breakouts",
        (
            "breakout",
            "breaking out",
            "new leaders",
            "transitioning",
            "just entered",
            "breakout candidates",
            "fresh breakouts",
        ),
    ),
    (
        "rotation",
        (
            "rotation",
            "sector rotation",
            "rrg",
            "relative rotation",
            "sectors rotating",
            "quadrant",
            "leading sectors",
            "weakening sectors",
            "improving sectors",
            "lagging sectors",
            "sectors are leading",
            "sectors are lagging",
            "sectors are improving",
            "sectors are weakening",
        ),
    ),
    (
        "leaders",
        (
            "top stocks",
            "leaders",
            "rs leaders",
            "strongest stocks",
            "leading stocks",
            "top rs",
            "best performers",
        ),
    ),
    (
        "regime",
        (
            "regime",
            "market state",
            "risk-on",
            "risk on",
            "risk off",
            "risk-off",
            "deployment",
            "dislocation",
            "market regime",
        ),
    ),
]


def classify_intent(query_text: str) -> str:
    """Return the intent key for ``query_text``, or ``"unknown"`` if no match.

    Args:
        query_text: The raw user query string (last user message).

    Returns:
        One of: ``"regime"``, ``"leaders"``, ``"rotation"``, ``"breakouts"``,
        ``"unknown"``.
    """
    lower = query_text.lower()
    for intent_key, triggers in _KEYWORD_TABLE:
        if any(phrase in lower for phrase in triggers):
            return intent_key
    # V2: route to Claude here with Atlas-context system prompt.
    # For now, return "unknown" → fallback message_chunk in query.py.
    return "unknown"

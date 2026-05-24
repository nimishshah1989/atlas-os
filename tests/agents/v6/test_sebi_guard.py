"""Tests for ``atlas.agents.v6.sebi_guard``.

Coverage:
* Each FORBIDDEN_PHRASES category trips the guard.
* Safe research prose passes silently.
* Case-insensitivity (uppercase + mixed).
* Type guard rejects non-str inputs.
* :func:`is_safe` mirrors :func:`check_brief` boolean-for-exception.
"""

from __future__ import annotations

import pytest

from atlas.agents.v6.sebi_guard import (
    FORBIDDEN_PHRASES,
    SEBIGuardTripped,
    check_brief,
    is_safe,
)

# ---------------------------------------------------------------------------
# Forbidden phrase enumeration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", list(FORBIDDEN_PHRASES))
def test_check_brief_trips_on_every_forbidden_phrase(phrase: str) -> None:
    """Every entry in :data:`FORBIDDEN_PHRASES` must trip the guard.

    Note: substring matches mean a plural form like ``guaranteed returns``
    is caught by the singular ``guaranteed return`` entry that comes
    earlier in the tuple — the test asserts that *some* allowlisted
    phrase trips, not necessarily the exact one passed.
    """
    brief = f"Sample text {phrase} more text."
    with pytest.raises(SEBIGuardTripped) as exc_info:
        check_brief(brief)
    # The tripped phrase must be in the allowlist and present in the brief.
    assert exc_info.value.phrase in FORBIDDEN_PHRASES
    assert exc_info.value.phrase in brief.lower()


def test_check_brief_case_insensitive_uppercase() -> None:
    """Uppercase forbidden phrase still trips."""
    with pytest.raises(SEBIGuardTripped):
        check_brief("YOU SHOULD BUY this stock today.")


def test_check_brief_case_insensitive_mixed_case() -> None:
    """Mixed-case forbidden phrase still trips."""
    with pytest.raises(SEBIGuardTripped):
        check_brief("Yields a GuArAnTeEd Return over the cycle.")


# ---------------------------------------------------------------------------
# Safe prose
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "brief",
    [
        "INFY ranks highly in the RS framework today and signals strength.",
        "Mid-cap Pullback registers improving momentum at 75% historical confidence.",
        "TCS exhibits weakening breadth in the recent window.",
        "The stock appears in the leaders table for the 12-month cell.",
        "Cell exhibits 75.2% confidence in the Risk-On regime.",
    ],
)
def test_check_brief_passes_safe_prose(brief: str) -> None:
    """Research-language briefs must pass silently."""
    check_brief(brief)  # should not raise


def test_check_brief_empty_string_passes() -> None:
    """Empty string contains no forbidden phrases — passes."""
    check_brief("")


# ---------------------------------------------------------------------------
# Type / input safety
# ---------------------------------------------------------------------------


def test_check_brief_rejects_non_string() -> None:
    """Non-str input is a programmer bug — surface it loudly."""
    with pytest.raises(TypeError, match="brief must be str"):
        check_brief(123)  # type: ignore[arg-type]


def test_check_brief_rejects_none() -> None:
    with pytest.raises(TypeError, match="brief must be str"):
        check_brief(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# is_safe wrapper
# ---------------------------------------------------------------------------


def test_is_safe_true_for_safe_brief() -> None:
    assert is_safe("INFY ranks highly today.") is True


def test_is_safe_false_for_forbidden_brief() -> None:
    assert is_safe("You should buy INFY now.") is False


def test_is_safe_does_not_swallow_type_error() -> None:
    """:func:`is_safe` should propagate type errors — those are bugs."""
    with pytest.raises(TypeError):
        is_safe(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Categories — sanity checks
# ---------------------------------------------------------------------------


def test_guarantee_category_present() -> None:
    """The guarantee category must be in the allowlist (smoke check)."""
    assert "guaranteed return" in FORBIDDEN_PHRASES
    assert "risk-free" in FORBIDDEN_PHRASES


def test_action_verb_category_present() -> None:
    assert "you should buy" in FORBIDDEN_PHRASES
    assert "must sell" in FORBIDDEN_PHRASES


def test_first_person_recommendation_category_present() -> None:
    assert "i recommend" in FORBIDDEN_PHRASES
    assert "we advise" in FORBIDDEN_PHRASES


def test_target_price_category_present() -> None:
    assert "target price of" in FORBIDDEN_PHRASES
    assert "will reach" in FORBIDDEN_PHRASES


def test_bare_verbs_not_in_phrase_list() -> None:
    """Bare 'buy'/'sell' must NOT be in FORBIDDEN_PHRASES.

    Substring 'buy' would false-positive on 'buyer', 'buy-side'.  The
    v5 SP07 system prompt forbids the bare verb in generation; here we
    rely on phrase-level matches that capture the *recommendation
    context*.
    """
    assert "buy" not in FORBIDDEN_PHRASES
    assert "sell" not in FORBIDDEN_PHRASES
    # Sanity: a brief that mentions 'buyers' should pass.
    check_brief("Buyers stepped up in the recent breadth window.")

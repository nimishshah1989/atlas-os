"""Tests for ``atlas.agents.v6.brief_generator``.

Coverage:
* Cache hit short-circuits the pipeline (no Groq call).
* Cache miss → Groq call → cache write.
* Groq failure → deterministic fallback served.
* Groq returns forbidden phrase → SEBI guard trips → fallback served.
* Empty Groq output → fallback served.
* :func:`_deterministic_fallback` never raises (property-style sweep).
* Missing signal_call row → safe placeholder fallback.
* MAX_CONCURRENT_GROQ_CALLS is exposed at module level.
* write_to_cache=False skips the cache write.

DB I/O is mocked by patching the cache + context fetch helpers.  No
live Postgres required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

from atlas.agents.v6 import brief_generator as bg
from atlas.agents.v6.brief_generator import (
    MAX_CONCURRENT_GROQ_CALLS,
    BriefGenerationResult,
    GroqClient,
    _deterministic_fallback,
    _missing_signal_fallback,
    generate_brief,
)

SIGNAL_CALL_ID = UUID("00000000-0000-4000-8000-000000000123")
INSTRUMENT_ID = UUID("00000000-0000-4000-8000-000000000456")
CELL_ID = UUID("00000000-0000-4000-8000-000000000789")
SCORECARD_ID = UUID("00000000-0000-4000-8000-000000000abc")


def _ctx_fixture() -> dict[str, Any]:
    return {
        "signal_call": {
            "signal_call_id": SIGNAL_CALL_ID,
            "instrument_id": INSTRUMENT_ID,
            "date": date(2026, 5, 20),
            "cell_id": CELL_ID,
            "cap_tier_at_trigger": "MID",
            "tenure": "TWELVE_MONTH",
            "action": "POSITIVE",
            "confidence_unconditional": Decimal("0.7520"),
            "regime_state_at_call": "RISK_ON",
            "stable_features": ["rs_z", "trend_slope"],
            "predicted_excess": Decimal("0.299"),
        },
        "cell": {"rule_type": "Pullback"},
        "instrument": {"symbol": "INFY", "company_name": "Infosys Ltd"},
        "recent_corp_actions": [],
    }


@dataclass
class _FakeGroq:
    """Test double for :class:`GroqClient`."""

    output: str = "INFY ranks highly in the RS framework today."
    raise_exc: Exception | None = None
    seen_prompt: str | None = None

    def complete(self, prompt: str, *, max_tokens: int = 200, timeout_s: float = 10.0) -> str:
        self.seen_prompt = prompt
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.output


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_max_concurrent_groq_calls_exposed() -> None:
    """Eng review §4 Finding 4.C — orchestrator-layer cap is at this value."""
    assert MAX_CONCURRENT_GROQ_CALLS == 4


def test_groq_client_protocol_is_runtime_checkable() -> None:
    """Mock objects pass the isinstance check."""
    assert isinstance(_FakeGroq(), GroqClient)


# ---------------------------------------------------------------------------
# Cache hit path
# ---------------------------------------------------------------------------


def test_cache_hit_returns_immediately() -> None:
    """When the cache has a fresh row, no Groq call should occur."""
    engine = MagicMock()
    groq = _FakeGroq()
    with (
        patch.object(bg, "_lookup_cache", return_value="cached brief text") as mock_lookup,
        patch.object(bg, "_fetch_brief_context") as mock_fetch,
        patch.object(bg, "open_readonly_session") as mock_session,
    ):
        result = generate_brief(SIGNAL_CALL_ID, engine, groq_client=groq)
    assert isinstance(result, BriefGenerationResult)
    assert result.cache_hit is True
    assert result.brief_text == "cached brief text"
    assert result.fallback_used is False
    assert result.sebi_guard_tripped is False
    assert result.cache_written is False
    mock_lookup.assert_called_once()
    mock_fetch.assert_not_called()
    mock_session.assert_not_called()
    assert groq.seen_prompt is None  # Groq never invoked


# ---------------------------------------------------------------------------
# Cache miss → Groq success path
# ---------------------------------------------------------------------------


def test_cache_miss_calls_groq_and_writes_cache() -> None:
    engine = MagicMock()
    groq = _FakeGroq(output="INFY ranks highly in the RS framework today.")
    with (
        patch.object(bg, "_lookup_cache", return_value=None),
        patch.object(bg, "_fetch_brief_context", return_value=_ctx_fixture()),
        patch.object(bg, "open_readonly_session") as mock_session,
        patch.object(bg, "_write_cache") as mock_write,
    ):
        mock_session.return_value.__enter__.return_value = MagicMock()
        result = generate_brief(SIGNAL_CALL_ID, engine, groq_client=groq)
    assert result.cache_hit is False
    assert result.fallback_used is False
    assert result.sebi_guard_tripped is False
    assert result.brief_text.startswith("INFY ranks highly")
    assert result.cache_written is True
    assert groq.seen_prompt is not None
    assert "INFY" in groq.seen_prompt
    mock_write.assert_called_once()


def test_cache_miss_write_disabled_skips_cache() -> None:
    engine = MagicMock()
    groq = _FakeGroq()
    with (
        patch.object(bg, "_lookup_cache", return_value=None),
        patch.object(bg, "_fetch_brief_context", return_value=_ctx_fixture()),
        patch.object(bg, "open_readonly_session") as mock_session,
        patch.object(bg, "_write_cache") as mock_write,
    ):
        mock_session.return_value.__enter__.return_value = MagicMock()
        result = generate_brief(SIGNAL_CALL_ID, engine, groq_client=groq, write_to_cache=False)
    assert result.cache_written is False
    mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# Groq failure → deterministic fallback
# ---------------------------------------------------------------------------


def test_groq_failure_returns_fallback() -> None:
    engine = MagicMock()
    groq = _FakeGroq(raise_exc=RuntimeError("groq HTTP 500"))
    with (
        patch.object(bg, "_lookup_cache", return_value=None),
        patch.object(bg, "_fetch_brief_context", return_value=_ctx_fixture()),
        patch.object(bg, "open_readonly_session") as mock_session,
        patch.object(bg, "_write_cache"),
    ):
        mock_session.return_value.__enter__.return_value = MagicMock()
        result = generate_brief(SIGNAL_CALL_ID, engine, groq_client=groq)
    assert result.fallback_used is True
    assert result.sebi_guard_tripped is False
    assert "INFY" in result.brief_text
    assert "Pullback" in result.brief_text


def test_groq_timeout_returns_fallback() -> None:
    engine = MagicMock()
    groq = _FakeGroq(raise_exc=TimeoutError("groq read timeout"))
    with (
        patch.object(bg, "_lookup_cache", return_value=None),
        patch.object(bg, "_fetch_brief_context", return_value=_ctx_fixture()),
        patch.object(bg, "open_readonly_session") as mock_session,
        patch.object(bg, "_write_cache"),
    ):
        mock_session.return_value.__enter__.return_value = MagicMock()
        result = generate_brief(SIGNAL_CALL_ID, engine, groq_client=groq)
    assert result.fallback_used is True


def test_groq_empty_output_returns_fallback() -> None:
    engine = MagicMock()
    groq = _FakeGroq(output="   ")
    with (
        patch.object(bg, "_lookup_cache", return_value=None),
        patch.object(bg, "_fetch_brief_context", return_value=_ctx_fixture()),
        patch.object(bg, "open_readonly_session") as mock_session,
        patch.object(bg, "_write_cache"),
    ):
        mock_session.return_value.__enter__.return_value = MagicMock()
        result = generate_brief(SIGNAL_CALL_ID, engine, groq_client=groq)
    assert result.fallback_used is True


# ---------------------------------------------------------------------------
# SEBI guard trip → fallback
# ---------------------------------------------------------------------------


def test_sebi_guard_trip_returns_fallback_and_sets_flag() -> None:
    engine = MagicMock()
    groq = _FakeGroq(output="You should buy INFY today for guaranteed returns.")
    with (
        patch.object(bg, "_lookup_cache", return_value=None),
        patch.object(bg, "_fetch_brief_context", return_value=_ctx_fixture()),
        patch.object(bg, "open_readonly_session") as mock_session,
        patch.object(bg, "_write_cache"),
    ):
        mock_session.return_value.__enter__.return_value = MagicMock()
        result = generate_brief(SIGNAL_CALL_ID, engine, groq_client=groq)
    assert result.fallback_used is True
    assert result.sebi_guard_tripped is True
    # Fallback text must NOT contain the forbidden phrase.
    assert "you should buy" not in result.brief_text.lower()
    assert "guaranteed return" not in result.brief_text.lower()


# ---------------------------------------------------------------------------
# Missing signal_call → safe placeholder
# ---------------------------------------------------------------------------


def test_missing_signal_call_returns_safe_fallback() -> None:
    engine = MagicMock()
    groq = _FakeGroq()
    with (
        patch.object(bg, "_lookup_cache", return_value=None),
        patch.object(bg, "_fetch_brief_context", return_value=None),
        patch.object(bg, "open_readonly_session") as mock_session,
    ):
        mock_session.return_value.__enter__.return_value = MagicMock()
        result = generate_brief(SIGNAL_CALL_ID, engine, groq_client=groq)
    assert result.fallback_used is True
    assert result.cache_written is False
    assert "temporarily unavailable" in result.brief_text.lower()
    # Groq was never asked.
    assert groq.seen_prompt is None


# ---------------------------------------------------------------------------
# Deterministic fallback — never raises
# ---------------------------------------------------------------------------


def test_deterministic_fallback_never_raises_on_full_ctx() -> None:
    ctx = _ctx_fixture()
    out = _deterministic_fallback(
        signal_call=ctx["signal_call"],
        instrument=ctx["instrument"],
        cell=ctx["cell"],
    )
    assert isinstance(out, str)
    assert "INFY" in out
    assert "Pullback" in out


def test_deterministic_fallback_handles_missing_fields() -> None:
    """All keys can be missing — fallback must still return a string."""
    out = _deterministic_fallback(
        signal_call={},
        instrument={},
        cell={},
    )
    assert isinstance(out, str)
    assert "—" in out  # placeholder marker


def test_deterministic_fallback_handles_none_features() -> None:
    sc = _ctx_fixture()["signal_call"]
    sc["stable_features"] = None
    out = _deterministic_fallback(
        signal_call=sc,
        instrument=_ctx_fixture()["instrument"],
        cell=_ctx_fixture()["cell"],
    )
    assert "no stable features recorded" in out


def test_deterministic_fallback_handles_bad_confidence() -> None:
    sc = _ctx_fixture()["signal_call"]
    sc["confidence_unconditional"] = "not-a-number"
    out = _deterministic_fallback(
        signal_call=sc,
        instrument=_ctx_fixture()["instrument"],
        cell=_ctx_fixture()["cell"],
    )
    assert "—" in out  # confidence falls back to placeholder


def test_deterministic_fallback_is_sebi_safe() -> None:
    """Fallback must never include a forbidden phrase by construction."""
    from atlas.agents.v6.sebi_guard import check_brief

    ctx = _ctx_fixture()
    out = _deterministic_fallback(
        signal_call=ctx["signal_call"],
        instrument=ctx["instrument"],
        cell=ctx["cell"],
    )
    check_brief(out)  # must not raise


def test_missing_signal_fallback_is_sebi_safe() -> None:
    from atlas.agents.v6.sebi_guard import check_brief

    out = _missing_signal_fallback(SIGNAL_CALL_ID)
    check_brief(out)
    assert "temporarily unavailable" in out.lower()


# ---------------------------------------------------------------------------
# Timing / result metadata
# ---------------------------------------------------------------------------


def test_generation_ms_is_non_negative() -> None:
    engine = MagicMock()
    with patch.object(bg, "_lookup_cache", return_value="hit"):
        result = generate_brief(SIGNAL_CALL_ID, engine, groq_client=_FakeGroq())
    assert result.generation_ms >= 0


def test_result_carries_signal_call_id_unchanged() -> None:
    engine = MagicMock()
    with patch.object(bg, "_lookup_cache", return_value="hit"):
        result = generate_brief(SIGNAL_CALL_ID, engine, groq_client=_FakeGroq())
    assert result.signal_call_id == SIGNAL_CALL_ID


# ---------------------------------------------------------------------------
# Custom `now` injection
# ---------------------------------------------------------------------------


def test_cache_lookup_receives_now_override() -> None:
    fixed = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    engine = MagicMock()
    with patch.object(bg, "_lookup_cache", return_value="hit") as mock_lookup:
        generate_brief(SIGNAL_CALL_ID, engine, groq_client=_FakeGroq(), now=fixed)
    args, _kwargs = mock_lookup.call_args
    # Positional: (engine, signal_call_id, now)
    assert args[2] == fixed

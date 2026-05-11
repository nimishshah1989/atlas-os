"""Unit tests for the intent classifier in handlers/router.py.

Pure unit tests — no DB, no HTTP, no async. ``classify_intent()`` is a plain
function so these run in < 1ms each.
"""

from __future__ import annotations

from atlas.api.openbb.handlers.router import classify_intent


class TestClassifyIntent:
    # --- regime ---
    def test_regime_keyword(self) -> None:
        assert classify_intent("show me current regime") == "regime"

    def test_market_state_phrase(self) -> None:
        assert classify_intent("What is the market state right now?") == "regime"

    def test_risk_on_phrase(self) -> None:
        assert classify_intent("Is the market risk-on?") == "regime"

    def test_deployment_keyword(self) -> None:
        assert classify_intent("show deployment multiplier") == "regime"

    # --- leaders ---
    def test_top_stocks_phrase(self) -> None:
        assert classify_intent("show me top stocks") == "leaders"

    def test_rs_leaders_phrase(self) -> None:
        assert classify_intent("List RS leaders") == "leaders"

    def test_strongest_stocks_phrase(self) -> None:
        assert classify_intent("which are the strongest stocks today") == "leaders"

    def test_leaders_with_sector(self) -> None:
        assert classify_intent("top rs stocks in IT") == "leaders"

    # --- rotation ---
    def test_rotation_keyword(self) -> None:
        assert classify_intent("sector rotation") == "rotation"

    def test_rrg_keyword(self) -> None:
        assert classify_intent("show me the RRG") == "rotation"

    def test_leading_sectors_phrase(self) -> None:
        assert classify_intent("which sectors are leading?") == "rotation"

    def test_lagging_sectors_phrase(self) -> None:
        assert classify_intent("show lagging sectors") == "rotation"

    # --- breakouts ---
    def test_breakout_keyword(self) -> None:
        assert classify_intent("breakout candidates today") == "breakouts"

    def test_breaking_out_phrase(self) -> None:
        assert classify_intent("which stocks are breaking out?") == "breakouts"

    def test_new_leaders_phrase(self) -> None:
        assert classify_intent("show new leaders") == "breakouts"

    # --- unknown ---
    def test_unknown_returns_unknown(self) -> None:
        assert classify_intent("what is the GDP of India?") == "unknown"

    def test_empty_string_returns_unknown(self) -> None:
        assert classify_intent("") == "unknown"

    def test_case_insensitive(self) -> None:
        assert classify_intent("SHOW ME THE REGIME") == "regime"
        assert classify_intent("TOP STOCKS") == "leaders"

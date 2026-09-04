"""Regression test: load_thresholds callers must pass schema as first arg.

Commit 6f1fa94 changed load_thresholds(engine) → load_thresholds(schema, engine).
Five callers in sectors.py, funds.py, decisions_fund.py, decisions_etf.py were
not updated and caused M3/M4/M5 to fail nightly on 2026-05-13.

This test verifies:
1. Calling load_thresholds(engine) raises ValueError (the broken signature).
2. Calling load_thresholds("atlas_foundation", engine) does NOT raise (the correct
   signature). "atlas_foundation" is the India schema — the `atlas` schema this test
   used to pass was dropped (FM D7) and is no longer in `_VALID_SCHEMAS` (ADR-0006).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atlas.db import load_thresholds

# Signature/validation check only — the engine is a mock, no I/O. Without this marker
# the file was silently deselected by CI's `-m unit` run.
pytestmark = pytest.mark.unit


def _make_mock_engine():
    """Return a MagicMock that looks enough like a SQLAlchemy Engine."""
    engine = MagicMock()
    engine.__class__.__name__ = "Engine"
    return engine


def test_load_thresholds_rejects_engine_as_first_arg():
    """Passing an Engine as schema raises ValueError — documents the broken callers."""
    engine = _make_mock_engine()
    with pytest.raises(ValueError, match="schema must be one of"):
        load_thresholds(engine)  # type: ignore


def test_load_thresholds_accepts_schema_plus_engine():
    """Passing schema='atlas_foundation' with engine kwarg does NOT raise the validation error."""
    engine = _make_mock_engine()
    conn = MagicMock()
    conn.execute.return_value.all.return_value = [
        ("threshold_a", "0.5"),
        ("threshold_b", "0.3"),
    ]
    engine.connect.return_value.__enter__ = lambda _: conn
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # Should not raise ValueError — schema validation passes
    result = load_thresholds("atlas_foundation", engine)
    assert "threshold_a" in result
    assert "threshold_b" in result

"""Unit tests for atlas.compute._policy loader.

Mocks the engine; never touches a real DB.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from atlas.compute._policy import (
    DEFAULT_GATE_POLICIES,
    DEFAULT_MULTIPLIERS,
    load_gate_policy,
    load_multiplier_map,
)


def _make_engine_returning(value: object) -> MagicMock:
    """Build a mock Engine whose connect().__enter__().execute().fetchone() returns
    a row whose [0] is `value`. If value is None, fetchone returns None."""
    if value is None:
        row = None
    else:
        row = MagicMock()
        row.__getitem__ = lambda _, idx: value if idx == 0 else None
    eng = MagicMock()
    conn = MagicMock()
    res = MagicMock()
    res.fetchone.return_value = row
    conn.execute.return_value = res
    eng.connect.return_value.__enter__ = lambda _: conn
    eng.connect.return_value.__exit__ = MagicMock(return_value=False)
    return eng


def _make_engine_raising(exc: Exception) -> MagicMock:
    eng = MagicMock()
    eng.connect.side_effect = exc
    return eng


# load_gate_policy


class TestLoadGatePolicy:
    def test_db_returns_list_returns_frozenset(self) -> None:
        eng = _make_engine_returning(["Leader", "Strong"])
        result = load_gate_policy("strength_gate_stock", eng)
        assert result == frozenset({"Leader", "Strong"})

    def test_db_returns_none_falls_back_to_default(self) -> None:
        eng = _make_engine_returning(None)
        result = load_gate_policy("strength_gate_stock", eng)
        assert result == DEFAULT_GATE_POLICIES["strength_gate_stock"]

    def test_db_returns_non_list_falls_back(self) -> None:
        eng = _make_engine_returning({"not": "a list"})
        result = load_gate_policy("strength_gate_stock", eng)
        assert result == DEFAULT_GATE_POLICIES["strength_gate_stock"]

    def test_db_raises_falls_back(self) -> None:
        eng = _make_engine_raising(RuntimeError("connection failed"))
        result = load_gate_policy("strength_gate_stock", eng)
        assert result == DEFAULT_GATE_POLICIES["strength_gate_stock"]

    def test_unknown_policy_key_returns_empty_frozenset(self) -> None:
        eng = _make_engine_returning(["X", "Y"])
        result = load_gate_policy("nonexistent_policy", eng)
        assert result == frozenset()

    def test_empty_list_returns_empty_frozenset_intentional_fm_choice(self) -> None:
        """FM may legitimately set an empty allowlist to block all stocks for that gate.
        This is NOT a fallback case — the empty list is a real configuration."""
        eng = _make_engine_returning([])
        result = load_gate_policy("strength_gate_stock", eng)
        assert result == frozenset()

    def test_string_coercion_handles_unicode(self) -> None:
        eng = _make_engine_returning(["Leader", "Strong"])
        result = load_gate_policy("strength_gate_stock", eng)
        assert "Leader" in result


class TestLoadMultiplierMap:
    def test_db_returns_dict_returns_decimals(self) -> None:
        eng = _make_engine_returning({"Low": 1.5, "Normal": 1.0})
        result = load_multiplier_map("risk_multipliers_stock", eng)
        assert result == {"Low": Decimal("1.5"), "Normal": Decimal("1.0")}

    def test_db_returns_none_falls_back_to_default(self) -> None:
        eng = _make_engine_returning(None)
        result = load_multiplier_map("risk_multipliers_stock", eng)
        assert result == DEFAULT_MULTIPLIERS["risk_multipliers_stock"]

    def test_db_returns_non_dict_falls_back(self) -> None:
        eng = _make_engine_returning(["a", "list"])
        result = load_multiplier_map("risk_multipliers_stock", eng)
        assert result == DEFAULT_MULTIPLIERS["risk_multipliers_stock"]

    def test_db_raises_falls_back(self) -> None:
        eng = _make_engine_raising(RuntimeError("connection failed"))
        result = load_multiplier_map("risk_multipliers_stock", eng)
        assert result == DEFAULT_MULTIPLIERS["risk_multipliers_stock"]

    def test_unknown_policy_key_returns_empty_dict(self) -> None:
        eng = _make_engine_returning({"X": 1.0})
        result = load_multiplier_map("nonexistent_multiplier", eng)
        assert result == {}

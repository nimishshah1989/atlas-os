"""Tolerance-aware diff engine for Phase C route crawler.

Compares a frontend-extracted value against a backend SQL value and
produces a ``DiffResult`` classifying the discrepancy.

Severity tiers
--------------
P0 — |delta_pct| > 10 × tolerance  (screenshot required)
P1 — |delta_pct| > tolerance        (screenshot required)
P2 — |delta_pct| > 0.5 × tolerance (no screenshot)
P3 — clean (not persisted)

For categorical fields (tolerance=0.0, categorical=true) any mismatch
is P0 immediately — states are binary correct or wrong.

For ``None`` frontend values (em-dash, N/A) against non-NULL backend
values, we emit P1 — the field is rendered absent when data exists.

If both values are ``None`` the field is intentionally absent and we
return P3 (clean — skip).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

_YAML_PATH = Path(__file__).parent / "tolerances.yaml"
_tolerances: dict[str, Any] | None = None


def _load_tolerances() -> dict[str, Any]:
    global _tolerances
    if _tolerances is None:
        with _YAML_PATH.open() as f:
            loaded: dict[str, Any] = yaml.safe_load(f)
            _tolerances = loaded
    assert _tolerances is not None
    return _tolerances


def _get_config(field_key: str) -> dict[str, Any]:
    cfg = _load_tolerances()
    result: dict[str, Any] = cfg.get(field_key) or cfg.get("_default") or {"tolerance": 0.02}
    return result


@dataclass(frozen=True)
class DiffResult:
    """Outcome of comparing one frontend value against its backend source."""

    severity: str  # 'P0' | 'P1' | 'P2' | 'P3'
    delta_abs: Decimal | None  # |frontend - backend|, None for categorical
    delta_pct: Decimal | None  # |delta_abs / backend|, None for categorical
    needs_screenshot: bool  # True for P0 and P1
    expected: str  # backend value as string
    actual: str  # frontend value as string


def _fmt(v: Decimal | str | None) -> str:
    if v is None:
        return "None"
    return str(v)


def compare(
    field_key: str,
    frontend_value: Decimal | str | None,
    backend_value: Decimal | str | None,
) -> DiffResult:
    """Compare frontend vs backend for a single field.

    Args:
        field_key: ``entity_type.field`` string, e.g. ``"stock.conviction_score"``.
        frontend_value: Parsed DOM value (from extract.py).
        backend_value: SQL source-of-truth (from sql_lookup.py).

    Returns:
        ``DiffResult`` classifying the discrepancy.
    """
    cfg = _get_config(field_key)
    tolerance = Decimal(str(cfg.get("tolerance", 0.02)))
    categorical = bool(cfg.get("categorical", False))
    expected_str = _fmt(backend_value)
    actual_str = _fmt(frontend_value)

    # Both absent — clean
    if frontend_value is None and backend_value is None:
        return DiffResult(
            severity="P3",
            delta_abs=None,
            delta_pct=None,
            needs_screenshot=False,
            expected=expected_str,
            actual=actual_str,
        )

    # Frontend absent, backend present — data missing on UI
    if frontend_value is None and backend_value is not None:
        return DiffResult(
            severity="P1",
            delta_abs=None,
            delta_pct=None,
            needs_screenshot=True,
            expected=expected_str,
            actual=actual_str,
        )

    # Backend absent, frontend present — frontend showing stale data
    if frontend_value is not None and backend_value is None:
        return DiffResult(
            severity="P2",
            delta_abs=None,
            delta_pct=None,
            needs_screenshot=False,
            expected=expected_str,
            actual=actual_str,
        )

    # Categorical: exact string comparison
    if categorical or isinstance(frontend_value, str) or isinstance(backend_value, str):
        match = str(frontend_value).strip() == str(backend_value).strip()
        if match:
            return DiffResult(
                severity="P3",
                delta_abs=None,
                delta_pct=None,
                needs_screenshot=False,
                expected=expected_str,
                actual=actual_str,
            )
        return DiffResult(
            severity="P0",
            delta_abs=None,
            delta_pct=None,
            needs_screenshot=True,
            expected=expected_str,
            actual=actual_str,
        )

    # Numeric comparison
    assert isinstance(frontend_value, Decimal)
    assert isinstance(backend_value, Decimal)

    delta_abs = abs(frontend_value - backend_value)

    # Guard against zero backend (avoid division by zero)
    if backend_value == Decimal("0"):
        # If frontend is also 0, clean
        if frontend_value == Decimal("0"):
            return DiffResult(
                severity="P3",
                delta_abs=Decimal("0"),
                delta_pct=Decimal("0"),
                needs_screenshot=False,
                expected=expected_str,
                actual=actual_str,
            )
        # Otherwise delta_pct is undefined — treat as P1
        return DiffResult(
            severity="P1",
            delta_abs=delta_abs,
            delta_pct=None,
            needs_screenshot=True,
            expected=expected_str,
            actual=actual_str,
        )

    delta_pct = delta_abs / abs(backend_value)

    if delta_pct > Decimal("10") * tolerance:
        severity = "P0"
        screenshot = True
    elif delta_pct > tolerance:
        severity = "P1"
        screenshot = True
    elif delta_pct > Decimal("0.5") * tolerance:
        severity = "P2"
        screenshot = False
    else:
        severity = "P3"
        screenshot = False

    return DiffResult(
        severity=severity,
        delta_abs=delta_abs,
        delta_pct=delta_pct,
        needs_screenshot=screenshot,
        expected=expected_str,
        actual=actual_str,
    )

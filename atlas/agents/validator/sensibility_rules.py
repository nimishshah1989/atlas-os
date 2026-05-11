"""Sensibility rules: per-column domain-constraint checks.

Each rule encodes a physical or business-domain constraint for a column-name
pattern. Rules are conservative — only flag what we can confidently call wrong.
False-negative is safer than false-positive for an alerting system.

Design (§7.3 of the validator design doc):
- Match columns by suffix (``column_name.endswith(suffix)``).
- Return ``RuleViolation`` if the value breaks a constraint.
- Return ``None`` for NULL values (DB NOT NULL is enforced at the DB layer).
- Return ``None`` for unknown column patterns (no false positives).
- Decimal-aware: detect ``Decimal('Infinity')`` and ``Decimal('NaN')``.

Severity map (for consumers):
- P0: inf, NaN, future date  (always wrong, user-visible corruption)
- P1: percentile out of range, negative volume, negative AUM  (domain violation)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class RuleViolation:
    """A single constraint violation for one (column, value) pair."""

    column: str
    value: object
    rule: str
    message: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_numeric(v: object) -> bool:
    return isinstance(v, int | float | Decimal)


def _is_inf(v: object) -> bool:
    """True for float ±inf or Decimal Infinity."""
    if isinstance(v, float):
        return math.isinf(v)
    if isinstance(v, Decimal):
        try:
            return v.is_infinite()
        except InvalidOperation:
            return False
    return False


def _is_nan(v: object) -> bool:
    """True for float NaN or Decimal NaN / sNaN."""
    if isinstance(v, float):
        return math.isnan(v)
    if isinstance(v, Decimal):
        try:
            return v.is_nan() or v.is_snan()
        except InvalidOperation:
            return False
    return False


def _numeric_val(v: object) -> float | None:
    """Return a float for comparison, or None if not representable."""
    if isinstance(v, float):
        return v
    if isinstance(v, int):
        return float(v)
    if isinstance(v, Decimal):
        try:
            return float(v)
        except (OverflowError, InvalidOperation):
            return None
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_value(
    column_name: str,
    value: object,
    table_name: str = "",  # reserved for future per-table overrides; unused in Phase A
) -> RuleViolation | None:
    """Check one column value against domain constraints.

    Args:
        column_name: The column name as it appears in the database.
        value: The value to check. May be any Python type.
        table_name: The source table (reserved for future per-table overrides).

    Returns:
        ``RuleViolation`` if the value violates a constraint, else ``None``.
        Always returns ``None`` for ``None`` values (NULL is a DB-layer concern).
    """
    if value is None:
        return None

    # ------------------------------------------------------------------ #
    # Rule 1: any numeric must be finite (no inf, no NaN)                 #
    # Severity: P0 — these are always user-visible corruption              #
    # ------------------------------------------------------------------ #
    if _is_numeric(value):
        if _is_inf(value):
            return RuleViolation(
                column=column_name,
                value=value,
                rule="any_numeric: finite",
                message=f"Column '{column_name}' contains inf; "
                "caused by zero-division or overflow in compute pipeline.",
            )
        if _is_nan(value):
            return RuleViolation(
                column=column_name,
                value=value,
                rule="any_numeric: not_nan",
                message=f"Column '{column_name}' contains NaN; "
                "indicates missing input or failed computation.",
            )

    # ------------------------------------------------------------------ #
    # Rule 2: date columns must be ≤ today                                #
    # Severity: P0 — future dates are impossible in historical data        #
    # ------------------------------------------------------------------ #
    if column_name == "date" or column_name.endswith("_date"):
        if isinstance(value, date):
            if value > date.today():
                return RuleViolation(
                    column=column_name,
                    value=value,
                    rule="date: <= today",
                    message=f"Column '{column_name}' has future date {value}; "
                    f"today is {date.today()}. "
                    "Likely an ETL clock-skew or bad source data.",
                )

    # ------------------------------------------------------------------ #
    # Rule 3: *_percentile columns must be in [0, 1]                      #
    # Severity: P1                                                         #
    # ------------------------------------------------------------------ #
    if column_name.endswith("_percentile"):
        n = _numeric_val(value)
        if n is not None and not (_is_inf(value) or _is_nan(value)):
            if n < 0.0 or n > 1.0:
                return RuleViolation(
                    column=column_name,
                    value=value,
                    rule="*_percentile: [0, 1]",
                    message=f"Column '{column_name}' = {value} is outside [0, 1]. "
                    "Percentile rank must be a probability.",
                )

    # ------------------------------------------------------------------ #
    # Rule 4: volume columns must be in [0, 1e12)                         #
    # Severity: P1 for negative; note: inf already caught above            #
    # ------------------------------------------------------------------ #
    if column_name == "volume" or column_name.endswith("_volume"):
        n = _numeric_val(value)
        if n is not None and not (_is_inf(value) or _is_nan(value)):
            if n < 0:
                return RuleViolation(
                    column=column_name,
                    value=value,
                    rule="volume: [0, 1e12)",
                    message=f"Column '{column_name}' = {value} is negative. "
                    "Volume cannot be negative.",
                )
            if n >= 1e12:
                return RuleViolation(
                    column=column_name,
                    value=value,
                    rule="volume: [0, 1e12)",
                    message=f"Column '{column_name}' = {value} exceeds 1 trillion. "
                    "Likely a data corruption or unit error.",
                )

    # ------------------------------------------------------------------ #
    # Rule 5: aum_* columns must be ≥ 0                                   #
    # Severity: P1                                                         #
    # ------------------------------------------------------------------ #
    if column_name.startswith("aum_"):
        n = _numeric_val(value)
        if n is not None and not (_is_inf(value) or _is_nan(value)):
            if n < 0:
                return RuleViolation(
                    column=column_name,
                    value=value,
                    rule="aum_*: >= 0",
                    message=f"Column '{column_name}' = {value} is negative. "
                    "AUM cannot be negative.",
                )

    return None

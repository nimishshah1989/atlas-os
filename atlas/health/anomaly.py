"""Anomaly detection — DoD pct change + 14-day rolling z-score.

Pure functions. No DB calls, no IO. Unit-tested in
tests/unit/test_anomaly.py.

For numeric metrics:
  pct_change_dod = (today - prior_day) / abs(prior_day)
  z_score        = (today - rolling_avg) / rolling_std

  Severity ladder (whichever fires first wins):
    critical : |z_score| > 4.0   OR  |pct_change_dod| > 0.50
    warn     : |z_score| > 2.5   OR  |pct_change_dod| > 0.20
    info     : |z_score| > 1.5   OR  |pct_change_dod| > 0.10
    None     : within bounds

For categorical metrics: any change vs prior_day flags the row.
Severity is set by the metric definition — domain context decides
whether a state flip is critical, warn, or info.

NULL handling:
  - prior_day NULL    → no DoD comparison, only z_score
  - rolling_std == 0  → z_score undefined; pct_change still applies
  - all None today    → metric simply not recorded
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

# Numeric thresholds — paired (z_threshold, pct_change_threshold).
SEVERITY_RULES: tuple[tuple[str, float, float], ...] = (
    ("critical", 4.0, 0.50),
    ("warn", 2.5, 0.20),
    ("info", 1.5, 0.10),
)


@dataclass(frozen=True)
class AnomalyResult:
    pct_change_dod: float | None
    z_score: float | None
    is_anomaly: bool
    severity: str | None
    notes: str | None


def _safe_pct_change(today: float, prior: float | None) -> float | None:
    if prior is None:
        return None
    if math.isclose(prior, 0.0, abs_tol=1e-12):
        # Avoid div-by-zero. If today is also ~0, no change. Otherwise undefined.
        if math.isclose(today, 0.0, abs_tol=1e-12):
            return 0.0
        return None
    return (today - prior) / abs(prior)


def _safe_zscore(
    today: float,
    rolling_avg: float | None,
    rolling_std: float | None,
) -> float | None:
    if rolling_avg is None or rolling_std is None:
        return None
    if math.isclose(rolling_std, 0.0, abs_tol=1e-12):
        return None
    return (today - rolling_avg) / rolling_std


def _classify_numeric(pct: float | None, z: float | None) -> tuple[bool, str | None]:
    """Return (is_anomaly, severity)."""
    abs_pct = abs(pct) if pct is not None else None
    abs_z = abs(z) if z is not None else None

    for severity, z_thr, pct_thr in SEVERITY_RULES:
        if (abs_z is not None and abs_z > z_thr) or (abs_pct is not None and abs_pct > pct_thr):
            return True, severity
    return False, None


def evaluate_numeric(
    today: float | None,
    prior_day: float | None,
    history_14d: Sequence[float] | None,
) -> AnomalyResult:
    """Numeric anomaly evaluation."""
    if today is None:
        return AnomalyResult(None, None, False, None, "metric not produced today")

    pct = _safe_pct_change(today, prior_day)

    avg: float | None = None
    std: float | None = None
    if history_14d:
        n = len(history_14d)
        avg = sum(history_14d) / n
        if n >= 2:
            var = sum((x - avg) ** 2 for x in history_14d) / (n - 1)
            std = math.sqrt(var)

    z = _safe_zscore(today, avg, std)
    is_anomaly, severity = _classify_numeric(pct, z)
    return AnomalyResult(pct, z, is_anomaly, severity, None)


def evaluate_categorical(
    today: object | None,
    prior_day: object | None,
    severity_on_change: str = "warn",
    severity_critical: bool = False,
) -> AnomalyResult:
    """Categorical anomaly: flagged when value differs from prior day.

    First observation (prior None) is NOT an anomaly.
    """
    if today is None:
        return AnomalyResult(None, None, False, None, "metric not produced today")
    if prior_day is None:
        return AnomalyResult(None, None, False, None, "first observation")
    if today == prior_day:
        return AnomalyResult(None, None, False, None, None)

    severity = "critical" if severity_critical else severity_on_change
    notes = f"value changed from {prior_day!r} to {today!r}"
    return AnomalyResult(None, None, True, severity, notes)


__all__ = [
    "AnomalyResult",
    "SEVERITY_RULES",
    "evaluate_numeric",
    "evaluate_categorical",
]

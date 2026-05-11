"""SP07: orchestrator — keyword-routed dispatch to the right specialist.

V1 strategy: case-insensitive substring matching, first-match wins. Mirror
of the SP03 OpenBB handler router. V2 (deferred) adds a Groq classification
fallback when no keyword matches and the question is ambiguous.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from atlas.agents.specialists.base import AgentResult, SpecialistAgent
from atlas.agents.specialists.drift_detector import DriftDetector
from atlas.agents.specialists.regime_watcher import RegimeWatcher
from atlas.agents.specialists.sector_rotation import SectorRotationAnalyst
from atlas.agents.specialists.stock_screener import StockScreener

# Registry of all v1 specialists. Order does not matter — keyed by name.
SPECIALISTS: dict[str, SpecialistAgent] = {
    "sector_rotation": SectorRotationAnalyst(),
    "stock_screener": StockScreener(),
    "regime_watcher": RegimeWatcher(),
    "drift_detector": DriftDetector(),
}

# Intent table: ordered list of (specialist_name, trigger_phrases).
# Order matters — more-specific specialists appear first so a "regime
# rotation" query routes to sector_rotation, not regime_watcher.
_INTENT_TABLE: list[tuple[str, tuple[str, ...]]] = [
    (
        "drift_detector",
        (
            "drift",
            "anomaly",
            "anomalies",
            "finding",
            "findings",
            "distribution",
            "outlier",
            "outliers",
            "sensibility",
            "violation",
            "violations",
            "data quality",
            "data integrity",
            "data drift",
        ),
    ),
    (
        "sector_rotation",
        (
            "rotation",
            "rotating",
            "quadrant",
            "rrg",
            "leading sectors",
            "lagging sectors",
            "weakening sectors",
            "improving sectors",
            "sector ",
            "sectors ",
        ),
    ),
    (
        "regime_watcher",
        (
            "regime",
            "risk-on",
            "risk on",
            "risk-off",
            "risk off",
            "deployment",
            "market state",
            "dislocation",
        ),
    ),
    # stock_screener: default fall-through; no triggers needed.
]


def classify_specialist(question: str) -> str:
    """Return the specialist name for ``question``.

    Args:
        question: Raw user query. Case-insensitive substring matching.

    Returns:
        One of: ``"sector_rotation"``, ``"stock_screener"``,
        ``"regime_watcher"``, ``"drift_detector"``. Defaults to
        ``"stock_screener"`` when no trigger matches.
    """
    lower = question.lower()
    for name, triggers in _INTENT_TABLE:
        if any(t in lower for t in triggers):
            return name
    return "stock_screener"


def get_specialist(name: str) -> SpecialistAgent:
    """Return the instantiated specialist by name.

    Raises:
        KeyError: if ``name`` is not a known specialist.
    """
    if name not in SPECIALISTS:
        raise KeyError(f"unknown specialist: {name!r}. Valid: {sorted(SPECIALISTS.keys())}")
    return SPECIALISTS[name]


def list_specialists() -> list[dict[str, str]]:
    """Return a list of ``{name, description}`` dicts for every specialist."""
    return [{"name": s.name, "description": s.description} for s in SPECIALISTS.values()]


def invoke_routed(
    question: str,
    *,
    engine: Engine,
    client: Any | None = None,
) -> tuple[str, AgentResult]:
    """Route ``question`` to a specialist and invoke it.

    Returns:
        Tuple of (specialist_name, AgentResult).
    """
    name = classify_specialist(question)
    agent = get_specialist(name)
    result = agent.invoke(question, engine=engine, client=client)
    return name, result

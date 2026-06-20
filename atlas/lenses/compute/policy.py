"""Policy lens scorer — government / regulatory tailwind signal.

Pure function, no I/O.  Consumes company sector/industry strings and a list of
policy dicts from the policy registry; emits a PolicyResult with a tailwind
subcomponent and a composite 0-100 score.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PolicyResult:
    tailwind: Decimal | None
    score: Decimal | None
    matching_policies: list[dict[str, Any]]
    evidence: dict[str, Any]


# ---------------------------------------------------------------------------
# Priority weights
# ---------------------------------------------------------------------------

_PRIORITY_SCORES: dict[str, int] = {
    "HIGH": 15,
    "MEDIUM": 10,
    "LOW": 5,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _normalise(s: str | None) -> str:
    return (s or "").strip().lower()


def _policy_matches(
    policy: dict[str, Any],
    sector_lower: str,
    industry_lower: str,
    combined_lower: str,
) -> bool:
    """Return True if a policy is relevant to the company's sector/industry.

    Match if:
      - Any beneficiary_sector contains or is contained in the company sector
        (bidirectional substring match, case-insensitive).
      - Any beneficiary_keyword appears in the "sector industry" string.
    """
    # Sector match
    ben_sectors: list[str] = policy.get("beneficiary_sectors") or []
    for bs in ben_sectors:
        bs_lower = bs.strip().lower()
        if not bs_lower:
            continue
        if bs_lower in sector_lower or sector_lower in bs_lower:
            return True

    # Keyword match
    ben_keywords: list[str] = policy.get("beneficiary_keywords") or []
    for kw in ben_keywords:
        kw_lower = kw.strip().lower()
        if not kw_lower:
            continue
        if kw_lower in combined_lower:
            return True

    return False


# ---------------------------------------------------------------------------
# Public scorer
# ---------------------------------------------------------------------------


def score_policy(
    sector: str | None,
    industry: str | None,
    policies: list[dict[str, Any]],
    thresholds: dict[str, Any],
) -> PolicyResult:
    """Score policy tailwinds into a 0-100 composite."""
    sector_n = _normalise(sector)
    industry_n = _normalise(industry)

    if not sector_n and not industry_n:
        return PolicyResult(
            tailwind=None,
            score=None,
            matching_policies=[],
            evidence={"reason": "no sector/industry provided"},
        )

    if not policies:
        return PolicyResult(
            tailwind=Decimal("0"),
            score=Decimal("0"),
            matching_policies=[],
            evidence={"reason": "no policies in registry"},
        )

    combined = f"{sector_n} {industry_n}"
    matched: list[dict[str, Any]] = []
    raw_total = 0.0

    for pol in policies:
        if not _policy_matches(pol, sector_n, industry_n, combined):
            continue

        priority = (pol.get("impact") or pol.get("priority") or "LOW").upper()
        pts = _PRIORITY_SCORES.get(
            priority,
            int(thresholds.get("policy_default_pts", 5)),
        )
        raw_total += pts
        matched.append({
            "policy_id": pol.get("id") or pol.get("policy_id"),
            "name": pol.get("name") or pol.get("title", ""),
            "priority": priority,
            "points": pts,
        })

    tailwind = _clamp(raw_total, 0, 100)
    score = tailwind  # single-component lens; score = tailwind

    return PolicyResult(
        tailwind=Decimal(str(round(tailwind, 2))),
        score=Decimal(str(round(score, 2))),
        matching_policies=matched,
        evidence={
            "policies_checked": len(policies),
            "policies_matched": len(matched),
            "raw_total": round(raw_total, 2),
        },
    )

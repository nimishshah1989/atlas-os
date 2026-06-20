"""Catalyst lens scorer — corporate filings / announcements signal.

Pure function, no I/O.  Consumes filing dicts from foundation_staging.lens_filings
and a thresholds dict; emits a CatalystResult with bucket subcomponents and a
composite 0-100 score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

@dataclass(frozen=True, slots=True)
class CatalystResult:
    earnings_strategy: Decimal | None
    capital_action: Decimal | None
    governance: Decimal | None
    score: Decimal | None
    evidence: dict[str, Any]


_TIER_A: dict[str, list[tuple[list[str], int]]] = {
    "credit_rating": [
        (["upgrade"], 15),
        (["reaffirm"], 5),
        (["downgrade"], -10),
        (["watch"], -5),
    ],
    "dividend": [
        (["special", "interim"], 10),
        (["final"], 5),
    ],
    "management_cessation": [
        (["cfo", "ceo", "md", "managing director"], -8),
        (["exec", "director"], -4),
    ],
    "management_appointment": [
        (["cfo", "ceo", "md", "managing director"], 5),
        (["kmp"], 3),
    ],
    "auditor_change": [
        (["mid-term", "casual"], -12),
        (["rotation"], -2),
    ],
    "acquisition": [
        (["strategic", "100%", "majority"], 12),
        (["subsidiary", "jv", "joint venture"], 8),
        (["stake"], 8),
    ],
    "press_release": [
        (["order win", "order received"], 10),
        (["partnership", "mou"], 8),
        (["expansion", "capacity"], 8),
        (["innovation", "patent"], 6),
        (["litigation"], -3),
        (["adverse"], -5),
    ],
    "buyback": [
        ([], 10),  # any buyback filing
    ],
    "bonus_split": [
        (["bonus"], 5),
        (["split"], 3),
    ],
    "esop": [
        ([], 2),
    ],
}

# Fallback for auditor_change when no specific keyword matches
_AUDITOR_FALLBACK_SCORE = -5

# Category -> bucket mapping
_BUCKET_MAP: dict[str, str] = {
    "credit_rating": "earnings_strategy",
    "dividend": "capital_action",
    "management_cessation": "governance",
    "management_appointment": "governance",
    "auditor_change": "governance",
    "acquisition": "capital_action",
    "press_release": "earnings_strategy",
    "buyback": "capital_action",
    "bonus_split": "capital_action",
    "esop": "governance",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _recency_multiplier(filing_date: date, as_of: date, thresholds: dict[str, Any]) -> float:
    days = (as_of - filing_date).days
    t1 = thresholds.get("catalyst_recency_t1", 90)
    t2 = thresholds.get("catalyst_recency_t2", 180)
    t3 = thresholds.get("catalyst_recency_t3", 365)
    if days <= t1:
        return 1.0
    if days <= t2:
        return 0.8
    if days <= t3:
        return 0.5
    return 0.3


def _match_keywords(text: str, keywords: list[str]) -> bool:
    """Return True if ANY keyword appears in text (case-insensitive)."""
    if not keywords:
        return True  # empty keyword list = unconditional match
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def _score_filing(category: str, subject: str) -> int:
    """Return raw Tier-A score for a filing based on category + subject."""
    rules = _TIER_A.get(category)
    if rules is None:
        return 0
    for keywords, pts in rules:
        if _match_keywords(subject, keywords):
            return pts
    # Auditor change fallback
    if category == "auditor_change":
        return _AUDITOR_FALLBACK_SCORE
    return 0


def _infer_category(bucket: str, subject: str) -> str:
    """Infer a Tier-A category from the bucket + subject text."""
    lower = subject.lower()
    if bucket == "earnings":
        if any(k in lower for k in ("credit", "rating")):
            return "credit_rating"
        return "press_release"
    if bucket == "capital":
        for cat in ("dividend", "acquisition", "buyback", "bonus_split"):
            if cat.replace("_", " ") in lower or cat.replace("_", "") in lower:
                return cat
        if "bonus" in lower:
            return "bonus_split"
        if "split" in lower:
            return "bonus_split"
        return "acquisition"
    if bucket == "governance":
        if any(k in lower for k in ("cessation", "resign", "termination")):
            return "management_cessation"
        if any(k in lower for k in ("appoint", "designat")):
            return "management_appointment"
        if "auditor" in lower:
            return "auditor_change"
        if "esop" in lower:
            return "esop"
        return "management_appointment"
    return "press_release"


# ---------------------------------------------------------------------------
# Public scorer
# ---------------------------------------------------------------------------


def score_catalyst(
    filings: list[dict[str, Any]],
    as_of_date: date,
    thresholds: dict[str, Any],
) -> CatalystResult:
    """Score corporate filings into a 0-100 catalyst composite."""
    if not filings:
        return CatalystResult(
            earnings_strategy=None,
            capital_action=None,
            governance=None,
            score=None,
            evidence={"reason": "no filings"},
        )

    bucket_totals: dict[str, float] = {
        "earnings_strategy": 0.0,
        "capital_action": 0.0,
        "governance": 0.0,
    }
    filing_details: list[dict[str, Any]] = []

    for f in filings:
        filing_date = f.get("filing_date")
        if filing_date is None:
            continue
        if isinstance(filing_date, str):
            filing_date = date.fromisoformat(filing_date)

        bucket_raw = (f.get("category_bucket") or "").lower()
        subject = f.get("subject_text") or ""

        category = _infer_category(bucket_raw, subject)
        raw = _score_filing(category, subject)
        if raw == 0:
            continue

        recency = _recency_multiplier(filing_date, as_of_date, thresholds)
        weighted = raw * recency

        bucket_key = _BUCKET_MAP.get(category, "earnings_strategy")
        bucket_totals[bucket_key] += weighted

        filing_details.append({
            "category": category,
            "subject": subject[:80],
            "raw": raw,
            "recency": recency,
            "weighted": round(weighted, 2),
            "bucket": bucket_key,
        })

    # Clamp each bucket 0-100
    es = Decimal(str(round(_clamp(bucket_totals["earnings_strategy"], 0, 100), 2)))
    ca = Decimal(str(round(_clamp(bucket_totals["capital_action"], 0, 100), 2)))
    gov = Decimal(str(round(_clamp(bucket_totals["governance"], 0, 100), 2)))

    w_es = Decimal(str(thresholds.get("catalyst_w_earnings", "0.55")))
    w_ca = Decimal(str(thresholds.get("catalyst_w_capital", "0.30")))
    w_gov = Decimal(str(thresholds.get("catalyst_w_governance", "0.15")))

    composite = es * w_es + ca * w_ca + gov * w_gov
    composite = Decimal(str(round(float(composite), 2)))

    return CatalystResult(
        earnings_strategy=es,
        capital_action=ca,
        governance=gov,
        score=composite,
        evidence={
            "filing_count": len(filing_details),
            "filings": filing_details,
            "bucket_totals_raw": {
                k: round(v, 2) for k, v in bucket_totals.items()
            },
        },
    )

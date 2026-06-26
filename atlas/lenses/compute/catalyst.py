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
    # Order-book momentum — real NSE "Bagging/Awarding of orders/contracts" filings
    # (the thesis for infra/capital-goods/defence/PSU names: L&T, RVNL, BEL, BHEL,
    # KEC, NCC…). Previously these landed in category='other' → governance LOW (+3
    # noise); now first-class in the high-weight earnings bucket. Subject keywords are
    # ranked: an explicit award/LoA outranks a generic "received an order".
    "order_win": [
        (["awarding", "awarded", "letter of award", "loa", "work order"], 12),
        (["bagging", "bagged", "secures", "secured", "wins order", "won order"], 11),
        (["receiving of order", "order win", "order received", "order book"], 10),
        ([], 8),  # any order/contract win filing routed here
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

# Default score when the category is known but no keyword-rule matches subject
_FALLBACK_SCORES: dict[str, int] = {
    "credit_rating": 5,
    "dividend": 5,
    "management_cessation": -4,
    "management_appointment": 3,
    "auditor_change": _AUDITOR_FALLBACK_SCORE,
    "acquisition": 8,
    "press_release": 3,
    "buyback": 10,
    "bonus_split": 3,
    "esop": 2,
    "order_win": 8,
}

# Map lens_filings.category values → _TIER_A keys (use before _infer_category)
_CATEGORY_MAP: dict[str, str] = {
    "credit rating": "credit_rating",
    "dividend": "dividend",
    "acquisition": "acquisition",
    "amalgamation": "acquisition",
    "merger": "acquisition",
    "takeover": "acquisition",
    "buyback": "buyback",
    "bonus": "bonus_split",
    "split": "bonus_split",
    "cessation": "management_cessation",
    "resignation": "management_cessation",
    "appointment": "management_appointment",
    "change in director": "management_appointment",
    "change in auditor": "auditor_change",
    "auditor": "auditor_change",
    "press release": "press_release",
    "outcome of board": "press_release",
    "financial results": "press_release",
    "investor presentation": "press_release",
    "annual report": "press_release",
    "analyst meet": "press_release",
}

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
    "order_win": "earnings_strategy",  # business momentum → highest-weight bucket
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


def _is_order_win(subject: str) -> bool:
    """True iff the filing is a genuine business order/contract WIN — not a
    regulatory 'order' (SEBI 'Action(s) taken or orders passed', 'orders
    initiated'). The real NSE subjects are 'Bagging/Receiving of orders/contracts'
    and 'Awarding of order(s)/contract(s)'. Require an explicit win verb, or both
    'order' and 'contract' present, while excluding regulatory/legal phrasing."""
    s = subject.lower()
    if any(
        bad in s
        for bad in (
            "orders passed",
            "order passed",
            "orders initiated",
            "action(s) taken",
            "action taken",
            "penalty",
            "adjudicat",
            "show cause",
            "sebi",
            "tribunal",
            "court",
        )
    ):
        return False
    if any(
        win in s
        for win in (
            "bagging",
            "bagged",
            "awarding of order",
            "awarded",
            "letter of award",
            "work order",
            "receiving of order",
            "secures order",
            "secured order",
            "wins order",
            "won order",
            "order win",
            "order received",
            "order book",
        )
    ):
        return True
    # 'order(s)/contract(s)' co-occurrence is the canonical NSE order-win subject
    return "order" in s and "contract" in s


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
        return _FALLBACK_SCORES.get(category, 0)
    for keywords, pts in rules:
        if _match_keywords(subject, keywords):
            return pts
    # Known category but no keyword match — use category-level default
    return _FALLBACK_SCORES.get(category, 0)


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

        # Use the category column directly when it maps to a known Tier-A key;
        # fall back to bucket+subject inference only for unmapped categories.
        raw_cat = (f.get("category") or "").lower().strip()
        subject = f.get("subject_text") or ""
        category = _CATEGORY_MAP.get(raw_cat)
        if category is None:
            if _is_order_win(subject):
                category = "order_win"
            else:
                bucket_raw = (f.get("category_bucket") or "").lower()
                category = _infer_category(bucket_raw, subject)
        raw = _score_filing(category, subject)
        if raw == 0:
            continue

        recency = _recency_multiplier(filing_date, as_of_date, thresholds)
        weighted = raw * recency

        bucket_key = _BUCKET_MAP.get(category, "earnings_strategy")
        bucket_totals[bucket_key] += weighted

        filing_details.append(
            {
                "category": category,
                "subject": subject[:80],
                "raw": raw,
                "recency": recency,
                "weighted": round(weighted, 2),
                "bucket": bucket_key,
            }
        )

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
            "bucket_totals_raw": {k: round(v, 2) for k, v in bucket_totals.items()},
        },
    )

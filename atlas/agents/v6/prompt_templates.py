"""Prompt skeletons for the v6 brief generator.

The brief generator constructs a **constrained JSON skeleton** of facts
drawn from the agent's read-only DB query, then asks the LLM to narrate
ABOUT those facts. The skeleton fixes the numeric values; the LLM cannot
invent alternative numbers. Per CONTEXT.md "LLM factuality guard"
(replacement architecture, item 1).

For issue #47, the skeleton is **loose** — full per-claim factuality
verification ships in issue #29. The loose skeleton is the foundation
that the per-claim checker will read.

The prompt embeds SEBI-compliant tone constraints; the keyword guard in
:mod:`atlas.agents.v6.sebi_guard` is the final layer.
"""

from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# Prompt skeleton template
# ---------------------------------------------------------------------------

BRIEF_PROMPT_TEMPLATE: str = """\
You are a SEBI-registered Research Analyst at Atlas. Generate a brief (2-3
sentences, 40-80 words) explaining WHY the signal call below fired.

HARD CONSTRAINTS (SEBI Research Analyst Regulations — non-negotiable):
1. Use ONLY the data provided in the JSON skeleton below. Do NOT invent
   metrics, names, percentages, prices, or events.
2. Do NOT mention specific price predictions, price targets, or
   directional guarantees.
3. Do NOT use forbidden phrases like "guaranteed return", "risk-free",
   "you should buy", "I recommend", "must buy", "must sell",
   "target price of", "will reach".
4. Use research language: "ranks highly in", "exhibits", "registers",
   "signals strength", "appears in", "shows".
5. Do NOT recommend any ticker other than the one in the skeleton.
6. Tone: factual, calm, methodology-anchored. Past or present tense
   describing observed state, not forecast.

FORMAT:
- 2 to 3 sentences. 40 to 80 words. Plain prose only.
- No markdown headers, bullet lists, or tables.
- Do NOT prefix with "Brief:" or any label — just the prose.

DATA SKELETON:
{skeleton_json}

Generate the brief now.
"""


# ---------------------------------------------------------------------------
# Skeleton construction
# ---------------------------------------------------------------------------

# Whitelisted keys that may appear in the skeleton.  Keeps the LLM context
# predictable + lets the per-claim verifier (issue #29) enumerate every
# numeric field deterministically.
SKELETON_KEYS: frozenset[str] = frozenset(
    {
        "signal_call_id",
        "ticker",
        "company_name",
        "cell_name",
        "action",
        "confidence_unconditional",
        "regime_state",
        "stable_features",
        "recent_corp_actions",
        "predicted_excess",
        "tenure",
        "cap_tier",
    }
)


def build_skeleton(
    *,
    signal_call: dict[str, Any],
    instrument: dict[str, Any],
    cell: dict[str, Any],
    recent_corp_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construct the constrained JSON skeleton for a single brief.

    Loose construction per issue #47 scope; the per-claim factuality
    checker (issue #29) will read the same shape.

    Parameters
    ----------
    signal_call:
        Row from ``atlas_signal_calls`` as a dict (keys per migration 080).
        Required keys: signal_call_id, action, confidence_unconditional,
        regime_state_at_call, stable_features, predicted_excess, tenure,
        cap_tier_at_trigger.
    instrument:
        Dict with at minimum ``symbol`` and ``company_name``.  Sourced
        from the readonly session's de_instruments-equivalent join.
    cell:
        Row from ``atlas_cell_definitions`` with at minimum
        ``rule_type`` (the human-readable rule name) and matching
        cap_tier / action / tenure for cross-check.
    recent_corp_actions:
        Optional list of corp-action dicts from de_corporate_actions
        within the lookback window. May be empty / None.

    Returns
    -------
    dict
        Skeleton ready to embed into :data:`BRIEF_PROMPT_TEMPLATE`.
    """
    cap_tier = signal_call.get("cap_tier_at_trigger") or signal_call.get("cap_tier")
    tenure = signal_call.get("tenure")
    rule_type = cell.get("rule_type") or cell.get("name") or "(unnamed rule)"
    cell_name = f"{cap_tier} {rule_type} @ {tenure}"

    skeleton: dict[str, Any] = {
        "signal_call_id": _stringify(signal_call.get("signal_call_id")),
        "ticker": instrument.get("symbol"),
        "company_name": instrument.get("company_name"),
        "cell_name": cell_name,
        "action": signal_call.get("action"),
        "confidence_unconditional": _coerce_float(signal_call.get("confidence_unconditional")),
        "regime_state": signal_call.get("regime_state_at_call"),
        "stable_features": list(signal_call.get("stable_features") or []),
        "predicted_excess": _coerce_float(signal_call.get("predicted_excess")),
        "tenure": tenure,
        "cap_tier": cap_tier,
        "recent_corp_actions": [_summarize_corp_action(ca) for ca in (recent_corp_actions or [])],
    }
    # Guarantee every key in the dict is in the whitelist — if a future
    # builder edit adds a key, the assertion fails at test time.
    extra = set(skeleton) - SKELETON_KEYS
    if extra:
        raise ValueError(f"skeleton contains non-whitelisted keys: {sorted(extra)}")
    return skeleton


def render_prompt(skeleton: dict[str, Any]) -> str:
    """Render the full prompt by formatting :data:`BRIEF_PROMPT_TEMPLATE`."""
    skeleton_json = json.dumps(skeleton, indent=2, sort_keys=True, default=str)
    return BRIEF_PROMPT_TEMPLATE.format(skeleton_json=skeleton_json)


def _stringify(value: Any) -> str | None:
    """Convert UUIDs / other ID values to a string for JSON safety."""
    if value is None:
        return None
    return str(value)


def _coerce_float(value: Any) -> float | None:
    """Coerce Numeric / Decimal / str values to float for the skeleton.

    Ratios + confidences are display-only here (the canonical Decimal
    stays in atlas_signal_calls). Returns None on missing.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summarize_corp_action(action: dict[str, Any]) -> dict[str, Any]:
    """Trim a corp-action row to the fields safe to surface in a brief.

    Hides internal monitoring / draft-stage fields. Keeps event_type +
    effective_date + a sanitized description if present.
    """
    return {
        "event_type": action.get("event_type"),
        "effective_date": _stringify(action.get("effective_date")),
        "description": _truncate(action.get("description"), max_len=180),
    }


def _truncate(value: Any, *, max_len: int) -> str | None:
    """Truncate a description for the prompt; None passes through."""
    if value is None:
        return None
    s = str(value)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"

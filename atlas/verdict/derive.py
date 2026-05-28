"""Derive the trader-facing verdict from cell state + Weinstein stage + gates + ownership.

Source of truth: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §4.
Vocabulary lock: CONTEXT.md §"Cell state vocabulary" (BUY/ACCUMULATE/WATCH/HOLD/AVOID/SELL/WAIT).

Spec locks enforced here:
- Q1 (2026-05-28): Stage 3 → WATCH/HOLD with reason "Stage 3 topping". NEVER WAIT for Stage 3.
- Q5 (2026-05-28): Micro cap_tier exempts from Weinstein veto entirely.
- Gate fail returns WAIT with the *named* gate (e.g. "Risk gate fail") not just "WAIT".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CellState = Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
Verdict = Literal["BUY", "ACCUMULATE", "WATCH", "HOLD", "AVOID", "SELL", "WAIT"]


@dataclass(frozen=True)
class VerdictInput:
    cell_state: CellState
    weinstein_stage: int | None  # 1, 2, 3, 4 or None
    user_owns: bool
    gates: dict  # keys: strength, direction, risk, sector, market → bool
    cap_tier: str = "Large"  # Large / Mid / Small / Micro


@dataclass(frozen=True)
class VerdictOutput:
    verdict: Verdict
    reason: str | None


# Gate display names — controls text in WAIT reason strings
_GATE_DISPLAY_NAMES: dict[str, str] = {
    "strength": "Strength",
    "direction": "Direction",
    "risk": "Risk",
    "sector": "Sector",
    "market": "Market",
}


def derive_verdict(inp: VerdictInput) -> VerdictOutput:
    """Apply the precedence ladder from spec §4 to produce a single trader-facing verdict.

    Precedence (highest to lowest):
    1. NEGATIVE cell_state  → SELL (owns) / AVOID (doesn't own). No gates apply.
    2. NEUTRAL cell_state   → HOLD (owns) / WATCH (doesn't own). No gates apply.
    3. POSITIVE cell_state  → check vetoes before promoting to BUY/ACCUMULATE:
       3a. Weinstein Stage 4 veto (Micro exempt — Q5 lock)
       3b. Any gate fail → WAIT with named gate
       3c. Weinstein Stage 3 → HOLD/WATCH with "Stage 3 topping" (Q1 lock — never WAIT)
       3d. Clear path → BUY (not owned) / ACCUMULATE (owned)
    """
    # 1. NEGATIVE cells — ownership decides verb; no gate/Weinstein logic applies
    if inp.cell_state == "NEGATIVE":
        return VerdictOutput("SELL" if inp.user_owns else "AVOID", None)

    # 2. NEUTRAL cells — holding pattern; no gate/Weinstein logic applies
    if inp.cell_state == "NEUTRAL":
        return VerdictOutput("HOLD" if inp.user_owns else "WATCH", None)

    # 3. POSITIVE — check vetoes before promoting to BUY/ACCUMULATE
    assert inp.cell_state == "POSITIVE"

    # 3a. Weinstein Stage 4 veto (Micro exempt per Q5 lock)
    if inp.cap_tier != "Micro" and inp.weinstein_stage == 4:
        return VerdictOutput("WAIT", "Stage 4 vetoes positive cell")

    # 3b. Gate veto — any fail blocks; named gate returned in reason
    for gate_key, passed in inp.gates.items():
        if passed is False:
            display = _GATE_DISPLAY_NAMES.get(gate_key, gate_key.replace("_", " ").title())
            return VerdictOutput("WAIT", f"{display} gate fail")

    # 3c. Stage 3 ambiguity — downgrade to WATCH/HOLD (Q1 lock: never WAIT for Stage 3)
    if inp.cap_tier != "Micro" and inp.weinstein_stage == 3:
        return VerdictOutput(
            "HOLD" if inp.user_owns else "WATCH",
            "Stage 3 topping",
        )

    # 3d. Clear path — all vetoes cleared
    return VerdictOutput("ACCUMULATE" if inp.user_owns else "BUY", None)

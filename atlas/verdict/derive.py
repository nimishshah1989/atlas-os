"""Derive the trader-facing verdict from cell state + Weinstein stage + gates + ownership.

Source of truth: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §4.
Vocabulary lock: CONTEXT.md §"Cell state vocabulary" (BUY/ACCUMULATE/WATCH/HOLD/AVOID/SELL/WAIT).

Spec locks enforced here:
- Q1 (2026-05-28): Stage 3 → WATCH/HOLD with reason "Stage 3 topping". NEVER WAIT for Stage 3.
- Q5 (2026-05-28): Micro cap_tier exempts from Weinstein veto entirely.
- Gate fail returns WAIT with the *named* gate (e.g. "Risk gate fail") not just "WAIT".

A3 amendment (2026-05-28): Stream A3 sector-confluence research found NO
Weinstein (cap_tier × lookback × confluence-subset) combination clears the
0.05 IC floor with ≥50 events/yr and positive min OOS IC. Stage 4 → WAIT
veto removed; Weinstein stage is now a why-strip context chip only.
Stage 3 → WATCH/HOLD downgrade retained per Q1 lock pending separate
review.
See docs/v6/2026-05-28-weinstein-a3-report.md for the empirical basis.
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
       3a. Any gate fail → WAIT with named gate
       3b. Weinstein Stage 3 → HOLD/WATCH with "Stage 3 topping" (Q1 lock — never WAIT)
       3c. Clear path → BUY (not owned) / ACCUMULATE (owned)

    Stage 4 no longer vetoes (A3 amendment 2026-05-28) — Weinstein is a
    context chip on the why-strip, not a precedence-ladder gate.
    """
    # 1. NEGATIVE cells — ownership decides verb; no gate/Weinstein logic applies
    if inp.cell_state == "NEGATIVE":
        return VerdictOutput("SELL" if inp.user_owns else "AVOID", None)

    # 2. NEUTRAL cells — holding pattern; no gate/Weinstein logic applies
    if inp.cell_state == "NEUTRAL":
        return VerdictOutput("HOLD" if inp.user_owns else "WATCH", None)

    # 3. POSITIVE — check vetoes before promoting to BUY/ACCUMULATE
    assert inp.cell_state == "POSITIVE"

    # 3a. Gate veto — any fail blocks; named gate returned in reason
    for gate_key, passed in inp.gates.items():
        if passed is False:
            display = _GATE_DISPLAY_NAMES.get(gate_key, gate_key.replace("_", " ").title())
            return VerdictOutput("WAIT", f"{display} gate fail")

    # 3b. Stage 3 ambiguity — downgrade to WATCH/HOLD (Q1 lock: never WAIT for Stage 3)
    if inp.cap_tier != "Micro" and inp.weinstein_stage == 3:
        return VerdictOutput(
            "HOLD" if inp.user_owns else "WATCH",
            "Stage 3 topping",
        )

    # 3c. Clear path — gates pass, Stage 1/2/4/None all promote to BUY/ACCUMULATE.
    # Stage 4 with positive cell is rendered as BUY with a Stage 4 warn-chip
    # on the why-strip (UI responsibility, not derivation responsibility).
    return VerdictOutput("ACCUMULATE" if inp.user_owns else "BUY", None)

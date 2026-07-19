"""Atlas Desk — the agentic layer over Atlas's ranks (spec 2026-07-04, Phase B1).

Pure: prompt builders, output validators, charters. All I/O (DB assembly, LLM
calls, trade booking, journaling) lives in scripts/foundation/desk_run.py. The
agents DECIDE; the portfolio engine EXECUTES — an agent can never invent a
price, breach a cap, or bypass the audited book_trade path (rule #0).
"""

from .prompts import (
    CHARTERS,
    build_debate_messages,
    build_pm_messages,
    build_reflect_messages,
    build_risk_messages,
    build_scout_messages,
    build_trader_messages,
    check_plan,
    validate_debate,
    validate_pm,
    validate_reflect,
    validate_risk,
    validate_scout,
    validate_trader,
)

__all__ = [
    "CHARTERS",
    "build_debate_messages",
    "build_pm_messages",
    "build_reflect_messages",
    "build_risk_messages",
    "build_scout_messages",
    "build_trader_messages",
    "check_plan",
    "validate_debate",
    "validate_pm",
    "validate_reflect",
    "validate_risk",
    "validate_scout",
    "validate_trader",
]

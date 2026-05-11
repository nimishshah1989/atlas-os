"""SP05: daily Atlas brief - Claude-authored market narrative.

See docs/phase2/plans/2026-05-12-sp05-daily-brief.md.
"""

from atlas.intelligence.briefs.audit import persist_brief
from atlas.intelligence.briefs.context import (
    DailyMarketContext,
    build_daily_context,
)
from atlas.intelligence.briefs.generator import DailyBrief, generate_brief
from atlas.intelligence.briefs.prompts import PROMPT_VERSION

__all__ = [
    "PROMPT_VERSION",
    "DailyBrief",
    "DailyMarketContext",
    "build_daily_context",
    "generate_brief",
    "persist_brief",
]

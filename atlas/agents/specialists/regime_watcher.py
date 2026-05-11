"""SP07: Regime Watcher specialist.

Reads the current market regime and recent regime history; reports the
regime state, the delta vs yesterday, and the breadth context.
"""

from __future__ import annotations

from atlas.agents.specialists._sebi import SEBI_PREAMBLE
from atlas.agents.specialists.base import SpecialistAgent


class RegimeWatcher(SpecialistAgent):
    """Reports the current Atlas market regime and recent transitions."""

    name = "regime_watcher"
    description = (
        "Reads mv_current_market_regime and atlas_market_regime_daily; "
        "reports the current regime state, the delta vs yesterday, the "
        "deployment multiplier, and the breadth signals."
    )
    tool_names = (
        "get_current_regime",
        "get_regime_history",
        "get_latest_brief",
    )

    def build_system_prompt(self) -> str:
        return (
            SEBI_PREAMBLE
            + "\n"
            + """\
I am the Regime Watcher. I read the Atlas market regime classification
(Risk-On, Neutral, Defensive, Risk-Off), the deployment multiplier (a
position-sizing calibration factor), and the breadth signals that produced
the classification. I describe the current state and the delta from
recent days.

Available tools:
- get_current_regime: today's regime + breadth signals + deployment multiplier
- get_regime_history(n_days): recent regime history (default 5 days)
- get_latest_brief: the most recent Atlas daily brief (optional context)

Workflow:
1. Always call get_current_regime first.
2. Call get_regime_history(n_days=5) to detect transitions.
3. If the question asks about narrative context, call get_latest_brief.
4. Open with the regime classification AND the deployment multiplier.
5. If the regime is unchanged for N days, say so explicitly. If it
   transitioned, state from-to with the date and mention the
   deployment-multiplier change.
6. Name the breadth signals that support the classification: "78% of
   names trade above their 50-day EMA", "the advance-decline ratio
   registers 1.8". Use exactly the numbers the tool returned.
7. Close with the data-as-of line.

The deployment multiplier "calibrates position sizing"; it does not "tell
you to do" anything. Never use directional language.
"""
        )

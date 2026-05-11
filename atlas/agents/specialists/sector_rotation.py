"""SP07: Sector Rotation Analyst specialist.

Reads the SP02 sector rotation MV + current regime, and explains the
quadrant distribution in SEBI-safe prose.
"""

from __future__ import annotations

from atlas.agents.specialists._sebi import SEBI_PREAMBLE
from atlas.agents.specialists.base import SpecialistAgent


class SectorRotationAnalyst(SpecialistAgent):
    """Analyzes sector RRG quadrants and RS metrics."""

    name = "sector_rotation"
    description = (
        "Reads mv_sector_rotation_state and the current market regime; "
        "explains which sectors are Leading, Improving, Weakening, Lagging, "
        "and which sectors are rotating between quadrants."
    )
    tool_names = (
        "get_current_regime",
        "get_sector_rotation_quadrants",
        "get_top_rs_stocks",
    )

    def build_system_prompt(self) -> str:
        return (
            SEBI_PREAMBLE
            + "\n"
            + """\
I am the Sector Rotation Analyst. I read the RRG (Relative Rotation Graph)
quadrant assignments and RS metrics for all NIFTY sectors and explain which
sectors are Leading, Improving, Weakening, or Lagging. I name sectors
specifically — never vaguely. I ground every claim in current data by
calling tools.

Available tools:
- get_sector_rotation_quadrants: full quadrant assignment for all sectors
- get_current_regime: macro overlay (regime + deployment multiplier)
- get_top_rs_stocks: only when the question specifically asks about
  leading stocks inside a sector

Workflow:
1. Almost always start with get_sector_rotation_quadrants.
2. If the regime context matters to the answer, call get_current_regime.
3. Synthesize: which sectors are in which quadrant, named ones to watch,
   the macro overlay if relevant.
4. Close with the data-as-of line.

When a sector has rs_velocity > 0 and high rs_pctile_cross_sector, it
"ranks highly in the RS framework and registers improving momentum". When
rs_velocity < 0 from a high level, it "shows deterioration from a leading
position". Use these phrasings.
"""
        )

"""SP07: Drift Detector specialist.

Reads validator findings + distribution stats; reports anomalies and
universe-wide distribution shifts in SEBI-safe prose.
"""

from __future__ import annotations

from atlas.agents.specialists._sebi import SEBI_PREAMBLE
from atlas.agents.specialists.base import SpecialistAgent


class DriftDetector(SpecialistAgent):
    """Reports recent validator findings and distribution drift."""

    name = "drift_detector"
    description = (
        "Reads atlas_validator_findings + recent distribution stats; "
        "reports recent anomalies grouped by severity and flags universe-"
        "wide distribution shifts (e.g., 'pct_above_ema_50 collapsed today')."
    )
    tool_names = (
        "get_recent_findings",
        "get_finding_summary",
        "get_distribution_stats",
    )

    def build_system_prompt(self) -> str:
        return (
            SEBI_PREAMBLE
            + "\n"
            + """\
I am the Drift Detector. I read the data-integrity findings produced by
the Atlas Validator agent plus distribution stats over recent stock and
sector metrics. I describe anomalies in plain language and flag when a
metric's distribution has shifted unusually.

Available tools:
- get_finding_summary(n_days): aggregate counts by severity + finding_class
- get_recent_findings(severity?, n): list recent findings (optionally
  filtered by severity P0/P1/P2/P3)
- get_distribution_stats(table, metric_column): basic stats for a
  whitelisted (table, column) pair over the last 30 days

Workflow:
1. Start with get_finding_summary(n_days=7) to see the shape of the
   problem.
2. If the summary shows P0 findings, call get_recent_findings(severity=P0)
   to enumerate them.
3. If the question hints at a specific metric (e.g. "breadth has been
   off"), call get_distribution_stats on the relevant whitelisted pair.
4. Synthesize: open with "the validator surfaces N findings over the last
   7 days, of which K are P0". Name a couple of specific finding
   surfaces. Close with a one-line characterization of overall data
   health.
5. Close with the data-as-of line.

If get_finding_summary returns zero findings, say plainly: "no anomalies
detected in the last 7 days; data-integrity signals nominal." Do not
fabricate findings.
"""
        )
